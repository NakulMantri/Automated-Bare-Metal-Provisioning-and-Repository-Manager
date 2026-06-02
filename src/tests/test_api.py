import os
import pytest
from fastapi.testclient import TestClient
from repo_manager.api import app, WORKSPACE


@pytest.fixture
def client():
    return TestClient(app)


def test_api_status(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "total_packages" in data
    assert "gpg_key_configured" in data
    assert "packages" in data
    assert "repo_url" in data


def test_api_provision_logs(client):
    # Retrieve logs
    response = client.get("/api/provision-logs")
    assert response.status_code == 200
    logs = response.json()
    assert isinstance(logs, list)

    # Trigger a new simulated provisioning
    response_trig = client.post(
        "/api/provision-logs/trigger", data={"node_name": "test-node.infra.local"}
    )
    assert response_trig.status_code == 200
    assert response_trig.json()["status"] == "triggered"

    # Verify new logs are appended
    response_updated = client.get("/api/provision-logs")
    logs_updated = response_updated.json()
    assert len(logs_updated) > len(logs)
    assert any(log["node"] == "test-node.infra.local" for log in logs_updated)


def test_api_compile_endpoint_validation(client):
    # Uploading a non-spec file should trigger 400 validation error
    files = {"spec_file": ("test.txt", b"invalid content", "text/plain")}
    response = client.post("/api/compile", files=files, data={"sim": "true"})
    assert response.status_code == 400
    assert "Only RPM SPEC files are allowed" in response.json()["detail"]


def test_api_compile_success(client):
    # Uploading a mock spec file
    spec_content = b"Name: api-test-pkg\nVersion: 1.0\nRelease: 1\n"
    files = {
        "spec_file": ("api-test-pkg.spec", spec_content, "application/octet-stream")
    }

    response = client.post("/api/compile", files=files, data={"sim": "true"})
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert "accepted in background" in data["message"]

    # Verify job is listed in active build queues
    response_builds = client.get("/api/builds")
    assert response_builds.status_code == 200
    jobs = response_builds.json()
    assert len(jobs) > 0
    assert any(job["id"] == data["job_id"] for job in jobs)
