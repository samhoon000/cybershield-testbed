"""Tests for CyberShield Security Incident Simulation API."""
from fastapi.testclient import TestClient

API_KEY = "sentinel-cybershield-demo-secret-key-2026"


def test_simulation_ping(client: TestClient):
    res = client.get("/api/simulation/ping")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert data["target"] == "CyberShield"
    assert data["simulation_enabled"] is True


def test_simulation_activate_unauthorized(client: TestClient):
    res = client.post("/api/simulation/activate", json={"notes": "Unauthorized test"})
    assert res.status_code == 401
    assert "Invalid or missing CyberShield API key" in res.json()["detail"]

    res_bad = client.post(
        "/api/simulation/activate",
        headers={"X-CyberShield-Key": "wrong-key"},
        json={"notes": "Wrong key"},
    )
    assert res_bad.status_code == 401


def test_simulation_activate_and_lifecycle(client: TestClient):
    # 1. Activate
    activate_res = client.post(
        "/api/simulation/activate",
        headers={"X-CyberShield-Key": API_KEY},
        json={"notes": "College Presentation Test", "ttl_minutes": 15},
    )
    assert activate_res.status_code == 200
    sim_data = activate_res.json()
    assert sim_data["status"] == "active"
    assert sim_data["incident_id"].startswith("INC-")
    session_id = sim_data["session_id"]
    assert session_id.startswith("sim_")
    assert "sim_session=" in sim_data["launch_url"]

    # 2. Query session
    query_res = client.get(f"/api/simulation/session/{session_id}")
    assert query_res.status_code == 200
    state = query_res.json()
    assert state["status"] == "active"
    assert state["is_active"] is True
    assert state["incident_id"] == sim_data["incident_id"]

    # 3. Query active
    active_res = client.get("/api/simulation/active")
    assert active_res.status_code == 200
    active_data = active_res.json()
    assert active_data["active"] is True
    assert active_data["session"]["session_id"] == session_id

    # 4. Unlock via Key '0' presentation action
    unlock_res = client.post("/api/simulation/unlock", json={"session_id": session_id})
    assert unlock_res.status_code == 200
    unlock_data = unlock_res.json()
    assert unlock_data["status"] == "unlocked"
    assert "unlocked successfully" in unlock_data["message"]

    # 5. Query session again: verify unlocked
    post_unlock = client.get(f"/api/simulation/session/{session_id}").json()
    assert post_unlock["status"] == "unlocked"
    assert post_unlock["is_active"] is False
    assert post_unlock["unlocked_at"] is not None


def test_simulation_terminate_by_admin(client: TestClient):
    # Activate
    sim = client.post(
        "/api/simulation/activate",
        headers={"X-CyberShield-Key": API_KEY},
        json={"notes": "Termination Test"},
    ).json()
    session_id = sim["session_id"]

    # Terminate
    term_res = client.post(
        "/api/simulation/terminate",
        headers={"X-CyberShield-Key": API_KEY},
        json={"session_id": session_id},
    )
    assert term_res.status_code == 200
    assert term_res.json()["status"] == "terminated"

    # Verify session is terminated
    state = client.get(f"/api/simulation/session/{session_id}").json()
    assert state["status"] == "terminated"
    assert state["is_active"] is False
