"""Dividend-gap helpers for equity/index training (§7H / P3.7)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE = ROOT / "data" / "dividends" / "moex_equities.json"


def load_dividend_cache(path: Path = DEFAULT_CACHE) -> Dict[str, List[Dict[str, Any]]]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return raw.get("symbols") or {}


def _day_start_ts(date_yyyy_mm_dd: str) -> int:
    dt = datetime.strptime(date_yyyy_mm_dd, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def events_in_window(
    events: Sequence[Dict[str, Any]],
    from_ts: Optional[int],
    to_ts: Optional[int],
) -> List[Dict[str, Any]]:
    out = []
    for e in events:
        ts = _day_start_ts(e["ex_effect_date"])
        if from_ts is not None and ts < from_ts:
            continue
        if to_ts is not None and ts > to_ts:
            continue
        out.append({**e, "ex_effect_ts": ts})
    return out


def trade_crosses_ex_div(
    *,
    entry_ts: int,
    exit_ts: Optional[int],
    side: str,
    events: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return dividend events a trade was exposed to.

    Short (`sell`) or long (`buy`) held open through ex_effect_date session.
    Rule: entry_ts <= ex_ts < exit_ts (exit_ts missing → still open → count).
    """
    if exit_ts is None:
        exit_ts = 2**31 - 1
    hit = []
    for e in events:
        ex_ts = int(e.get("ex_effect_ts") or _day_start_ts(e["ex_effect_date"]))
        if entry_ts <= ex_ts < exit_ts:
            hit.append(e)
    return hit


def adjust_trade_pnl(
    trade: Dict[str, Any],
    events: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Cash-adjust one closed trade for dividends crossed.

    Short pays dividend (PnL − div×qty); long receives (PnL + div×qty).
    """
    side = (trade.get("side") or "").lower()
    entry = int(trade["entryTime"])
    exit_t = trade.get("exitTime")
    exit_ts = int(exit_t) if exit_t is not None else None
    qty = float(trade.get("qty") or 1.0)
    raw = float(trade["pnl"]) if trade.get("pnl") is not None else None
    crossed = trade_crosses_ex_div(entry_ts=entry, exit_ts=exit_ts, side=side, events=events)
    cash = 0.0
    for e in crossed:
        div = float(e.get("dividend_rub") or 0.0)
        if side in ("sell", "short"):
            cash -= div * qty
        elif side in ("buy", "long"):
            cash += div * qty
    adj = None if raw is None else raw + cash
    return {
        **trade,
        "crossed_ex_div": bool(crossed),
        "div_events": [
            {"date": e["ex_effect_date"], "dividend_rub": e.get("dividend_rub")} for e in crossed
        ],
        "div_cash_adjust": cash,
        "pnl_raw": raw,
        "pnl_div_adjusted": adj,
    }


def adjust_trades(
    trades: Iterable[Dict[str, Any]],
    events: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    out = [adjust_trade_pnl(t, events) for t in trades]
    raw_sum = sum(t["pnl_raw"] for t in out if t.get("pnl_raw") is not None)
    adj_sum = sum(t["pnl_div_adjusted"] for t in out if t.get("pnl_div_adjusted") is not None)
    n_cross = sum(1 for t in out if t.get("crossed_ex_div"))
    short_cross = sum(
        1 for t in out if t.get("crossed_ex_div") and (t.get("side") or "").lower() in ("sell", "short")
    )
    return out, {
        "n_trades": float(len(out)),
        "n_crossed": float(n_cross),
        "n_short_crossed": float(short_cross),
        "pnl_raw": float(raw_sum),
        "pnl_div_adjusted": float(adj_sum),
        "delta_from_div": float(adj_sum - raw_sum),
    }
