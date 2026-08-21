#!/usr/bin/env python3
"""B0: annotate C16 engines with market regime; join C17 pairs; ANALYTICS_REGIME.html."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path("/Users/kreckeroff/Fintech (startup)/AI_algo")
C16 = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c16-atr-sltp"
C17 = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c17-walkforward-div"
SESSION = ROOT / "artifacts/agent_loop/sessions/2026-08-21-b0-regime-annotate"
ITALGO = ROOT.parent / "it-algo-desktop/docs/work/scripting/samples/ai-train"

sys.path.insert(0, str(ROOT / "src"))
from ai_algo.domain.market_regime import annotate_trades, classify_bars, summarize_regimes  # noqa: E402
from ai_algo.domain.trade_analysis import infer_script_regime  # noqa: E402

TFS = ["1d", "1h"]
FUTURES = {"CNYRUBF", "GLDRUBF", "IMOEXF"}
PROMO = tuple(f"{i}p-" for i in range(27, 40))

SESSION.mkdir(parents=True, exist_ok=True)
(SESSION / "results").mkdir(exist_ok=True)


def infer_kind(var_name: str) -> Optional[str]:
    mapping = [
        ("__atrsltp", "add_block_atr_sltp"),
        ("__rmfilter", "remove_block_filter"),
        ("__period15x", "change_period_15x"),
        ("__period067", "change_period_067"),
        ("__period2x", "change_period_2x"),
        ("__period05x", "change_period_05x"),
        ("__ema50", "add_block_ema"),
        ("__adx25", "add_block_adx"),
        ("__sma200", "add_block_sma200"),
        ("__rsi50", "add_block_rsi50"),
    ]
    for suf, kind in mapping:
        if suf in var_name:
            return kind
    return None


def base_of(var_name: str) -> Optional[str]:
    if "__" not in var_name:
        return None
    return var_name.split("__", 1)[0] + ".italgo"


def chop_bucket(share: float) -> str:
    if share < 0.35:
        return "low_chop"
    if share < 0.55:
        return "mid_chop"
    return "high_chop"


def script_regime_cached(cache: Dict[str, str], file_name: str, nodes) -> str:
    if file_name in cache:
        return cache[file_name]
    path = ITALGO / file_name
    if path.exists():
        doc = json.loads(path.read_text())
        nodes = (doc.get("graph") or {}).get("nodes") or nodes
    reg = infer_script_regime(nodes)
    cache[file_name] = reg
    return reg


def main() -> None:
    # per (sym,tf): bars + labels + summary
    bar_cache: Dict[Tuple[str, str], dict] = {}
    for bars_path in sorted(C16.glob("bars_*.json")):
        parts = bars_path.stem.split("_")
        if len(parts) < 3:
            continue
        sym, tf = parts[1], parts[2]
        if tf not in TFS:
            continue
        bars = json.loads(bars_path.read_text())
        labels = classify_bars(bars)
        bar_cache[(sym, tf)] = {
            "bars": bars,
            "labels": labels,
            "summary": summarize_regimes(labels),
        }
    print("bar windows", len(bar_cache), flush=True)

    # annotate each engine script (bases + variants used in pairs)
    per_script: List[dict] = []
    script_ann: Dict[Tuple[str, str, str], dict] = {}
    regime_cache: Dict[str, str] = {}

    engines = [p for p in sorted(C16.glob("engine_*.jsonl")) if p.stem.split("_")[-1] in TFS]
    for ei, eng in enumerate(engines, 1):
        parts = eng.stem.split("_")
        sym, tf = parts[1], parts[2]
        bc = bar_cache.get((sym, tf))
        if not bc:
            continue
        bars, labels = bc["bars"], bc["labels"]
        win = bc["summary"]
        n_ok = 0
        for line in eng.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if not row.get("ok"):
                continue
            fname = row["file"]
            if fname.startswith(PROMO):
                continue
            trades = row.get("trades") or []
            ann = annotate_trades(trades, bars, labels)
            sreg = script_regime_cached(regime_cache, fname, row.get("nodes"))
            rec = {
                "symbol": sym,
                "timeframe": tf,
                "file": fname,
                "script_regime": sreg,
                "asset_class": "future" if sym in FUTURES else "equity",
                "window_chop_share": win["chop_share"],
                "window_trend_share": win["trend_share"],
                "frac_trades_in_chop": ann["frac_trades_in_chop"],
                "pnl_in_chop": ann["pnl_in_chop"],
                "pnl_in_trend": ann["pnl_in_trend"],
                "n_closed": ann["n_closed"],
                "count_by_regime": ann["count_by_regime"],
                "net_pnl": float((row.get("stats") or {}).get("netPnl") or 0.0),
            }
            per_script.append(rec)
            script_ann[(sym, tf, fname)] = rec
            n_ok += 1
        print(f"[{ei}/{len(engines)}] {sym} {tf} scripts={n_ok}", flush=True)

    # join C17 pairs
    pairs = json.loads((C17 / "results" / "intervention_pairs.json").read_text())
    enriched = []
    kind_bucket = defaultdict(lambda: {"n": 0, "better": 0, "sum_delta": 0.0, "sum_d_chop": 0.0})
    for p in pairs:
        if p.get("timeframe") not in TFS:
            continue
        sym, tf = p["symbol"], p["timeframe"]
        base_a = script_ann.get((sym, tf, p["base"]))
        var_a = script_ann.get((sym, tf, p["variant"]))
        if not base_a or not var_a:
            continue
        bucket = chop_bucket(float(base_a["window_chop_share"]))
        d_chop = float(var_a["pnl_in_chop"]) - float(base_a["pnl_in_chop"])
        d_trend = float(var_a["pnl_in_trend"]) - float(base_a["pnl_in_trend"])
        ep = {
            "symbol": p["symbol"],
            "timeframe": p["timeframe"],
            "base": p["base"],
            "variant": p["variant"],
            "kind": p["kind"],
            "better": p["better"],
            "delta_pnl": p["delta_pnl"],
            "side_mode": p.get("side_mode"),
            "asset_class": p.get("asset_class"),
            "script_regime": base_a["script_regime"],
            "window_chop_share": base_a["window_chop_share"],
            "chop_bucket": bucket,
            "base_frac_trades_in_chop": base_a["frac_trades_in_chop"],
            "base_pnl_in_chop": base_a["pnl_in_chop"],
            "base_pnl_in_trend": base_a["pnl_in_trend"],
            "delta_pnl_in_chop": d_chop,
            "delta_pnl_in_trend": d_trend,
            "better_in_chop": d_chop > 1e-6,
        }
        enriched.append(ep)
        key = (p["kind"], bucket)
        kind_bucket[key]["n"] += 1
        kind_bucket[key]["sum_delta"] += float(p["delta_pnl"])
        kind_bucket[key]["sum_d_chop"] += d_chop
        if p["better"]:
            kind_bucket[key]["better"] += 1

    kind_bucket_out = []
    for (kind, bucket), st in kind_bucket.items():
        kind_bucket_out.append({
            "kind": kind,
            "chop_bucket": bucket,
            "n": st["n"],
            "better_rate": st["better"] / max(1, st["n"]),
            "mean_delta": st["sum_delta"] / max(1, st["n"]),
            "mean_delta_pnl_in_chop": st["sum_d_chop"] / max(1, st["n"]),
        })
    kind_bucket_out.sort(key=lambda x: (x["chop_bucket"], -x["mean_delta_pnl_in_chop"]))

    # hypothesis candidates: trend scripts that lose in chop on base
    candidates = []
    for (sym, tf, fname), rec in script_ann.items():
        if "__" in fname:
            continue
        if rec["script_regime"] != "trend":
            continue
        if rec["pnl_in_chop"] < -1e-6 and rec["pnl_in_trend"] > 1e-6 and rec["window_chop_share"] >= 0.35:
            candidates.append({
                "symbol": sym,
                "timeframe": tf,
                "file": fname,
                "window_chop_share": rec["window_chop_share"],
                "pnl_in_chop": rec["pnl_in_chop"],
                "pnl_in_trend": rec["pnl_in_trend"],
                "frac_trades_in_chop": rec["frac_trades_in_chop"],
            })
    candidates.sort(key=lambda x: x["pnl_in_chop"])

    window_rows = [
        {"symbol": s, "timeframe": t, **bar_cache[(s, t)]["summary"]}
        for (s, t) in sorted(bar_cache.keys())
    ]

    summary = {
        "session": "2026-08-21-b0-regime-annotate",
        "tfs": TFS,
        "n_bar_windows": len(bar_cache),
        "n_script_annotations": len(per_script),
        "n_enriched_pairs": len(enriched),
        "n_hypothesis_candidates": len(candidates),
        "kind_by_chop_bucket": kind_bucket_out,
        "mean_window_chop_share": (
            sum(w["chop_share"] for w in window_rows) / max(1, len(window_rows))
        ),
    }

    (SESSION / "results" / "window_regimes.json").write_text(
        json.dumps(window_rows, indent=2) + "\n"
    )
    (SESSION / "results" / "script_annotations.json").write_text(
        json.dumps(per_script, indent=2, ensure_ascii=False) + "\n"
    )
    (SESSION / "results" / "pairs_enriched.json").write_text(
        json.dumps(enriched, indent=2, ensure_ascii=False) + "\n"
    )
    (SESSION / "results" / "kind_by_chop_bucket.json").write_text(
        json.dumps(kind_bucket_out, indent=2, ensure_ascii=False) + "\n"
    )
    (SESSION / "results" / "hypothesis_candidates.json").write_text(
        json.dumps(candidates[:80], indent=2, ensure_ascii=False) + "\n"
    )
    (SESSION / "results" / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    # HTML
    buckets = ["low_chop", "mid_chop", "high_chop"]
    kinds = sorted({r["kind"] for r in kind_bucket_out})
    lookup = {(r["kind"], r["chop_bucket"]): r for r in kind_bucket_out}

    def cell(kind, bucket, field):
        r = lookup.get((kind, bucket))
        if not r:
            return "—"
        if field == "better_rate":
            return f"{100 * r['better_rate']:.0f}%"
        return f"{r[field]:.1f}"

    heat_rows = "".join(
        "<tr><td class='f'>" + k + "</td>"
        + "".join(f"<td>{cell(k, b, 'mean_delta_pnl_in_chop')}</td><td>{cell(k, b, 'better_rate')}</td>" for b in buckets)
        + "</tr>"
        for k in kinds
    )
    cand_rows = "".join(
        f"<tr><td class='f'>{c['symbol']}</td><td>{c['timeframe']}</td><td class='f'>{c['file']}</td>"
        f"<td>{c['window_chop_share']:.2f}</td><td>{c['pnl_in_chop']:.1f}</td><td>{c['pnl_in_trend']:.1f}</td></tr>"
        for c in candidates[:25]
    )
    win_rows = "".join(
        f"<tr><td class='f'>{w['symbol']}</td><td>{w['timeframe']}</td>"
        f"<td>{w['chop_share']:.2f}</td><td>{w['trend_share']:.2f}</td><td>{int(w['n_bars'])}</td></tr>"
        for w in window_rows
    )
    html = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"/>
<title>B0 Regime Analytics</title>
<style>
body{{font-family:IBM Plex Sans,system-ui,sans-serif;background:#0f1419;color:#e8eef4;padding:28px}}
.sub{{color:#8b9aab;max-width:900px;line-height:1.45}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0}}
.card{{background:#1a222c;border:1px solid #2a3542;border-radius:10px;padding:12px}}
.k{{color:#8b9aab;font-size:.68rem;text-transform:uppercase}} .v{{font-size:1.15rem;font-weight:600;margin-top:4px}}
table{{border-collapse:collapse;width:100%;font-size:.75rem;background:#1a222c;margin:12px 0}}
th,td{{border:1px solid #2a3542;padding:6px;text-align:right}} th,td.f{{text-align:left;color:#8b9aab}}
h1{{margin:0 0 8px}} h2{{margin:28px 0 8px;font-size:1.05rem}}
</style></head><body>
<h1>B0 — Market regime annotate</h1>
<p class="sub">ADX+ER labels on C16 bars (1d+1h) · joined to C17 pairs · hypothesis: trend scripts that bleed in chop.</p>
<div class="grid">
<div class="card"><div class="k">Windows</div><div class="v">{summary['n_bar_windows']}</div></div>
<div class="card"><div class="k">Script ann.</div><div class="v">{summary['n_script_annotations']}</div></div>
<div class="card"><div class="k">Enriched pairs</div><div class="v">{summary['n_enriched_pairs']}</div></div>
<div class="card"><div class="k">Mean chop share</div><div class="v">{summary['mean_window_chop_share']:.2f}</div></div>
</div>
<h2>Kind × chop bucket — mean ΔPnL<sub>chop</sub> / better%</h2>
<table><thead><tr><th>kind</th>
<th>low Δchop</th><th>low better</th>
<th>mid Δchop</th><th>mid better</th>
<th>high Δchop</th><th>high better</th>
</tr></thead><tbody>{heat_rows}</tbody></table>
<h2>Trend scripts losing in chop (candidates for gate/overlay)</h2>
<table><thead><tr><th>sym</th><th>tf</th><th>file</th><th>chop_share</th><th>pnl_chop</th><th>pnl_trend</th></tr></thead>
<tbody>{cand_rows}</tbody></table>
<h2>Window regime shares</h2>
<table><thead><tr><th>sym</th><th>tf</th><th>chop</th><th>trend</th><th>n_bars</th></tr></thead>
<tbody>{win_rows}</tbody></table>
</body></html>
"""
    (SESSION / "ANALYTICS_REGIME.html").write_text(html)
    (SESSION / "notes.md").write_text(
        "B0: market_regime ADX+ER on C16 1d+1h; enriched C17 pairs; candidates for B1 chop_gate.\n"
    )
    (SESSION / "REPORT.md").write_text(
        "# B0 Regime annotate\n\n"
        f"- Windows: {summary['n_bar_windows']}\n"
        f"- Script annotations: {summary['n_script_annotations']}\n"
        f"- Enriched pairs: {summary['n_enriched_pairs']}\n"
        f"- Hypothesis candidates: {summary['n_hypothesis_candidates']}\n"
        f"- Mean window chop_share: {summary['mean_window_chop_share']:.3f}\n"
    )
    print("SUMMARY", summary["n_enriched_pairs"], "candidates", summary["n_hypothesis_candidates"], flush=True)


if __name__ == "__main__":
    main()
