import json
from pathlib import Path

from fastapi.testclient import TestClient

from ai_algo.app import app
from ai_algo.store import memory as store_mod
from ai_algo.store.file_store import FileStore, reset_store_for_tests

client = TestClient(app)


def setup_function():
    reset_store_for_tests()


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
    assert store_mod.store.bars
    listed = client.get("/v1/ingest/datasets")
    assert listed.json()["bars"] == 1


def test_ingest_graph_depth_rejected():
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


def test_file_store_persists(tmp_path: Path):
    store = FileStore(tmp_path)
    bid = store.put_bars(
        {
            "dataset_id": "sber-5m",
            "symbol": "SBER",
            "timeframe": "5m",
            "bars": [
                {
                    "ts": "2026-01-01T00:00:00Z",
                    "open": 1,
                    "high": 2,
                    "low": 0.5,
                    "close": 1.5,
                    "volume": 10,
                }
            ],
        }
    )
    assert bid == "sber-5m"
    path = tmp_path / "bars" / "sber-5m.json"
    assert path.exists()
    reloaded = FileStore(tmp_path)
    assert "sber-5m" in reloaded.bars
    assert reloaded.bars["sber-5m"]["symbol"] == "SBER"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["_id"] == "sber-5m"
