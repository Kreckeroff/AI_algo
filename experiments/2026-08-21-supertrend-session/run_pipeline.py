#!/usr/bin/env python3
"""
SuperTrend + EMA/RSI training session pipeline.

1) Fetch OHLCV: MOEX futures + blue chips, Yahoo SPY/^GSPC
2) Build features (v1-basic) across TF/horizons
3) Train LightGBM (or HGB fallback)
4) Vectorized backtest of script variants (v0 / v1 ADX-ish filter / v2 ATR exits)
5) Write session report under artifacts/agent_loop/sessions/...

This is the agent training lab path — Desktop UI polish comes later.
"""
from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
SESSION = REPO / "artifacts" / "agent_loop" / "sessions" / "2026-08-21-supertrend-ema-rsi"
RAW = SESSION / "data" / "raw"
PROC = SESSION / "data" / "processed"
MODELS = SESSION / "models"
RESULTS = SESSION / "results"

# Blue chips (MOEX boards TQBR) + futures + US
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
YAHOO = {
    "SPY": "SPY",  # S&P 500 ETF proxy
    "GSPC": "^GSPC",
}

# MOEX candle intervals: 1=1m 10=10m 60=1h 24=day 7=week
TF_MAP = {
    "1h": 60,
    "1d": 24,
    "1w": 7,
}


def _http_json(url: str, retries: int = 3) -> dict:
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AI_algo-train/0.1"})
            with urllib.request.urlopen(req, timeout=60) as resp:
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
    """Fetch MOEX ISS candles (single request window; ISS caps page size)."""
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
        if len(rows) > 250_000:
            break
        time.sleep(0.12)

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


def fetch_yahoo(symbol: str, yahoo_ticker: str, start: str, end: str, interval: str) -> pd.DataFrame:
    import yfinance as yf

    # yfinance intervals: 1h, 1d, 1wk
    yf_iv = {"1h": "1h", "1d": "1d", "1w": "1wk"}[interval]
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


def supertrend(df: pd.DataFrame, period: int = 10, mult: float = 3.0) -> pd.Series:
    """Return SuperTrend line (approx)."""
    atr_v = atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2
    upper = hl2 + mult * atr_v
    lower = hl2 - mult * atr_v
    st = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(1, index=df.index)
    for i in range(len(df)):
        if i == 0:
            st.iloc[i] = lower.iloc[i]
            continue
        if df["close"].iloc[i - 1] > st.iloc[i - 1]:
            direction.iloc[i] = 1
        elif df["close"].iloc[i - 1] < st.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]
        if direction.iloc[i] == 1:
            st.iloc[i] = max(lower.iloc[i], st.iloc[i - 1]) if direction.iloc[i - 1] == 1 else lower.iloc[i]
        else:
            st.iloc[i] = min(upper.iloc[i], st.iloc[i - 1]) if direction.iloc[i - 1] == -1 else upper.iloc[i]
    return st


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
    fut = out["close"].shift(-horizon)
    out["y_up"] = (fut > out["close"]).astype(float)
    return out


@dataclass
class BtResult:
    name: str
    symbol: str
    timeframe: str
    trades: int
    winrate: float
    pnl: float
    max_dd: float


def backtest_variant(df: pd.DataFrame, variant: str) -> Tuple[float, float, float, int, List[dict]]:
    """
    Variants:
      v0: SuperTrend + RSI50 cross (like sample)
      v1: v0 + EMA50 trend filter (only long if close>EMA, short if close<EMA)
      v2: v1 + ATR stop/take (1.5 / 3.0)
    """
    d = df.copy()
    d["st"] = supertrend(d, 10, 3.0)
    d["rsi"] = rsi(d["close"], 14)
    d["ema50"] = ema(d["close"], 50)
    d["atr"] = atr(d, 14)

    rsi_prev = d["rsi"].shift(1)
    cross_up = (rsi_prev <= 50) & (d["rsi"] > 50)
    cross_dn = (rsi_prev >= 50) & (d["rsi"] < 50)
    st_bull = d["st"] < d["close"]
    st_bear = d["st"] > d["close"]

    long_sig = st_bull & cross_up
    short_sig = st_bear & cross_dn
    if variant in ("v1", "v2"):
        long_sig = long_sig & (d["close"] > d["ema50"])
        short_sig = short_sig & (d["close"] < d["ema50"])

    cash = 0.0
    pos = 0  # 1 long -1 short 0 flat
    entry = 0.0
    sl = tp = None
    equity = []
    trades = []
    peak = 0.0
    max_dd = 0.0

    for i in range(len(d)):
        price = float(d["close"].iloc[i])
        a = float(d["atr"].iloc[i]) if not math.isnan(d["atr"].iloc[i]) else 0.0

        # exits
        if pos != 0:
            exit_now = False
            if variant == "v2" and a > 0 and sl is not None and tp is not None:
                if pos == 1 and (price <= sl or price >= tp):
                    exit_now = True
                if pos == -1 and (price >= sl or price <= tp):
                    exit_now = True
            # opposite signal
            if pos == 1 and short_sig.iloc[i]:
                exit_now = True
            if pos == -1 and long_sig.iloc[i]:
                exit_now = True
            if exit_now:
                pnl = (price - entry) * pos
                cash += pnl
                trades.append({"pnl": pnl, "side": "long" if pos == 1 else "short"})
                pos = 0
                sl = tp = None

        # entries
        if pos == 0:
            if long_sig.iloc[i]:
                pos = 1
                entry = price
                if variant == "v2" and a > 0:
                    sl = entry - 1.5 * a
                    tp = entry + 3.0 * a
            elif short_sig.iloc[i]:
                pos = -1
                entry = price
                if variant == "v2" and a > 0:
                    sl = entry + 1.5 * a
                    tp = entry - 3.0 * a

        mtm = cash + ((price - entry) * pos if pos else 0.0)
        equity.append(mtm)
        peak = max(peak, mtm)
        max_dd = max(max_dd, peak - mtm)

    pnls = [t["pnl"] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    n = len(pnls)
    winrate = wins / n if n else 0.0
    return float(cash), float(max_dd), float(winrate), n, trades


def download_all(years: float = 5.0) -> Dict[str, Dict[str, Path]]:
    RAW.mkdir(parents=True, exist_ok=True)
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=int(365 * years))
    start_s, end_s = start.isoformat(), end.isoformat()
    index: Dict[str, Dict[str, Path]] = {}

    for sec in MOEX_STOCKS:
        index[sec] = {}
        for tf, interval in TF_MAP.items():
            path = RAW / f"MOEX_{sec}_{tf}.csv"
            if path.exists() and path.stat().st_size > 100:
                index[sec][tf] = path
                continue
            print(f"fetch MOEX stock {sec} {tf}…")
            try:
                df = fetch_moex_candles(
                    sec,
                    interval,
                    start_s,
                    end_s,
                    engine="stock",
                    market="shares",
                    board="TQBR",
                )
                if df.empty:
                    df = fetch_moex_candles(
                        sec, interval, start_s, end_s, engine="stock", market="shares"
                    )
                if not df.empty:
                    df.to_csv(path, index=False)
                    index[sec][tf] = path
                    print(f"  {len(df)} bars → {path.name}")
                else:
                    print(f"  empty {sec} {tf}")
            except Exception as exc:  # noqa: BLE001
                print(f"  fail {sec} {tf}: {exc}")
            time.sleep(0.2)

    for sec in MOEX_FUTURES:
        index[sec] = {}
        for tf, interval in TF_MAP.items():
            path = RAW / f"MOEX_{sec}_{tf}.csv"
            if path.exists() and path.stat().st_size > 100:
                index[sec][tf] = path
                continue
            print(f"fetch MOEX fut {sec} {tf}…")
            try:
                df = fetch_moex_candles(
                    sec, interval, start_s, end_s, engine="futures", market="forts"
                )
                if not df.empty:
                    df.to_csv(path, index=False)
                    index[sec][tf] = path
                    print(f"  {len(df)} bars → {path.name}")
                else:
                    print(f"  empty {sec} {tf}")
            except Exception as e:  # noqa: BLE001
                print(f"  fail {sec} {tf}: {e}")
            time.sleep(0.2)

    for name, ticker in YAHOO.items():
        index[name] = {}
        for tf in TF_MAP:
            path = RAW / f"YF_{name}_{tf}.csv"
            if path.exists() and path.stat().st_size > 100:
                index[name][tf] = path
                continue
            print(f"fetch Yahoo {ticker} {tf}…")
            try:
                df = fetch_yahoo(name, ticker, start_s, end_s, tf)
                if not df.empty:
                    df.to_csv(path, index=False)
                    index[name][tf] = path
                    print(f"  {len(df)} bars → {path.name}")
                else:
                    print(f"  empty {name} {tf}")
            except Exception as e:  # noqa: BLE001
                print(f"  fail {name} {tf}: {e}")
            time.sleep(0.3)

    (RAW / "index.json").write_text(json.dumps({k: {t: str(p) for t, p in v.items()} for k, v in index.items()}, indent=2), encoding="utf-8")
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
            feat = build_features(df, horizon=5)
            feat["symbol"] = sym
            feat["timeframe"] = tf
            frames.append(feat)

    if not frames:
        raise SystemExit("No feature frames — download failed?")

    all_df = pd.concat(frames, ignore_index=True)
    feats = ["ret_1", "ret_5", "rsi_14", "atr_14", "ema_dist_50", "volume_z"]
    all_df = all_df.dropna(subset=feats + ["y_up", "ts"]).sort_values("ts")
    csv_path = PROC / "features_v1.csv"
    all_df.to_csv(csv_path, index=False)
    print(f"features rows={len(all_df)} → {csv_path}")

    # time split global
    split = int(len(all_df) * 0.7)
    train, test = all_df.iloc[:split], all_df.iloc[split:]
    x_tr, y_tr = train[feats], train["y_up"].astype(int)
    x_te, y_te = test[feats], test["y_up"].astype(int)

    kind = "hgb"
    try:
        import lightgbm as lgb

        model = lgb.LGBMClassifier(
            n_estimators=120,
            learning_rate=0.05,
            num_leaves=31,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=42,
            verbose=-1,
        )
        kind = "lgbm"
    except Exception as exc:  # noqa: BLE001
        print("LightGBM unavailable, HGB fallback:", exc)
        from sklearn.ensemble import HistGradientBoostingClassifier

        model = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, random_state=42)

    model.fit(x_tr, y_tr)
    proba = model.predict_proba(x_te)[:, 1]
    pred = (proba >= 0.5).astype(int)
    from sklearn.metrics import accuracy_score, roc_auc_score

    acc = float(accuracy_score(y_te, pred))
    try:
        auc = float(roc_auc_score(y_te, proba))
    except ValueError:
        auc = float("nan")

    meta = {
        "session": "2026-08-21-supertrend-ema-rsi",
        "feature_schema_id": "v1-basic",
        "feature_names": feats,
        "model_kind": kind,
        "metrics": {
            "accuracy": acc,
            "roc_auc": auc,
            "n_train": int(len(train)),
            "n_test": int(len(test)),
            "n_symbols": len(index),
        },
        "symbols": sorted(index.keys()),
        "timeframes": sorted(TF_MAP.keys()),
    }
    joblib.dump({"model": model, "kind": kind, "feature_schema_id": "v1-basic"}, MODELS / "model.joblib")
    (MODELS / "feature_names.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"train kind={kind} acc={acc:.4f} auc={auc:.4f}")
    return meta


def run_script_variants(index: Dict[str, Dict[str, Path]]) -> List[dict]:
    RESULTS.mkdir(parents=True, exist_ok=True)
    rows = []
    # Prefer daily for multi-year fairness; also 1h if enough bars
    for sym, tfs in index.items():
        for tf in ("1d", "1h"):
            path = tfs.get(tf)
            if not path or not Path(path).exists():
                continue
            df = pd.read_csv(path)
            if len(df) < 120:
                continue
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
            for variant in ("v0", "v1", "v2"):
                pnl, dd, wr, n, _ = backtest_variant(df, variant)
                rows.append(
                    {
                        "variant": variant,
                        "symbol": sym,
                        "timeframe": tf,
                        "pnl": pnl,
                        "max_dd": dd,
                        "winrate": wr,
                        "trades": n,
                    }
                )
                print(f"BT {variant} {sym} {tf}: pnl={pnl:.2f} dd={dd:.2f} wr={wr:.2f} n={n}")

    out = RESULTS / "script_variants_backtest.json"
    out.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")

    # Aggregate: mean pnl by variant
    agg = {}
    for v in ("v0", "v1", "v2"):
        subset = [r for r in rows if r["variant"] == v and r["trades"] >= 5]
        if not subset:
            agg[v] = {"n": 0}
            continue
        agg[v] = {
            "n": len(subset),
            "mean_pnl": float(np.mean([r["pnl"] for r in subset])),
            "mean_dd": float(np.mean([r["max_dd"] for r in subset])),
            "mean_wr": float(np.mean([r["winrate"] for r in subset])),
            "mean_trades": float(np.mean([r["trades"] for r in subset])),
        }
    # Verdict chain
    verdicts = []
    order = ["v0", "v1", "v2"]
    for a, b in zip(order, order[1:]):
        if agg.get(a, {}).get("n", 0) and agg.get(b, {}).get("n", 0):
            better = agg[b]["mean_pnl"] > agg[a]["mean_pnl"] and agg[b]["mean_dd"] <= agg[a]["mean_dd"] * 1.15
            worse = agg[b]["mean_pnl"] < agg[a]["mean_pnl"] and agg[b]["mean_dd"] >= agg[a]["mean_dd"]
            if better:
                ver = "better"
            elif worse:
                ver = "worse"
            else:
                ver = "mixed"
            verdicts.append({"from": a, "to": b, "verdict": ver, "agg_before": agg[a], "agg_after": agg[b]})

    summary = {"aggregates": agg, "verdicts": verdicts, "rows": len(rows)}
    (RESULTS / "variant_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return rows


def write_report(train_meta: dict, bt_rows: List[dict]) -> None:
    summary = json.loads((RESULTS / "variant_summary.json").read_text(encoding="utf-8"))
    lines = [
        "# Session report — SuperTrend + EMA/RSI",
        "",
        f"Дата: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Цель",
        "Обучить сигнал-модель A на мульти-инструмент / мульти-ТФ данных и прогнать улучшения скрипта",
        "(фильтр EMA, ATR SL/TP) с вердиктами better/worse/mixed.",
        "",
        "## Инструменты",
        f"- MOEX акции: {', '.join(MOEX_STOCKS)}",
        f"- MOEX фьючерсы: {', '.join(MOEX_FUTURES)}",
        "- US: SPY, ^GSPC (Yahoo) — прокси S&P500 без брокера",
        f"- ТФ: {', '.join(TF_MAP)}",
        "- История: ~5 лет (где доступно)",
        "",
        "## Signal model",
        f"- kind: `{train_meta['model_kind']}`",
        f"- accuracy: **{train_meta['metrics']['accuracy']:.4f}**",
        f"- roc_auc: **{train_meta['metrics']['roc_auc']:.4f}**",
        f"- n_train/n_test: {train_meta['metrics']['n_train']} / {train_meta['metrics']['n_test']}",
        f"- артефакт: `models/model.joblib`",
        "",
        "## Варианты скрипта (векторный бэктест)",
        "- **v0**: SuperTrend + RSI cross 50 (база)",
        "- **v1**: + фильтр тренда EMA(50)",
        "- **v2**: + ATR SL 1.5 / TP 3.0",
        "",
        "### Агрегаты",
        "```json",
        json.dumps(summary["aggregates"], indent=2, ensure_ascii=False),
        "```",
        "",
        "### Вердикты v0→v1→v2",
        "```json",
        json.dumps(summary["verdicts"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Desktop",
        "`.italgo` для ручного прогона в `ai-train`: `scripts/v0_supertrend_rsi.italgo`,",
        "`scripts/v0_supertrend_di_adx.italgo`. Следующая волна: 10–20 скриптов с другими индикаторами.",
        "",
        "## Важно",
        "1. Больше ТФ (5m/15m) когда ISS/Yahoo отдаёт длинную историю",
        "2. Кормить compare_scripts + trade_analysis из Desktop ingest",
        "3. Ранжировщик графов (контур B) на вердиктах вариантов",
        "",
    ]
    (SESSION / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote", SESSION / "REPORT.md")


def main() -> int:
    SESSION.mkdir(parents=True, exist_ok=True)
    print("=== download ===")
    index = download_all(years=5.0)
    print("=== train signal ===")
    meta = train_signal(index)
    print("=== script variants BT ===")
    rows = run_script_variants(index)
    write_report(meta, rows)
    # notes for agent loop
    (SESSION / "notes.md").write_text(
        "User-directed session: SuperTrend+EMA/RSI multi-asset train.\n"
        "Next: expand to 10–20 indicator families after reviewing REPORT.md.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
