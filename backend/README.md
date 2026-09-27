# PyCraft Backend

FastAPI service that serves the PyCraft API: challenge catalogue, progress, and the
Run/Submit endpoints that drive the isolated execution engine.

See [docs/architecture.md](../docs/architecture.md) for the full design and
[docs/api.md](../docs/api.md) for the endpoint reference.

## Quick start

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload
```

Interactive API docs: <http://127.0.0.1:8000/docs>

## Tests

```bash
.venv/bin/pytest                      # unit + API tests (no Docker required)
.venv/bin/pytest -m docker            # adds real-sandbox integration tests
```

## Configuration

Every setting is read from the environment with a `PYCRAFT_` prefix, or from a
`.env` file. See [`app/core/config.py`](app/core/config.py) for the full list.
