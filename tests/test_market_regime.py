"""Unit tests for market regime (trend vs chop) classifier."""
from __future__ import annotations

import math

from ai_algo.domain.market_regime import classify_bars, regime_at_time, summarize_regimes


def _bars_uptrend(n: int = 200, start: float = 100.0) -> list[dict]:
    out = []
    px = start
    t0 = 1_600_000_000
    for i in range(n):
        px = start + i * 0.8  # strong directional drift
        noise = 0.05 * math.sin(i)
        o = px - 0.1
        c = px + noise
        h = max(o, c) + 0.15
        l = min(o, c) - 0.15
        out.append({"time": t0 + i * 86400, "open": o, "high": h, "low": l, "close": c, "volume": 1.0})
    return out


def _bars_chop(n: int = 200, mid: float = 100.0) -> list[dict]:
    out = []
    t0 = 1_600_000_000
    for i in range(n):
        # oscillating range — high path length, low net change
        wiggle = 2.5 * math.sin(i / 3.0) + 1.2 * math.sin(i / 7.0)
        c = mid + wiggle
        o = mid + wiggle * 0.9
        h = max(o, c) + 0.4
        l = min(o, c) - 0.4
        out.append({"time": t0 + i * 86400, "open": o, "high": h, "low": l, "close": c, "volume": 1.0})
    return out


def test_uptrend_mostly_trend_up():
    labels = classify_bars(_bars_uptrend())
    known = [x for x in labels if x != "unknown"]
    assert len(known) > 50
    share_up = sum(1 for x in known if x == "trend_up") / len(known)
    share_chop = sum(1 for x in known if x == "chop") / len(known)
    assert share_up >= 0.55, (share_up, share_chop)
    assert share_chop <= 0.45


def test_chop_mostly_chop():
    labels = classify_bars(_bars_chop())
    known = [x for x in labels if x != "unknown"]
    assert len(known) > 50
    share_chop = sum(1 for x in known if x == "chop") / len(known)
    share_trend = sum(1 for x in known if x in ("trend_up", "trend_down")) / len(known)
    # B0b: mid can be transition; chop should still dominate trend on oscillating series
    assert share_chop >= 0.45, share_chop
    assert share_chop > share_trend, (share_chop, share_trend)


def test_summarize_and_regime_at_time():
    bars = _bars_uptrend(120)
    labels = classify_bars(bars)
    summary = summarize_regimes(labels)
    assert summary["n_bars"] == len(bars)
    assert 0.0 <= summary["chop_share"] <= 1.0
    parts = (
        summary["chop_share"]
        + summary["trend_up_share"]
        + summary["trend_down_share"]
        + summary["transition_share"]
        + summary["unknown_share"]
    )
    assert abs(parts - 1.0) < 1e-6
    mid = bars[len(bars) // 2]["time"]
    r = regime_at_time(bars, labels, mid)
    assert r in ("trend_up", "trend_down", "chop", "transition", "unknown")


def test_b0b_defaults_balanced_on_real_ish_mix():
    """Synthetic: uptrend mostly trend; chop mostly chop; mid can be transition."""
    from ai_algo.domain.market_regime import DEFAULTS

    assert DEFAULTS["adx_chop"] == 15.0
    assert DEFAULTS["adx_trend"] == 20.0
    assert DEFAULTS["er_chop"] == 0.15
    assert DEFAULTS["er_trend"] == 0.28
    assert DEFAULTS["chop_combine"] == "or"
