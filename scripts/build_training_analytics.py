#!/usr/bin/env python3
"""Build ANALYTICS.html for a training session vs previous session."""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def find_summary(session: Path) -> Optional[dict]:
    for name in ("c3_summary.json", "c2_summary.json", "c1_summary.json", "variant_summary.json"):
        p = session / "results" / name
        data = load_json(p)
        if data:
            data["_source"] = str(p.relative_to(session)) if session in p.parents else str(p)
            return data
    return load_json(session / "results" / "variant_summary.json")


def find_meta(session: Path) -> Optional[dict]:
    return load_json(session / "models" / "feature_names.json")


def top_list(summary: dict) -> List[dict]:
    for key in ("top20_by_score", "top20_by_median", "ranking_v2"):
        if key in summary and summary[key]:
            return summary[key]
    # wave2 family aggregates → fake ranking
    fam = summary.get("family_aggregates") or summary.get("aggregates")
    if isinstance(fam, dict):
        rows = []
        for name, agg in fam.items():
            v2 = agg.get("v2") if isinstance(agg, dict) and "v2" in agg else agg
            if not isinstance(v2, dict) or not v2.get("n"):
                continue
            rows.append(
                {
                    "entry": name,
                    "filter": "v2",
                    "median_pnl": v2.get("mean_pnl", 0),
                    "mean_pnl": v2.get("mean_pnl", 0),
                    "mean_wr": v2.get("mean_wr", 0),
                    "mean_dd": v2.get("mean_dd", 0),
                    "n": v2.get("n", 0),
                    "regime": "trend",
                }
            )
        rows.sort(key=lambda x: x["mean_pnl"], reverse=True)
        return rows
    return []


def aggregate_from_tops(tops: List[dict]) -> dict:
    if not tops:
        return {"n_tops": 0, "med_pnl": 0, "mean_pnl": 0, "mean_wr": 0, "mean_dd": 0}
    pnls = [t.get("median_pnl", t.get("mean_pnl", 0)) for t in tops[:20]]
    wrs = [t.get("mean_wr", 0) for t in tops[:20]]
    dds = [t.get("mean_dd", 0) for t in tops[:20]]
    means = [t.get("mean_pnl", t.get("median_pnl", 0)) for t in tops[:20]]
    return {
        "n_tops": len(tops[:20]),
        "med_pnl": float(sorted(pnls)[len(pnls) // 2]),
        "mean_pnl": float(sum(means) / len(means)),
        "mean_wr": float(sum(wrs) / len(wrs)) if wrs else 0,
        "mean_dd": float(sum(dds) / len(dds)) if dds else 0,
        "best_med_pnl": float(max(pnls)),
    }


def verdict(prev_agg: dict, cur_agg: dict, *, trend_first: bool = True) -> str:
    if not prev_agg.get("n_tops") or not cur_agg.get("n_tops"):
        return "n/a"
    dp = cur_agg["med_pnl"] - prev_agg["med_pnl"]
    dwr = cur_agg["mean_wr"] - prev_agg["mean_wr"]
    ddd = cur_agg["mean_dd"] - prev_agg["mean_dd"]
    eps = 1e-6
    if abs(dp) < eps and abs(dwr) < 0.005:
        return "unchanged"
    if trend_first:
        better = dp > 0 and ddd <= prev_agg["mean_dd"] * 1.15 + 1e-9
        worse = dp < 0 and ddd >= prev_agg["mean_dd"] - 1e-9
    else:
        better = dp > 0 and dwr >= -0.02
        worse = dp < 0 and dwr <= 0.02
    if better:
        return "better"
    if worse:
        return "worse"
    return "mixed"


def html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build(session: Path, prev: Optional[Path]) -> Path:
    summary = find_summary(session) or {}
    meta = find_meta(session) or {}
    prev_summary = find_summary(prev) if prev else None
    prev_meta = find_meta(prev) if prev else None

    tops = top_list(summary)
    cur_agg = aggregate_from_tops(tops)
    prev_tops = top_list(prev_summary) if prev_summary else []
    prev_agg = aggregate_from_tops(prev_tops) if prev_summary else {"n_tops": 0}
    ver = verdict(prev_agg, cur_agg) if prev_summary else "n/a (no prev)"

    sid = session.name
    prev_name = prev.name if prev else "—"
    metrics = (meta.get("metrics") or {}) if meta else {}
    prev_metrics = (prev_meta.get("metrics") or {}) if prev_meta else {}

    def fmt(x: Any, nd: int = 1) -> str:
        if x is None:
            return "—"
        if isinstance(x, float):
            return f"{x:.{nd}f}"
        return str(x)

    top_rows = "".join(
        f"<tr><td>{i+1}</td><td>{html_escape(str(t.get('entry', t.get('family','—'))))}</td>"
        f"<td>{html_escape(str(t.get('filter', '—')))}</td>"
        f"<td>{t.get('regime','—')}</td>"
        f"<td>{fmt(t.get('median_pnl', t.get('mean_pnl')))}</td>"
        f"<td>{fmt(t.get('mean_pnl'))}</td>"
        f"<td>{fmt(t.get('mean_wr'), 3)}</td>"
        f"<td>{fmt(t.get('mean_dd'))}</td>"
        f"<td>{t.get('n','—')}</td></tr>"
        for i, t in enumerate(tops[:15])
    )

    cmp_block = ""
    if prev_summary:
        cmp_block = f"""
  <h2>Сравнение с предыдущей сессией</h2>
  <p class="sub"><b>{html_escape(prev_name)}</b> → <b>{html_escape(sid)}</b> · verdict: <span class="verdict {ver}">{ver}</span>
  (политика §7C: для тренда PnL first)</p>
  <table class="stats">
    <thead><tr><th>метрика</th><th>prev</th><th>current</th><th>Δ</th></tr></thead>
    <tbody>
      <tr><td>best / top med PnL</td><td>{fmt(prev_agg.get('best_med_pnl'))}</td><td>{fmt(cur_agg.get('best_med_pnl'))}</td>
          <td>{fmt(cur_agg.get('best_med_pnl',0)-prev_agg.get('best_med_pnl',0))}</td></tr>
      <tr><td>median of top-20 med PnL</td><td>{fmt(prev_agg.get('med_pnl'))}</td><td>{fmt(cur_agg.get('med_pnl'))}</td>
          <td>{fmt(cur_agg.get('med_pnl',0)-prev_agg.get('med_pnl',0))}</td></tr>
      <tr><td>mean of top-20 mean PnL</td><td>{fmt(prev_agg.get('mean_pnl'))}</td><td>{fmt(cur_agg.get('mean_pnl'))}</td>
          <td>{fmt(cur_agg.get('mean_pnl',0)-prev_agg.get('mean_pnl',0))}</td></tr>
      <tr><td>mean WR (top-20)</td><td>{fmt(prev_agg.get('mean_wr'),3)}</td><td>{fmt(cur_agg.get('mean_wr'),3)}</td>
          <td>{fmt(cur_agg.get('mean_wr',0)-prev_agg.get('mean_wr',0),3)}</td></tr>
      <tr><td>mean DD (top-20)</td><td>{fmt(prev_agg.get('mean_dd'))}</td><td>{fmt(cur_agg.get('mean_dd'))}</td>
          <td>{fmt(cur_agg.get('mean_dd',0)-prev_agg.get('mean_dd',0))}</td></tr>
      <tr><td>signal acc (если есть)</td><td>{fmt(prev_metrics.get('accuracy'),4)}</td><td>{fmt(metrics.get('accuracy'),4)}</td>
          <td>{fmt((metrics.get('accuracy') or 0)-(prev_metrics.get('accuracy') or 0),4)}</td></tr>
      <tr><td>signal AUC</td><td>{fmt(prev_metrics.get('roc_auc'),4)}</td><td>{fmt(metrics.get('roc_auc'),4)}</td>
          <td>{fmt((metrics.get('roc_auc') or 0)-(prev_metrics.get('roc_auc') or 0),4)}</td></tr>
      <tr><td>n_rows / cells</td><td>{prev_summary.get('n_rows','—')} / {prev_summary.get('n_cells','—')}</td>
          <td>{summary.get('n_rows','—')} / {summary.get('n_cells','—')}</td><td>—</td></tr>
    </tbody>
  </table>
"""
    else:
        cmp_block = "<h2>Сравнение</h2><p class='sub'>Предыдущая сессия не указана (`--prev`).</p>"

    html = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"/>
<title>ANALYTICS — {html_escape(sid)}</title>
<style>
:root {{ --bg:#0f1419; --panel:#1a222c; --text:#e8eef4; --muted:#8b9aab; --line:#2a3542; }}
body {{ margin:0; font-family:IBM Plex Sans,Segoe UI,system-ui,sans-serif; background:radial-gradient(1000px 500px at 0% 0%,#1a2a3a,var(--bg));
  color:var(--text); padding:28px; }}
h1 {{ font-size:1.45rem; margin:0 0 6px; }} h2 {{ font-size:1.05rem; margin:28px 0 10px; }}
.sub {{ color:var(--muted); max-width:920px; line-height:1.45; }}
.grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:16px 0 22px; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }}
.card .k {{ color:var(--muted); font-size:.72rem; text-transform:uppercase; letter-spacing:.05em; }}
.card .v {{ font-size:1.25rem; font-weight:600; margin-top:4px; font-variant-numeric:tabular-nums; }}
table.stats {{ border-collapse:collapse; width:100%; background:var(--panel); border:1px solid var(--line); border-radius:10px; overflow:hidden; font-size:.85rem; }}
th,td {{ border:1px solid var(--line); padding:8px 10px; text-align:left; }}
th {{ background:#121820; color:var(--muted); font-weight:500; }}
td {{ font-variant-numeric:tabular-nums; }}
.verdict {{ padding:2px 8px; border-radius:4px; font-weight:600; }}
.verdict.better {{ background:#1e3d2c; color:#9ad67a; }}
.verdict.worse {{ background:#3d1e1e; color:#f0a0a0; }}
.verdict.mixed {{ background:#3d3420; color:#e6c87a; }}
.verdict.unchanged {{ background:#243040; color:#8b9aab; }}
</style></head><body>
<h1>Аналитика обучения — {html_escape(sid)}</h1>
<p class="sub">Сгенерировано {datetime.now(timezone.utc).isoformat()} · AGENTS.md §3.4 · полная аналитика + сравнение версий</p>

<div class="grid">
  <div class="card"><div class="k">Session</div><div class="v" style="font-size:1rem">{html_escape(sid)}</div></div>
  <div class="card"><div class="k">Prev</div><div class="v" style="font-size:1rem">{html_escape(prev_name)}</div></div>
  <div class="card"><div class="k">Verdict prev→cur</div><div class="v"><span class="verdict {ver.split()[0]}">{ver}</span></div></div>
  <div class="card"><div class="k">Rows / cells</div><div class="v">{summary.get('n_rows','—')} / {summary.get('n_cells','—')}</div></div>
</div>

<h2>Как прошло обучение</h2>
<ul class="sub">
  <li>Policy: {html_escape(str(summary.get('policy', meta.get('feature_schema_id', '—'))))}</li>
  <li>TFs: {html_escape(str(summary.get('bt_tfs') or meta.get('timeframes') or '—'))}</li>
  <li>max_period: {summary.get('max_period', '—')}</li>
  <li>Summary source: {html_escape(str(summary.get('_source', 'results/*_summary.json')))}</li>
  <li>Signal model: kind={html_escape(str(meta.get('model_kind','—')))} acc={fmt(metrics.get('accuracy'),4)} auc={fmt(metrics.get('roc_auc'),4)}</li>
</ul>

<h2>Показатели текущей версии (top-20 aggregate)</h2>
<div class="grid">
  <div class="card"><div class="k">Best med PnL</div><div class="v">{fmt(cur_agg.get('best_med_pnl'))}</div></div>
  <div class="card"><div class="k">Med of top med PnL</div><div class="v">{fmt(cur_agg.get('med_pnl'))}</div></div>
  <div class="card"><div class="k">Mean WR</div><div class="v">{fmt(cur_agg.get('mean_wr'),3)}</div></div>
  <div class="card"><div class="k">Mean DD</div><div class="v">{fmt(cur_agg.get('mean_dd'))}</div></div>
</div>

{cmp_block}

<h2>Топ связок (текущая сессия)</h2>
<table class="stats">
  <thead><tr><th>#</th><th>entry</th><th>filter</th><th>regime</th><th>med PnL</th><th>mean PnL</th><th>WR</th><th>DD</th><th>n</th></tr></thead>
  <tbody>{top_rows or '<tr><td colspan="9">нет топов</td></tr>'}</tbody>
</table>

<h2>Что дальше</h2>
<p class="sub">Shortlist топов → Desktop validate · следующая волна (C2/C3 или period expand) · параллель §7B индикаторы.</p>
</body></html>
"""
    out = session / "ANALYTICS.html"
    out.write_text(html, encoding="utf-8")
    print("wrote", out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, type=Path)
    ap.add_argument("--prev", type=Path, default=None)
    args = ap.parse_args()
    build(args.session.resolve(), args.prev.resolve() if args.prev else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
