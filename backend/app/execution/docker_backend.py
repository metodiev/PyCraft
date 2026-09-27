"""Docker execution backend.

Runs each submission in a throwaway container built from ``runner/Dockerfile``
with a deliberately aggressive containment profile:

======================  =====================================================
``--network=none``      no DNS, no egress, no SSRF pivot
``--read-only``         immutable root filesystem
``--cap-drop=ALL``      no Linux capabilities (no ptrace, no raw sockets)
``--no-new-privileges`` setuid binaries cannot escalate
``--pids-limit``        fork-bomb containment
``--memory``/``--cpus`` resource ceilings
``--user 1000:1000``    never root
tmpfs ``/tmp``          isolated scratch space, ``nosuid``, size-capped
======================  =====================================================

The API process never imports or executes user code; it only talks to the
Docker daemon.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import tarfile
import uuid
from typing import Any

import docker
from docker.errors import APIError, DockerException, ImageNotFound, NotFound
from requests.exceptions import ReadTimeout

from app.core.config import Settings
from app.execution.base import ExecutionBackend
from app.execution.models import (
    ExecutionError,
    ExecutionPayload,
    ExecutionReport,
    ExecutionStatus,
)
from app.execution.parser import ReportParseError, parse_report

logger = logging.getLogger(__name__)

PAYLOAD_MOUNT = "/opt/payload"
PAYLOAD_FILE = "payload.json"
RUNNER_UID = "1000:1000"
# Headroom added to the container-level wait so the runner's own (tighter)
# in-container timeout is always the first to fire and produce a real report.
WAIT_GRACE_SECONDS = 30


class DockerExecutionBackend(ExecutionBackend):
    """Executes payloads in hardened, ephemeral Docker containers."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: docker.DockerClient | None = None
        # Bounds concurrent sandboxes so a submission storm cannot exhaust the host.
        self._semaphore = asyncio.Semaphore(settings.execution_concurrency)

    # --- lifecycle -------------------------------------------------------
    async def start(self) -> None:
        client = await asyncio.to_thread(self._build_client)
        self._client = client
        try:
            await asyncio.to_thread(client.images.get, self._settings.runner_image)
        except ImageNotFound as exc:
            raise ExecutionError(
                f"Runner image {self._settings.runner_image!r} not found. Build it with: "
                f"docker build -t {self._settings.runner_image} -f runner/Dockerfile runner/"
            ) from exc
        except DockerException as exc:
            raise ExecutionError(f"Unable to reach the Docker daemon: {exc}") from exc
        logger.info("Execution backend ready (image=%s)", self._settings.runner_image)

    async def stop(self) -> None:
        client = self._client
        if client is None:
            return
        self._client = None
        await asyncio.to_thread(client.close)

    @property
    def name(self) -> str:
        return "docker"

    # --- execution -------------------------------------------------------
    async def execute(self, payload: ExecutionPayload) -> ExecutionReport:
        if self._client is None:
            raise ExecutionError("Execution backend is not started")
        if not payload.files:
            raise ExecutionError("Submission contains no files")

        limits = payload.limits.clamped(
            max_time_ms=self._settings.max_time_limit_ms,
            max_memory_mb=self._settings.max_memory_limit_mb,
        )

        async with self._semaphore:
            return await asyncio.to_thread(self._execute_sync, payload, limits)

    def _execute_sync(self, payload: ExecutionPayload, limits: Any) -> ExecutionReport:
        client = self._client
        assert client is not None  # guarded by execute()

        volume_name = f"pycraft-payload-{uuid.uuid4().hex[:16]}"
        container = None
        volume = None
        try:
            volume = client.volumes.create(name=volume_name, labels={"pycraft": "payload-staging"})
            self._stage_payload(client, volume.name, payload)
            container = self._create_runner_container(client, volume.name, limits)

            try:
                container.start()
            except APIError as exc:
                raise ExecutionError(f"Could not start the sandbox container: {exc}") from exc

            timed_out = False
            try:
                result = container.wait(timeout=limits.time_limit_ms / 1000 + WAIT_GRACE_SECONDS)
                exit_code = result.get("StatusCode")
            except ReadTimeout:
                # Safety net only: the runner enforces the same limit internally.
                timed_out = True
                exit_code = None
                with contextlib.suppress(APIError, NotFound):
                    container.kill()
                container.wait(timeout=10)

            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

            if timed_out:
                return ExecutionReport(
                    status=ExecutionStatus.TIMEOUT,
                    error_message="Execution exceeded the time limit",
                    stdout=self._truncate(stdout),
                    stderr=self._truncate(stderr),
                    exit_code=exit_code,
                )

            try:
                report = parse_report(stdout, stderr)
            except ReportParseError as exc:
                return ExecutionReport(
                    status=ExecutionStatus.FAILED,
                    error_message=f"Sandbox produced no result: {exc}",
                    stdout=self._truncate(stdout),
                    stderr=self._truncate(stderr),
                    exit_code=exit_code,
                )

            report.stdout = self._truncate(report.stdout)
            report.stderr = self._truncate(report.stderr)
            if exit_code not in (None, 0) and report.status is ExecutionStatus.COMPLETED:
                report.status = ExecutionStatus.FAILED
            return report

        except APIError as exc:
            raise ExecutionError(f"Docker rejected the execution request: {exc}") from exc
        except DockerException as exc:  # pragma: no cover - daemon-level failure
            raise ExecutionError(f"Docker execution failed: {exc}") from exc
        finally:
            self._remove(container, volume)

    # --- helpers ---------------------------------------------------------
    def _build_client(self) -> docker.DockerClient:
        if self._settings.docker_host:
            return docker.DockerClient(base_url=self._settings.docker_host)
        return docker.from_env()

    def _create_runner_container(
        self, client: docker.DockerClient, volume_name: str, limits: Any
    ) -> Any:
        return client.containers.create(
            self._settings.runner_image,
            network_disabled=True,
            read_only=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            pids_limit=limits.process_limit,
            mem_limit=f"{limits.memory_limit_mb}m",
            memswap_limit=f"{limits.memory_limit_mb}m",
            nano_cpus=int(limits.cpu_count * 1_000_000_000),
            user=RUNNER_UID,
            working_dir="/tmp",
            volumes={volume_name: {"bind": PAYLOAD_MOUNT, "mode": "ro"}},
            tmpfs={"/tmp": f"rw,nosuid,nodev,size={limits.tmpfs_size_mb}m"},
            labels={"pycraft": "execution"},
            detach=True,
        )

    def _stage_payload(
        self, client: docker.DockerClient, volume_name: str, payload: ExecutionPayload
    ) -> None:
        """Write the payload JSON into a dedicated volume.

        A volume is used instead of a host bind mount because the API may not
        share a filesystem with the Docker daemon (Docker Desktop, Colima, a
        remote ``DOCKER_HOST``, or Kubernetes). ``put_archive`` requires a
        writable root filesystem, so staging happens in a short-lived helper
        container that is destroyed immediately afterwards.
        """
        document = json.dumps(payload.to_wire()).encode("utf-8")
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as tar:
            info = tarfile.TarInfo(PAYLOAD_FILE)
            info.size = len(document)
            info.mode = 0o644
            info.uid = 1000
            info.gid = 1000
            tar.addfile(info, io.BytesIO(document))
        archive.seek(0)

        helper = client.containers.create(
            self._settings.runner_image,
            entrypoint=["/bin/true"],
            user="0:0",
            volumes={volume_name: {"bind": PAYLOAD_MOUNT, "mode": "rw"}},
            network_disabled=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            detach=True,
        )
        try:
            if not helper.put_archive(PAYLOAD_MOUNT, archive):
                raise ExecutionError("Failed to stage the payload archive")
        finally:
            self._remove(helper, None)

    def _remove(self, container: Any, volume: Any) -> None:
        if container is not None:
            try:
                container.remove(force=True, v=False)
            except (NotFound, DockerException, APIError):
                logger.debug("Container already removed")
        if volume is not None:
            try:
                volume.remove(force=True)
            except (NotFound, DockerException, APIError):
                logger.debug("Volume already removed")

    def _truncate(self, text: str) -> str:
        limit = self._settings.max_output_bytes
        if len(text) <= limit:
            return text
        return f"{text[:limit]}\n... [output truncated at {limit} bytes]\n"
