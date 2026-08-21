#!/usr/bin/env python3
"""P3.8 / §7I: annotate C14 engines with buy&hold beat rate."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path("/Users/kreckeroff/Fintech (startup)/AI_algo")
sys.path.insert(0, str(ROOT / "src"))

from ai_algo.domain.buy_hold import evaluate_vs_buy_hold  # noqa: E402

C14 = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c14-futures-expand"
ITALGO = ROOT.parent / "it-algo-desktop/docs/work/scripting/samples/ai-train"
SESSION = ROOT / "artifacts/agent_loop/sessions/2026-08-21-p38-buyhold"
SYMBOLS = [
    "SBER", "GAZP", "LKOH", "ROSN", "GMKN", "NVTK", "TATN", "PLZL", "MGNT", "MTSS",
    "CNYRUBF", "GLDRUBF", "IMOEXF",
]
TFS = ["1d", "1h"]
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def side_mode_of(file_name: str) -> str:
    path = ITALGO / file_name
    # also check session scripts
    if not path.exists():
        path = C14 / "scripts" / file_name
    if path.exists():
        meta = (json.loads(path.read_text()).get("meta") or {})
        sm = meta.get("side_mode")
        if sm:
            return str(sm)
    # heuristic from filename
    if "-ls" in file_name or "_ls" in file_name or "long-short" in file_name:
        return "long_short"
    return "long_only"


def main() -> None:
    SESSION.mkdir(parents=True, exist_ok=True)
    (SESSION / "results").mkdir(exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for sym in SYMBOLS:
        for tf in TFS:
            bars_path = C14 / f"bars_{sym}_{tf}.json"
            eng = C14 / f"engine_{sym}_{tf}.jsonl"
            if not bars_path.exists() or not eng.exists():
                print("SKIP", sym, tf, flush=True)
                continue
            bars = json.loads(bars_path.read_text())
            for line in eng.read_text().splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                if not r.get("ok"):
                    continue
                fname = r.get("file") or ""
                # skip promoted copies
                if fname.startswith(("27p-", "28p-", "29p-", "30p-", "31p-", "32p-", "33p-", "34p-")):
                    continue
                sm = side_mode_of(fname)
                ev = evaluate_vs_buy_hold(
                    bars=bars,
                    trades=r.get("trades") or [],
                    side_mode=sm,
                    net_pnl=(r.get("stats") or {}).get("netPnl"),
                )
                rows.append(
                    {
                        "symbol": sym,
                        "timeframe": tf,
                        "file": fname,
                        **ev,
                        "stats_netPnl": (r.get("stats") or {}).get("netPnl"),
                        "stats_trades": (r.get("stats") or {}).get("totalTrades"),
                    }
                )
            print(sym, tf, "rows", sum(1 for x in rows if x["symbol"] == sym and x["timeframe"] == tf), flush=True)

    def rate(subset: List[dict], key: str = "beats_buy_hold") -> Optional[float]:
        vals = [x[key] for x in subset if x.get(key) is not None]
        if not vals:
            return None
        return sum(1 for v in vals if v) / len(vals)

    by_mode = defaultdict(list)
    by_sym = defaultdict(list)
    for r in rows:
        by_mode[r["side_mode"]].append(r)
        by_sym[r["symbol"]].append(r)

    summary = {
        "session": "2026-08-21-p38-buyhold",
        "source": str(C14),
        "n_rows": len(rows),
        "beat_rate_all": rate(rows),
        "beat_rate_long_only": rate(by_mode.get("long_only", [])),
        "beat_rate_long_short": rate(by_mode.get("long_short", [])),
        "pseudo_buy_hold_n": sum(1 for r in rows if r.get("pseudo_buy_hold")),
        "mean_edge_vs_bh": (
            sum(r["edge_vs_bh"] for r in rows if r.get("edge_vs_bh") is not None)
            / max(1, sum(1 for r in rows if r.get("edge_vs_bh") is not None))
        ),
        "by_side_mode": {
            m: {
                "n": len(xs),
                "beat_rate": rate(xs),
                "mean_edge": sum(x["edge_vs_bh"] for x in xs if x.get("edge_vs_bh") is not None)
                / max(1, sum(1 for x in xs if x.get("edge_vs_bh") is not None)),
                "pseudo_n": sum(1 for x in xs if x.get("pseudo_buy_hold")),
            }
            for m, xs in by_mode.items()
        },
        "by_symbol": {
            s: {
                "n": len(xs),
                "beat_rate": rate(xs),
                "mean_edge": sum(x["edge_vs_bh"] for x in xs if x.get("edge_vs_bh") is not None)
                / max(1, sum(1 for x in xs if x.get("edge_vs_bh") is not None)),
            }
            for s, xs in by_sym.items()
        },
        "rule": "long_only: long_trades_pnl > BH; long_short: netPnl > BH (§7I)",
    }

    (SESSION / "results" / "per_script_buyhold.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    )
    (SESSION / "results" / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    (SESSION / "notes.md").write_text(
        "P3.8/§7I: strategy must beat buy&hold on the same chart window. "
        "LO: long trades > BH; LS: net > BH; flag pseudo_buy_hold for near-BH few trades.\n"
    )

    # HTML
    mode_rows = "".join(
        f"<tr><td>{m}</td><td>{v['n']}</td><td>{(v['beat_rate'] or 0)*100:.1f}%</td>"
        f"<td>{v['mean_edge']:.1f}</td><td>{v['pseudo_n']}</td></tr>"
        for m, v in summary["by_side_mode"].items()
    )
    sym_rows = "".join(
        f"<tr><td>{s}</td><td>{v['n']}</td><td>{(v['beat_rate'] or 0)*100:.1f}%</td>"
        f"<td>{v['mean_edge']:.1f}</td></tr>"
        for s, v in sorted(summary["by_symbol"].items(), key=lambda x: -((x[1]["beat_rate"] or 0)))
    )
    html = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"/><title>P3.8 buy&hold</title>
<style>
body{{font-family:IBM Plex Sans,system-ui,sans-serif;background:#0f1419;color:#e8eef4;padding:28px}}
table{{border-collapse:collapse;width:100%;background:#1a222c;font-size:.85rem;margin:10px 0}}
th,td{{border:1px solid #2a3542;padding:8px;text-align:right}} th,td:first-child{{text-align:left;color:#8b9aab}}
.card{{display:inline-block;background:#1a222c;border:1px solid #2a3542;border-radius:10px;padding:12px 16px;margin:6px 8px 6px 0}}
.sub{{color:#8b9aab}}
</style></head><body>
<h1>P3.8 — бить buy&amp;hold (§7I)</h1>
<p class="sub">C14 engines 1d+1h · LO: long PnL &gt; BH · LS: net PnL &gt; BH · {NOW}</p>
<div class="card">rows<br><b>{summary['n_rows']}</b></div>
<div class="card">beat rate all<br><b>{(summary['beat_rate_all'] or 0)*100:.1f}%</b></div>
<div class="card">LO beat<br><b>{(summary['beat_rate_long_only'] or 0)*100:.1f}%</b></div>
<div class="card">LS beat<br><b>{(summary['beat_rate_long_short'] or 0)*100:.1f}%</b></div>
<div class="card">pseudo B&amp;H<br><b>{summary['pseudo_buy_hold_n']}</b></div>
<h2>По side_mode</h2>
<table><thead><tr><th>mode</th><th>n</th><th>beat %</th><th>mean edge</th><th>pseudo</th></tr></thead>
<tbody>{mode_rows}</tbody></table>
<h2>По symbol</h2>
<table><thead><tr><th>symbol</th><th>n</th><th>beat %</th><th>mean edge</th></tr></thead>
<tbody>{sym_rows}</tbody></table>
</body></html>
"""
    (SESSION / "ANALYTICS.html").write_text(html)
    (SESSION / "REPORT.md").write_text(
        "\n".join(
            [
                "# P3.8 / §7I beat buy&hold",
                "",
                f"- Rows: {summary['n_rows']}",
                f"- Beat rate all: {(summary['beat_rate_all'] or 0)*100:.1f}%",
                f"- Long-only: {(summary['beat_rate_long_only'] or 0)*100:.1f}%",
                f"- Long-short: {(summary['beat_rate_long_short'] or 0)*100:.1f}%",
                f"- Pseudo B&H flags: {summary['pseudo_buy_hold_n']}",
                f"- Mean edge vs BH: {summary['mean_edge_vs_bh']:.2f}",
            ]
        )
        + "\n"
    )
    print(
        "SUMMARY",
        "beat_all",
        summary["beat_rate_all"],
        "LO",
        summary["beat_rate_long_only"],
        "LS",
        summary["beat_rate_long_short"],
        "pseudo",
        summary["pseudo_buy_hold_n"],
    )


if __name__ == "__main__":
    main()
