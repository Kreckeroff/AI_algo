from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def metrics_diff(before: dict, after: dict) -> Dict[str, float]:
    keys = ("pnl", "max_dd", "winrate", "trades")
    out: Dict[str, float] = {}
    for k in keys:
        out[k] = float(after[k]) - float(before[k])
    for k in ("sharpe", "sortino"):
        if k in before and k in after:
            out[k] = float(after[k]) - float(before[k])
    return out


def verdict_from_diff(
    before: dict,
    after: dict,
    align_before: Optional[dict] = None,
    align_after: Optional[dict] = None,
) -> Tuple[str, Dict[str, float], List[str], List[str]]:
    """Return verdict, diff, warnings, suggestions."""
    warnings: List[str] = []
    suggestions: List[str] = []

    if align_before is not None and align_after is not None:
        for key in ("symbol", "timeframe", "commission", "from", "to"):
            if align_before.get(key) != align_after.get(key):
                raise ValueError("align_mismatch")

    diff = metrics_diff(before, after)

    if before.get("trades", 0) < 5 or after.get("trades", 0) < 5:
        warnings.append("low_sample")

    pnl_better = after["pnl"] > before["pnl"]
    dd_better = after["max_dd"] < before["max_dd"]  # lower drawdown is better
    pnl_worse = after["pnl"] < before["pnl"]
    dd_worse = after["max_dd"] > before["max_dd"]

    if pnl_better and dd_better:
        verdict = "better"
    elif pnl_worse and dd_worse:
        verdict = "worse"
    else:
        verdict = "mixed"

    if not dd_better and dd_worse:
        suggestions.append("Reduce max drawdown (risk / stops / size).")
    if not pnl_better and pnl_worse:
        suggestions.append("Improve expectancy or reduce costs before adding complexity.")
    if verdict == "mixed":
        suggestions.append("PnL and drawdown moved in different directions — decide primary objective.")
    if not suggestions:
        suggestions.append("Keep the change and re-validate on another out-of-sample window.")

    return verdict, diff, warnings, suggestions[:3]


def commentary(verdict: str, diff: Dict[str, float]) -> str:
    return (
        "Verdict: {v}. "
        "Δpnl={pnl:.4f}, Δmax_dd={dd:.4f}, Δwinrate={wr:.4f}, Δtrades={tr:.0f}."
    ).format(
        v=verdict,
        pnl=diff.get("pnl", 0.0),
        dd=diff.get("max_dd", 0.0),
        wr=diff.get("winrate", 0.0),
        tr=diff.get("trades", 0.0),
    )
