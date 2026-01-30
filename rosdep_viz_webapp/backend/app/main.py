"""FastAPI app: list packages and serve dependency trees for the frontend."""

from __future__ import annotations


from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from rosdep_viz import build_tree, list_known_packages

app = FastAPI(
    title="rosdep_viz API",
    description="ROS 2 package dependency visualization backend",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/packages")
def get_packages() -> dict:
    """List all known ROS 2 packages (name -> path to package.xml)."""
    paths = list_known_packages()
    return {"packages": {name: str(p) for name, p in paths.items()}}


@app.get("/api/tree/{package_name}")
def get_tree(
    package_name: str,
    max_depth: int | None = Query(None, ge=1, le=50),
) -> dict:
    """Return dependency tree for a package. Optional max_depth query param."""
    root = build_tree(package_name, max_depth=max_depth)
    if root is None or (not root.path and "(not found)" in (root.description or "")):
        raise HTTPException(status_code=404, detail=f"Package not found: {package_name}")
    return root.to_dict()
