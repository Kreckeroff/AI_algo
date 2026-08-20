from fastapi.testclient import TestClient

from ai_algo.app import app
from ai_algo.models.loader import clear_model_cache

client = TestClient(app)

FEATURES = {
    "ret_1": 0.001,
    "ret_5": 0.002,
    "rsi_14": 55.0,
    "atr_14": 0.5,
    "ema_dist_50": 0.01,
    "volume_z": 0.2,
}


def setup_function():
    clear_model_cache()


def _infer(payload):
    return client.post(
        "/v1/infer",
        json={
            "api_version": "2026-08-20",
            "request_id": "s1",
            "client": {
                "product": "it-algo-desktop",
                "app_version": "0.0.0",
                "env": "dev",
            },
            "intent": "signal",
            "payload": payload,
        },
    )


def test_signal_missing_feature():
    bad = dict(FEATURES)
    del bad["rsi_14"]
    r = _infer({"feature_vector": bad})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "validation_failed"


def test_signal_ok():
    r = _infer({"feature_vector": FEATURES, "model_id": "signal-cpu-v1"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "p" in body["result"]
    assert body["result"]["label"] in (0, 1)
    assert body["result"]["feature_schema_id"] == "v1-basic"
    assert "disclaimer" in body["result"]


def test_capabilities_includes_signal():
    r = client.get("/v1/capabilities")
    assert "signal" in r.json()["intents"]
