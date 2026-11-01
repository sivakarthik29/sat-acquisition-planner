import pytest
from fastapi.testclient import TestClient

from app.main import create_app

from .conftest import ConstantCloud

START, END_5D, END_14D = "2026-07-19T20:00:00Z", "2026-07-24T20:00:00Z", "2026-08-02T20:00:00Z"


@pytest.fixture(scope="module")
def client(real_sats, tmp_path_factory):
    app = create_app(satellites=real_sats, cloud_client=ConstantCloud(5), data_dir=tmp_path_factory.mktemp("data"))
    with TestClient(app) as c:
        yield c


def test_health_reports_orbit_source(client):
    """REQ-API-01: health is up and says where the orbit data came from."""
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["satellites"] == 3 and body["orbit_source"] == "provided"


def test_limits_expose_provenance(client):
    """REQ-API-01: every limit is tagged published, derived or assumed, so the UI can show what is and is not Pixxel's."""
    body = client.get("/api/limits").json()
    assert {l["source"] for l in body["limits"]} == {"published", "derived", "assumed"}
    assert body["dictionary"]["notional"] is True


def test_satellites_endpoint_compares_with_published_orbit(client):
    """REQ-API-01: orbit facts and the published reference values come back together."""
    body = client.get("/api/satellites").json()
    assert body["published"]["altitude_km"] == 589.0 and len(body["satellites"]) == 3
    assert all(s["altitude_km"] > 500 for s in body["satellites"])


def test_feasibility_happy_path(client):
    """REQ-API-02: a feasible request returns checks, passes and a probability."""
    r = client.post("/api/feasibility", json={"lat": 12.97, "lon": 77.59, "area_km2": 500, "start": START, "end": END_14D})
    body = r.json()
    assert r.status_code == 200 and body["feasible"] and body["opportunities"] and body["probability"] == 1.0
    assert all({"id", "label", "passed", "detail", "source"} <= set(c) for c in body["checks"])


def test_feasibility_rejects_bad_input(client):
    """REQ-API-02: bad coordinates, areas and windows are rejected with 422 and a readable message."""
    good = {"lat": 12.97, "lon": 77.59, "area_km2": 500, "start": START, "end": END_5D}
    assert client.post("/api/feasibility", json={**good, "lat": 123}).status_code == 422
    assert client.post("/api/feasibility", json={**good, "area_km2": -5}).status_code == 422
    r = client.post("/api/feasibility", json={**good, "end": START})
    assert r.status_code == 422 and "after the start" in r.json()["detail"]


def test_plan_returns_both_solvers_and_a_valid_command_list(client):
    """REQ-API-03: the plan endpoint compares greedy and optimized, and the commands pass validation."""
    reqs = [{"id": "blr", "name": "Bengaluru", "lat": 12.97, "lon": 77.59, "area_km2": 300, "priority": 3},
            {"id": "del", "name": "Delhi", "lat": 28.61, "lon": 77.21, "area_km2": 600, "priority": 5},
            {"id": "huge", "name": "Too big", "lat": 19.07, "lon": 72.88, "area_km2": 9000, "priority": 4}]
    body = client.post("/api/plan", json={"requests": reqs, "start": START, "end": END_14D}).json()
    assert body["solutions"]["optimized"]["total_value"] >= body["solutions"]["greedy"]["total_value"]
    assert body["validation"]["passed"] and body["commands"] and body["captures"]
    assert any(u["request_id"] == "huge" and "limit" in u["reason"] for u in body["unscheduled"])
    assert body["dictionary"]["notional"] is True


def test_plan_rejects_duplicate_ids_and_long_windows(client):
    """REQ-API-03: duplicate request ids and over-long windows are refused."""
    one = {"id": "a", "name": "A", "lat": 12.97, "lon": 77.59, "area_km2": 300, "priority": 3}
    assert client.post("/api/plan", json={"requests": [one, one], "start": START, "end": END_5D}).status_code == 422
    assert client.post("/api/plan", json={"requests": [one], "start": START, "end": "2026-09-30T00:00:00Z"}).status_code == 422
