#!/usr/bin/env python3
"""B0b: retune market-regime thresholds; re-score C18/C18b chop metrics without engine re-run."""
from __future__ import annotations

import json
import statistics as st
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys

ROOT = Path("/Users/kreckeroff/Fintech (startup)/AI_algo")
sys.path.insert(0, str(ROOT / "src"))

from ai_algo.domain.market_regime import (  # noqa: E402
    DEFAULTS,
    annotate_trades,
    classify_bars,
    summarize_regimes,
)

C16 = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c16-atr-sltp"
C18 = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c18-regime-dual"
C18B = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c18b-mr-overlay"
B0 = ROOT / "artifacts/agent_loop/sessions/2026-08-21-b0-regime-annotate"
SESSION = ROOT / "artifacts/agent_loop/sessions/2026-08-21-b0b-regime-thresholds"
# v1 thresholds kept for compare
V1 = {
    "adx_trend": 25.0,
    "adx_chop": 20.0,
    "er_trend": 0.35,
    "er_chop": 0.25,
    "chop_combine": "or",
    # force mid→chop like v1 by treating transition as chop in post (we re-run old logic via cfg)
}

SESSION.mkdir(parents=True, exist_ok=True)
(SESSION / "results").mkdir(exist_ok=True)


def v1_classify(bars):
    """Reproduce B0 v1: mid-band labeled chop (no transition)."""
    from ai_algo.domain import market_regime as mr

    conf = {**mr.DEFAULTS, **V1, "adx_trend": 25.0, "adx_chop": 20.0, "er_trend": 0.35, "er_chop": 0.25}
    closes = [float(b["close"]) for b in bars]
    adx = mr._adx_series(bars, 14)
    er = mr._efficiency_ratio(closes, 20)
    sma = mr._sma(closes, 50)
    labels = []
    for i in range(len(bars)):
        if adx[i] is None or er[i] is None or sma[i] is None:
            labels.append("unknown")
            continue
        a, e = float(adx[i]), float(er[i])
        if a < conf["adx_chop"] or e < conf["er_chop"]:
            labels.append("chop")
        elif a >= conf["adx_trend"] and e >= conf["er_trend"]:
            labels.append("trend_up" if closes[i] > float(sma[i]) else "trend_down")
        else:
            labels.append("chop")
    return labels


def window_stats(cfg_name: str, classify_fn) -> Dict[str, Any]:
    rows = []
    for p in sorted(C16.glob("bars_*.json")):
        if not (p.name.endswith("_1d.json") or p.name.endswith("_1h.json")):
            continue
        parts = p.stem.split("_")  # bars_SYM_TF
        sym, tf = parts[1], parts[2]
        bars = json.loads(p.read_text())
        s = summarize_regimes(classify_fn(bars))
        # for v1, transition_share may be 0
        rows.append({
            "symbol": sym, "timeframe": tf,
            "chop_share": s["chop_share"], "trend_share": s["trend_share"],
            "transition_share": s.get("transition_share", 0.0),
            "unknown_share": s["unknown_share"],
        })
    return {
        "cfg": cfg_name,
        "n_windows": len(rows),
        "mean_chop": st.mean(r["chop_share"] for r in rows),
        "mean_trend": st.mean(r["trend_share"] for r in rows),
        "mean_transition": st.mean(r["transition_share"] for r in rows),
        "by_tf": {
            tf: {
                "mean_chop": st.mean(r["chop_share"] for r in rows if r["timeframe"] == tf),
                "mean_trend": st.mean(r["trend_share"] for r in rows if r["timeframe"] == tf),
                "mean_transition": st.mean(r["transition_share"] for r in rows if r["timeframe"] == tf),
            }
            for tf in ("1d", "1h")
        },
        "rows": rows,
    }


def load_engine(session: Path, sym: str, tf: str) -> Dict[str, dict]:
    p = session / f"engine_{sym}_{tf}.jsonl"
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("ok"):
            out[r["file"]] = r
    return out


def rescore_pairs(session: Path, pairs_path: Path, classify_fn) -> List[dict]:
    pairs = json.loads(pairs_path.read_text())
    cache_bars: Dict[tuple, list] = {}
    cache_lab: Dict[tuple, list] = {}
    cache_eng: Dict[tuple, Dict[str, dict]] = {}
    out = []
    for p in pairs:
        sym, tf = p["symbol"], p["timeframe"]
        key = (sym, tf)
        if key not in cache_bars:
            bp = C16 / f"bars_{sym}_{tf}.json"
            if not bp.exists():
                continue
            cache_bars[key] = json.loads(bp.read_text())
            cache_lab[key] = classify_fn(cache_bars[key])
            cache_eng[key] = load_engine(session, sym, tf)
            print("loaded", sym, tf, "scripts", len(cache_eng[key]), flush=True)
        bars, labels = cache_bars[key], cache_lab[key]
        eng = cache_eng[key]
        b = eng.get(p["base"])
        v = eng.get(p["variant"])
        if not b or not v:
            continue
        b_reg = annotate_trades(b.get("trades") or [], bars, labels)
        v_reg = annotate_trades(v.get("trades") or [], bars, labels)
        d_chop = v_reg["pnl_in_chop"] - b_reg["pnl_in_chop"]
        d_trend = v_reg["pnl_in_trend"] - b_reg["pnl_in_trend"]
        win = summarize_regimes(labels)
        out.append({
            **{k: p[k] for k in (
                "symbol", "timeframe", "base", "variant", "kind", "script_regime",
                "delta_pnl", "better",
            ) if k in p},
            "window_chop_share": win["chop_share"],
            "window_trend_share": win["trend_share"],
            "window_transition_share": win.get("transition_share", 0.0),
            "delta_pnl_in_chop": d_chop,
            "delta_pnl_in_trend": d_trend,
            "better_in_chop": d_chop > 1e-6,
            "base_frac_trades_in_chop": b_reg["frac_trades_in_chop"],
        })
    return out


def summarize_pairs(name: str, rows: List[dict]) -> Dict[str, Any]:
    if not rows:
        return {"name": name, "n": 0}
    high = [r for r in rows if r["window_chop_share"] >= 0.40]
    return {
        "name": name,
        "n": len(rows),
        "mean_delta_pnl": st.mean(r["delta_pnl"] for r in rows),
        "mean_delta_pnl_in_chop": st.mean(r["delta_pnl_in_chop"] for r in rows),
        "mean_delta_pnl_in_trend": st.mean(r["delta_pnl_in_trend"] for r in rows),
        "better_rate": sum(1 for r in rows if r.get("better")) / len(rows),
        "better_in_chop_rate": sum(1 for r in rows if r["better_in_chop"]) / len(rows),
        "mean_window_chop": st.mean(r["window_chop_share"] for r in rows),
        "high_chop_n": len(high),
        "high_chop_mean_d_chop": st.mean(r["delta_pnl_in_chop"] for r in high) if high else None,
        "high_chop_better_in_chop_rate": (
            sum(1 for r in high if r["better_in_chop"]) / len(high) if high else None
        ),
    }


def main() -> None:
    w_v1 = window_stats("v1_mid_as_chop", v1_classify)
    w_v2 = window_stats("b0b_defaults", lambda bars: classify_bars(bars))

    c18_v1 = rescore_pairs(C18, C18 / "results" / "intervention_pairs.json", v1_classify)
    c18_v2 = rescore_pairs(C18, C18 / "results" / "intervention_pairs.json", lambda b: classify_bars(b))
    c18b_v1 = rescore_pairs(C18B, C18B / "results" / "intervention_pairs.json", v1_classify)
    c18b_v2 = rescore_pairs(C18B, C18B / "results" / "intervention_pairs.json", lambda b: classify_bars(b))

    summary = {
        "defaults_b0b": DEFAULTS,
        "windows_v1": {k: w_v1[k] for k in w_v1 if k != "rows"},
        "windows_b0b": {k: w_v2[k] for k in w_v2 if k != "rows"},
        "c18_gate_v1": summarize_pairs("c18_gate_v1", c18_v1),
        "c18_gate_b0b": summarize_pairs("c18_gate_b0b", c18_v2),
        "c18b_overlay_v1": summarize_pairs("c18b_overlay_v1", c18b_v1),
        "c18b_overlay_b0b": summarize_pairs("c18b_overlay_b0b", c18b_v2),
    }

    (SESSION / "results" / "window_stats_v1.json").write_text(json.dumps(w_v1, indent=2) + "\n")
    (SESSION / "results" / "window_stats_b0b.json").write_text(json.dumps(w_v2, indent=2) + "\n")
    (SESSION / "results" / "c18_rescored_b0b.json").write_text(json.dumps(c18_v2, indent=2) + "\n")
    (SESSION / "results" / "c18b_rescored_b0b.json").write_text(json.dumps(c18b_v2, indent=2) + "\n")
    (SESSION / "results" / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    report = [
        "# B0b regime threshold retune",
        "",
        f"- New DEFAULTS: `{DEFAULTS}`",
        f"- Windows mean chop/trend/trans: "
        f"**{w_v2['mean_chop']:.3f} / {w_v2['mean_trend']:.3f} / {w_v2['mean_transition']:.3f}** "
        f"(was {w_v1['mean_chop']:.3f} / {w_v1['mean_trend']:.3f})",
        "",
        "## C18 gate re-score (same trades, new labels)",
        f"- mean Δchop v1→b0b: {summary['c18_gate_v1']['mean_delta_pnl_in_chop']:.1f} → "
        f"**{summary['c18_gate_b0b']['mean_delta_pnl_in_chop']:.1f}**",
        f"- better_in_chop rate: {summary['c18_gate_v1']['better_in_chop_rate']:.3f} → "
        f"**{summary['c18_gate_b0b']['better_in_chop_rate']:.3f}**",
        f"- high_chop (≥0.40) mean Δchop: {summary['c18_gate_b0b']['high_chop_mean_d_chop']}",
        "",
        "## C18b overlay re-score",
        f"- mean Δchop v1→b0b: {summary['c18b_overlay_v1']['mean_delta_pnl_in_chop']:.1f} → "
        f"**{summary['c18b_overlay_b0b']['mean_delta_pnl_in_chop']:.1f}**",
        f"- better_in_chop rate: {summary['c18b_overlay_v1']['better_in_chop_rate']:.3f} → "
        f"**{summary['c18b_overlay_b0b']['better_in_chop_rate']:.3f}**",
        "",
        "Note: graph mutations still use ADX>25; this retune is the **labeler** only.",
    ]
    (SESSION / "REPORT.md").write_text("\n".join(report) + "\n")
    (SESSION / "notes.md").write_text(
        "B0b: mid→transition; adx_chop=15 er_chop=0.15 adx_trend=20 er_trend=0.28; re-score C18/C18b.\n"
    )

    html = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"/><title>B0b thresholds</title>
<style>
body{{font-family:IBM Plex Sans,system-ui,sans-serif;background:#0f1419;color:#e8eef4;padding:28px}}
.card{{background:#1a222c;border:1px solid #2a3542;border-radius:10px;padding:12px}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px}}
.k{{color:#8b9aab;font-size:.68rem;text-transform:uppercase}} .v{{font-size:1.15rem;font-weight:600;margin-top:4px}}
table{{border-collapse:collapse;width:100%;font-size:.8rem;background:#1a222c}}
th,td{{border:1px solid #2a3542;padding:7px;text-align:right}} th,td.f{{text-align:left;color:#8b9aab}}
</style></head><body>
<h1>B0b — regime thresholds</h1>
<div class="grid">
<div class="card"><div class="k">chop mean</div><div class="v">{w_v1['mean_chop']:.2f} → {w_v2['mean_chop']:.2f}</div></div>
<div class="card"><div class="k">trend mean</div><div class="v">{w_v1['mean_trend']:.2f} → {w_v2['mean_trend']:.2f}</div></div>
<div class="card"><div class="k">transition</div><div class="v">{w_v2['mean_transition']:.2f}</div></div>
</div>
<table><thead><tr><th class="f">wave</th><th>mean Δchop v1</th><th>mean Δchop b0b</th><th>better_in_chop b0b</th></tr></thead>
<tbody>
<tr><td class="f">C18 gate</td><td>{summary['c18_gate_v1']['mean_delta_pnl_in_chop']:.1f}</td>
<td>{summary['c18_gate_b0b']['mean_delta_pnl_in_chop']:.1f}</td>
<td>{summary['c18_gate_b0b']['better_in_chop_rate']:.2f}</td></tr>
<tr><td class="f">C18b overlay</td><td>{summary['c18b_overlay_v1']['mean_delta_pnl_in_chop']:.1f}</td>
<td>{summary['c18b_overlay_b0b']['mean_delta_pnl_in_chop']:.1f}</td>
<td>{summary['c18b_overlay_b0b']['better_in_chop_rate']:.2f}</td></tr>
</tbody></table>
</body></html>"""
    (SESSION / "ANALYTICS.html").write_text(html)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
