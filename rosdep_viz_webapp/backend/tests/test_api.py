"""API tests for the rosdep_viz backend."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_packages() -> None:
    """GET /api/packages returns 200 and a packages dict."""
    response = client.get("/api/packages")
    assert response.status_code == 200
    data = response.json()
    assert "packages" in data
    assert isinstance(data["packages"], dict)


def test_get_tree_not_found() -> None:
    """GET /api/tree/<unknown> returns 404."""
    response = client.get("/api/tree/nonexistent_package_xyz_123")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
