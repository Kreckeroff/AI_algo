"""Bar-level market regime: trend_up / trend_down / chop (§B0 dual-structure)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

DEFAULTS = {
    "adx_period": 14,
    "er_period": 20,
    "sma_period": 50,
    "adx_trend": 25.0,
    "adx_chop": 20.0,
    "er_trend": 0.35,
    "er_chop": 0.25,
}


def _sma(xs: Sequence[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(xs)
    if period <= 0 or len(xs) < period:
        return out
    s = sum(xs[:period])
    out[period - 1] = s / period
    for i in range(period, len(xs)):
        s += xs[i] - xs[i - period]
        out[i] = s / period
    return out


def _wilder_smooth(xs: Sequence[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(xs)
    if len(xs) < period:
        return out
    s = sum(xs[:period])
    out[period - 1] = s
    for i in range(period, len(xs)):
        prev = out[i - 1]
        assert prev is not None
        out[i] = prev - (prev / period) + xs[i]
    return out


def _adx_series(bars: Sequence[Dict[str, Any]], period: int) -> List[Optional[float]]:
    n = len(bars)
    if n < period + 2:
        return [None] * n
    tr: List[float] = [0.0] * n
    plus_dm: List[float] = [0.0] * n
    minus_dm: List[float] = [0.0] * n
    for i in range(1, n):
        h = float(bars[i]["high"])
        l = float(bars[i]["low"])
        pc = float(bars[i - 1]["close"])
        ph = float(bars[i - 1]["high"])
        pl = float(bars[i - 1]["low"])
        tr[i] = max(h - l, abs(h - pc), abs(l - pc))
        up = h - ph
        down = pl - l
        plus_dm[i] = up if up > down and up > 0 else 0.0
        minus_dm[i] = down if down > up and down > 0 else 0.0

    atr = _wilder_smooth(tr, period)
    sm_plus = _wilder_smooth(plus_dm, period)
    sm_minus = _wilder_smooth(minus_dm, period)
    dx: List[Optional[float]] = [None] * n
    for i in range(n):
        if atr[i] is None or sm_plus[i] is None or sm_minus[i] is None:
            continue
        if atr[i] <= 1e-12:
            dx[i] = 0.0
            continue
        pdi = 100.0 * (sm_plus[i] / atr[i])
        mdi = 100.0 * (sm_minus[i] / atr[i])
        denom = pdi + mdi
        dx[i] = 0.0 if denom <= 1e-12 else 100.0 * abs(pdi - mdi) / denom

    # ADX = Wilder smooth of DX starting when DX becomes available
    adx: List[Optional[float]] = [None] * n
    first = next((i for i, v in enumerate(dx) if v is not None), None)
    if first is None:
        return adx
    # need `period` DX values
    start = first + period - 1
    if start >= n:
        return adx
    seed = [dx[i] for i in range(first, start + 1) if dx[i] is not None]
    if len(seed) < period:
        return adx
    adx[start] = sum(seed[-period:]) / period
    for i in range(start + 1, n):
        if dx[i] is None or adx[i - 1] is None:
            continue
        adx[i] = ((adx[i - 1] * (period - 1)) + dx[i]) / period
    return adx


def _efficiency_ratio(closes: Sequence[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(closes)
    for i in range(period, len(closes)):
        change = abs(closes[i] - closes[i - period])
        volatility = 0.0
        for j in range(i - period + 1, i + 1):
            volatility += abs(closes[j] - closes[j - 1])
        out[i] = 0.0 if volatility <= 1e-12 else change / volatility
    return out


def classify_bars(
    bars: Sequence[Dict[str, Any]],
    *,
    cfg: Optional[Dict[str, float]] = None,
) -> List[str]:
    """Return per-bar labels: unknown | chop | trend_up | trend_down."""
    conf = {**DEFAULTS, **(cfg or {})}
    n = len(bars)
    if n == 0:
        return []
    closes = [float(b["close"]) for b in bars]
    adx = _adx_series(bars, int(conf["adx_period"]))
    er = _efficiency_ratio(closes, int(conf["er_period"]))
    sma = _sma(closes, int(conf["sma_period"]))

    labels: List[str] = []
    for i in range(n):
        if adx[i] is None or er[i] is None or sma[i] is None:
            labels.append("unknown")
            continue
        a = float(adx[i])
        e = float(er[i])
        if a < conf["adx_chop"] or e < conf["er_chop"]:
            labels.append("chop")
        elif a >= conf["adx_trend"] and e >= conf["er_trend"]:
            labels.append("trend_up" if closes[i] > float(sma[i]) else "trend_down")
        else:
            labels.append("chop")
    return labels


def summarize_regimes(labels: Sequence[str]) -> Dict[str, float]:
    n = len(labels)
    if n == 0:
        return {
            "n_bars": 0.0,
            "chop_share": 0.0,
            "trend_up_share": 0.0,
            "trend_down_share": 0.0,
            "unknown_share": 0.0,
            "trend_share": 0.0,
        }
    counts = {"chop": 0, "trend_up": 0, "trend_down": 0, "unknown": 0}
    for lab in labels:
        counts[lab if lab in counts else "unknown"] += 1
    return {
        "n_bars": float(n),
        "chop_share": counts["chop"] / n,
        "trend_up_share": counts["trend_up"] / n,
        "trend_down_share": counts["trend_down"] / n,
        "unknown_share": counts["unknown"] / n,
        "trend_share": (counts["trend_up"] + counts["trend_down"]) / n,
    }


def regime_at_time(
    bars: Sequence[Dict[str, Any]],
    labels: Sequence[str],
    ts: int,
) -> str:
    """Nearest bar at or before ts; if none, first bar."""
    if not bars or not labels or len(bars) != len(labels):
        return "unknown"
    best_i = 0
    for i, b in enumerate(bars):
        if int(b["time"]) <= int(ts):
            best_i = i
        else:
            break
    return labels[best_i]


def annotate_trades(
    trades: Sequence[Dict[str, Any]],
    bars: Sequence[Dict[str, Any]],
    labels: Sequence[str],
    *,
    use_pnl_key: str = "pnl",
) -> Dict[str, Any]:
    """Aggregate trade PnL split by market regime at entry."""
    buckets = {"chop": 0.0, "trend_up": 0.0, "trend_down": 0.0, "unknown": 0.0}
    counts = {"chop": 0, "trend_up": 0, "trend_down": 0, "unknown": 0}
    annotated = []
    for t in trades or []:
        entry = t.get("entryTime")
        if entry is None:
            reg = "unknown"
        else:
            reg = regime_at_time(bars, labels, int(entry))
        pnl = t.get(use_pnl_key)
        if pnl is None:
            pnl = t.get("pnl")
        if pnl is not None:
            buckets[reg] = buckets.get(reg, 0.0) + float(pnl)
            counts[reg] = counts.get(reg, 0) + 1
        annotated.append({**t, "market_regime_at_entry": reg})
    n_closed = sum(counts.values())
    pnl_trend = buckets["trend_up"] + buckets["trend_down"]
    return {
        "trades": annotated,
        "n_closed": n_closed,
        "frac_trades_in_chop": (counts["chop"] / n_closed) if n_closed else 0.0,
        "pnl_in_chop": buckets["chop"],
        "pnl_in_trend": pnl_trend,
        "pnl_by_regime": buckets,
        "count_by_regime": counts,
    }
