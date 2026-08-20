from fastapi.testclient import TestClient

from ai_algo.app import app
from ai_algo.store.memory import store

client = TestClient(app)


def setup_function():
    store.bars.clear()
    store.graphs.clear()
    store.runs.clear()


def test_ingest_bars_accepted():
    r = client.post(
        "/v1/ingest/bars",
        json={
            "symbol": "SBER",
            "timeframe": "5m",
            "bars": [
                {
                    "ts": "2026-01-01T00:00:00Z",
                    "open": 1,
                    "high": 2,
                    "low": 0.5,
                    "close": 1.5,
                    "volume": 100,
                }
            ],
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"
    assert store.bars
    listed = client.get("/v1/ingest/datasets")
    assert listed.json()["bars"] == 1


def test_ingest_graph_depth_rejected():
    # n1 <- n2 <- n3 <- n4  => depth 3 > 2
    graph = {
        "graph_id": "deep",
        "version": 1,
        "nodes": [
            {"id": "n1", "type": "indicator", "kind": "RSI", "source": "close"},
            {"id": "n2", "type": "indicator", "kind": "EMA", "source_node": "n1"},
            {"id": "n3", "type": "indicator", "kind": "EMA", "source_node": "n2"},
            {"id": "n4", "type": "indicator", "kind": "EMA", "source_node": "n3"},
        ],
    }
    r = client.post("/v1/ingest/graphs", json={"graphs": [graph]})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "validation_failed"
