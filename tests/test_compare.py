import pytest

from ai_algo.domain.compare import verdict_from_diff
from fastapi.testclient import TestClient

from ai_algo.app import app

client = TestClient(app)


def test_verdict_better():
    before = {"pnl": 1.0, "max_dd": 0.2, "winrate": 0.4, "trades": 20}
    after = {"pnl": 2.0, "max_dd": 0.1, "winrate": 0.5, "trades": 22}
    v, diff, warnings, _ = verdict_from_diff(before, after)
    assert v == "better"
    assert diff["pnl"] == 1.0
    assert warnings == []


def test_verdict_worse():
    before = {"pnl": 2.0, "max_dd": 0.1, "winrate": 0.5, "trades": 20}
    after = {"pnl": 1.0, "max_dd": 0.3, "winrate": 0.4, "trades": 18}
    v, _, _, _ = verdict_from_diff(before, after)
    assert v == "worse"


def test_verdict_mixed_and_low_sample():
    before = {"pnl": 1.0, "max_dd": 0.2, "winrate": 0.4, "trades": 3}
    after = {"pnl": 2.0, "max_dd": 0.3, "winrate": 0.5, "trades": 4}
    v, _, warnings, _ = verdict_from_diff(before, after)
    assert v == "mixed"
    assert "low_sample" in warnings


def test_align_mismatch():
    before = {"pnl": 1.0, "max_dd": 0.2, "winrate": 0.4, "trades": 20}
    after = {"pnl": 2.0, "max_dd": 0.1, "winrate": 0.5, "trades": 22}
    with pytest.raises(ValueError, match="align_mismatch"):
        verdict_from_diff(
            before,
            after,
            {"symbol": "SBER"},
            {"symbol": "GAZP"},
        )


def test_infer_compare_ok():
    r = client.post(
        "/v1/infer",
        json={
            "api_version": "2026-08-20",
            "request_id": "c1",
            "client": {
                "product": "it-algo-desktop",
                "app_version": "0.0.0",
                "env": "dev",
            },
            "intent": "compare_scripts",
            "payload": {
                "before": {
                    "backtest_metrics": {
                        "pnl": 1.0,
                        "max_dd": 0.2,
                        "winrate": 0.4,
                        "trades": 20,
                    }
                },
                "after": {
                    "backtest_metrics": {
                        "pnl": 2.0,
                        "max_dd": 0.1,
                        "winrate": 0.5,
                        "trades": 22,
                    }
                },
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["result"]["verdict"] == "better"
    assert "commentary" in body["result"]
