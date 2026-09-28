# Containers, Images and Layer Caching

A container image is not a snapshot of a running process. It is an ordered stack of immutable layers, each the filesystem delta produced by one build instruction, plus a small amount of metadata. A container is that stack with one writable layer on top. Almost everything about build speed and image size follows from those two sentences.

## Layers, digests and the cache key

Each `RUN`, `COPY` and `ADD` produces the filesystem delta for a layer, and a layer is addressed by a digest derived from its parent's digest and the instruction that produced it. During a build the engine walks the instructions in order and asks, for each one, whether a layer with that parent and that instruction already exists locally. The first instruction that misses is where the cache breaks, and *every instruction after it in the file* is rebuilt, even when those later instructions would have produced byte-identical layers.

The cache is a chain, not a set: an edit early in the file invalidates that layer and everything stacked on top of it. Reordering instructions is therefore free, and it is the cheapest fix available — move the volatile work as late as it can go.

The two invalidating instructions behave differently:

- `RUN` keys on the literal command string. Rewriting `pip install -r requirements.txt` as `pip install -r  requirements.txt` is a miss although the effect is identical. Conversely, a command that reads volatile remote state can *hit* and return a stale layer, which is why unpinned installs are a correctness bug as much as a caching one.
- `COPY` and `ADD` key on a checksum of the copied content, not on timestamps. `COPY . .` therefore invalidates on a whitespace change in `README.md`, because the context is checksummed wholesale. A `.dockerignore` excluding `.git`, `__pycache__` and test fixtures is a caching control, not just hygiene.

An `ARG` whose value changes invalidates every later instruction that consumes it, which is a common accidental miss when a build argument carries a timestamp or a pipeline run id.

## Ordering dependencies before source

The practical consequence of chaining is that the least volatile inputs go first:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "app"]
```

Application source changes far more often than dependency manifests, so the dependency layer survives those edits. Reverse the last two lines and every source edit reinstalls every dependency — often the difference between a four-second and a four-minute pipeline. Locking the manifest matters here too: a file of bare package names resolves to different versions on different days, and the cached layer will keep serving the old resolution until the manifest itself changes.

## Layer size is what costs; layer count mostly is not

A union filesystem overlays layers at read time, so deleting a file in a later layer writes a whiteout entry: the bytes stay in the earlier layer and every user of the image still pulls them. Cleanup in a separate instruction therefore cleans nothing:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
 && pip install --no-cache-dir -r requirements.txt \
 && apt-get purge -y build-essential && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
```

One instruction, so the install and the removal cancel out inside the same layer. Split across `RUN`s, the compiler and the package lists stay in the image forever.

Layer *count* is largely a red herring: pull time is dominated by bytes transferred and the per-layer metadata overhead is small. Nine thin layers can beat two fat ones. Squashing an image into a single layer is useful for an ossified release artefact and a trap for a base image, because squashing resets the cache chain and forces a full rebuild afterwards.

## Multi-stage builds

Most of a naive Python image's bulk is toolchain that is only needed while building. A multi-stage build keeps the build environment and the runtime environment as separate images and copies only artefacts across the boundary:

```dockerfile
FROM python:3.12 AS build
WORKDIR /src
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim AS runtime
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl \
 && rm -rf /wheels
COPY . /app
WORKDIR /app
```

Only the wheel directory crosses over, so compilers, headers and pip's cache never enter the runtime image, and the runtime image's cache chain does not depend on the build stage's internals. The same boundary is a secret-management tool: `COPY`ing a credentials file bakes it into a layer permanently. A later `RUN rm` hides the path but leaves the blob recoverable in the image history, so use build secrets or the build stage instead.

## `latest` is a default, not a version

A tag is a mutable pointer to a digest. `latest` is merely the tag applied when you push without one; it carries no ordering and no guarantee. Two builds a week apart can differ because the upstream `python:3.12-slim` moved, and the local cache will not warn you: without an explicit pull the daemon builds against whatever base it already has. Pin at least major.minor, and record the resolved digest in release metadata if you need bit-identical rebuilds.

The same reasoning applies to your own images. Deploying `myapp:latest` means a rollback is a rebuild — a different artefact from the one that was tested — and it defeats digest-addressed deploy tooling. Tag with the commit SHA.

## Practice

Take a Dockerfile, edit one line of application code, and account for exactly which layers rebuild. [Docker Layer Cache Analysis](../challenges/cloud-devops-docker-layer-cache) asks for that accounting: locate the first cache miss, measure how much is rebuilt because of it, and reorder the instructions so dependencies sit below the frequently edited source.
