#!/usr/bin/env python3
"""
C3b (потихоньку): lookback windows 1d…5y ONLY on C3 shortlist tops.
Not full cartesian — backlog §7B P1.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments" / "2026-08-21-c1-entry-filter"))
sys.path.insert(0, str(REPO / "experiments" / "2026-08-21-c2-composition"))

from run_c1 import apply_filter, backtest_atr, entry_catalog, entry_signals, filter_catalog  # noqa: E402
from run_c2 import comp_signals, composition_catalog  # noqa: E402

SESSION = REPO / "artifacts" / "agent_loop" / "sessions" / "2026-08-21-c3b-lookback-shortlist"
RESULTS = SESSION / "results"
# modest TF set for first lookback pass
TFS = ("15m", "1h", "1d")
# history windows in days (1d … 5y)
LOOKBACKS_DAYS = (1, 7, 30, 90, 180, 365, 730, 1095, 1825)

# Shortlist from C3 tops (labels)
SHORTLIST = [
    ("ema_rsi_ob_os|rsi21_ema14", "supertrend|14x3", "comp"),
    ("ema_rsi_ob_os|rsi14_ema14", "supertrend|14x3", "comp"),
    ("roc_momentum|20", "ema|50", "entry"),
    ("keltner|20", "ema|100", "entry"),
    ("donchian|10", "ema|100", "entry"),
]


def load_index() -> Dict[str, Dict[str, Path]]:
    raw = SESSION / "data" / "raw"
    idx = json.loads((raw / "index.json").read_text(encoding="utf-8"))
    out: Dict[str, Dict[str, Path]] = {}
    for sym, tfs in idx.items():
        bucket = {}
        for tf, path in tfs.items():
            if tf not in TFS:
                continue
            p = Path(path)
            if not p.exists():
                alt = raw / Path(path).name
                if alt.exists():
                    p = alt
                else:
                    continue
            bucket[tf] = p
        if bucket:
            out[sym] = bucket
    return out


def slice_lookback(df: pd.DataFrame, days: int) -> pd.DataFrame:
    if df.empty or "ts" not in df.columns:
        return df
    end = df["ts"].max()
    start = end - pd.Timedelta(days=days)
    out = df[df["ts"] >= start].copy()
    return out.reset_index(drop=True)


def resolve_pair(entry_label: str, filter_label: str, kind: str):
    if kind == "entry":
        espec = next(e for e in entry_catalog() if e.label == entry_label)
        fspec = next(f for f in filter_catalog() if f.label == filter_label)

        def sigs(df):
            long0, short0 = entry_signals(df, espec)
            return apply_filter(df, long0, short0, fspec)

        return sigs
    cspec = next(e for e in composition_catalog() if e.label == entry_label)
    fspec = next(f for f in filter_catalog() if f.label == filter_label)

    def sigs(df):
        long0, short0 = comp_signals(df, cspec)
        return apply_filter(df, long0, short0, fspec)

    return sigs


def run() -> List[dict]:
    RESULTS.mkdir(parents=True, exist_ok=True)
    index = load_index()
    rows = []
    t0 = time.time()
    total = 0
    print(f"C3b shortlist={len(SHORTLIST)} lookbacks={LOOKBACKS_DAYS} tfs={TFS} syms={len(index)}")
    for entry_label, filter_label, kind in SHORTLIST:
        make_sigs = resolve_pair(entry_label, filter_label, kind)
        for sym, tfs in index.items():
            for tf, path in tfs.items():
                df = pd.read_csv(path)
                if len(df) < 50:
                    continue
                df["ts"] = pd.to_datetime(df["ts"], utc=True)
                for days in LOOKBACKS_DAYS:
                    d = slice_lookback(df, days)
                    if len(d) < 40:
                        continue
                    try:
                        long_sig, short_sig = make_sigs(d)
                        pnl, dd, wr, n = backtest_atr(d, long_sig, short_sig)
                    except Exception as exc:  # noqa: BLE001
                        print("fail", entry_label, days, sym, tf, exc)
                        continue
                    rows.append(
                        {
                            "entry": entry_label,
                            "filter": filter_label,
                            "kind": kind,
                            "lookback_days": days,
                            "symbol": sym,
                            "timeframe": tf,
                            "bars": len(d),
                            "pnl": pnl,
                            "max_dd": dd,
                            "winrate": wr,
                            "trades": n,
                            "regime": "trend",
                        }
                    )
                    total += 1
                    if total % 200 == 0:
                        print(f"  {total} ({time.time()-t0:.0f}s)")
    path = RESULTS / "c3b_lookback_backtest.json"
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print("wrote", path, "rows", len(rows))
    return rows


def summarize(rows: List[dict]) -> dict:
    cell = defaultdict(list)
    for r in rows:
        if r["trades"] < 3:
            continue
        key = (r["entry"], r["filter"], r["lookback_days"])
        cell[key].append(r)
    ranking = []
    for (entry, filt, lb), xs in cell.items():
        med = float(np.median([x["pnl"] for x in xs]))
        ranking.append(
            {
                "entry": entry,
                "filter": filt,
                "lookback_days": lb,
                "regime": "trend",
                "n": len(xs),
                "median_pnl": med,
                "mean_pnl": float(np.mean([x["pnl"] for x in xs])),
                "mean_wr": float(np.mean([x["winrate"] for x in xs])),
                "mean_dd": float(np.mean([x["max_dd"] for x in xs])),
                "score": med,
            }
        )
    ranking.sort(key=lambda x: x["score"], reverse=True)
    # best lookback per entry×filter
    best_lb = {}
    for r in ranking:
        k = (r["entry"], r["filter"])
        if k not in best_lb or r["score"] > best_lb[k]["score"]:
            best_lb[k] = r
    summary = {
        "session": "2026-08-21-c3b-lookback-shortlist",
        "policy": "P1 gradual: lookback 1d…5y on C3 shortlist only; §7C PnL-first",
        "lookbacks_days": list(LOOKBACKS_DAYS),
        "bt_tfs": list(TFS),
        "shortlist": [{"entry": a, "filter": b, "kind": c} for a, b, c in SHORTLIST],
        "n_rows": len(rows),
        "n_cells": len(ranking),
        "top20_by_score": ranking[:20],
        "best_lookback_per_pair": list(best_lb.values()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (RESULTS / "c3b_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "c1_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (SESSION / "REPORT.md").write_text(
        "# C3b lookback shortlist\n\n" + json.dumps(summary["best_lookback_per_pair"], indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    SESSION.mkdir(parents=True, exist_ok=True)
    data = SESSION / "data"
    if not data.exists():
        data.symlink_to(
            REPO / "artifacts" / "agent_loop" / "sessions" / "2026-08-21-multi-indicator-wave" / "data",
            target_is_directory=True,
        )
    rows = run()
    summary = summarize(rows)
    print("BEST lookback per pair:")
    for r in summary["best_lookback_per_pair"]:
        print(f"  {r['entry']} + {r['filter']}: {r['lookback_days']}d med={r['median_pnl']:+.1f}")
    prev = REPO / "artifacts" / "agent_loop" / "sessions" / "2026-08-21-c3-all-tf"
    subprocess.check_call(
        [
            sys.executable,
            str(REPO / "scripts" / "build_training_analytics.py"),
            "--session",
            str(SESSION),
            "--prev",
            str(prev),
        ]
    )
    (SESSION / "notes.md").write_text(
        "C3b gradual P1: lookback sweep on shortlist only.\n"
        "Desktop: 20 .italgo in ai-train samples (P0).\n"
        "Next P2: Desktop engine runs + ingest.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
