#!/usr/bin/env python3
"""C2: composition entries EMA(RSI)/SMA(RSI)/… × filters. Then ANALYTICS vs C1."""
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

# Reuse C1 helpers
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments" / "2026-08-21-c1-entry-filter"))
from run_c1 import (  # noqa: E402
    BT_TFS,
    MAX_BT_BARS,
    MAX_PERIOD,
    TREND_FAMILIES,
    FilterSpec,
    apply_filter,
    atr,
    backtest_atr,
    clamp_period,
    ema,
    filter_catalog,
    load_index,
    rsi,
    sma,
)

SESSION = REPO / "artifacts" / "agent_loop" / "sessions" / "2026-08-21-c2-composition"
RESULTS = SESSION / "results"
# point data symlink like C1
RAW_LINK = SESSION / "data"


@dataclass(frozen=True)
class CompEntry:
    family: str
    params: Dict
    label: str
    regime: str = "trend"


def composition_catalog() -> List[CompEntry]:
    """Composition whitelist — periods ∈ [1,200]."""
    out: List[CompEntry] = []
    for rsi_p in (7, 14, 21):
        for ma_p in (3, 5, 8, 14):
            out.append(
                CompEntry(
                    "ema_rsi_cross",
                    {"rsi_period": rsi_p, "ema_period": ma_p},
                    f"ema_rsi_cross|rsi{rsi_p}_ema{ma_p}",
                )
            )
            out.append(
                CompEntry(
                    "sma_rsi_cross",
                    {"rsi_period": rsi_p, "sma_period": ma_p},
                    f"sma_rsi_cross|rsi{rsi_p}_sma{ma_p}",
                )
            )
    for rsi_p in (7, 14, 21):
        out.append(CompEntry("rsi_hl2_ob_os", {"rsi_period": rsi_p}, f"rsi_hl2_ob_os|{rsi_p}", "other"))
    for rsi_p in (14, 21):
        for ema_p in (5, 14):
            out.append(
                CompEntry(
                    "ema_rsi_ob_os",
                    {"rsi_period": rsi_p, "ema_period": ema_p},
                    f"ema_rsi_ob_os|rsi{rsi_p}_ema{ema_p}",
                    "other",
                )
            )
    return out


def hl2(df: pd.DataFrame) -> pd.Series:
    return (df["high"] + df["low"]) / 2


def comp_signals(df: pd.DataFrame, spec: CompEntry) -> Tuple[pd.Series, pd.Series]:
    p, fam = spec.params, spec.family
    if fam == "ema_rsi_cross":
        r = rsi(df["close"], int(p["rsi_period"]))
        e = ema(r, int(p["ema_period"]))
        ep, rp = e.shift(1), pd.Series(50.0, index=df.index)
        # cross of EMA(RSI) through 50
        long_sig = (ep <= 50) & (e > 50)
        short_sig = (ep >= 50) & (e < 50)
    elif fam == "sma_rsi_cross":
        r = rsi(df["close"], int(p["rsi_period"]))
        s = sma(r, int(p["sma_period"]))
        sp = s.shift(1)
        long_sig = (sp <= 50) & (s > 50)
        short_sig = (sp >= 50) & (s < 50)
    elif fam == "rsi_hl2_ob_os":
        r = rsi(hl2(df), int(p["rsi_period"]))
        rp = r.shift(1)
        long_sig = (rp < 30) & (r >= 30)
        short_sig = (rp > 70) & (r <= 70)
    elif fam == "ema_rsi_ob_os":
        r = rsi(df["close"], int(p["rsi_period"]))
        e = ema(r, int(p["ema_period"]))
        ep = e.shift(1)
        long_sig = (ep < 30) & (e >= 30)
        short_sig = (ep > 70) & (e <= 70)
    else:
        raise ValueError(fam)
    return long_sig.fillna(False), short_sig.fillna(False)


def run_grid(index: Dict[str, Dict[str, Path]]) -> List[dict]:
    RESULTS.mkdir(parents=True, exist_ok=True)
    entries = composition_catalog()
    # fewer filters for C2 budget — still include ST + EMA periods
    filters = [f for f in filter_catalog() if f.kind in ("none", "ema", "supertrend", "adx", "donchian_mid")]
    # drop some ema periods keep 20,50,100,200 and ST variants
    rows: List[dict] = []
    total = 0
    t0 = time.time()
    print(f"C2 composition entries={len(entries)} filters={len(filters)} tfs={BT_TFS} syms={len(index)}")
    for sym, tfs in index.items():
        for tf, path in tfs.items():
            df = pd.read_csv(path)
            if len(df) < 120:
                continue
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
            for espec in entries:
                try:
                    long0, short0 = comp_signals(df, espec)
                except Exception as exc:  # noqa: BLE001
                    print("entry fail", espec.label, exc)
                    continue
                for fspec in filters:
                    try:
                        long_sig, short_sig = apply_filter(df, long0, short0, fspec)
                        pnl, dd, wr, n = backtest_atr(df, long_sig, short_sig)
                    except Exception as exc:  # noqa: BLE001
                        print("bt fail", espec.label, fspec.label, exc)
                        continue
                    rows.append(
                        {
                            "entry": espec.label,
                            "entry_family": espec.family,
                            "entry_params": espec.params,
                            "filter": fspec.label,
                            "filter_kind": fspec.kind,
                            "filter_params": fspec.params,
                            "regime": espec.regime if espec.regime == "other" else (
                                "trend" if espec.family.startswith("ema_rsi_cross") or espec.family.startswith("sma_rsi") else espec.regime
                            ),
                            "symbol": sym,
                            "timeframe": tf,
                            "pnl": pnl,
                            "max_dd": dd,
                            "winrate": wr,
                            "trades": n,
                        }
                    )
                    total += 1
                    if total % 400 == 0:
                        print(f"  {total} ({time.time()-t0:.0f}s) {espec.label}+{fspec.label} {sym} {tf}")
    path = RESULTS / "c2_grid_backtest.json"
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path} rows={len(rows)}")
    return rows


def summarize(rows: List[dict]) -> dict:
    from collections import defaultdict

    cell: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for r in rows:
        if r["trades"] < 5:
            continue
        cell[(r["entry"], r["filter"])].append(r)
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
                "n": len(xs),
                "mean_pnl": mean_pnl,
                "median_pnl": med_pnl,
                "mean_wr": mean_wr,
                "mean_dd": mean_dd,
                "score": score,
            }
        )
    ranking.sort(key=lambda x: x["score"], reverse=True)
    summary = {
        "session": "2026-08-21-c2-composition",
        "policy": "C2 composition EMA(RSI)/SMA(RSI)/RSI(HL2) × filters; §7C PnL-first for trend-like",
        "max_period": MAX_PERIOD,
        "bt_tfs": list(BT_TFS),
        "n_rows": len(rows),
        "n_cells": len(ranking),
        "top20_by_score": ranking[:20],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (RESULTS / "c2_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (SESSION / "REPORT.md").write_text(
        "# C2 composition\n\n" + json.dumps(summary["top20_by_score"][:10], indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def ensure_data_link() -> None:
    SESSION.mkdir(parents=True, exist_ok=True)
    target = REPO / "artifacts" / "agent_loop" / "sessions" / "2026-08-21-multi-indicator-wave" / "data"
    if RAW_LINK.exists() or RAW_LINK.is_symlink():
        return
    RAW_LINK.symlink_to(target, target_is_directory=True)


def main() -> int:
    ensure_data_link()
    # patch load_index RAW path: run_c1 uses its SESSION — override by copying index loader locally
    # Fix: load_index reads C1 session RAW. Re-implement quick load from our symlink.
    raw = SESSION / "data" / "raw"
    idx = json.loads((raw / "index.json").read_text(encoding="utf-8"))
    index: Dict[str, Dict[str, Path]] = {}
    for sym, tfs in idx.items():
        bucket = {}
        for tf, path in tfs.items():
            if tf not in BT_TFS:
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
            index[sym] = bucket
    print("=== C2 grid ===")
    rows = run_grid(index)
    print("=== summarize ===")
    summary = summarize(rows)
    for r in summary["top20_by_score"][:5]:
        print(f"  {r['entry']} + {r['filter']}: med={r['median_pnl']:+.1f} wr={r['mean_wr']:.2f}")
    print("=== ANALYTICS vs C1 ===")
    prev = REPO / "artifacts" / "agent_loop" / "sessions" / "2026-08-21-c1-entry-filter"
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
    # also backfill C1 analytics vs wave2
    w2 = REPO / "artifacts" / "agent_loop" / "sessions" / "2026-08-21-multi-indicator-wave"
    if not (prev / "ANALYTICS.html").exists():
        subprocess.check_call(
            [
                sys.executable,
                str(REPO / "scripts" / "build_training_analytics.py"),
                "--session",
                str(prev),
                "--prev",
                str(w2),
            ]
        )
    (SESSION / "notes.md").write_text(
        "C2 composition done. ANALYTICS.html vs C1 required by AGENTS.md §3.4.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
