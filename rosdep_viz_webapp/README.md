# rosdep_viz_webapp

Web UI for visualizing ROS 2 package dependency trees: FastAPI backend + React/Vite/Tailwind frontend.

## Prerequisites

- **Backend**: Python 3.10+, [uv](https://github.com/astral-sh/uv). Install `rosdep_viz` first (from repo root: `uv pip install -e .`).
- **Frontend**: Node 22 (`nvm use 22`).

## Backend

```bash
cd rosdep_viz_webapp/backend
uv pip install -e .
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API:

- `GET /api/packages` — list known ROS 2 packages (name → path to package.xml).
- `GET /api/tree/{package_name}?max_depth=N` — dependency tree for a package.

Ensure your ROS 2 environment is sourced (e.g. `source /opt/ros/<distro>/setup.bash` and workspace `install/setup.bash`) so the backend can discover packages.

## Frontend

```bash
cd rosdep_viz_webapp/frontend
nvm use 22
npm install
npm run dev
```

Open http://localhost:5173. Use “Load packages” to fetch packages from the backend, then select a package to view its dependency tree (interactive graph with zoom/pan).

## Running together

1. Start backend: `cd rosdep_viz_webapp/backend && uv run uvicorn app.main:app --reload --port 8000`
2. Start frontend: `cd rosdep_viz_webapp/frontend && npm run dev`
3. Vite proxies `/api` to the backend; no CORS issues in dev.
