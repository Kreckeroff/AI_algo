#!/usr/bin/env python3
"""
Wave-2 training session: max timeframes + 12 indicator families.

MOEX native ISS: 1m, 10m, 1h, 1d, 1w, 1M (no native 5/15).
Derived from 1m: 5m, 15m, 30m.
Yahoo: 5m, 15m, 30m, 1h, 1d, 1w (lookback capped per TF).

Each family: v0 base → v1 filter → v2 ATR SL/TP.
"""
from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
SESSION = REPO / "artifacts" / "agent_loop" / "sessions" / "2026-08-21-multi-indicator-wave"
RAW = SESSION / "data" / "raw"
PROC = SESSION / "data" / "processed"
MODELS = SESSION / "models"
RESULTS = SESSION / "results"
SCRIPTS = SESSION / "scripts"

MOEX_STOCKS = [
    "SBER",
    "GAZP",
    "LKOH",
    "GMKN",
    "NVTK",
    "ROSN",
    "MGNT",
    "TATN",
    "MTSS",
    "PLZL",
]
MOEX_FUTURES = ["GLDRUBF", "IMOEXF", "CNYRUBF"]
YAHOO = {"SPY": "SPY", "GSPC": "^GSPC"}

# Native MOEX interval codes
MOEX_NATIVE = {
    "1m": 1,
    "10m": 10,
    "1h": 60,
    "1d": 24,
    "1w": 7,
    "1M": 31,
}
# Resample rules from 1m → target
RESAMPLE_FROM_1M = {"5m": "5min", "15m": "15min", "30m": "30min"}

# Lookback days by TF (API / size caps)
LOOKBACK_DAYS = {
    "1m": 45,
    "5m": 55,
    "15m": 55,
    "30m": 90,
    "10m": 730,
    "1h": 1825,
    "1d": 1825,
    "1w": 1825,
    "1M": 1825,
}

YF_INTERVAL = {
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "1d": "1d",
    "1w": "1wk",
}

FAMILIES = [
    "supertrend_rsi",
    "ema_cross",
    "macd_cross",
    "bb_mean_rev",
    "rsi_ob_os",
    "stochastic",
    "adx_di",
    "donchian",
    "keltner",
    "cci",
    "dual_sma_rsi",
    "roc_momentum",
]

VARIANTS = ("v0", "v1", "v2")
BT_TFS = ("5m", "15m", "30m", "10m", "1h", "1d", "1w")
MAX_BT_BARS = 8000
MAX_TRAIN_ROWS = 600_000


def _http_json(url: str, retries: int = 3) -> dict:
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AI_algo-train/0.2"})
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"HTTP failed {url}: {last}")


def fetch_moex_candles(
    secid: str,
    interval: int,
    start: str,
    end: str,
    *,
    engine: str,
    market: str,
    board: Optional[str] = None,
) -> pd.DataFrame:
    if board:
        base = (
            f"https://iss.moex.com/iss/engines/{engine}/markets/{market}/boards/{board}/securities/"
            f"{urllib.parse.quote(secid)}/candles.json"
        )
    else:
        base = (
            f"https://iss.moex.com/iss/engines/{engine}/markets/{market}/securities/"
            f"{urllib.parse.quote(secid)}/candles.json"
        )
    rows: List[list] = []
    cols: Optional[List[str]] = None
    start_idx = 0
    while True:
        url = f"{base}?from={start}&till={end}&interval={interval}&start={start_idx}"
        payload = _http_json(url)
        block = payload.get("candles") or {}
        if cols is None:
            cols = block.get("columns") or []
        data = block.get("data") or []
        if not data:
            break
        rows.extend(data)
        start_idx += len(data)
        if len(data) < 500:
            break
        if len(rows) > 400_000:
            break
        time.sleep(0.08)

    if not rows or not cols:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=cols)
    ts_col = "begin" if "begin" in df.columns else df.columns[0]
    vol = (
        pd.to_numeric(df["volume"], errors="coerce").fillna(0)
        if "volume" in df.columns
        else pd.Series(0, index=df.index)
    )
    out = pd.DataFrame(
        {
            "ts": pd.to_datetime(df[ts_col], utc=True),
            "open": pd.to_numeric(df["open"], errors="coerce"),
            "high": pd.to_numeric(df["high"], errors="coerce"),
            "low": pd.to_numeric(df["low"], errors="coerce"),
            "close": pd.to_numeric(df["close"], errors="coerce"),
            "volume": vol,
        }
    ).dropna(subset=["open", "high", "low", "close"])
    return out.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)


def fetch_yahoo(yahoo_ticker: str, start: str, end: str, tf: str) -> pd.DataFrame:
    import yfinance as yf

    yf_iv = YF_INTERVAL[tf]
    t = yf.Ticker(yahoo_ticker)
    df = t.history(start=start, end=end, interval=yf_iv, auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.reset_index()
    ts_col = "Datetime" if "Datetime" in df.columns else "Date"
    out = pd.DataFrame(
        {
            "ts": pd.to_datetime(df[ts_col], utc=True),
            "open": df["Open"].astype(float),
            "high": df["High"].astype(float),
            "low": df["Low"].astype(float),
            "close": df["Close"].astype(float),
            "volume": df["Volume"].astype(float),
        }
    ).dropna()
    return out.sort_values("ts").reset_index(drop=True)


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty:
        return df
    x = df.set_index("ts").sort_index()
    o = x["open"].resample(rule).first()
    h = x["high"].resample(rule).max()
    l = x["low"].resample(rule).min()
    c = x["close"].resample(rule).last()
    v = x["volume"].resample(rule).sum()
    out = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}).dropna()
    return out.reset_index().rename(columns={"index": "ts"})


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(alpha=1 / period, adjust=False).mean()
    ma_down = down.ewm(alpha=1 / period, adjust=False).mean()
    rs = ma_up / ma_down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            (df["high"] - df["low"]).abs(),
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def supertrend(df: pd.DataFrame, period: int = 10, mult: float = 3.0) -> pd.Series:
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
    return pd.Series(st, index=df.index)


def macd(series: pd.Series) -> Tuple[pd.Series, pd.Series]:
    line = ema(series, 12) - ema(series, 26)
    signal = ema(line, 9)
    return line, signal


def stochastic(df: pd.DataFrame, k: int = 14, d: int = 3) -> Tuple[pd.Series, pd.Series]:
    low_n = df["low"].rolling(k).min()
    high_n = df["high"].rolling(k).max()
    k_line = 100 * (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan)
    d_line = k_line.rolling(d).mean()
    return k_line, d_line


def adx_di(df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = atr(df, period)  # already smoothed-ish; use true TR SMA path
    prev_close = df["close"].shift(1)
    tr_raw = pd.concat(
        [
            (df["high"] - df["low"]).abs(),
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
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
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx, plus_di, minus_di


def cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    ma = tp.rolling(period).mean()
    md = (tp - ma).abs().rolling(period).mean()
    return (tp - ma) / (0.015 * md.replace(0, np.nan))


def build_features(df: pd.DataFrame, horizon: int = 5) -> pd.DataFrame:
    out = df.copy()
    out["ret_1"] = out["close"].pct_change(1)
    out["ret_5"] = out["close"].pct_change(5)
    out["rsi_14"] = rsi(out["close"], 14)
    out["atr_14"] = atr(out, 14)
    ema50 = ema(out["close"], 50)
    out["ema_dist_50"] = (out["close"] - ema50) / out["close"]
    vol_mean = out["volume"].rolling(20).mean()
    vol_std = out["volume"].rolling(20).std().replace(0, np.nan)
    out["volume_z"] = (out["volume"] - vol_mean) / vol_std
    # Extra family-aware features
    macd_line, macd_sig = macd(out["close"])
    out["macd_hist"] = macd_line - macd_sig
    bb_mid = sma(out["close"], 20)
    bb_std = out["close"].rolling(20).std()
    out["bb_pct"] = (out["close"] - (bb_mid - 2 * bb_std)) / (4 * bb_std).replace(0, np.nan)
    out["roc_10"] = out["close"].pct_change(10)
    fut = out["close"].shift(-horizon)
    out["y_up"] = (fut > out["close"]).astype(float)
    return out


SignalFn = Callable[[pd.DataFrame], Tuple[pd.Series, pd.Series]]


def signals_for_family(df: pd.DataFrame, family: str) -> Tuple[pd.Series, pd.Series]:
    """Return (long_sig, short_sig) boolean series for family base logic."""
    close = df["close"]
    if family == "supertrend_rsi":
        st = supertrend(df, 10, 3.0)
        r = rsi(close, 14)
        rp = r.shift(1)
        long_sig = (st < close) & (rp <= 50) & (r > 50)
        short_sig = (st > close) & (rp >= 50) & (r < 50)
    elif family == "ema_cross":
        f, s = ema(close, 9), ema(close, 21)
        fp, sp = f.shift(1), s.shift(1)
        long_sig = (fp <= sp) & (f > s)
        short_sig = (fp >= sp) & (f < s)
    elif family == "macd_cross":
        line, sig = macd(close)
        lp, sp = line.shift(1), sig.shift(1)
        long_sig = (lp <= sp) & (line > sig)
        short_sig = (lp >= sp) & (line < sig)
    elif family == "bb_mean_rev":
        mid = sma(close, 20)
        std = close.rolling(20).std()
        lower, upper = mid - 2 * std, mid + 2 * std
        long_sig = (close.shift(1) < lower.shift(1)) & (close > lower)
        short_sig = (close.shift(1) > upper.shift(1)) & (close < upper)
    elif family == "rsi_ob_os":
        r = rsi(close, 14)
        rp = r.shift(1)
        long_sig = (rp < 30) & (r >= 30)
        short_sig = (rp > 70) & (r <= 70)
    elif family == "stochastic":
        k, d = stochastic(df)
        kp, dp = k.shift(1), d.shift(1)
        long_sig = (kp <= dp) & (k > d) & (k < 20)
        short_sig = (kp >= dp) & (k < d) & (k > 80)
    elif family == "adx_di":
        adx, pdi, mdi = adx_di(df)
        long_sig = (adx > 25) & (pdi > mdi) & (pdi.shift(1) <= mdi.shift(1))
        short_sig = (adx > 25) & (mdi > pdi) & (mdi.shift(1) <= pdi.shift(1))
    elif family == "donchian":
        hi = df["high"].rolling(20).max().shift(1)
        lo = df["low"].rolling(20).min().shift(1)
        long_sig = close > hi
        short_sig = close < lo
    elif family == "keltner":
        mid = ema(close, 20)
        a = atr(df, 14)
        upper, lower = mid + 1.5 * a, mid - 1.5 * a
        long_sig = (close.shift(1) <= upper.shift(1)) & (close > upper)
        short_sig = (close.shift(1) >= lower.shift(1)) & (close < lower)
    elif family == "cci":
        c = cci(df, 20)
        cp = c.shift(1)
        long_sig = (cp < -100) & (c >= -100)
        short_sig = (cp > 100) & (c <= 100)
    elif family == "dual_sma_rsi":
        s20, s50 = sma(close, 20), sma(close, 50)
        r = rsi(close, 14)
        long_sig = (s20 > s50) & (r > 50) & (s20.shift(1) <= s50.shift(1))
        short_sig = (s20 < s50) & (r < 50) & (s20.shift(1) >= s50.shift(1))
    elif family == "roc_momentum":
        roc = close.pct_change(10)
        rp = roc.shift(1)
        long_sig = (rp <= 0) & (roc > 0)
        short_sig = (rp >= 0) & (roc < 0)
    else:
        raise ValueError(family)
    return long_sig.fillna(False), short_sig.fillna(False)


def backtest(
    df: pd.DataFrame,
    family: str,
    variant: str,
) -> Tuple[float, float, float, int]:
    d = df.tail(MAX_BT_BARS).copy().reset_index(drop=True)
    if len(d) < 80:
        return 0.0, 0.0, 0.0, 0

    long_sig, short_sig = signals_for_family(d, family)
    ema50 = ema(d["close"], 50)
    atr_v = atr(d, 14)

    if variant in ("v1", "v2"):
        long_sig = long_sig & (d["close"] > ema50)
        short_sig = short_sig & (d["close"] < ema50)

    close = d["close"].to_numpy(dtype=float)
    atr_a = atr_v.to_numpy(dtype=float)
    long_a = long_sig.to_numpy(dtype=bool)
    short_a = short_sig.to_numpy(dtype=bool)

    cash = 0.0
    pos = 0
    entry = 0.0
    sl = tp = None
    trades: List[float] = []
    peak = 0.0
    max_dd = 0.0

    for i in range(len(close)):
        price = close[i]
        a = atr_a[i] if not math.isnan(atr_a[i]) else 0.0

        if pos != 0:
            exit_now = False
            if variant == "v2" and a > 0 and sl is not None and tp is not None:
                if pos == 1 and (price <= sl or price >= tp):
                    exit_now = True
                if pos == -1 and (price >= sl or price <= tp):
                    exit_now = True
            if pos == 1 and short_a[i]:
                exit_now = True
            if pos == -1 and long_a[i]:
                exit_now = True
            if exit_now:
                pnl = (price - entry) * pos
                cash += pnl
                trades.append(pnl)
                pos = 0
                sl = tp = None

        if pos == 0:
            if long_a[i]:
                pos = 1
                entry = price
                if variant == "v2" and a > 0:
                    sl = entry - 1.5 * a
                    tp = entry + 3.0 * a
            elif short_a[i]:
                pos = -1
                entry = price
                if variant == "v2" and a > 0:
                    sl = entry + 1.5 * a
                    tp = entry - 3.0 * a

        mtm = cash + ((price - entry) * pos if pos else 0.0)
        peak = max(peak, mtm)
        max_dd = max(max_dd, peak - mtm)

    n = len(trades)
    wr = (sum(1 for p in trades if p > 0) / n) if n else 0.0
    return float(cash), float(max_dd), float(wr), n


def _window(tf: str) -> Tuple[str, str]:
    end = datetime.now(timezone.utc).date()
    days = LOOKBACK_DAYS.get(tf, 365)
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def _save_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False)


def download_all() -> Dict[str, Dict[str, Path]]:
    RAW.mkdir(parents=True, exist_ok=True)
    index: Dict[str, Dict[str, Path]] = {}

    def ensure_sym(sym: str) -> Dict[str, Path]:
        index.setdefault(sym, {})
        return index[sym]

    # --- MOEX stocks native ---
    for sec in MOEX_STOCKS:
        bucket = ensure_sym(sec)
        for tf, interval in MOEX_NATIVE.items():
            path = RAW / f"MOEX_{sec}_{tf}.csv"
            if path.exists() and path.stat().st_size > 100:
                bucket[tf] = path
                continue
            start_s, end_s = _window(tf)
            print(f"fetch MOEX stock {sec} {tf} ({start_s}→{end_s})…")
            try:
                df = fetch_moex_candles(
                    sec, interval, start_s, end_s, engine="stock", market="shares", board="TQBR"
                )
                if df.empty:
                    df = fetch_moex_candles(
                        sec, interval, start_s, end_s, engine="stock", market="shares"
                    )
                if not df.empty:
                    _save_csv(path, df)
                    bucket[tf] = path
                    print(f"  {len(df)} bars → {path.name}")
                else:
                    print(f"  empty {sec} {tf}")
            except Exception as exc:  # noqa: BLE001
                print(f"  fail {sec} {tf}: {exc}")
            time.sleep(0.15)

        # derived 5/15/30 from 1m
        m1 = bucket.get("1m")
        if m1 and Path(m1).exists():
            base = pd.read_csv(m1)
            base["ts"] = pd.to_datetime(base["ts"], utc=True)
            for tf, rule in RESAMPLE_FROM_1M.items():
                path = RAW / f"MOEX_{sec}_{tf}.csv"
                if path.exists() and path.stat().st_size > 100:
                    bucket[tf] = path
                    continue
                rdf = resample_ohlcv(base, rule)
                if not rdf.empty:
                    _save_csv(path, rdf)
                    bucket[tf] = path
                    print(f"  resample {sec} {tf}: {len(rdf)} bars")

    # --- MOEX futures ---
    for sec in MOEX_FUTURES:
        bucket = ensure_sym(sec)
        for tf, interval in MOEX_NATIVE.items():
            path = RAW / f"MOEX_{sec}_{tf}.csv"
            if path.exists() and path.stat().st_size > 100:
                bucket[tf] = path
                continue
            start_s, end_s = _window(tf)
            print(f"fetch MOEX fut {sec} {tf}…")
            try:
                df = fetch_moex_candles(
                    sec, interval, start_s, end_s, engine="futures", market="forts"
                )
                if not df.empty:
                    _save_csv(path, df)
                    bucket[tf] = path
                    print(f"  {len(df)} bars → {path.name}")
                else:
                    print(f"  empty {sec} {tf}")
            except Exception as exc:  # noqa: BLE001
                print(f"  fail {sec} {tf}: {exc}")
            time.sleep(0.15)

        m1 = bucket.get("1m")
        if m1 and Path(m1).exists():
            base = pd.read_csv(m1)
            base["ts"] = pd.to_datetime(base["ts"], utc=True)
            for tf, rule in RESAMPLE_FROM_1M.items():
                path = RAW / f"MOEX_{sec}_{tf}.csv"
                if path.exists() and path.stat().st_size > 100:
                    bucket[tf] = path
                    continue
                rdf = resample_ohlcv(base, rule)
                if not rdf.empty:
                    _save_csv(path, rdf)
                    bucket[tf] = path
                    print(f"  resample {sec} {tf}: {len(rdf)} bars")

    # --- Yahoo ---
    for name, ticker in YAHOO.items():
        bucket = ensure_sym(name)
        for tf in YF_INTERVAL:
            path = RAW / f"YF_{name}_{tf}.csv"
            if path.exists() and path.stat().st_size > 100:
                bucket[tf] = path
                continue
            start_s, end_s = _window(tf)
            print(f"fetch Yahoo {ticker} {tf} ({start_s}→{end_s})…")
            try:
                df = fetch_yahoo(ticker, start_s, end_s, tf)
                if not df.empty:
                    _save_csv(path, df)
                    bucket[tf] = path
                    print(f"  {len(df)} bars → {path.name}")
                else:
                    print(f"  empty {name} {tf}")
            except Exception as exc:  # noqa: BLE001
                print(f"  fail {name} {tf}: {exc}")
            time.sleep(0.25)

    (RAW / "index.json").write_text(
        json.dumps({k: {t: str(p) for t, p in v.items()} for k, v in index.items()}, indent=2),
        encoding="utf-8",
    )
    return index


def train_signal(index: Dict[str, Dict[str, Path]]) -> dict:
    PROC.mkdir(parents=True, exist_ok=True)
    MODELS.mkdir(parents=True, exist_ok=True)
    frames = []
    for sym, tfs in index.items():
        for tf, path in tfs.items():
            df = pd.read_csv(path)
            if "ts" not in df.columns or len(df) < 80:
                continue
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
            # Cap very dense series for feature build
            if len(df) > 25_000:
                df = df.tail(25_000).reset_index(drop=True)
            feat = build_features(df, horizon=5)
            feat["symbol"] = sym
            feat["timeframe"] = tf
            frames.append(feat)

    if not frames:
        raise SystemExit("No feature frames — download failed?")

    all_df = pd.concat(frames, ignore_index=True)
    feats = [
        "ret_1",
        "ret_5",
        "rsi_14",
        "atr_14",
        "ema_dist_50",
        "volume_z",
        "macd_hist",
        "bb_pct",
        "roc_10",
    ]
    all_df = all_df.dropna(subset=feats + ["y_up", "ts"]).sort_values("ts")
    if len(all_df) > MAX_TRAIN_ROWS:
        # Stratified downsample by timeframe
        parts = []
        per = MAX_TRAIN_ROWS // max(1, all_df["timeframe"].nunique())
        for tf, g in all_df.groupby("timeframe"):
            parts.append(g.tail(per) if len(g) > per else g)
        all_df = pd.concat(parts, ignore_index=True).sort_values("ts")
        print(f"downsampled features to {len(all_df)}")

    csv_path = PROC / "features_v2.csv"
    all_df.to_csv(csv_path, index=False)
    print(f"features rows={len(all_df)} tfs={sorted(all_df['timeframe'].unique())} → {csv_path}")

    split = int(len(all_df) * 0.7)
    train, test = all_df.iloc[:split], all_df.iloc[split:]
    x_tr, y_tr = train[feats], train["y_up"].astype(int)
    x_te, y_te = test[feats], test["y_up"].astype(int)

    kind = "hgb"
    try:
        import lightgbm as lgb

        model = lgb.LGBMClassifier(
            n_estimators=150,
            learning_rate=0.05,
            num_leaves=47,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=42,
            verbose=-1,
        )
        kind = "lgbm"
    except Exception as exc:  # noqa: BLE001
        print("LightGBM unavailable, HGB fallback:", exc)
        from sklearn.ensemble import HistGradientBoostingClassifier

        model = HistGradientBoostingClassifier(max_depth=5, learning_rate=0.05, random_state=42)

    model.fit(x_tr, y_tr)
    proba = model.predict_proba(x_te)[:, 1]
    pred = (proba >= 0.5).astype(int)
    from sklearn.metrics import accuracy_score, roc_auc_score

    acc = float(accuracy_score(y_te, pred))
    try:
        auc = float(roc_auc_score(y_te, proba))
    except ValueError:
        auc = float("nan")

    all_tfs = sorted({t for v in index.values() for t in v})
    meta = {
        "session": "2026-08-21-multi-indicator-wave",
        "feature_schema_id": "v2-multi",
        "feature_names": feats,
        "model_kind": kind,
        "families": FAMILIES,
        "metrics": {
            "accuracy": acc,
            "roc_auc": auc,
            "n_train": int(len(train)),
            "n_test": int(len(test)),
            "n_symbols": len(index),
        },
        "symbols": sorted(index.keys()),
        "timeframes": all_tfs,
        "lookback_days": LOOKBACK_DAYS,
    }
    joblib.dump({"model": model, "kind": kind, "feature_schema_id": "v2-multi"}, MODELS / "model.joblib")
    (MODELS / "feature_names.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"train kind={kind} acc={acc:.4f} auc={auc:.4f}")
    return meta


def run_script_variants(index: Dict[str, Dict[str, Path]]) -> List[dict]:
    RESULTS.mkdir(parents=True, exist_ok=True)
    rows: List[dict] = []
    total = 0
    for sym, tfs in index.items():
        for tf in BT_TFS:
            path = tfs.get(tf)
            if not path or not Path(path).exists():
                continue
            df = pd.read_csv(path)
            if len(df) < 120:
                continue
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
            for family in FAMILIES:
                for variant in VARIANTS:
                    pnl, dd, wr, n = backtest(df, family, variant)
                    rows.append(
                        {
                            "family": family,
                            "variant": variant,
                            "symbol": sym,
                            "timeframe": tf,
                            "pnl": pnl,
                            "max_dd": dd,
                            "winrate": wr,
                            "trades": n,
                        }
                    )
                    total += 1
                    if total % 100 == 0:
                        print(f"  BT progress {total}… last={family}/{variant} {sym} {tf}")

    out = RESULTS / "script_variants_backtest.json"
    out.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")

    # Aggregate per family × variant
    family_agg: Dict[str, dict] = {}
    for family in FAMILIES:
        family_agg[family] = {}
        for v in VARIANTS:
            subset = [r for r in rows if r["family"] == family and r["variant"] == v and r["trades"] >= 5]
            if not subset:
                family_agg[family][v] = {"n": 0}
                continue
            family_agg[family][v] = {
                "n": len(subset),
                "mean_pnl": float(np.mean([r["pnl"] for r in subset])),
                "mean_dd": float(np.mean([r["max_dd"] for r in subset])),
                "mean_wr": float(np.mean([r["winrate"] for r in subset])),
                "mean_trades": float(np.mean([r["trades"] for r in subset])),
            }

    # Verdicts v0→v1→v2 per family
    verdicts = []
    for family in FAMILIES:
        agg = family_agg[family]
        for a, b in zip(VARIANTS, VARIANTS[1:]):
            if agg.get(a, {}).get("n", 0) and agg.get(b, {}).get("n", 0):
                better = agg[b]["mean_pnl"] > agg[a]["mean_pnl"] and agg[b]["mean_dd"] <= agg[a]["mean_dd"] * 1.15
                worse = agg[b]["mean_pnl"] < agg[a]["mean_pnl"] and agg[b]["mean_dd"] >= agg[a]["mean_dd"]
                ver = "better" if better else ("worse" if worse else "mixed")
                verdicts.append(
                    {
                        "family": family,
                        "from": a,
                        "to": b,
                        "verdict": ver,
                        "agg_before": agg[a],
                        "agg_after": agg[b],
                    }
                )

    # Best family by v2 mean_pnl among those with n>=10
    ranking = []
    for family, agg in family_agg.items():
        v2 = agg.get("v2") or {}
        if v2.get("n", 0) >= 10:
            ranking.append({"family": family, "mean_pnl_v2": v2["mean_pnl"], "mean_dd_v2": v2["mean_dd"], "n": v2["n"]})
    ranking.sort(key=lambda x: x["mean_pnl_v2"], reverse=True)

    # TF coverage stats
    tf_counts: Dict[str, int] = {}
    for sym, tfs in index.items():
        for tf in tfs:
            tf_counts[tf] = tf_counts.get(tf, 0) + 1

    summary = {
        "family_aggregates": family_agg,
        "verdicts": verdicts,
        "ranking_v2": ranking,
        "tf_file_counts": tf_counts,
        "rows": len(rows),
    }
    (RESULTS / "variant_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"BT done rows={len(rows)} families={len(FAMILIES)}")
    return rows


def write_report(train_meta: dict) -> None:
    summary = json.loads((RESULTS / "variant_summary.json").read_text(encoding="utf-8"))
    lines = [
        "# Session report — Multi-indicator wave (max TFs)",
        "",
        f"Дата: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Цель",
        "Максимум таймфреймов + 12 семейств индикаторов с улучшением v0→v1→v2,",
        "сигнал-модель A на расширенных фичах.",
        "",
        "## Таймфреймы",
        "- MOEX native: 1m, 10m, 1h, 1d, 1w, 1M",
        "- MOEX derived (из 1m): 5m, 15m, 30m",
        "- Yahoo: 5m, 15m, 30m, 1h, 1d, 1w",
        "- Lookback по ТФ (короче для интрадея): см. `models/feature_names.json`",
        "",
        f"Файлов по ТФ: `{json.dumps(summary.get('tf_file_counts', {}), ensure_ascii=False)}`",
        "",
        "## Инструменты",
        f"- MOEX акции: {', '.join(MOEX_STOCKS)}",
        f"- MOEX фьючерсы: {', '.join(MOEX_FUTURES)}",
        "- US: SPY, ^GSPC (Yahoo)",
        "",
        "## Signal model",
        f"- kind: `{train_meta['model_kind']}`",
        f"- schema: `{train_meta['feature_schema_id']}`",
        f"- accuracy: **{train_meta['metrics']['accuracy']:.4f}**",
        f"- roc_auc: **{train_meta['metrics']['roc_auc']:.4f}**",
        f"- n_train/n_test: {train_meta['metrics']['n_train']} / {train_meta['metrics']['n_test']}",
        f"- timeframes in train: {', '.join(train_meta.get('timeframes', []))}",
        "",
        "## Семейства (v0 base → v1 EMA50 filter → v2 ATR SL/TP)",
        "",
    ]
    for f in FAMILIES:
        lines.append(f"- `{f}`")
    lines += [
        "",
        "### Ranking by v2 mean PnL",
        "```json",
        json.dumps(summary.get("ranking_v2", []), indent=2, ensure_ascii=False),
        "```",
        "",
        "### Aggregates (per family)",
        "```json",
        json.dumps(summary.get("family_aggregates", {}), indent=2, ensure_ascii=False)[:12000],
        "```",
        "",
        "### Verdicts (sample / full in results/variant_summary.json)",
        "```json",
        json.dumps(summary.get("verdicts", [])[:24], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Артефакты",
        "- `models/model.joblib`, `models/feature_names.json`",
        "- `results/script_variants_backtest.json`, `results/variant_summary.json`",
        "- `data/processed/features_v2.csv`",
        "",
    ]
    (SESSION / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote", SESSION / "REPORT.md")


def write_family_readme() -> None:
    SCRIPTS.mkdir(parents=True, exist_ok=True)
    text = """# Indicator families (wave 2)

Vectorized BT families in this session (Desktop `.italgo` ports can follow ranking):

1. supertrend_rsi — SuperTrend + RSI50 cross
2. ema_cross — EMA9/21 cross
3. macd_cross — MACD/signal cross
4. bb_mean_rev — Bollinger mean reversion
5. rsi_ob_os — RSI 30/70 exits from extremes
6. stochastic — Stoch K/D in OS/OB
7. adx_di — ADX>25 + DI cross
8. donchian — 20-bar Donchian breakout
9. keltner — Keltner channel breakout
10. cci — CCI ±100 reclaim
11. dual_sma_rsi — SMA20/50 + RSI filter
12. roc_momentum — ROC(10) zero-cross

Each: v0 → v1 (+EMA50 trend filter) → v2 (+ATR 1.5/3.0 SL/TP).
"""
    (SCRIPTS / "README.md").write_text(text, encoding="utf-8")


def main() -> int:
    SESSION.mkdir(parents=True, exist_ok=True)
    write_family_readme()
    print("=== download (max TFs) ===")
    index = download_all()
    print("=== train signal ===")
    meta = train_signal(index)
    print("=== script families BT ===")
    run_script_variants(index)
    write_report(meta)
    (SESSION / "notes.md").write_text(
        "Wave-2: max TFs (incl. 5m/15m derived + Yahoo) + 12 indicator families.\n"
        "Next: port top families to Desktop .italgo and feed compare ingest.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
