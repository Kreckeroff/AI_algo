#!/usr/bin/env python3
"""C3: ALL timeframes × ALL whitelist entry+composition × ALL filters. ANALYTICS vs C2."""
from __future__ import annotations

import json
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

from run_c1 import (  # noqa: E402
    MAX_PERIOD,
    TREND_FAMILIES,
    apply_filter,
    backtest_atr,
    entry_catalog,
    entry_signals,
    filter_catalog,
)
from run_c2 import (  # noqa: E402
    CompEntry,
    comp_signals,
    composition_catalog,
)

SESSION = REPO / "artifacts" / "agent_loop" / "sessions" / "2026-08-21-c3-all-tf"
RESULTS = SESSION / "results"
# All TFs present in wave-2 index
ALL_TFS = ("1m", "5m", "10m", "15m", "30m", "1h", "1d", "1w", "1M")


def load_index_all() -> Dict[str, Dict[str, Path]]:
    raw = SESSION / "data" / "raw"
    idx = json.loads((raw / "index.json").read_text(encoding="utf-8"))
    out: Dict[str, Dict[str, Path]] = {}
    for sym, tfs in idx.items():
        bucket = {}
        for tf, path in tfs.items():
            if tf not in ALL_TFS:
                continue
            p = Path(path)
            if not p.exists():
                alt = raw / Path(path).name
                if not alt.exists():
                    continue
                p = alt
            bucket[tf] = p
        if bucket:
            out[sym] = bucket
    return out


def run_grid(index: Dict[str, Dict[str, Path]]) -> Tuple[List[dict], dict]:
    RESULTS.mkdir(parents=True, exist_ok=True)
    entries_c1 = entry_catalog()
    entries_c2 = composition_catalog()
    filters = filter_catalog()
    rows: List[dict] = []
    covered_tfs = set()
    missing_pairs = []  # symbol lacking some tf
    total = 0
    t0 = time.time()
    print(
        f"C3 ALL-TF entries_c1={len(entries_c1)} comp={len(entries_c2)} "
        f"filters={len(filters)} tfs={ALL_TFS} syms={len(index)}"
    )
    approx = (len(entries_c1) + len(entries_c2)) * len(filters) * len(ALL_TFS) * len(index)
    print(f"approx max combos={approx}")

    for sym, tfs in index.items():
        missing = [tf for tf in ALL_TFS if tf not in tfs]
        if missing:
            missing_pairs.append({"symbol": sym, "missing_tfs": missing})
        for tf, path in tfs.items():
            covered_tfs.add(tf)
            df = pd.read_csv(path)
            if len(df) < 80 or "close" not in df.columns:
                continue
            df["ts"] = pd.to_datetime(df["ts"], utc=True)

            # C1-style entries
            for espec in entries_c1:
                try:
                    long0, short0 = entry_signals(df, espec)
                except Exception as exc:  # noqa: BLE001
                    print("entry fail", espec.label, exc)
                    continue
                for fspec in filters:
                    try:
                        long_sig, short_sig = apply_filter(df, long0, short0, fspec)
                        pnl, dd, wr, n = backtest_atr(df, long_sig, short_sig)
                    except Exception as exc:  # noqa: BLE001
                        continue
                    rows.append(
                        {
                            "entry": espec.label,
                            "entry_family": espec.family,
                            "entry_params": espec.params,
                            "filter": fspec.label,
                            "filter_kind": fspec.kind,
                            "filter_params": fspec.params,
                            "regime": "trend" if espec.family in TREND_FAMILIES else "other",
                            "source": "c1_entry",
                            "symbol": sym,
                            "timeframe": tf,
                            "pnl": pnl,
                            "max_dd": dd,
                            "winrate": wr,
                            "trades": n,
                        }
                    )
                    total += 1
                    if total % 500 == 0:
                        print(f"  {total} ({time.time()-t0:.0f}s) {espec.label}+{fspec.label} {sym} {tf}")

            # C2 composition
            for cspec in entries_c2:
                try:
                    long0, short0 = comp_signals(df, cspec)
                except Exception as exc:  # noqa: BLE001
                    print("comp fail", cspec.label, exc)
                    continue
                for fspec in filters:
                    try:
                        long_sig, short_sig = apply_filter(df, long0, short0, fspec)
                        pnl, dd, wr, n = backtest_atr(df, long_sig, short_sig)
                    except Exception:
                        continue
                    rows.append(
                        {
                            "entry": cspec.label,
                            "entry_family": cspec.family,
                            "entry_params": cspec.params,
                            "filter": fspec.label,
                            "filter_kind": fspec.kind,
                            "filter_params": fspec.params,
                            "regime": getattr(cspec, "regime", "trend"),
                            "source": "c2_composition",
                            "symbol": sym,
                            "timeframe": tf,
                            "pnl": pnl,
                            "max_dd": dd,
                            "winrate": wr,
                            "trades": n,
                        }
                    )
                    total += 1
                    if total % 500 == 0:
                        print(f"  {total} ({time.time()-t0:.0f}s) {cspec.label}+{fspec.label} {sym} {tf}")

    path = RESULTS / "c3_grid_backtest.json"
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    coverage = {
        "target_tfs": list(ALL_TFS),
        "covered_tfs": sorted(covered_tfs),
        "missing_tfs_global": [t for t in ALL_TFS if t not in covered_tfs],
        "per_symbol_missing": missing_pairs,
        "n_entries_c1": len(entries_c1),
        "n_entries_comp": len(entries_c2),
        "n_filters": len(filters),
        "n_rows": len(rows),
        "elapsed_s": time.time() - t0,
    }
    (RESULTS / "c3_coverage.json").write_text(json.dumps(coverage, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path} rows={len(rows)} covered_tfs={coverage['covered_tfs']}")
    return rows, coverage


def summarize(rows: List[dict], coverage: dict) -> dict:
    cell: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    by_tf: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        if r["trades"] < 5:
            continue
        cell[(r["entry"], r["filter"])].append(r)
        by_tf[r["timeframe"]].append(r["pnl"])

    ranking = []
    for (entry, filt), xs in cell.items():
        regime = xs[0].get("regime", "trend")
        med_pnl = float(np.median([x["pnl"] for x in xs]))
        mean_pnl = float(np.mean([x["pnl"] for x in xs]))
        mean_wr = float(np.mean([x["winrate"] for x in xs]))
        mean_dd = float(np.mean([x["max_dd"] for x in xs]))
        score = med_pnl if regime == "trend" else med_pnl + 50.0 * (mean_wr - 0.45)
        ranking.append(
            {
                "entry": entry,
                "filter": filt,
                "regime": regime,
                "source": xs[0].get("source"),
                "n": len(xs),
                "mean_pnl": mean_pnl,
                "median_pnl": med_pnl,
                "mean_wr": mean_wr,
                "mean_dd": mean_dd,
                "score": score,
            }
        )
    ranking.sort(key=lambda x: x["score"], reverse=True)

    tf_stats = {
        tf: {
            "n": len(v),
            "median_pnl": float(np.median(v)),
            "mean_pnl": float(np.mean(v)),
        }
        for tf, v in sorted(by_tf.items())
    }

    summary = {
        "session": "2026-08-21-c3-all-tf",
        "policy": "C3 ALL TFs + C1 entries + C2 composition × all filters; §7C PnL-first; full linkage goal §7A",
        "max_period": MAX_PERIOD,
        "bt_tfs": coverage["covered_tfs"],
        "target_tfs": coverage["target_tfs"],
        "coverage": coverage,
        "tf_stats": tf_stats,
        "n_rows": len(rows),
        "n_cells": len(ranking),
        "top20_by_score": ranking[:20],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (RESULTS / "c3_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    # alias for analytics helper
    (RESULTS / "c1_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (SESSION / "REPORT.md").write_text(
        "# C3 all-TF\n\n"
        f"covered TFs: {coverage['covered_tfs']}\n"
        f"missing global: {coverage['missing_tfs_global']}\n"
        f"rows: {len(rows)}\n\n"
        + json.dumps(ranking[:10], indent=2)
        + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    SESSION.mkdir(parents=True, exist_ok=True)
    index = load_index_all()
    print("symbols", sorted(index))
    rows, coverage = run_grid(index)
    summary = summarize(rows, coverage)
    print("TOP5:")
    for r in summary["top20_by_score"][:5]:
        print(f"  {r['entry']} + {r['filter']}: med={r['median_pnl']:+.1f} wr={r['mean_wr']:.2f} [{r.get('source')}]")
    prev = REPO / "artifacts" / "agent_loop" / "sessions" / "2026-08-21-c2-composition"
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
        "C3: all available TFs + C1 entries + C2 composition × all filters.\n"
        f"Covered: {coverage['covered_tfs']}\n"
        f"Per-symbol gaps: see results/c3_coverage.json\n"
        "Goal: full whitelist coverage (§7A). ANALYTICS vs C2.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
