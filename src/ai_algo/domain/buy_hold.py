"""Buy&hold baseline vs strategy trades (§7I / P3.8)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


def buy_hold_pnl(bars: Sequence[Dict[str, Any]], *, qty: float = 1.0) -> Optional[float]:
    """Passive long: buy first open, sell last close (qty units)."""
    if not bars or len(bars) < 2:
        return None
    return float(qty) * (float(bars[-1]["close"]) - float(bars[0]["open"]))


def trade_side_pnls(trades: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    long_pnl = 0.0
    short_pnl = 0.0
    n_long = 0
    n_short = 0
    for t in trades or []:
        if t.get("pnl") is None:
            continue
        pnl = float(t["pnl"])
        side = (t.get("side") or "").lower()
        if side in ("buy", "long"):
            long_pnl += pnl
            n_long += 1
        elif side in ("sell", "short"):
            short_pnl += pnl
            n_short += 1
    return {
        "long_trades_pnl": long_pnl,
        "short_trades_pnl": short_pnl,
        "n_long_trades": float(n_long),
        "n_short_trades": float(n_short),
        "strategy_net_pnl": long_pnl + short_pnl,
    }


def evaluate_vs_buy_hold(
    *,
    bars: Sequence[Dict[str, Any]],
    trades: Sequence[Dict[str, Any]],
    side_mode: str,
    net_pnl: Optional[float] = None,
    qty: float = 1.0,
    pseudo_max_long_trades: int = 2,
    pseudo_edge_eps: float = 1e-6,
) -> Dict[str, Any]:
    """Return B&H metrics and beats_buy_hold for long_only / long_short."""
    bh = buy_hold_pnl(bars, qty=qty)
    sides = trade_side_pnls(trades)
    strat = float(net_pnl) if net_pnl is not None else float(sides["strategy_net_pnl"])
    mode = (side_mode or "unknown").lower()

    if bh is None:
        return {
            "buy_hold_pnl": None,
            "beats_buy_hold": None,
            "edge_vs_bh": None,
            "pseudo_buy_hold": False,
            "side_mode": mode,
            **sides,
            "strategy_net_pnl": strat,
        }

    if mode == "long_only":
        compare = float(sides["long_trades_pnl"])
        beats = compare > bh
        edge = compare - bh
    elif mode == "long_short":
        compare = strat
        beats = compare > bh
        edge = compare - bh
    else:
        # unknown: still report edge of net vs BH, but don't claim pass/fail
        compare = strat
        beats = None
        edge = compare - bh

    n_long = int(sides["n_long_trades"])
    pseudo = bool(
        beats is True
        and n_long <= pseudo_max_long_trades
        and abs(edge) <= max(abs(bh) * 0.05, pseudo_edge_eps)
    ) or bool(
        # near-BH with almost no trading activity
        n_long <= pseudo_max_long_trades
        and abs(strat - bh) <= max(abs(bh) * 0.05, 1.0)
        and abs(bh) > 1.0
    )

    return {
        "buy_hold_pnl": bh,
        "beats_buy_hold": beats,
        "edge_vs_bh": edge,
        "pseudo_buy_hold": pseudo,
        "side_mode": mode,
        "compare_pnl": compare,
        **sides,
        "strategy_net_pnl": strat,
    }
