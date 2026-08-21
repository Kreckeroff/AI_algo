#!/usr/bin/env python3
"""Build TRAINING_UNIVERSE_MAP.html — full cross-session training analytics (C7→C17)."""
from __future__ import annotations

import json
import random
import statistics as stats
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESS = ROOT / "artifacts/agent_loop/sessions"
OUT_DIR = ROOT / "artifacts/agent_loop"

WAVES = [
    ("C7", "2026-08-21-c7-intervention-policy"),
    ("C8", "2026-08-21-c8-p3-expand"),
    ("C9", "2026-08-21-c9-multi-symbol"),
    ("C10", "2026-08-21-c10-multi-symbol-expand"),
    ("C11", "2026-08-21-c11-multi-symbol-9"),
    ("C12", "2026-08-21-c12-quality-push"),
    ("C13", "2026-08-21-c13-all-tf"),
    ("C14", "2026-08-21-c14-futures-expand"),
    ("C15", "2026-08-21-c15-buyhold-policy"),
    ("C16", "2026-08-21-c16-atr-sltp"),
    ("C17", "2026-08-21-c17-walkforward-div"),
]

FOCUS_ID = "C17"
FOCUS_SESSION = "2026-08-21-c17-walkforward-div"
FUTURES = {"CNYRUBF", "GLDRUBF", "IMOEXF"}


def agg(xs):
    if not xs:
        return None
    return {
        "n": len(xs),
        "mean": sum(xs) / len(xs),
        "median": stats.median(xs),
        "p10": sorted(xs)[max(0, len(xs) // 10)],
        "p90": sorted(xs)[min(len(xs) - 1, 9 * len(xs) // 10)],
    }


def round_agg(d):
    return {
        k: ({kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in v.items()} if isinstance(v, dict) else v)
        for k, v in d.items()
    }


def wave_metrics(sid: str, s: dict, m: dict) -> tuple:
    """Return (acc, auc, n_pairs, n_better, n_promoted)."""
    met = m.get("metrics") or {}
    if sid.endswith("c17-walkforward-div"):
        fc = s.get("full_cv") or met.get("full_cv") or {}
        return (
            fc.get("cv_accuracy"),
            fc.get("cv_auc"),
            s.get("n_pairs_full") or met.get("n_pairs_full"),
            s.get("n_better_full") or met.get("n_better_full"),
            s.get("n_promoted"),
        )
    model = s.get("model") or met
    return (
        model.get("cv_accuracy") or model.get("loo_accuracy") or met.get("cv_accuracy"),
        model.get("cv_auc") or model.get("loo_auc") or met.get("cv_auc"),
        s.get("n_pairs"),
        s.get("n_better"),
        s.get("n_promoted"),
    )


def analyze_pairs(pairs: list) -> dict:
    random.seed(42)
    deltas = [p["delta_pnl"] for p in pairs]
    sample = random.sample(deltas, min(1500, len(deltas)))

    cov = defaultdict(lambda: defaultdict(list))
    kind_by_ac = defaultdict(lambda: defaultdict(list))
    kind_overall = defaultdict(list)
    kind_better = defaultdict(list)
    tf_overall = defaultdict(list)
    sym_overall = defaultdict(list)
    side_kind = defaultdict(lambda: defaultdict(list))

    for p in pairs:
        cov[p["symbol"]][p["timeframe"]].append(p["delta_pnl"])
        ac = p.get("asset_class") or ("future" if p["symbol"] in FUTURES else "equity")
        kind_by_ac[ac][p["kind"]].append(p["delta_pnl"])
        kind_overall[p["kind"]].append(p["delta_pnl"])
        kind_better[p["kind"]].append(1 if p["better"] else 0)
        tf_overall[p["timeframe"]].append(p["delta_pnl"])
        sym_overall[p["symbol"]].append(p["delta_pnl"])
        side_kind[p.get("side_mode") or "unknown"][p["kind"]].append(1 if p["better"] else 0)

    cov_mat = {s: {tf: agg(v) for tf, v in tfs.items()} for s, tfs in cov.items()}
    return {
        "n_pairs": len(pairs),
        "n_better": sum(1 for p in pairs if p["better"]),
        "delta_sample": sample,
        "cov_mean": {s: {tf: (v["mean"] if v else None) for tf, v in tfs.items()} for s, tfs in cov_mat.items()},
        "cov_n": {s: {tf: (v["n"] if v else 0) for tf, v in tfs.items()} for s, tfs in cov_mat.items()},
        "kind_overall": round_agg({k: agg(v) for k, v in kind_overall.items()}),
        "kind_better_rate": {
            k: {"rate": (sum(xs) / len(xs) if xs else 0), "n": len(xs)} for k, xs in kind_better.items()
        },
        "kind_by_ac": {ac: round_agg({k: agg(v) for k, v in kinds.items()}) for ac, kinds in kind_by_ac.items()},
        "tf_overall": round_agg({tf: agg(v) for tf, v in tf_overall.items()}),
        "sym_overall": round_agg({s: agg(v) for s, v in sym_overall.items()}),
        "better_rate_side_kind": {
            side: {k: (sum(xs) / len(xs) if xs else 0, len(xs)) for k, xs in kinds.items()}
            for side, kinds in side_kind.items()
        },
        "top20": [
            {
                "symbol": p["symbol"],
                "tf": p["timeframe"],
                "base": p["base"],
                "kind": p["kind"],
                "delta": round(p["delta_pnl"], 2),
                "better": p["better"],
                "side": p.get("side_mode"),
                "asset": p.get("asset_class"),
            }
            for p in sorted(pairs, key=lambda x: -x["delta_pnl"])[:20]
        ],
        "bottom20": [
            {
                "symbol": p["symbol"],
                "tf": p["timeframe"],
                "base": p["base"],
                "kind": p["kind"],
                "delta": round(p["delta_pnl"], 2),
                "better": p["better"],
                "side": p.get("side_mode"),
                "asset": p.get("asset_class"),
            }
            for p in sorted(pairs, key=lambda x: x["delta_pnl"])[:20]
        ],
    }


def build_data() -> dict:
    out: dict = {"waves": [], "focus": {}, "c14": {}, "p37": {}, "p38": {}, "div_cal": {}, "focus_id": FOCUS_ID}

    for name, sid in WAVES:
        p = SESS / sid
        s = json.loads((p / "results" / "variant_summary.json").read_text()) if (p / "results" / "variant_summary.json").exists() else {}
        m = json.loads((p / "models" / "feature_names.json").read_text()) if (p / "models" / "feature_names.json").exists() else {}
        acc, auc, n_pairs, n_better, n_prom = wave_metrics(sid, s, m)
        out["waves"].append(
            {
                "id": name,
                "session": sid,
                "n_pairs": n_pairs,
                "n_better": n_better,
                "n_promoted": n_prom,
                "acc": acc,
                "auc": auc,
                "symbols": s.get("symbols") or m.get("symbols"),
                "tfs": s.get("timeframes") or m.get("timeframes"),
                "kind_stats": s.get("kind_stats"),
                "label_rule": s.get("label_rule"),
            }
        )

    # Focus = C17
    focus_dir = SESS / FOCUS_SESSION
    pairs = json.loads((focus_dir / "results" / "intervention_pairs.json").read_text())
    focus = analyze_pairs(pairs)
    feat = json.loads((focus_dir / "models" / "feature_names.json").read_text())
    prom = json.loads((focus_dir / "results" / "promoted.json").read_text())
    summary = json.loads((focus_dir / "results" / "variant_summary.json").read_text())

    # LOSO from C16 (C17 uses walk-forward instead)
    c16_feat = json.loads((SESS / "2026-08-21-c16-atr-sltp" / "models" / "feature_names.json").read_text())
    loso = (c16_feat.get("metrics") or {}).get("loso_1d") or {}

    focus.update(
        {
            "id": FOCUS_ID,
            "session": FOCUS_SESSION,
            "promoted": prom,
            "loso_1d": loso,
            "loso_note": "LOSO from C16 (C17 reports walk-forward OOS)",
            "importance": feat.get("feature_importance_top") or [],
            "model": {
                "cv_accuracy": (summary.get("full_cv") or {}).get("cv_accuracy"),
                "cv_auc": (summary.get("full_cv") or {}).get("cv_auc"),
                "n": summary.get("n_pairs_full"),
                "label_rule": summary.get("label_rule"),
            },
            "walk_forward": summary.get("walk_forward") or [],
            "year_pooled_cv": summary.get("year_pooled_cv"),
            "near_ex_div_heatmap": summary.get("near_ex_div_heatmap") or {},
            "pairs_by_year": summary.get("pairs_by_year") or {},
            "wf_tfs": summary.get("wf_tfs") or ["1d", "1h"],
            "promo_prefix": "37p",
        }
    )
    out["focus"] = focus
    # backward-compat alias used by older snippets
    out["c14"] = focus

    # Keep raw C14 snapshot for wave comparison note
    c14_sum = json.loads((SESS / "2026-08-21-c14-futures-expand" / "results" / "variant_summary.json").read_text())
    out["c14_wave"] = {
        "n_pairs": c14_sum.get("n_pairs"),
        "n_better": c14_sum.get("n_better"),
        "n_promoted": c14_sum.get("n_promoted"),
        "acc": (c14_sum.get("model") or {}).get("cv_accuracy"),
        "auc": (c14_sum.get("model") or {}).get("cv_auc"),
    }

    p37 = json.loads((SESS / "2026-08-21-p37-divgap" / "results" / "summary.json").read_text())
    out["p37"] = {
        "total_short_crossed": p37["total_short_crossed"],
        "total_short_div_paid": p37["total_short_div_paid"],
        "total_long_div_received": p37["total_long_div_received"],
        "ls_short_div_paid": p37["ls_short_div_paid"],
        "ls_delta_from_div": p37["ls_delta_from_div"],
        "per_symbol": {
            s: {
                "n_div": v["n_div_events_cache"],
                "short_crossed": v["n_short_crossed"],
                "delta": v["delta_from_div"],
                "pnl_raw": v["pnl_raw"],
                "pnl_adj": v["pnl_div_adjusted"],
            }
            for s, v in p37["per_symbol"].items()
        },
    }

    p38_path = SESS / "2026-08-21-p38-buyhold" / "results" / "summary.json"
    if p38_path.exists():
        out["p38"] = json.loads(p38_path.read_text())
    else:
        out["p38"] = {}

    cal = json.loads((ROOT / "data/dividends/moex_equities.json").read_text())
    events = []
    for sym, evs in cal["symbols"].items():
        for e in evs:
            events.append(
                {"symbol": sym, "date": e["ex_effect_date"], "div": e.get("dividend_rub"), "yield": e.get("yield_pct")}
            )
    events.sort(key=lambda x: x["date"])
    out["div_cal"] = {
        "n_events": len(events),
        "events": events,
        "fetched_at": cal.get("fetched_at"),
        "source": cal.get("source"),
    }
    return out


HTML_SHELL = r'''<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>AI_algo — Training Universe Map</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fontsource/ibm-plex-sans@5.0.0/400.css"/>
<style>
:root { --bg:#0c1117; --panel:#151c25; --line:#2a3544; --text:#e8eef4; --muted:#8b9aab; --accent:#3d9cf0; --good:#5ecf8c; --bad:#e07070; --warn:#e0b45e; }
*{box-sizing:border-box} body{margin:0;font-family:"IBM Plex Sans",system-ui,sans-serif;background:radial-gradient(900px 480px at 8% -5%,#152033,var(--bg));color:var(--text);padding:28px 28px 80px}
h1{font-size:1.55rem;font-weight:650;margin:0 0 6px;letter-spacing:-.02em} h2{font-size:1.05rem;margin:28px 0 10px;font-weight:600} h3{font-size:.88rem;margin:0 0 8px;color:var(--muted);font-weight:550}
.sub{color:var(--muted);font-size:.88rem;margin-bottom:18px;max-width:960px;line-height:1.45}
nav.toc{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 22px}
nav.toc a{color:var(--muted);text-decoration:none;font-size:.78rem;border:1px solid var(--line);padding:5px 10px;border-radius:999px;background:var(--panel)}
nav.toc a:hover{color:var(--text);border-color:var(--accent)}
.grid{display:grid;gap:12px} .g4{grid-template-columns:repeat(4,1fr)} .g3{grid-template-columns:repeat(3,1fr)} .g2{grid-template-columns:repeat(2,1fr)}
@media(max-width:980px){.g4,.g3{grid-template-columns:1fr 1fr} .g2{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.k{color:var(--muted);font-size:.68rem;text-transform:uppercase;letter-spacing:.04em} .v{font-size:1.35rem;font-weight:650;margin-top:4px} .v.sm{font-size:1.05rem}
.chart-box{position:relative;height:280px} .chart-box.tall{height:340px}
table.heat,table.data{width:100%;border-collapse:collapse;font-size:.72rem;background:var(--panel);border:1px solid var(--line)}
th,td{border:1px solid var(--line);padding:5px 6px;text-align:center} th{background:#101820;color:var(--muted);font-weight:550}
td.f{text-align:left;font-family:ui-monospace,Menlo,monospace;font-size:.68rem;background:#101820} td.empty{color:#445}
.heat .cell-v{font-weight:650;color:#0b1020} .heat .cell-n{font-size:.58rem;opacity:.75;color:#0b1020}
.legend{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:.75rem;margin:6px 0 10px}
.bar{width:140px;height:8px;border-radius:4px;background:linear-gradient(90deg,#c85a5a,#ddd,#4caf70)}
.timeline{display:flex;flex-direction:column;gap:4px;max-height:420px;overflow:auto;border:1px solid var(--line);border-radius:10px;background:var(--panel);padding:8px}
.tl-row{display:grid;grid-template-columns:88px 64px 1fr 72px;gap:8px;align-items:center;font-size:.75rem;padding:4px 6px;border-radius:6px}
.tl-row:nth-child(odd){background:#121820} .tl-sym{font-family:ui-monospace,monospace;color:var(--accent)} .tl-div{text-align:right;color:var(--good)}
.tl-bar-wrap{background:#0c1117;height:8px;border-radius:4px;overflow:hidden} .tl-bar{height:100%;background:var(--accent);opacity:.85}
.note{color:var(--muted);font-size:.78rem;line-height:1.4} footer{margin-top:36px;color:var(--muted);font-size:.75rem}
</style></head><body>
<h1>Training Universe Map</h1>
<p class="sub">Сводная аналитика AI_algo: волны C7→C17, покрытие TF×symbol, intervention kinds (вкл. ATR SL/TP + rmfilter), Q–Q ΔPnL, LOSO/WF, feature importance, дивидендный календарь и cash-adjust (§7H). Данные на __NOW__.</p>
<nav class="toc">
<a href="#kpi">KPI</a><a href="#waves">C7→C17</a><a href="#wf">Walk-forward</a><a href="#coverage">Coverage</a><a href="#kinds">Kinds</a>
<a href="#qq">Q–Q</a><a href="#loso">LOSO / Imp</a><a href="#tops">Tops</a><a href="#div">Div §7H</a><a href="#graph">DAG</a>
</nav>
<section id="kpi"><h2>Текущий снимок (C17 · §7I+§7H)</h2><div class="grid g4" id="kpi-cards"></div></section>
<section id="waves"><h2>Эволюция модели C7→C17</h2>
<div class="grid g2">
<div class="card"><h3>Pairs &amp; promoted</h3><div class="chart-box"><canvas id="ch-pairs"></canvas></div></div>
<div class="card"><h3>CV accuracy &amp; AUC</h3><div class="chart-box"><canvas id="ch-metrics"></canvas></div></div>
</div>
<div class="card" style="margin-top:12px;overflow:auto"><table class="data" id="tbl-waves"></table></div>
</section>
<section id="wf"><h2>Walk-forward OOS (C17 · 1d+1h)</h2>
<div class="grid g2">
<div class="card"><h3>OOS accuracy / AUC by test year</h3><div class="chart-box"><canvas id="ch-wf"></canvas></div></div>
<div class="card"><h3>near_ex_div × side (better%)</h3><div id="heat-near"></div></div>
</div>
<div class="card" style="margin-top:12px;overflow:auto"><table class="data" id="tbl-wf"></table></div>
</section>
<section id="coverage"><h2>Coverage heatmap — symbol × TF (C17 mean ΔPnL, div-adj)</h2>
<div class="legend"><div class="bar"></div><span>mean ΔPnL</span></div><div id="heat-cov" style="overflow:auto"></div>
<div class="grid g2" style="margin-top:12px">
<div class="card"><h3>Mean ΔPnL by timeframe</h3><div class="chart-box"><canvas id="ch-tf"></canvas></div></div>
<div class="card"><h3>Mean ΔPnL by symbol</h3><div class="chart-box tall"><canvas id="ch-sym"></canvas></div></div>
</div></section>
<section id="kinds"><h2>Intervention kinds (C17)</h2>
<div class="grid g2">
<div class="card"><h3>Mean ΔPnL by kind</h3><div class="chart-box tall"><canvas id="ch-kind"></canvas></div></div>
<div class="card"><h3>Better-rate by kind</h3><div class="chart-box tall"><canvas id="ch-kind-br"></canvas></div></div>
</div>
<div class="grid g2" style="margin-top:12px">
<div class="card"><h3>Equity vs future (mean Δ)</h3><div class="chart-box tall"><canvas id="ch-kind-ac"></canvas></div></div>
<div class="card"><h3>Better-rate: side_mode × kind</h3><div id="heat-side"></div></div>
</div>
</section>
<section id="qq"><h2>Распределение ΔPnL (C17)</h2>
<div class="grid g2">
<div class="card"><h3>Histogram</h3><div class="chart-box"><canvas id="ch-hist"></canvas></div></div>
<div class="card"><h3>Q–Q vs normal</h3><div class="chart-box"><canvas id="ch-qq"></canvas></div></div>
</div></section>
<section id="loso"><h2>LOSO 1d (C16) &amp; feature importance (C17)</h2>
<p class="note" id="loso-note"></p>
<div class="grid g2">
<div class="card"><h3>Leave-one-symbol-out (1d)</h3><div class="chart-box"><canvas id="ch-loso"></canvas></div></div>
<div class="card"><h3>Top feature importance</h3><div class="chart-box tall"><canvas id="ch-imp"></canvas></div></div>
</div></section>
<section id="tops"><h2>Экстремумы пар + promotes</h2>
<div class="grid g2">
<div class="card" style="overflow:auto"><h3>Top +ΔPnL</h3><table class="data" id="tbl-top"></table></div>
<div class="card" style="overflow:auto"><h3>Bottom −ΔPnL</h3><table class="data" id="tbl-bot"></table></div>
</div>
<div class="card" style="margin-top:12px;overflow:auto"><h3>Promoted <span id="promo-label">37p-*</span></h3><table class="data" id="tbl-prom"></table></div>
</section>
<section id="div"><h2>§7H / P3.7 — дивиденды</h2>
<div class="grid g4" id="div-kpi"></div>
<div class="grid g2" style="margin-top:12px">
<div class="card"><h3>Short crossed &amp; Δ by equity</h3><div class="chart-box tall"><canvas id="ch-div-sym"></canvas></div></div>
<div class="card"><h3>Календарь событий</h3><p class="note" id="div-meta"></p><div class="timeline" id="div-tl"></div></div>
</div></section>
<section id="graph"><h2>Граф пайплайна обучения</h2>
<div class="card"><svg id="dag" viewBox="0 0 1100 300" width="100%" height="300"></svg>
<p class="note">Lab → policy → multi-symbol/TF → futures → BH labels → ATR/rmfilter → WF+div. Desktop wire (§7G) out of path.</p></div>
</section>
<footer>AI_algo TRAINING_UNIVERSE_MAP · regenerate: scripts/build_training_universe_map.py</footer>
<script type="application/json" id="DATA">__DATA__</script>
<script>
__JS__
</script>
</body></html>
'''


def main() -> None:
    data = build_data()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "TRAINING_UNIVERSE_DATA.json").write_text(json.dumps(data, ensure_ascii=False))
    NOW = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    payload = json.dumps(data, ensure_ascii=False)
    js = (OUT_DIR / "TRAINING_UNIVERSE_MAP.js").read_text()
    html = (
        HTML_SHELL.replace("__NOW__", NOW)
        .replace("__DATA__", payload)
        .replace("__JS__", js)
    )
    (OUT_DIR / "TRAINING_UNIVERSE_MAP.html").write_text(html)
    print(
        "updated",
        OUT_DIR / "TRAINING_UNIVERSE_MAP.html",
        "waves",
        len(data["waves"]),
        "focus",
        data["focus"]["n_pairs"],
        "promoted",
        len(data["focus"]["promoted"]),
    )


if __name__ == "__main__":
    main()
