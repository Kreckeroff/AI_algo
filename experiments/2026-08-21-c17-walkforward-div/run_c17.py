#!/usr/bin/env python3
"""C17: walk-forward by year + §7H dividend-adjusted labels/features on C16 corpus (fast)."""
from __future__ import annotations

import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import joblib
import lightgbm as lgb
import numpy as np
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold

ROOT = Path("/Users/kreckeroff/Fintech (startup)/AI_algo")
DESKTOP = ROOT.parent / "it-algo-desktop"
ITALGO = DESKTOP / "docs/work/scripting/samples/ai-train"
C16 = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c16-atr-sltp"
SESSION = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c17-walkforward-div"
LIB = Path.home() / (
    "Library/Application Support/ru.it-algo.desktop/scripting/"
    "6882ee6d-8a3f-4eda-a4a9-235652c2b455/library/ai-train"
)

sys.path.insert(0, str(ROOT / "src"))
from ai_algo.domain.buy_hold import evaluate_vs_buy_hold  # noqa: E402
from ai_algo.domain.dividends import (  # noqa: E402
    adjust_trades,
    events_in_window,
    load_dividend_cache,
)
from ai_algo.domain.trade_analysis import analyze_trades  # noqa: E402

EQUITIES = ["SBER", "GAZP", "LKOH", "ROSN", "GMKN", "NVTK", "TATN", "PLZL", "MGNT", "MTSS"]
FUTURES = ["CNYRUBF", "GLDRUBF", "IMOEXF"]
SYMBOLS = EQUITIES + FUTURES
TFS = ["1m", "5m", "10m", "15m", "30m", "1h", "1d", "1w"]
WF_TFS = {"1d", "1h"}  # year-slices only on these (speed)
WF_SLICE_YEARS = [2021, 2022, 2023, 2024, 2025, 2026]  # build year pairs (incl. train-only)
WF_TEST_YEARS = [2023, 2024, 2025, 2026]
FINDING_KEYS = [
    "пила_короткие_сделки", "сверхкороткие_удержания", "серия_убытков",
    "перекос_сторон", "мало_закрытых_сделок", "псевдо_buy_hold",
]
KINDS = [
    "change_period_15x", "change_period_067", "change_period_2x", "change_period_05x",
    "add_block_ema", "add_block_adx", "add_block_sma200", "add_block_rsi50",
    "add_block_atr_sltp", "remove_block_filter",
]
REGIMES = ["trend", "mean_reversion", "breakout", "unknown"]
SIDES = ["long_only", "long_short", "unknown"]
PROMO_PREFIXES = tuple(f"{i}p-" for i in range(27, 38))
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

SESSION.mkdir(parents=True, exist_ok=True)
for sub in ("scripts", "results", "models"):
    (SESSION / sub).mkdir(exist_ok=True)


def infer_kind(var_name: str) -> Optional[str]:
    mapping = [
        ("__atrsltp", "add_block_atr_sltp"),
        ("__rmfilter", "remove_block_filter"),
        ("__period15x", "change_period_15x"),
        ("__period067", "change_period_067"),
        ("__period2x", "change_period_2x"),
        ("__period05x", "change_period_05x"),
        ("__ema50", "add_block_ema"),
        ("__adx25", "add_block_adx"),
        ("__sma200", "add_block_sma200"),
        ("__rsi50", "add_block_rsi50"),
    ]
    for suf, kind in mapping:
        if suf in var_name:
            return kind
    return None


def base_of_variant(var_name: str) -> Optional[str]:
    if "__" not in var_name:
        return None
    return var_name.split("__", 1)[0] + ".italgo"


def trade_year(t: dict) -> Optional[int]:
    et = t.get("exitTime") or t.get("entryTime")
    if et is None:
        return None
    return datetime.fromtimestamp(int(et), tz=timezone.utc).year


def filter_trades_by_year(trades: Sequence[dict], year: Optional[int]) -> List[dict]:
    if year is None:
        return list(trades or [])
    return [t for t in (trades or []) if trade_year(t) == year]


def bars_for_year(bars: Sequence[dict], year: Optional[int]) -> List[dict]:
    if year is None:
        return list(bars)
    out = []
    for b in bars:
        y = datetime.fromtimestamp(int(b["time"]), tz=timezone.utc).year
        if y == year:
            out.append(b)
    return out


def net_pnl_from_trades(trades: Sequence[dict], *, use_div_adj: bool) -> float:
    total = 0.0
    for t in trades or []:
        if use_div_adj and t.get("pnl_div_adjusted") is not None:
            total += float(t["pnl_div_adjusted"])
        elif t.get("pnl") is not None:
            total += float(t["pnl"])
    return total


def win_rate(trades: Sequence[dict], *, use_div_adj: bool) -> float:
    closed = []
    for t in trades or []:
        if use_div_adj and t.get("pnl_div_adjusted") is not None:
            closed.append(float(t["pnl_div_adjusted"]))
        elif t.get("pnl") is not None:
            closed.append(float(t["pnl"]))
    if not closed:
        return 0.0
    return sum(1 for p in closed if p > 0) / len(closed)


def label_counts(trades: Sequence[dict], *, use_div_adj: bool) -> dict:
    c: Dict[str, int] = defaultdict(int)
    for t in trades or []:
        if use_div_adj and t.get("pnl_div_adjusted") is not None:
            pnl = float(t["pnl_div_adjusted"])
        elif t.get("pnl") is not None:
            pnl = float(t["pnl"])
        else:
            c["open"] += 1
            continue
        h = t.get("barsHeld")
        h = float(h) if h is not None else None
        if pnl > 0:
            c["good_weak" if h is not None and h <= 1 else "good"] += 1
        elif pnl < 0:
            c["bad_noise" if h is not None and h <= 2 else "bad"] += 1
        else:
            c["flat"] += 1
    return dict(c)


def buy_hold_with_div(bars: Sequence[dict], events: Sequence[dict]) -> Optional[float]:
    if not bars or len(bars) < 2:
        return None
    raw = float(bars[-1]["close"]) - float(bars[0]["open"])
    cash = sum(float(e.get("dividend_rub") or 0.0) for e in events_in_window(
        events, int(bars[0]["time"]), int(bars[-1]["time"])
    ))
    return raw + cash


def resolve_side_mode(file_name: str, trades: List[dict]) -> str:
    for base in (ITALGO / file_name, C16 / "scripts" / file_name):
        if base.exists():
            sm = (json.loads(base.read_text()).get("meta") or {}).get("side_mode")
            if sm:
                return str(sm)
    if "-ls" in file_name:
        return "long_short"
    has_short = any((t.get("side") or "").lower() in ("sell", "short") for t in trades or [])
    return "long_short" if has_short else "long_only"


def prepare_trades(
    trades: Sequence[dict],
    *,
    symbol: str,
    events_by_sym: Dict[str, List[dict]],
) -> Tuple[List[dict], Dict[str, float]]:
    raw = list(trades or [])
    if symbol in FUTURES or symbol not in events_by_sym:
        out = []
        for t in raw:
            pnl = float(t["pnl"]) if t.get("pnl") is not None else None
            out.append({
                **t,
                "crossed_ex_div": False,
                "div_cash_adjust": 0.0,
                "pnl_raw": pnl,
                "pnl_div_adjusted": pnl,
            })
        pnl_sum = sum(t["pnl_div_adjusted"] for t in out if t.get("pnl_div_adjusted") is not None)
        return out, {
            "n_trades": float(len(out)),
            "n_crossed": 0.0,
            "n_short_crossed": 0.0,
            "pnl_raw": float(pnl_sum),
            "pnl_div_adjusted": float(pnl_sum),
            "delta_from_div": 0.0,
        }
    return adjust_trades(raw, events_by_sym[symbol])


def with_pnl(trades: List[dict], *, use_div: bool) -> List[dict]:
    out = []
    for t in trades:
        tt = dict(t)
        if use_div and t.get("pnl_div_adjusted") is not None:
            tt["pnl"] = t["pnl_div_adjusted"]
        out.append(tt)
    return out


FEATURE_NAMES = (
    ["base_pnl", "base_wr", "base_trades", "base_dd", "good", "bad", "bad_noise", "good_weak", "good_share", "bad_share",
     "buy_hold_pnl", "base_edge_vs_bh", "base_beats_bh", "base_pseudo_bh",
     "base_n_crossed", "base_n_short_crossed", "base_div_cash", "base_frac_crossed", "base_near_ex_div",
     "window_div_events", "window_div_cash", "year"]
    + [f"f_{k}" for k in FINDING_KEYS]
    + [f"regime_{r}" for r in REGIMES]
    + [f"kind_{k}" for k in KINDS]
    + [f"side_{s}" for s in SIDES]
    + [f"sym_{s}" for s in SYMBOLS]
    + [f"tf_{t}" for t in TFS]
    + ["is_future"]
)


def featurize(p: dict) -> List[float]:
    lab = p.get("base_labels") or {}
    findings = set(p.get("findings") or [])
    feats = [
        float(p["base_pnl"]), float(p["base_wr"]), float(p["base_trades"]), float(p["base_dd"]),
        float(lab.get("good", 0)), float(lab.get("bad", 0)), float(lab.get("bad_noise", 0)), float(lab.get("good_weak", 0)),
        float(lab.get("good", 0) + lab.get("good_weak", 0)) / max(1, sum(lab.values()) or 1),
        float(lab.get("bad", 0) + lab.get("bad_noise", 0)) / max(1, sum(lab.values()) or 1),
        float(p.get("buy_hold_pnl") or 0.0),
        float(p.get("base_edge_vs_bh") or 0.0),
        1.0 if p.get("base_beats_buy_hold") else 0.0,
        1.0 if p.get("base_pseudo_buy_hold") else 0.0,
        float(p.get("base_n_crossed") or 0.0),
        float(p.get("base_n_short_crossed") or 0.0),
        float(p.get("base_div_cash") or 0.0),
        float(p.get("base_frac_crossed") or 0.0),
        1.0 if p.get("base_near_ex_div") else 0.0,
        float(p.get("window_div_events") or 0.0),
        float(p.get("window_div_cash") or 0.0),
        float(p.get("year") or 0.0),
    ]
    for k in FINDING_KEYS:
        feats.append(1.0 if k in findings else 0.0)
    for r in REGIMES:
        feats.append(1.0 if p.get("regime") == r else 0.0)
    for k in KINDS:
        feats.append(1.0 if p.get("kind") == k else 0.0)
    for s in SIDES:
        feats.append(1.0 if p.get("side_mode") == s else 0.0)
    for sym in SYMBOLS:
        feats.append(1.0 if p.get("symbol") == sym else 0.0)
    for tf in TFS:
        feats.append(1.0 if p.get("timeframe") == tf else 0.0)
    feats.append(1.0 if p.get("symbol") in FUTURES else 0.0)
    return feats


def build_pair(
    *,
    sym: str,
    tf: str,
    year: Optional[int],
    base_name: str,
    var_name: str,
    kind: str,
    b_tr_full: List[dict],
    v_tr_full: List[dict],
    b_dd: float,
    v_dd: float,
    bars_full: List[dict],
    events_by_sym: Dict[str, List[dict]],
    findings: List[str],
    regime: str,
    side: str,
) -> Optional[dict]:
    bars = bars_for_year(bars_full, year)
    if len(bars) < 10:
        return None
    b_tr = filter_trades_by_year(b_tr_full, year)
    v_tr = filter_trades_by_year(v_tr_full, year)
    if year is not None and not b_tr and not v_tr:
        return None

    use_div = sym in EQUITIES
    bpnl = net_pnl_from_trades(b_tr, use_div_adj=use_div)
    vpnl = net_pnl_from_trades(v_tr, use_div_adj=use_div)
    delta = vpnl - bpnl
    dd_ok = True if b_dd <= 1e-9 else (v_dd <= b_dd * 1.5 + 1e-9)

    ev = events_by_sym.get(sym, [])
    win_ev = events_in_window(ev, int(bars[0]["time"]), int(bars[-1]["time"])) if use_div else []
    bh = buy_hold_with_div(bars, win_ev) if use_div else None

    base_bh = evaluate_vs_buy_hold(
        bars=bars, trades=with_pnl(b_tr, use_div=use_div), side_mode=side, net_pnl=bpnl
    )
    var_bh = evaluate_vs_buy_hold(
        bars=bars, trades=with_pnl(v_tr, use_div=use_div), side_mode=side, net_pnl=vpnl
    )
    if use_div and bh is not None:
        base_bh = dict(base_bh)
        var_bh = dict(var_bh)
        base_bh["buy_hold_pnl"] = bh
        var_bh["buy_hold_pnl"] = bh
        if side == "long_only":
            base_cmp = float(base_bh.get("long_trades_pnl") or 0.0)
            var_cmp = float(var_bh.get("long_trades_pnl") or 0.0)
        else:
            base_cmp, var_cmp = bpnl, vpnl
        base_bh["edge_vs_bh"] = base_cmp - bh
        var_bh["edge_vs_bh"] = var_cmp - bh
        base_bh["beats_buy_hold"] = base_cmp > bh
        var_bh["beats_buy_hold"] = var_cmp > bh

    base_edge = float(base_bh.get("edge_vs_bh") or 0.0)
    var_edge = float(var_bh.get("edge_vs_bh") or 0.0)
    delta_edge = var_edge - base_edge

    findings_out = list(findings)
    if var_bh.get("pseudo_buy_hold"):
        findings_out = list(dict.fromkeys(findings_out + ["псевдо_buy_hold"]))

    better = (
        delta > 1e-6 and dd_ok and delta_edge > 1e-6
        and bool(var_bh.get("beats_buy_hold"))
        and not bool(var_bh.get("pseudo_buy_hold"))
    )

    n_tr = len(b_tr)
    n_cross = sum(1 for t in b_tr if t.get("crossed_ex_div"))
    n_short_cross = sum(
        1 for t in b_tr
        if t.get("crossed_ex_div") and (t.get("side") or "").lower() in ("sell", "short")
    )
    div_cash = sum(float(t.get("div_cash_adjust") or 0.0) for t in b_tr)

    return {
        "symbol": sym, "timeframe": tf, "year": year if year is not None else 0,
        "base": base_name, "variant": var_name, "kind": kind,
        "asset_class": "future" if sym in FUTURES else "equity",
        "side_mode": side,
        "base_pnl": bpnl, "variant_pnl": vpnl, "delta_pnl": delta,
        "better": better, "dd_ok": dd_ok,
        "base_wr": win_rate(b_tr, use_div_adj=use_div),
        "variant_wr": win_rate(v_tr, use_div_adj=use_div),
        "base_trades": float(n_tr), "base_dd": b_dd, "variant_dd": v_dd,
        "base_labels": label_counts(b_tr, use_div_adj=use_div),
        "findings": findings_out, "regime": regime,
        "buy_hold_pnl": base_bh.get("buy_hold_pnl"),
        "base_edge_vs_bh": base_edge, "variant_edge_vs_bh": var_edge,
        "delta_edge_vs_bh": delta_edge,
        "base_beats_buy_hold": bool(base_bh.get("beats_buy_hold")),
        "variant_beats_buy_hold": bool(var_bh.get("beats_buy_hold")),
        "base_pseudo_buy_hold": bool(base_bh.get("pseudo_buy_hold")),
        "variant_pseudo_buy_hold": bool(var_bh.get("pseudo_buy_hold")),
        "base_n_crossed": float(n_cross),
        "base_n_short_crossed": float(n_short_cross),
        "base_div_cash": float(div_cash),
        "base_frac_crossed": float(n_cross) / max(1, n_tr),
        "base_near_ex_div": bool(n_cross > 0 or win_ev),
        "window_div_events": float(len(win_ev)),
        "window_div_cash": float(sum(float(e.get("dividend_rub") or 0) for e in win_ev)),
    }


def train_eval(pairs: List[dict], *, tag: str) -> Dict[str, Any]:
    if len(pairs) < 50:
        return {"tag": tag, "n": len(pairs), "skipped": True}
    X = np.array([featurize(p) for p in pairs], dtype=float)
    y = np.array([1 if p["better"] else 0 for p in pairs], dtype=int)
    if len(set(y.tolist())) < 2:
        return {"tag": tag, "n": len(pairs), "skipped": True, "positives": int(y.sum())}
    w = np.array([
        1.0 + min(abs(p["delta_pnl"]) / 50.0, 6.0) + min(abs(p.get("delta_edge_vs_bh") or 0) / 50.0, 4.0)
        for p in pairs
    ], dtype=float)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    preds = np.zeros(len(y))
    probas = np.zeros(len(y))
    for train_idx, test_idx in skf.split(X, y):
        clf = lgb.LGBMClassifier(
            n_estimators=180, max_depth=5, learning_rate=0.06, subsample=0.85,
            colsample_bytree=0.85, min_child_samples=6, verbosity=-1, random_state=42,
        )
        clf.fit(X[train_idx], y[train_idx], sample_weight=w[train_idx])
        preds[test_idx] = clf.predict(X[test_idx])
        probas[test_idx] = clf.predict_proba(X[test_idx])[:, 1]
    acc = float(accuracy_score(y, preds))
    try:
        auc = float(roc_auc_score(y, probas))
    except ValueError:
        auc = float("nan")
    return {
        "tag": tag, "n": len(y), "positives": int(y.sum()), "better_rate": float(y.mean()),
        "cv_accuracy": acc, "cv_auc": auc, "skipped": False,
    }


def main() -> None:
    events_by_sym = load_dividend_cache()
    print("div symbols", sorted(events_by_sym.keys()), flush=True)

    variants_meta: List[Tuple[str, str, str]] = []
    for p in sorted((C16 / "scripts").glob("*__*.italgo")):
        if p.name.startswith(PROMO_PREFIXES):
            continue
        kind = infer_kind(p.name)
        base = base_of_variant(p.name)
        if kind and base and (C16 / "scripts" / base).exists():
            variants_meta.append((base, p.name, kind))
    print("variants", len(variants_meta), flush=True)

    for p in (C16 / "scripts").glob("*.italgo"):
        if not p.name.startswith(PROMO_PREFIXES):
            shutil.copy(p, SESSION / "scripts" / p.name)

    # side_mode cache
    side_cache: Dict[str, str] = {}
    for base, _, _ in variants_meta:
        if base not in side_cache:
            side_cache[base] = resolve_side_mode(base, [])

    pairs_full: List[dict] = []
    pairs_by_year: Dict[int, List[dict]] = defaultdict(list)
    needed_files = set()
    for base, var, _ in variants_meta:
        needed_files.add(base)
        needed_files.add(var)

    engines = sorted(C16.glob("engine_*.jsonl"))
    for ei, eng in enumerate(engines, 1):
        parts = eng.stem.split("_")
        if len(parts) < 3:
            continue
        sym, tf = parts[1], parts[2]
        bars_path = C16 / f"bars_{sym}_{tf}.json"
        if not bars_path.exists():
            print("SKIP bars", sym, tf, flush=True)
            continue
        bars = json.loads(bars_path.read_text())
        by_file: Dict[str, dict] = {}
        for line in eng.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("ok") and r["file"] in needed_files:
                by_file[r["file"]] = r

        # pre-adjust trades once per file
        adj: Dict[str, List[dict]] = {}
        for fname, row in by_file.items():
            tr, _ = prepare_trades(row.get("trades") or [], symbol=sym, events_by_sym=events_by_sym)
            adj[fname] = tr

        # analyze_trades once per base (full window only)
        analysis: Dict[str, dict] = {}
        for base_name, _, _ in variants_meta:
            if base_name in analysis or base_name not in adj:
                continue
            # subsample huge trade lists for speed
            tr = adj[base_name]
            sample = tr if len(tr) <= 800 else tr[:: max(1, len(tr) // 800)]
            analysis[base_name] = analyze_trades(
                with_pnl(sample, use_div=sym in EQUITIES),
                graph_nodes=(by_file[base_name].get("nodes") if base_name in by_file else None),
            )

        n_full = n_year = 0
        for base_name, var_name, kind in variants_meta:
            if base_name not in adj or var_name not in adj:
                continue
            b_row, v_row = by_file[base_name], by_file[var_name]
            rb = analysis.get(base_name) or {}
            side = side_cache.get(base_name) or resolve_side_mode(base_name, adj[base_name])
            full = build_pair(
                sym=sym, tf=tf, year=None, base_name=base_name, var_name=var_name, kind=kind,
                b_tr_full=adj[base_name], v_tr_full=adj[var_name],
                b_dd=float((b_row.get("stats") or {}).get("maxDrawdown") or 0),
                v_dd=float((v_row.get("stats") or {}).get("maxDrawdown") or 0),
                bars_full=bars, events_by_sym=events_by_sym,
                findings=list(rb.get("findings") or []),
                regime=rb.get("regime") or "unknown",
                side=side,
            )
            if full:
                pairs_full.append(full)
                n_full += 1
            if tf in WF_TFS:
                for y in WF_SLICE_YEARS:
                    py = build_pair(
                        sym=sym, tf=tf, year=y, base_name=base_name, var_name=var_name, kind=kind,
                        b_tr_full=adj[base_name], v_tr_full=adj[var_name],
                        b_dd=float((b_row.get("stats") or {}).get("maxDrawdown") or 0),
                        v_dd=float((v_row.get("stats") or {}).get("maxDrawdown") or 0),
                        bars_full=bars, events_by_sym=events_by_sym,
                        findings=list(rb.get("findings") or []),
                        regime=rb.get("regime") or "unknown",
                        side=side,
                    )
                    if py:
                        pairs_by_year[y].append(py)
                        n_year += 1
        print(f"[{ei}/{len(engines)}] {sym} {tf} full+={n_full} year+={n_year}", flush=True)

    print(
        "pairs_full", len(pairs_full), "better", sum(1 for p in pairs_full if p["better"]),
        "by_year", {y: len(v) for y, v in sorted(pairs_by_year.items())},
        flush=True,
    )

    wf_results = []
    for test_year in WF_TEST_YEARS:
        train_pairs = [p for y, plist in pairs_by_year.items() if y < test_year for p in plist]
        test_pairs = pairs_by_year.get(test_year) or []
        if len(train_pairs) < 80 or len(test_pairs) < 40:
            wf_results.append({
                "test_year": test_year, "n_train": len(train_pairs), "n_test": len(test_pairs), "skipped": True,
            })
            continue
        Xtr = np.array([featurize(p) for p in train_pairs], dtype=float)
        ytr = np.array([1 if p["better"] else 0 for p in train_pairs], dtype=int)
        Xte = np.array([featurize(p) for p in test_pairs], dtype=float)
        yte = np.array([1 if p["better"] else 0 for p in test_pairs], dtype=int)
        if len(set(ytr.tolist())) < 2 or len(set(yte.tolist())) < 2:
            wf_results.append({
                "test_year": test_year, "n_train": len(train_pairs), "n_test": len(test_pairs), "skipped": True,
            })
            continue
        wtr = np.array([
            1.0 + min(abs(p["delta_pnl"]) / 50.0, 6.0) + min(abs(p.get("delta_edge_vs_bh") or 0) / 50.0, 4.0)
            for p in train_pairs
        ], dtype=float)
        clf = lgb.LGBMClassifier(
            n_estimators=200, max_depth=5, learning_rate=0.06, subsample=0.85,
            colsample_bytree=0.85, min_child_samples=6, verbosity=-1, random_state=42,
        )
        clf.fit(Xtr, ytr, sample_weight=wtr)
        pred = clf.predict(Xte)
        proba = clf.predict_proba(Xte)[:, 1]
        acc = float(accuracy_score(yte, pred))
        try:
            auc = float(roc_auc_score(yte, proba))
        except ValueError:
            auc = float("nan")
        wf_results.append({
            "test_year": test_year,
            "n_train": len(train_pairs), "n_test": len(test_pairs),
            "train_better_rate": float(ytr.mean()), "test_better_rate": float(yte.mean()),
            "oos_accuracy": acc, "oos_auc": auc, "skipped": False,
        })
        print("WF", test_year, "acc", round(acc, 3), "auc", round(auc, 3) if auc == auc else auc,
              "n_te", len(yte), flush=True)

    full_cv = train_eval(pairs_full, tag="full_window_div")
    year_cv = train_eval([p for ys in pairs_by_year.values() for p in ys], tag="year_sliced_1d_1h")
    print("FULL_CV", full_cv, flush=True)
    print("YEAR_CV", year_cv, flush=True)

    X = np.array([featurize(p) for p in pairs_full], dtype=float)
    y = np.array([1 if p["better"] else 0 for p in pairs_full], dtype=int)
    w = np.array([
        1.0 + min(abs(p["delta_pnl"]) / 50.0, 6.0) + min(abs(p.get("delta_edge_vs_bh") or 0) / 50.0, 4.0)
        for p in pairs_full
    ], dtype=float)
    final = lgb.LGBMClassifier(
        n_estimators=240, max_depth=5, learning_rate=0.06, subsample=0.85,
        colsample_bytree=0.85, min_child_samples=6, verbosity=-1, random_state=42,
    )
    final.fit(X, y, sample_weight=w)
    imp = sorted(zip(FEATURE_NAMES, final.feature_importances_.tolist()), key=lambda x: -x[1])

    joblib.dump({
        "model": final, "feature_names": list(FEATURE_NAMES), "kinds": KINDS,
        "symbols": SYMBOLS, "timeframes": TFS,
        "metrics": {
            "full_cv": full_cv, "year_pooled_cv": year_cv, "walk_forward": wf_results,
            "n": len(y), "positives": int(y.sum()),
        },
        "label_rule": "div-adj ΔPnL>0 & DD-ok & Δedge_vs_bh>0 & beats BH(div) & !pseudo (§7I+§7H)",
    }, SESSION / "models" / "intervention_policy_lgbm.joblib")

    KIND_TAG = {
        "change_period_15x": "period15x", "change_period_067": "period067",
        "change_period_2x": "period2x", "change_period_05x": "period05x",
        "add_block_ema": "ema50", "add_block_adx": "adx25", "add_block_sma200": "sma200",
        "add_block_rsi50": "rsi50", "add_block_atr_sltp": "atrsltp", "remove_block_filter": "rmfilter",
    }
    key_stats = defaultdict(lambda: {"wins": 0, "n": 0, "sum_delta": 0.0, "sum_edge": 0.0, "by_sym": {}})
    for p in pairs_full:
        if p["timeframe"] != "1d":
            continue
        k = (p["base"], p["kind"])
        key_stats[k]["n"] += 1
        key_stats[k]["sum_delta"] += p["delta_pnl"]
        key_stats[k]["sum_edge"] += float(p.get("delta_edge_vs_bh") or 0)
        key_stats[k]["by_sym"][p["symbol"]] = {
            "delta": p["delta_pnl"], "better": p["better"], "variant_pnl": p["variant_pnl"],
            "variant": p["variant"], "beats_bh": p.get("variant_beats_buy_hold"),
        }
        if p["better"]:
            key_stats[k]["wins"] += 1

    stable, promoted = [], []
    LIB.mkdir(parents=True, exist_ok=True)
    for (base, kind), st in key_stats.items():
        sym_wins = [s for s, v in st["by_sym"].items() if v["better"] and v["variant_pnl"] > 0 and v.get("beats_bh")]
        mean_delta = st["sum_delta"] / max(1, st["n"])
        mean_edge = st["sum_edge"] / max(1, st["n"])
        if len(sym_wins) >= 6 and mean_delta >= 15 and mean_edge > 0:
            item = {
                "base": base, "kind": kind, "n_symbols_win": len(sym_wins),
                "symbols_win": sorted(sym_wins), "mean_delta": mean_delta,
                "mean_delta_edge_vs_bh": mean_edge,
                "variant": next(iter(st["by_sym"].values()))["variant"],
            }
            stable.append(item)
            src = SESSION / "scripts" / item["variant"]
            if src.exists():
                stem = base.replace(".italgo", "")
                out_name = f"37p-{stem}__{KIND_TAG[kind]}.italgo"
                doc = json.loads(src.read_text())
                doc["meta"]["name"] = f"[WF+div] {doc['meta'].get('name')}"
                doc["meta"]["updatedAt"] = NOW
                doc["meta"]["tags"] = list(dict.fromkeys(
                    (doc["meta"].get("tags") or []) + ["promoted", "c17", "cross-symbol", "beats-buyhold", "div-adj"]
                ))
                doc["meta"]["cross_symbol"] = {
                    "symbols_win": item["symbols_win"], "mean_delta": item["mean_delta"],
                    "mean_delta_edge_vs_bh": item["mean_delta_edge_vs_bh"],
                }
                text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
                (ITALGO / out_name).write_text(text)
                (LIB / out_name).write_text(text)
                (SESSION / "scripts" / out_name).write_text(text)
                promoted.append({"to": out_name, **{k: item[k] for k in (
                    "base", "kind", "mean_delta", "mean_delta_edge_vs_bh", "symbols_win", "n_symbols_win"
                )}})
    stable.sort(key=lambda x: (-x["n_symbols_win"], -x["mean_delta_edge_vs_bh"]))

    kind_stats = defaultdict(lambda: {"n": 0, "wins": 0, "sum_delta": 0.0, "sum_edge": 0.0})
    for p in pairs_full:
        kind_stats[p["kind"]]["n"] += 1
        kind_stats[p["kind"]]["sum_delta"] += p["delta_pnl"]
        kind_stats[p["kind"]]["sum_edge"] += float(p.get("delta_edge_vs_bh") or 0)
        if p["better"]:
            kind_stats[p["kind"]]["wins"] += 1
    for k, v in kind_stats.items():
        v["mean_delta"] = v["sum_delta"] / max(1, v["n"])
        v["mean_delta_edge"] = v["sum_edge"] / max(1, v["n"])
        v["winrate"] = v["wins"] / max(1, v["n"])

    heat = defaultdict(lambda: {"n": 0, "better": 0})
    for p in pairs_full:
        if p["asset_class"] != "equity":
            continue
        key = f"near={int(bool(p.get('base_near_ex_div')))}|side={p.get('side_mode')}"
        heat[key]["n"] += 1
        if p["better"]:
            heat[key]["better"] += 1
    for v in heat.values():
        v["better_rate"] = v["better"] / max(1, v["n"])

    summary = {
        "session": "2026-08-21-c17-walkforward-div",
        "symbols": SYMBOLS, "timeframes": TFS, "wf_tfs": sorted(WF_TFS),
        "n_pairs_full": len(pairs_full), "n_better_full": int(y.sum()),
        "full_cv": full_cv, "year_pooled_cv": year_cv, "walk_forward": wf_results,
        "kind_stats": dict(kind_stats), "near_ex_div_heatmap": dict(heat),
        "n_promoted": len(promoted),
        "label_rule": "div-adj ΔPnL>0 & DD-ok & Δedge_vs_bh>0 & beats BH(div) & !pseudo (§7I+§7H)",
    }

    (SESSION / "results" / "intervention_pairs.json").write_text(
        json.dumps(pairs_full, indent=2, ensure_ascii=False) + "\n"
    )
    (SESSION / "results" / "pairs_by_year.json").write_text(json.dumps(
        {str(y): len(v) for y, v in sorted(pairs_by_year.items())}, indent=2
    ) + "\n")
    (SESSION / "results" / "walk_forward.json").write_text(json.dumps(wf_results, indent=2) + "\n")
    (SESSION / "results" / "cross_symbol_stable.json").write_text(
        json.dumps(stable, indent=2, ensure_ascii=False) + "\n"
    )
    (SESSION / "results" / "promoted.json").write_text(
        json.dumps(promoted, indent=2, ensure_ascii=False) + "\n"
    )
    (SESSION / "results" / "variant_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    )
    (SESSION / "results" / "near_ex_div_heatmap.json").write_text(
        json.dumps(dict(heat), indent=2, ensure_ascii=False) + "\n"
    )
    (SESSION / "models" / "feature_names.json").write_text(json.dumps({
        "feature_names": list(FEATURE_NAMES), "symbols": SYMBOLS, "timeframes": TFS,
        "metrics": summary, "feature_importance_top": imp[:30],
        "label_rule": summary["label_rule"],
    }, indent=2) + "\n")

    wf_lines = [
        f"- {r['test_year']}: "
        + ("skipped" if r.get("skipped") else f"OOS acc={r['oos_accuracy']:.3f} AUC={r['oos_auc']:.3f} "
           f"(train {r['n_train']} → test {r['n_test']})")
        for r in wf_results
    ]
    (SESSION / "REPORT.md").write_text("\n".join([
        "# C17 walk-forward + §7H div features",
        "",
        f"- Full-window pairs: {len(pairs_full)} · better: {int(y.sum())} ({100 * y.mean():.1f}%)",
        f"- Full CV: acc={full_cv.get('cv_accuracy')} AUC={full_cv.get('cv_auc')}",
        f"- Year-pooled CV (1d+1h): acc={year_cv.get('cv_accuracy')} AUC={year_cv.get('cv_auc')}",
        f"- Promoted 37p-*: {len(promoted)}",
        "",
        "## Walk-forward (1d+1h)",
        *wf_lines,
        "",
        "## near_ex_div × side",
        json.dumps(dict(heat), indent=2, ensure_ascii=False),
    ]) + "\n")
    (SESSION / "notes.md").write_text(
        "C17: C16 engines; div-adj labels/features (§7H); WF by exit year on 1d+1h; 37p-*.\n"
    )
    print("MODEL", full_cv.get("cv_accuracy"), full_cv.get("cv_auc"), "promoted", len(promoted), flush=True)
    print("WF", wf_results, flush=True)


if __name__ == "__main__":
    main()
