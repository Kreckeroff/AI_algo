#!/usr/bin/env python3
"""P3.7 / §7H: annotate C14 equity engine runs with dividend cash-adjust.

Uses cached Smart-Lab calendar. For each equity×TF engine jsonl (default 1d+1h):
- detect trades that cross ex_effect_date
- short: pnl − div; long: pnl + div
- compare raw vs adjusted; write ANALYTICS + datasets

Futures skipped (no div gap).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path("/Users/kreckeroff/Fintech (startup)/AI_algo")
sys.path.insert(0, str(ROOT / "src"))

from ai_algo.domain.dividends import (  # noqa: E402
    adjust_trades,
    events_in_window,
    load_dividend_cache,
)

C14 = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c14-futures-expand"
SESSION = ROOT / "artifacts/agent_loop/sessions/2026-08-21-p37-divgap"
CACHE = ROOT / "data" / "dividends" / "moex_equities.json"
EQUITIES = ["SBER", "GAZP", "LKOH", "ROSN", "GMKN", "NVTK", "TATN", "PLZL", "MGNT", "MTSS"]
TFS = ["1d", "1h"]
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    SESSION.mkdir(parents=True, exist_ok=True)
    (SESSION / "results").mkdir(exist_ok=True)

    cal = load_dividend_cache(CACHE)
    if not cal:
        raise SystemExit(f"missing dividend cache: {CACHE} — run scripts/fetch_moex_dividends.py")

    per_script: List[Dict[str, Any]] = []
    per_symbol: Dict[str, Dict[str, Any]] = {}
    short_cross_examples: List[Dict[str, Any]] = []

    for sym in EQUITIES:
        events_all = cal.get(sym) or []
        sym_agg = {
            "symbol": sym,
            "n_div_events_cache": len(events_all),
            "n_scripts": 0,
            "n_trades": 0,
            "n_short_crossed": 0,
            "pnl_raw": 0.0,
            "pnl_div_adjusted": 0.0,
            "by_tf": {},
        }
        for tf in TFS:
            eng = C14 / f"engine_{sym}_{tf}.jsonl"
            if not eng.exists():
                print("SKIP missing engine", eng.name, flush=True)
                continue
            # chart window from bars if present
            bars_path = C14 / f"bars_{sym}_{tf}.json"
            from_ts = to_ts = None
            if bars_path.exists():
                bars = json.loads(bars_path.read_text())
                if bars:
                    from_ts = int(bars[0]["time"])
                    to_ts = int(bars[-1]["time"])
            events = events_in_window(events_all, from_ts, to_ts)
            tf_stats = {
                "n_div_in_window": len(events),
                "div_dates": [e["ex_effect_date"] for e in events],
                "n_scripts": 0,
                "n_short_crossed": 0,
                "delta_from_div": 0.0,
            }
            for line in eng.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if not row.get("ok"):
                    continue
                trades = row.get("trades") or []
                if not trades:
                    continue
                adj_trades, summary = adjust_trades(trades, events)
                short_pay = sum(
                    abs(t["div_cash_adjust"])
                    for t in adj_trades
                    if t.get("crossed_ex_div") and (t.get("side") or "").lower() in ("sell", "short")
                )
                long_recv = sum(
                    t["div_cash_adjust"]
                    for t in adj_trades
                    if t.get("crossed_ex_div") and (t.get("side") or "").lower() in ("buy", "long")
                )
                per_script.append(
                    {
                        "symbol": sym,
                        "timeframe": tf,
                        "file": row.get("file"),
                        "side_mode": None,
                        "chart_from_ts": from_ts,
                        "chart_to_ts": to_ts,
                        "div_events_in_window": len(events),
                        **summary,
                        "short_div_paid": short_pay,
                        "long_div_received": long_recv,
                        "stats_raw_netPnl": (row.get("stats") or {}).get("netPnl"),
                    }
                )
                sym_agg["n_scripts"] += 1
                sym_agg["n_trades"] += int(summary["n_trades"])
                sym_agg["n_short_crossed"] += int(summary["n_short_crossed"])
                sym_agg["pnl_raw"] += summary["pnl_raw"]
                sym_agg["pnl_div_adjusted"] += summary["pnl_div_adjusted"]
                tf_stats["n_scripts"] += 1
                tf_stats["n_short_crossed"] += int(summary["n_short_crossed"])
                tf_stats["delta_from_div"] += summary["delta_from_div"]

                if summary["n_short_crossed"] > 0 and len(short_cross_examples) < 40:
                    for t in adj_trades:
                        if t.get("crossed_ex_div") and (t.get("side") or "").lower() == "sell":
                            short_cross_examples.append(
                                {
                                    "symbol": sym,
                                    "timeframe": tf,
                                    "file": row.get("file"),
                                    "entryTime": t.get("entryTime"),
                                    "exitTime": t.get("exitTime"),
                                    "pnl_raw": t.get("pnl_raw"),
                                    "pnl_div_adjusted": t.get("pnl_div_adjusted"),
                                    "div_cash_adjust": t.get("div_cash_adjust"),
                                    "div_events": t.get("div_events"),
                                }
                            )
                            if len(short_cross_examples) >= 40:
                                break
            sym_agg["by_tf"][tf] = tf_stats
            print(
                sym,
                tf,
                "div_in_window",
                len(events),
                "scripts",
                tf_stats["n_scripts"],
                "short_cross",
                tf_stats["n_short_crossed"],
                "Δdiv",
                round(tf_stats["delta_from_div"], 2),
                flush=True,
            )
        sym_agg["delta_from_div"] = sym_agg["pnl_div_adjusted"] - sym_agg["pnl_raw"]
        per_symbol[sym] = sym_agg

    # LS scripts impact: files with -ls or side from name
    ls_delta = [
        p
        for p in per_script
        if "ls" in (p.get("file") or "").lower() or "-ls." in (p.get("file") or "")
    ]
    summary = {
        "session": "2026-08-21-p37-divgap",
        "source_engine": str(C14),
        "dividend_cache": str(CACHE),
        "equities": EQUITIES,
        "timeframes": TFS,
        "n_script_rows": len(per_script),
        "total_short_crossed": sum(int(p["n_short_crossed"]) for p in per_script),
        "total_delta_from_div": sum(p["delta_from_div"] for p in per_script),
        "total_short_div_paid": sum(p.get("short_div_paid", 0) for p in per_script),
        "total_long_div_received": sum(p.get("long_div_received", 0) for p in per_script),
        "ls_rows": len(ls_delta),
        "ls_delta_from_div": sum(p["delta_from_div"] for p in ls_delta),
        "ls_short_div_paid": sum(p.get("short_div_paid", 0) for p in ls_delta),
        "per_symbol": per_symbol,
        "fetched_note": "Smart-Lab cache; short pays div when held through last_buy/ex_effect",
    }

    (SESSION / "results" / "per_script_div_adjust.json").write_text(
        json.dumps(per_script, ensure_ascii=False, indent=2) + "\n"
    )
    (SESSION / "results" / "short_cross_examples.json").write_text(
        json.dumps(short_cross_examples, ensure_ascii=False, indent=2) + "\n"
    )
    (SESSION / "results" / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    (SESSION / "notes.md").write_text(
        "P3.7/§7H: Smart-Lab dividend calendar × C14 equity engines (1d+1h). "
        "Short through last_buy pays dividend; long receives. Futures untouched.\n"
    )

    # compact HTML
    rows_html = "".join(
        f"<tr><td>{s}</td><td>{v['n_div_events_cache']}</td>"
        f"<td>{v['n_short_crossed']}</td>"
        f"<td>{v['pnl_raw']:.1f}</td><td>{v['pnl_div_adjusted']:.1f}</td>"
        f"<td>{v['delta_from_div']:.1f}</td></tr>"
        for s, v in per_symbol.items()
    )
    html = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"/><title>P3.7 divgap</title>
<style>
body{{font-family:IBM Plex Sans,system-ui,sans-serif;background:#0f1419;color:#e8eef4;padding:28px}}
table{{border-collapse:collapse;width:100%;background:#1a222c;font-size:.85rem}}
th,td{{border:1px solid #2a3542;padding:8px;text-align:right}} th{{text-align:left;color:#8b9aab}}
td:first-child,th:first-child{{text-align:left}} .sub{{color:#8b9aab}}
.card{{display:inline-block;background:#1a222c;border:1px solid #2a3542;border-radius:10px;padding:12px 16px;margin:6px 8px 6px 0}}
</style></head><body>
<h1>P3.7 — дивгэп на периоде графика</h1>
<p class="sub">Календарь Smart-Lab → кэш · join к C14 engine equities 1d+1h · short платит дивиденд</p>
<div class="card">script rows<br><b>{len(per_script)}</b></div>
<div class="card">short×ex-div<br><b>{summary['total_short_crossed']}</b></div>
<div class="card">short paid (₽)<br><b>{summary['total_short_div_paid']:.0f}</b></div>
<div class="card">long received (₽)<br><b>{summary['total_long_div_received']:.0f}</b></div>
<div class="card">LS short paid<br><b>{summary['ls_short_div_paid']:.0f}</b></div>
<h2>По тикеру (сумма по скриптам 1d+1h)</h2>
<table><thead><tr><th>symbol</th><th>div events</th><th>short crossed</th><th>PnL raw</th><th>PnL adj</th><th>Δ div</th></tr></thead>
<tbody>{rows_html}</tbody></table>
<p class="sub">generated {NOW} · cache {CACHE.name}</p>
</body></html>
"""
    (SESSION / "ANALYTICS.html").write_text(html)
    (SESSION / "REPORT.md").write_text(
        "\n".join(
            [
                "# P3.7 / §7H dividend gap annotation",
                "",
                f"- Cache: `{CACHE}`",
                f"- Engine source: C14 equities × {', '.join(TFS)}",
                f"- Script rows: {len(per_script)}",
                f"- Short trades crossing ex-div: {summary['total_short_crossed']}",
                f"- Total Δ PnL from cash adjust: {summary['total_delta_from_div']:.2f}",
                f"- LS scripts Δ: {summary['ls_delta_from_div']:.2f}",
                "",
                "Rule: short held through `last_buy_date`/`ex_effect_date` pays `dividend_rub`×qty; long receives.",
            ]
        )
        + "\n"
    )
    print("SUMMARY short_crossed", summary["total_short_crossed"], "delta", summary["total_delta_from_div"])
    print("wrote", SESSION)


if __name__ == "__main__":
    main()
