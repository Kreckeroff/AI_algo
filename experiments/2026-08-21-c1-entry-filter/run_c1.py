#!/usr/bin/env python3
"""C1: Entry × Filter × period grids (periods ∈ [1,200]). Reuses wave-2 OHLCV."""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
SESSION = REPO / "artifacts" / "agent_loop" / "sessions" / "2026-08-21-c1-entry-filter"
RAW = SESSION / "data" / "raw"
RESULTS = SESSION / "results"
MAX_PERIOD, MIN_PERIOD = 200, 1
MAX_BT_BARS = 5000
BT_TFS = ("15m", "1h", "1d")

# Trend-like families: rank primarily by PnL (§7C)
TREND_FAMILIES = {
    "supertrend_rsi",
    "ema_cross",
    "macd_cross",
    "adx_di",
    "donchian",
    "keltner",
    "dual_sma_rsi",
    "roc_momentum",
}


def clamp_period(p: int) -> int:
    if not (MIN_PERIOD <= p <= MAX_PERIOD):
        raise ValueError(f"period {p} outside [{MIN_PERIOD},{MAX_PERIOD}]")
    return p


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    period = clamp_period(period)
    delta = series.diff()
    up, down = delta.clip(lower=0), -delta.clip(upper=0)
    ma_up = up.ewm(alpha=1 / period, adjust=False).mean()
    ma_down = down.ewm(alpha=1 / period, adjust=False).mean()
    rs = ma_up / ma_down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    period = clamp_period(period)
    prev = df["close"].shift(1)
    tr = pd.concat(
        [(df["high"] - df["low"]).abs(), (df["high"] - prev).abs(), (df["low"] - prev).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=clamp_period(period), adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(clamp_period(period)).mean()


def supertrend(df: pd.DataFrame, period: int = 10, mult: float = 3.0) -> Tuple[pd.Series, pd.Series]:
    period = clamp_period(period)
    atr_v = atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2
    upper = (hl2 + mult * atr_v).to_numpy()
    lower = (hl2 - mult * atr_v).to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    st = np.zeros(n)
    direction = np.ones(n)
    for i in range(n):
        if i == 0:
            st[i] = lower[i]
            continue
        if close[i - 1] > st[i - 1]:
            direction[i] = 1
        elif close[i - 1] < st[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]
        if direction[i] == 1:
            st[i] = max(lower[i], st[i - 1]) if direction[i - 1] == 1 else lower[i]
        else:
            st[i] = min(upper[i], st[i - 1]) if direction[i - 1] == -1 else upper[i]
    return pd.Series(st, index=df.index), pd.Series(direction, index=df.index)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, sig: int = 9) -> Tuple[pd.Series, pd.Series]:
    line = ema(series, fast) - ema(series, slow)
    return line, ema(line, sig)


def stochastic(df: pd.DataFrame, k: int = 14, d: int = 3) -> Tuple[pd.Series, pd.Series]:
    k, d = clamp_period(k), clamp_period(d)
    low_n, high_n = df["low"].rolling(k).min(), df["high"].rolling(k).max()
    k_line = 100 * (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan)
    return k_line, k_line.rolling(d).mean()


def adx_di(df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    period = clamp_period(period)
    up, down = df["high"].diff(), -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    prev = df["close"].shift(1)
    tr_raw = pd.concat(
        [(df["high"] - df["low"]).abs(), (df["high"] - prev).abs(), (df["low"] - prev).abs()],
        axis=1,
    ).max(axis=1)
    atr_s = tr_raw.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_s.replace(
        0, np.nan
    )
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_s.replace(
        0, np.nan
    )
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean(), plus_di, minus_di


def cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
    period = clamp_period(period)
    tp = (df["high"] + df["low"] + df["close"]) / 3
    ma = tp.rolling(period).mean()
    md = (tp - ma).abs().rolling(period).mean()
    return (tp - ma) / (0.015 * md.replace(0, np.nan))


@dataclass(frozen=True)
class EntrySpec:
    family: str
    params: Dict
    label: str


@dataclass(frozen=True)
class FilterSpec:
    kind: str
    params: Dict
    label: str


def entry_catalog() -> List[EntrySpec]:
    out: List[EntrySpec] = [
        EntrySpec("supertrend_rsi", {"st_period": 10, "rsi_period": 14}, "supertrend_rsi|st10_rsi14"),
        EntrySpec("ema_cross", {"fast": 9, "slow": 21}, "ema_cross|9_21"),
        EntrySpec("ema_cross", {"fast": 12, "slow": 26}, "ema_cross|12_26"),
        EntrySpec("ema_cross", {"fast": 20, "slow": 50}, "ema_cross|20_50"),
        EntrySpec("macd_cross", {"fast": 12, "slow": 26, "sig": 9}, "macd_cross|12_26_9"),
        EntrySpec("bb_mean_rev", {"period": 20}, "bb_mean_rev|20"),
        EntrySpec("rsi_ob_os", {"period": 7}, "rsi_ob_os|7"),
        EntrySpec("rsi_ob_os", {"period": 14}, "rsi_ob_os|14"),
        EntrySpec("rsi_ob_os", {"period": 21}, "rsi_ob_os|21"),
        EntrySpec("stochastic", {"k": 14, "d": 3}, "stochastic|14_3"),
        EntrySpec("adx_di", {"period": 14}, "adx_di|14"),
        EntrySpec("keltner", {"period": 20}, "keltner|20"),
        EntrySpec("cci", {"period": 14}, "cci|14"),
        EntrySpec("cci", {"period": 20}, "cci|20"),
        EntrySpec("dual_sma_rsi", {"fast": 20, "slow": 50, "rsi": 14}, "dual_sma_rsi|20_50_rsi14"),
        EntrySpec("roc_momentum", {"period": 10}, "roc_momentum|10"),
        EntrySpec("roc_momentum", {"period": 20}, "roc_momentum|20"),
    ]
    for p in (10, 20, 55):
        out.append(EntrySpec("donchian", {"period": p}, f"donchian|{p}"))
    return out


def filter_catalog() -> List[FilterSpec]:
    out: List[FilterSpec] = [FilterSpec("none", {}, "none")]
    for p in (20, 50, 100, 200):
        out.append(FilterSpec("ema", {"period": p}, f"ema|{p}"))
    for p in (50, 200):
        out.append(FilterSpec("sma", {"period": p}, f"sma|{p}"))
    for period, mult in ((7, 2.0), (10, 3.0), (14, 3.0)):
        out.append(FilterSpec("supertrend", {"period": period, "mult": mult}, f"supertrend|{period}x{mult:g}"))
    for p in (14, 20):
        out.append(FilterSpec("adx", {"period": p, "threshold": 25}, f"adx|{p}"))
    for p in (10, 20, 55):
        out.append(FilterSpec("donchian_mid", {"period": p}, f"donchian_mid|{p}"))
    return out


def entry_signals(df: pd.DataFrame, spec: EntrySpec) -> Tuple[pd.Series, pd.Series]:
    close, p, fam = df["close"], spec.params, spec.family
    if fam == "supertrend_rsi":
        st, _ = supertrend(df, int(p["st_period"]), 3.0)
        r = rsi(close, int(p["rsi_period"]))
        rp = r.shift(1)
        long_sig = (st < close) & (rp <= 50) & (r > 50)
        short_sig = (st > close) & (rp >= 50) & (r < 50)
    elif fam == "ema_cross":
        f, s = ema(close, int(p["fast"])), ema(close, int(p["slow"]))
        fp, sp = f.shift(1), s.shift(1)
        long_sig, short_sig = (fp <= sp) & (f > s), (fp >= sp) & (f < s)
    elif fam == "macd_cross":
        line, sig = macd(close, int(p["fast"]), int(p["slow"]), int(p["sig"]))
        lp, sp = line.shift(1), sig.shift(1)
        long_sig, short_sig = (lp <= sp) & (line > sig), (lp >= sp) & (line < sig)
    elif fam == "bb_mean_rev":
        mid = sma(close, int(p["period"]))
        std = close.rolling(int(p["period"])).std()
        lower, upper = mid - 2 * std, mid + 2 * std
        long_sig = (close.shift(1) < lower.shift(1)) & (close > lower)
        short_sig = (close.shift(1) > upper.shift(1)) & (close < upper)
    elif fam == "rsi_ob_os":
        r, rp = rsi(close, int(p["period"])), rsi(close, int(p["period"])).shift(1)
        long_sig, short_sig = (rp < 30) & (r >= 30), (rp > 70) & (r <= 70)
    elif fam == "stochastic":
        k, d = stochastic(df, int(p["k"]), int(p["d"]))
        kp, dp = k.shift(1), d.shift(1)
        long_sig = (kp <= dp) & (k > d) & (k < 20)
        short_sig = (kp >= dp) & (k < d) & (k > 80)
    elif fam == "adx_di":
        adx, pdi, mdi = adx_di(df, int(p["period"]))
        long_sig = (adx > 25) & (pdi > mdi) & (pdi.shift(1) <= mdi.shift(1))
        short_sig = (adx > 25) & (mdi > pdi) & (mdi.shift(1) <= pdi.shift(1))
    elif fam == "donchian":
        per = int(p["period"])
        hi, lo = df["high"].rolling(per).max().shift(1), df["low"].rolling(per).min().shift(1)
        long_sig, short_sig = close > hi, close < lo
    elif fam == "keltner":
        mid, a = ema(close, int(p["period"])), atr(df, 14)
        upper, lower = mid + 1.5 * a, mid - 1.5 * a
        long_sig = (close.shift(1) <= upper.shift(1)) & (close > upper)
        short_sig = (close.shift(1) >= lower.shift(1)) & (close < lower)
    elif fam == "cci":
        c, cp = cci(df, int(p["period"])), cci(df, int(p["period"])).shift(1)
        long_sig, short_sig = (cp < -100) & (c >= -100), (cp > 100) & (c <= 100)
    elif fam == "dual_sma_rsi":
        s_f, s_s = sma(close, int(p["fast"])), sma(close, int(p["slow"]))
        r = rsi(close, int(p["rsi"]))
        long_sig = (s_f > s_s) & (r > 50) & (s_f.shift(1) <= s_s.shift(1))
        short_sig = (s_f < s_s) & (r < 50) & (s_f.shift(1) >= s_s.shift(1))
    elif fam == "roc_momentum":
        roc = close.pct_change(int(p["period"]))
        rp = roc.shift(1)
        long_sig, short_sig = (rp <= 0) & (roc > 0), (rp >= 0) & (roc < 0)
    else:
        raise ValueError(fam)
    return long_sig.fillna(False), short_sig.fillna(False)


def apply_filter(
    df: pd.DataFrame, long_sig: pd.Series, short_sig: pd.Series, fspec: FilterSpec
) -> Tuple[pd.Series, pd.Series]:
    if fspec.kind == "none":
        return long_sig, short_sig
    close, p = df["close"], fspec.params
    if fspec.kind == "ema":
        m = ema(close, int(p["period"]))
        return long_sig & (close > m), short_sig & (close < m)
    if fspec.kind == "sma":
        m = sma(close, int(p["period"]))
        return long_sig & (close > m), short_sig & (close < m)
    if fspec.kind == "supertrend":
        st, direction = supertrend(df, int(p["period"]), float(p["mult"]))
        return long_sig & (direction > 0) & (close > st), short_sig & (direction < 0) & (close < st)
    if fspec.kind == "adx":
        adx, pdi, mdi = adx_di(df, int(p["period"]))
        thr = float(p["threshold"])
        return long_sig & (adx > thr) & (pdi > mdi), short_sig & (adx > thr) & (mdi > pdi)
    if fspec.kind == "donchian_mid":
        per = int(p["period"])
        mid = (df["high"].rolling(per).max() + df["low"].rolling(per).min()) / 2
        return long_sig & (close > mid), short_sig & (close < mid)
    raise ValueError(fspec.kind)


def backtest_atr(
    df: pd.DataFrame, long_sig: pd.Series, short_sig: pd.Series, sl_mult: float = 1.5, tp_mult: float = 3.0
) -> Tuple[float, float, float, int]:
    d = df.tail(MAX_BT_BARS).reset_index(drop=True)
    if len(d) < 80:
        return 0.0, 0.0, 0.0, 0
    long_a = long_sig.iloc[-len(d) :].to_numpy(dtype=bool)
    short_a = short_sig.iloc[-len(d) :].to_numpy(dtype=bool)
    if len(long_a) != len(d):
        long_a = long_sig.reindex(d.index).fillna(False).to_numpy(dtype=bool)
        short_a = short_sig.reindex(d.index).fillna(False).to_numpy(dtype=bool)
    # Recompute signals on trimmed frame for alignment safety
    # (signals were on full df; use positional tail)
    atr_a = atr(d, 14).to_numpy(dtype=float)
    close = d["close"].to_numpy(dtype=float)
    # Fix: long_sig/short_sig from full df — take last len(d) by position
    long_a = np.asarray(long_sig.values[-len(d) :], dtype=bool)
    short_a = np.asarray(short_sig.values[-len(d) :], dtype=bool)

    cash = pos = 0.0
    entry = 0.0
    sl = tp = None
    trades: List[float] = []
    peak = max_dd = 0.0
    pos_i = 0
    for i in range(len(close)):
        price = float(close[i])
        a = float(atr_a[i]) if not math.isnan(atr_a[i]) else 0.0
        if pos_i != 0:
            exit_now = False
            if a > 0 and sl is not None and tp is not None:
                if pos_i == 1 and (price <= sl or price >= tp):
                    exit_now = True
                if pos_i == -1 and (price >= sl or price <= tp):
                    exit_now = True
            if pos_i == 1 and short_a[i]:
                exit_now = True
            if pos_i == -1 and long_a[i]:
                exit_now = True
            if exit_now:
                pnl = (price - entry) * pos_i
                cash += pnl
                trades.append(pnl)
                pos_i = 0
                sl = tp = None
        if pos_i == 0:
            if long_a[i]:
                pos_i, entry = 1, price
                if a > 0:
                    sl, tp = entry - sl_mult * a, entry + tp_mult * a
            elif short_a[i]:
                pos_i, entry = -1, price
                if a > 0:
                    sl, tp = entry + sl_mult * a, entry - tp_mult * a
        mtm = cash + ((price - entry) * pos_i if pos_i else 0.0)
        peak = max(peak, mtm)
        max_dd = max(max_dd, peak - mtm)
    n = len(trades)
    wr = (sum(1 for p in trades if p > 0) / n) if n else 0.0
    return float(cash), float(max_dd), float(wr), n


def load_index() -> Dict[str, Dict[str, Path]]:
    idx_path = RAW / "index.json"
    if not idx_path.exists():
        raise SystemExit(f"Missing {idx_path}")
    raw = json.loads(idx_path.read_text(encoding="utf-8"))
    out: Dict[str, Dict[str, Path]] = {}
    for sym, tfs in raw.items():
        bucket = {}
        for tf, path in tfs.items():
            if tf not in BT_TFS:
                continue
            p = Path(path)
            if not p.exists():
                alt = RAW / Path(path).name
                if alt.exists():
                    p = alt
                else:
                    continue
            bucket[tf] = p
        if bucket:
            out[sym] = bucket
    return out


def run_grid(index: Dict[str, Dict[str, Path]]) -> List[dict]:
    RESULTS.mkdir(parents=True, exist_ok=True)
    entries, filters = entry_catalog(), filter_catalog()
    rows: List[dict] = []
    total = 0
    t0 = time.time()
    print(f"C1 entries={len(entries)} filters={len(filters)} tfs={BT_TFS} syms={len(index)}")
    for sym, tfs in index.items():
        for tf, path in tfs.items():
            df = pd.read_csv(path)
            if len(df) < 120 or "close" not in df.columns:
                continue
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
            for espec in entries:
                try:
                    long0, short0 = entry_signals(df, espec)
                except Exception as exc:  # noqa: BLE001
                    print(f"  entry fail {espec.label}: {exc}")
                    continue
                for fspec in filters:
                    try:
                        long_sig, short_sig = apply_filter(df, long0, short0, fspec)
                        pnl, dd, wr, n = backtest_atr(df, long_sig, short_sig)
                    except Exception as exc:  # noqa: BLE001
                        print(f"  bt fail {espec.label}+{fspec.label}: {exc}")
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
                            "symbol": sym,
                            "timeframe": tf,
                            "pnl": pnl,
                            "max_dd": dd,
                            "winrate": wr,
                            "trades": n,
                        }
                    )
                    total += 1
                    if total % 250 == 0:
                        print(f"  {total} ({time.time()-t0:.0f}s) {espec.label}+{fspec.label} {sym} {tf}")
    path = RESULTS / "c1_grid_backtest.json"
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
        fam = entry.split("|")[0]
        regime = "trend" if fam in TREND_FAMILIES else "other"
        mean_pnl = float(np.mean([x["pnl"] for x in xs]))
        med_pnl = float(np.median([x["pnl"] for x in xs]))
        mean_wr = float(np.mean([x["winrate"] for x in xs]))
        mean_dd = float(np.mean([x["max_dd"] for x in xs]))
        # §7C: trend → PnL primary; WR secondary only
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

    none_med = {r["entry"]: r["median_pnl"] for r in ranking if r["filter"] == "none"}
    lifts = []
    for r in ranking:
        if r["filter"] == "none":
            continue
        base = none_med.get(r["entry"])
        if base is None:
            continue
        lifts.append({**{k: r[k] for k in ("entry", "filter", "regime", "median_pnl", "mean_wr", "n")}, "vs_none": r["median_pnl"] - base})
    lifts.sort(key=lambda x: x["vs_none"], reverse=True)

    best_fam = {}
    for r in ranking:
        fam = r["entry"].split("|")[0]
        if fam not in best_fam or r["score"] > best_fam[fam]["score"]:
            best_fam[fam] = r

    summary = {
        "session": "2026-08-21-c1-entry-filter",
        "policy": "§7C trend=PnL-first (WR often <40% ok); other=PnL+WR score",
        "max_period": MAX_PERIOD,
        "bt_tfs": list(BT_TFS),
        "n_rows": len(rows),
        "n_cells": len(ranking),
        "top20_by_score": ranking[:20],
        "best_per_entry_family": best_fam,
        "top_filter_lifts_vs_none": lifts[:25],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (RESULTS / "c1_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def write_report(summary: dict) -> None:
    lines = [
        "# Session report — C1 Entry × Filter × periods",
        "",
        f"Дата: {summary['generated_at']}",
        "",
        "## Цель",
        "C1 (§7A): entry × filter (ST/ADX/MA/Donchian mid…), periods ∈ [1,200].",
        "Ранжирование (§7C): тренд → PnL first; WR вторичен.",
        "",
        f"- ТФ: {', '.join(summary['bt_tfs'])}",
        f"- rows: {summary['n_rows']}, cells: {summary['n_cells']}",
        "",
        "## Top-20 (score)",
        "```json",
        json.dumps(summary["top20_by_score"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Лучший фильтр на семейство",
        "```json",
        json.dumps(summary["best_per_entry_family"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Топ lift фильтра vs none",
        "```json",
        json.dumps(summary["top_filter_lifts_vs_none"][:15], indent=2, ensure_ascii=False),
        "```",
        "",
    ]
    (SESSION / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def write_heatmap(summary: dict, rows: List[dict]) -> None:
    from collections import defaultdict

    cell = defaultdict(list)
    for r in rows:
        if r["trades"] < 5:
            continue
        cell[(r["entry"], r["filter"])].append(r["pnl"])
    meds = {k: float(np.median(v)) for k, v in cell.items()}
    if not meds:
        return
    vals = list(meds.values())
    med = float(np.median(vals))
    mad = float(np.median([abs(v - med) for v in vals])) or 1.0
    filters = sorted({f for _, f in meds})
    entry_best = {}
    for (e, f), m in meds.items():
        entry_best[e] = max(entry_best.get(e, -1e18), m)
    top_entries = sorted(entry_best, key=entry_best.get, reverse=True)[:18]

    def norm(v: float) -> float:
        return (math.tanh(0.6745 * (v - med) / mad / 2.5) + 1) / 2

    def color(n: float) -> str:
        if n < 0.5:
            t = n * 2
            r, g, b = 220, int(80 + 175 * t), int(80 + 175 * t)
        else:
            t = (n - 0.5) * 2
            r, g, b = int(220 - 160 * t), int(220 - 40 * t), int(220 - 160 * t)
        return f"rgb({r},{g},{b})"

    th = "".join(f"<th>{f}</th>" for f in filters)
    body = []
    for e in top_entries:
        tds = [f'<td class="f">{e}</td>']
        for f in filters:
            if (e, f) in meds:
                m, n = meds[(e, f)], len(cell[(e, f)])
                tds.append(
                    f'<td style="background:{color(norm(m))}"><div class="v">{m:+.0f}</div><div class="n">n={n}</div></td>'
                )
            else:
                tds.append('<td class="empty">—</td>')
        body.append("<tr>" + "".join(tds) + "</tr>")
    chips = "".join(
        f'<span class="chip">{r["entry"]} + <b>{r["filter"]}</b> · med {r["median_pnl"]:+.0f} · wr {r["mean_wr"]:.0%}</span>'
        for r in summary["top20_by_score"][:8]
    )
    html = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"/><title>C1 map</title>
<style>
body{{margin:0;font-family:IBM Plex Sans,Segoe UI,sans-serif;background:#0f1419;color:#e8eef4;padding:28px}}
table{{border-collapse:collapse;width:100%;font-size:.7rem;background:#1a222c}}
th,td{{border:1px solid #2a3542;padding:4px;text-align:center}} th{{background:#121820;color:#8b9aab}}
td.f{{text-align:left;font-family:ui-monospace,monospace;background:#121820;font-size:.65rem}}
.v{{font-weight:600;color:#0b1020}} .n{{font-size:.55rem;color:#1a2030}} .empty{{color:#445}}
.chip{{display:inline-block;margin:3px;padding:4px 10px;border:1px solid #2a3542;border-radius:999px;font-size:.78rem;background:#121820}}
.sub{{color:#8b9aab}}
</style></head><body>
<h1>C1 Entry × Filter</h1>
<p class="sub">§7C: trend = PnL first. Periods 1…200. TFs: {', '.join(BT_TFS)}</p>
<div>{chips}</div>
<table><thead><tr><th>entry</th>{th}</tr></thead><tbody>{''.join(body)}</tbody></table>
</body></html>"""
    (SESSION / "C1_MAP.html").write_text(html, encoding="utf-8")


def main() -> int:
    SESSION.mkdir(parents=True, exist_ok=True)
    print("=== C1 load ===")
    index = load_index()
    print("symbols", sorted(index))
    print("=== C1 grid ===")
    rows = run_grid(index)
    print("=== summarize ===")
    summary = summarize(rows)
    write_report(summary)
    write_heatmap(summary, rows)
    (SESSION / "notes.md").write_text(
        "C1 done. §7A entry×filter×periods + §7C PnL-first for trend.\nNext: Desktop shortlist; C2 EMA(RSI).\n",
        encoding="utf-8",
    )
    print("TOP5:")
    for r in summary["top20_by_score"][:5]:
        print(
            f"  {r['entry']} + {r['filter']}: medPnL={r['median_pnl']:+.1f} wr={r['mean_wr']:.2f} [{r['regime']}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
