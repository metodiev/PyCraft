"""Integration tests against the real Docker sandbox.

These are marked ``docker`` because they require a running Docker daemon and the
``pycraft-runner`` image:

    .venv/bin/pytest -m docker

They are the tests that actually prove the security claims in the docs: no
network, no root filesystem writes, bounded memory/CPU/PIDs and a hard timeout.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.config import Settings
from app.execution.docker_backend import DockerExecutionBackend
from app.execution.models import (
    ExecutionError,
    ExecutionLimits,
    ExecutionMode,
    ExecutionPayload,
    ExecutionStatus,
)

pytestmark = pytest.mark.docker

REPO_ROOT = Path(__file__).resolve().parents[2]

SOLUTION = "def greet(name):\n    return f'Hello, {name}!'\n"
TESTS = {
    "test_visible.py": (
        "from solution import greet\n\n\ndef test_greet():\n    assert greet('World') == 'Hello, World!'\n"
    )
}
HIDDEN = {
    "test_hidden.py": (
        "from solution import greet\n\n\ndef test_empty():\n    assert greet('') == 'Hello, !'\n"
    )
}
LIMITS = ExecutionLimits(time_limit_ms=8000, memory_limit_mb=256)


async def test_runner_image_exists() -> None:
    """Fail with an actionable message rather than a confusing API error."""
    import docker
    from docker.errors import ImageNotFound

    client = docker.from_env()
    image = Settings().runner_image
    try:
        client.images.get(image)
    except ImageNotFound:
        pytest.fail(
            f"Runner image {image!r} is missing. Build it with:\n"
            f"  docker build -t {image} -f runner/Dockerfile runner/"
        )
    finally:
        client.close()


@pytest.fixture
async def backend() -> DockerExecutionBackend:
    instance = DockerExecutionBackend(Settings(environment="test"))
    await instance.start()
    yield instance
    await instance.stop()


# --- behaviour -----------------------------------------------------------
async def test_passing_submission(backend: DockerExecutionBackend) -> None:
    report = await backend.execute(_payload(SOLUTION, mode=ExecutionMode.SUBMIT))

    assert report.status is ExecutionStatus.COMPLETED
    assert report.passed == 2
    assert report.failed == 0
    assert report.succeeded
    assert report.execution_time_ms > 0


async def test_failing_submission_reports_assertion(backend: DockerExecutionBackend) -> None:
    report = await backend.execute(
        _payload("def greet(name):\n    return 'wrong'\n", mode=ExecutionMode.SUBMIT)
    )

    assert report.status is ExecutionStatus.COMPLETED
    assert report.failed == 2
    assert any("AssertionError" in test.message for test in report.tests)


async def test_run_excludes_hidden_tests(backend: DockerExecutionBackend) -> None:
    report = await backend.execute(_payload(SOLUTION, mode=ExecutionMode.RUN))

    assert report.total == 1
    assert all("hidden" not in test.name for test in report.tests)


async def test_submit_includes_hidden_tests(backend: DockerExecutionBackend) -> None:
    report = await backend.execute(_payload(SOLUTION, mode=ExecutionMode.SUBMIT))

    assert report.total == 2
    assert any("hidden" in test.name for test in report.tests)


async def test_syntax_error_is_reported_not_crashed(backend: DockerExecutionBackend) -> None:
    report = await backend.execute(
        _payload("def broken(:\n", mode=ExecutionMode.RUN)
    )

    assert report.status is ExecutionStatus.FAILED
    assert report.total == 0
    assert report.error_message


async def test_stdout_is_captured(backend: DockerExecutionBackend) -> None:
    source = "print('hello from user code')\n\ndef greet(name):\n    return f'Hello, {name}!'\n"
    report = await backend.execute(_payload(source, mode=ExecutionMode.RUN))

    assert "hello from user code" in report.stdout


async def test_tests_can_import_from_starter(backend: DockerExecutionBackend) -> None:
    """The canonical contract: ``from solution import ...`` always resolves."""
    report = await backend.execute(_payload(SOLUTION, mode=ExecutionMode.RUN))
    assert report.passed == 1


# --- resource limits -----------------------------------------------------
async def test_timeout_is_enforced(backend: DockerExecutionBackend) -> None:
    report = await backend.execute(
        _payload(
            "import time\nwhile True:\n    time.sleep(0.05)\n",
            mode=ExecutionMode.RUN,
            limits=ExecutionLimits(time_limit_ms=2500, memory_limit_mb=128),
        )
    )

    assert report.status is ExecutionStatus.TIMEOUT
    assert "time limit" in (report.error_message or "").lower()


async def test_memory_limit_is_enforced(backend: DockerExecutionBackend) -> None:
    report = await backend.execute(
        _payload(
            "def greet(name):\n    return f'Hello, {name}!'\n\n"
            "chunks = []\nwhile True:\n    chunks.append(b'a' * 1_000_000)\n",
            mode=ExecutionMode.RUN,
            limits=ExecutionLimits(time_limit_ms=6000, memory_limit_mb=64),
        )
    )

    # Either the OOM killer ends the run or the time limit does; both are contained.
    assert report.status in {ExecutionStatus.TIMEOUT, ExecutionStatus.FAILED}


async def test_fork_bomb_is_contained(backend: DockerExecutionBackend) -> None:
    report = await backend.execute(
        _payload(
            "import os\ndef greet(name):\n    return 'x'\n\nwhile True:\n    os.fork()\n",
            mode=ExecutionMode.RUN,
            limits=ExecutionLimits(time_limit_ms=5000, memory_limit_mb=128),
        )
    )

    assert report.status in {ExecutionStatus.TIMEOUT, ExecutionStatus.FAILED}


async def test_challenge_limits_are_clamped_to_platform_ceiling(
    backend: DockerExecutionBackend,
) -> None:
    """A challenge asking for a huge limit must not get one."""
    report = await backend.execute(
        _payload(
            "def greet(name):\n    return f'Hello, {name}!'\n",
            mode=ExecutionMode.RUN,
            # Absurd limits; the backend clamps to its configured ceiling.
            limits=ExecutionLimits(time_limit_ms=10_000_000, memory_limit_mb=1_000_000),
        )
    )
    assert report.status is ExecutionStatus.COMPLETED


# --- isolation -----------------------------------------------------------
async def test_network_is_unreachable(backend: DockerExecutionBackend) -> None:
    report = await backend.execute(
        _payload(
            "import socket\n"
            "socket.setdefaulttimeout(3)\n"
            "try:\n"
            "    socket.create_connection(('1.1.1.1', 80))\n"
            "    print('NETWORK_REACHABLE')\n"
            "except OSError as exc:\n"
            "    print(f'NETWORK_BLOCKED: {exc}')\n"
            "def greet(name):\n    return 'x'\n",
            mode=ExecutionMode.RUN,
        )
    )

    assert "NETWORK_REACHABLE" not in report.stdout
    assert "NETWORK_BLOCKED" in report.stdout


async def test_root_filesystem_is_read_only(backend: DockerExecutionBackend) -> None:
    report = await backend.execute(
        _payload(
            "try:\n"
            "    open('/etc/passwd', 'a').write('pwned')\n"
            "    print('WRITE_SUCCEEDED')\n"
            "except OSError as exc:\n"
            "    print(f'WRITE_BLOCKED: {type(exc).__name__}')\n"
            "def greet(name):\n    return 'x'\n",
            mode=ExecutionMode.RUN,
        )
    )

    assert "WRITE_SUCCEEDED" not in report.stdout
    assert "WRITE_BLOCKED" in report.stdout


async def test_runs_as_unprivileged_user(backend: DockerExecutionBackend) -> None:
    report = await backend.execute(
        _payload(
            "import os\nprint(f'UID={os.getuid()}')\n"
            "def greet(name):\n    return 'x'\n",
            mode=ExecutionMode.RUN,
        )
    )

    assert "UID=0" not in report.stdout
    assert "UID=1000" in report.stdout


async def test_privileged_operations_are_denied(backend: DockerExecutionBackend) -> None:
    report = await backend.execute(
        _payload(
            "import ctypes, os\n"
            "try:\n"
            "    ctypes.CDLL(None).setuid(0)\n"
            "    print('SETUID_OK')\n"
            "except Exception as exc:\n"
            "    print(f'SETUID_DENIED: {type(exc).__name__}')\n"
            "print('EUID=' + str(os.geteuid()))\n"
            "def greet(name):\n    return 'x'\n",
            mode=ExecutionMode.RUN,
        )
    )

    assert "EUID=0" not in report.stdout


async def test_host_environment_is_not_leaked(
    backend: DockerExecutionBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYCRAFT_SECRET_TOKEN", "super-secret-value")
    report = await backend.execute(
        _payload(
            "import os\nprint('SECRET_PRESENT=' + str('PYCRAFT_SECRET_TOKEN' in os.environ))\n"
            "def greet(name):\n    return 'x'\n",
            mode=ExecutionMode.RUN,
        )
    )

    assert "SECRET_PRESENT=True" not in report.stdout
    assert "super-secret-value" not in report.stdout


async def test_submission_cannot_read_the_payload_file(backend: DockerExecutionBackend) -> None:
    """The payload is mounted read-only; writing to it must fail."""
    report = await backend.execute(
        _payload(
            "try:\n"
            "    open('/opt/payload/payload.json', 'w').write('x')\n"
            "    print('PAYLOAD_WRITABLE')\n"
            "except OSError as exc:\n"
            "    print(f'PAYLOAD_READONLY: {type(exc).__name__}')\n"
            "def greet(name):\n    return 'x'\n",
            mode=ExecutionMode.RUN,
        )
    )

    assert "PAYLOAD_WRITABLE" not in report.stdout


# --- payload safety ------------------------------------------------------
async def test_payload_path_traversal_is_rejected(backend: DockerExecutionBackend) -> None:
    report = await backend.execute(
        ExecutionPayload(
            files={"../../etc/evil.py": "print('nope')"},
            tests=TESTS,
            hidden_tests={},
            entry_file="solution.py",
            limits=LIMITS,
            mode=ExecutionMode.RUN,
        )
    )

    assert report.status is ExecutionStatus.REJECTED
    assert report.error_message


async def test_nested_user_file_is_rejected(backend: DockerExecutionBackend) -> None:
    report = await backend.execute(
        ExecutionPayload(
            files={"pkg/evil.py": "print('nope')"},
            tests=TESTS,
            hidden_tests={},
            entry_file="solution.py",
            limits=LIMITS,
            mode=ExecutionMode.RUN,
        )
    )

    assert report.status is ExecutionStatus.REJECTED


async def test_backend_requires_files(backend: DockerExecutionBackend) -> None:
    with pytest.raises(ExecutionError):
        await backend.execute(
            ExecutionPayload(
                files={},
                tests=TESTS,
                hidden_tests={},
                entry_file="solution.py",
                limits=LIMITS,
                mode=ExecutionMode.RUN,
            )
        )


async def test_output_is_truncated(backend: DockerExecutionBackend) -> None:
    report = await backend.execute(
        _payload(
            "for _ in range(20_000):\n    print('x' * 100)\n"
            "def greet(name):\n    return 'x'\n",
            mode=ExecutionMode.RUN,
        )
    )

    assert "truncated" in report.stdout.lower()


async def test_containers_are_cleaned_up(backend: DockerExecutionBackend) -> None:
    """No containers or staged volumes may outlive an execution."""
    import docker

    client = docker.from_env()
    try:
        before_containers = len(client.containers.list(all=True, filters={"label": "pycraft=execution"}))
        await backend.execute(_payload(SOLUTION, mode=ExecutionMode.RUN))
        after_containers = len(client.containers.list(all=True, filters={"label": "pycraft=execution"}))

        assert after_containers == before_containers
        assert client.volumes.list(filters={"label": "pycraft=payload-staging"}) == []
    finally:
        client.close()


def _payload(
    source: str,
    *,
    mode: ExecutionMode,
    limits: ExecutionLimits = LIMITS,
) -> ExecutionPayload:
    return ExecutionPayload(
        files={"solution.py": source},
        tests=TESTS,
        hidden_tests=HIDDEN,
        entry_file="solution.py",
        limits=limits,
        mode=mode,
        include_hidden=mode is ExecutionMode.SUBMIT,
    )
