from fastapi.testclient import TestClient

from ai_algo.app import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_capabilities_includes_compare_scripts():
    r = client.get("/v1/capabilities")
    assert r.status_code == 200
    body = r.json()
    assert body["api_version"] == "2026-08-20"
    assert "compare_scripts" in body["intents"]


def test_infer_unsupported_intent():
    r = client.post(
        "/v1/infer",
        json={
            "api_version": "2026-08-20",
            "request_id": "req-1",
            "client": {
                "product": "it-algo-desktop",
                "app_version": "0.0.0",
                "env": "dev",
            },
            "intent": "advise",
            "payload": {},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "unsupported_intent"
