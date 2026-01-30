# rosdep_viz webapp backend

FastAPI server that uses `rosdep_viz` to list packages and build dependency trees. Serves JSON for the frontend.

## Install

From this directory (with `rosdep_viz` installed or editable):

```bash
uv pip install -e .
# or install rosdep_viz from parent: uv pip install -e ../..
```

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API:

- `GET /api/packages` — list known package names and paths
- `GET /api/tree/{package_name}` — dependency tree for a package (optional `?max_depth=10`)
