#!/usr/bin/env python3
"""C16: new intervention kinds ATR SL/TP + remove-filter; §7I BH labels; all TF×symbols."""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import lightgbm as lgb
import numpy as np
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold

ROOT = Path("/Users/kreckeroff/Fintech (startup)/AI_algo")
DESKTOP = ROOT.parent / "it-algo-desktop"
ITALGO = DESKTOP / "docs/work/scripting/samples/ai-train"
C14 = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c14-futures-expand"
C15 = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c15-buyhold-policy"
SESSION = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c16-atr-sltp"
RAW = ROOT / "artifacts/agent_loop/sessions/2026-08-21-multi-indicator-wave/data/raw"
LIB = Path.home() / (
    "Library/Application Support/ru.it-algo.desktop/scripting/"
    "6882ee6d-8a3f-4eda-a4a9-235652c2b455/library/ai-train"
)

sys.path.insert(0, str(ROOT / "src"))
from ai_algo.domain.buy_hold import evaluate_vs_buy_hold  # noqa: E402
from ai_algo.domain.trade_analysis import analyze_trades  # noqa: E402

EQUITIES = ["SBER", "GAZP", "LKOH", "ROSN", "GMKN", "NVTK", "TATN", "PLZL", "MGNT", "MTSS"]
FUTURES = ["CNYRUBF", "GLDRUBF", "IMOEXF"]
SYMBOLS = EQUITIES + FUTURES
TFS = ["1m", "5m", "10m", "15m", "30m", "1h", "1d", "1w"]
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

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
PROMO_PREFIXES = ("27p-", "28p-", "29p-", "30p-", "31p-", "32p-", "33p-", "34p-", "35p-", "36p-")

SESSION.mkdir(parents=True, exist_ok=True)
for sub in ("scripts", "results", "models"):
    (SESSION / sub).mkdir(exist_ok=True)


def parse_ts(s: str) -> int:
    core = s.strip().replace("T", " ").split("+")[0].split("Z")[0].strip()
    return int(datetime.strptime(core, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())


def load_csv(path: Path) -> List[dict]:
    lines = path.read_text().strip().splitlines()
    hdr = [h.strip() for h in lines[0].split(",")]
    idx = {h: i for i, h in enumerate(hdr)}
    out = []
    for line in lines[1:]:
        p = line.split(",")
        out.append({
            "time": parse_ts(p[idx["ts"]]),
            "open": float(p[idx["open"]]),
            "high": float(p[idx["high"]]),
            "low": float(p[idx["low"]]),
            "close": float(p[idx["close"]]),
            "volume": float(p[idx["volume"]]),
        })
    return out


def run_engine(scripts_dir: Path, bars_path: Path, out: Path, symbol: str, timeframe: str) -> List[dict]:
    cmd = [
        "cargo", "run", "-p", "backtest", "--example", "run_ai_train_corpus", "--release", "--",
        "--dir", str(scripts_dir), "--bars", str(bars_path),
        "--symbol", symbol, "--timeframe", timeframe, "--trades", "--out", str(out),
    ]
    print("RUN", symbol, timeframe, flush=True)
    r = subprocess.run(cmd, cwd=str(DESKTOP))
    if r.returncode != 0:
        raise SystemExit(r.returncode)
    return [json.loads(l) for l in out.read_text().splitlines() if l.strip()]


def save_doc(doc: dict, path: Path, *, kind: str, base: str, extra: dict) -> None:
    doc = copy.deepcopy(doc)
    doc.setdefault("meta", {})
    doc["meta"]["updatedAt"] = NOW
    doc["meta"]["intervention"] = {"kind": kind, "base": base, **extra}
    tags = list(doc["meta"].get("tags") or []) + ["c16", f"intervention:{kind}"]
    doc["meta"]["tags"] = list(dict.fromkeys(tags))
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")


def add_atr_sl_tp(doc: dict) -> bool:
    nodes, edges = doc["graph"]["nodes"], doc["graph"]["edges"]
    types = {n["type"] for n in nodes}
    if "position_close_sl" in types or "position_close_tp" in types:
        return False
    ids = {n["id"] for n in nodes}
    # only single long open
    opens = [
        n for n in nodes
        if n["type"] == "position_open_market"
        and (n.get("data") or {}).get("direction", "buy") == "buy"
    ]
    if len(opens) != 1:
        return False
    open_id = opens[0]["id"]
    if any(x in ids for x in ("atr_c16", "sl_c16", "tp_c16")):
        return False
    if "close" not in ids:
        return False
    # ensure entry price node
    entry_id = "entry_c16"
    if "entry" in ids:
        entry_id = "entry"
    elif entry_id not in ids:
        nodes.append({
            "id": entry_id, "type": "position_entry_price",
            "position": {"x": 920, "y": 200}, "data": {"label": "Entry"},
        })
        edges.append({
            "id": "c16_open_entry", "source": open_id, "target": entry_id,
            "sourceHandle": "position", "targetHandle": "position",
        })
    # ATR block
    if "atr" not in ids:
        nodes.append({
            "id": "atr_c16", "type": "indicator_atr",
            "position": {"x": 480, "y": 280}, "data": {"period": 14, "label": "ATR14"},
        })
        atr_id = "atr_c16"
        edges.append({
            "id": "c16_inst_atr", "source": "instrument", "target": atr_id,
            "sourceHandle": "instrument", "targetHandle": "instrument",
        })
    else:
        atr_id = "atr"
    nodes.extend([
        {"id": "atr_sl_c16", "type": "math_mul_const", "position": {"x": 700, "y": 320},
         "data": {"label": "ATR×1.5", "mult": 1.5}},
        {"id": "atr_tp_c16", "type": "math_mul_const", "position": {"x": 700, "y": 440},
         "data": {"label": "ATR×3", "mult": 3.0}},
        {"id": "sl_lvl_c16", "type": "math_sub", "position": {"x": 920, "y": 320},
         "data": {"label": "SL=entry−ATR"}},
        {"id": "tp_lvl_c16", "type": "math_add", "position": {"x": 920, "y": 440},
         "data": {"label": "TP=entry+ATR"}},
        {"id": "sl_c16", "type": "position_close_sl", "position": {"x": 1140, "y": 300},
         "data": {"label": "SL"}},
        {"id": "tp_c16", "type": "position_close_tp", "position": {"x": 1140, "y": 440},
         "data": {"label": "TP"}},
    ])
    edges.extend([
        {"id": "c16_atr_sl", "source": atr_id, "target": "atr_sl_c16", "sourceHandle": "value", "targetHandle": "a"},
        {"id": "c16_atr_tp", "source": atr_id, "target": "atr_tp_c16", "sourceHandle": "value", "targetHandle": "a"},
        {"id": "c16_e_sl_a", "source": entry_id, "target": "sl_lvl_c16", "sourceHandle": "value", "targetHandle": "a"},
        {"id": "c16_e_sl_b", "source": "atr_sl_c16", "target": "sl_lvl_c16", "sourceHandle": "value", "targetHandle": "b"},
        {"id": "c16_e_tp_a", "source": entry_id, "target": "tp_lvl_c16", "sourceHandle": "value", "targetHandle": "a"},
        {"id": "c16_e_tp_b", "source": "atr_tp_c16", "target": "tp_lvl_c16", "sourceHandle": "value", "targetHandle": "b"},
        {"id": "c16_o_sl", "source": open_id, "target": "sl_c16", "sourceHandle": "position", "targetHandle": "position"},
        {"id": "c16_lvl_sl", "source": "sl_lvl_c16", "target": "sl_c16", "sourceHandle": "value", "targetHandle": "level"},
        {"id": "c16_o_tp", "source": open_id, "target": "tp_c16", "sourceHandle": "position", "targetHandle": "position"},
        {"id": "c16_lvl_tp", "source": "tp_lvl_c16", "target": "tp_c16", "sourceHandle": "value", "targetHandle": "level"},
    ])
    doc["graph"]["edges"] = edges
    return True


def remove_block_filter(doc: dict) -> bool:
    """Unwrap logic_and feeding a long open: keep primary cross/break signal only."""
    nodes, edges = doc["graph"]["nodes"], doc["graph"]["edges"]
    opens = [
        n["id"] for n in nodes
        if n["type"] == "position_open_market"
        and (n.get("data") or {}).get("direction", "buy") == "buy"
    ]
    if len(opens) != 1:
        return False
    open_id = opens[0]
    cond_edges = [e for e in edges if e.get("target") == open_id and e.get("targetHandle") == "condition"]
    if len(cond_edges) != 1:
        return False
    and_id = cond_edges[0]["source"]
    and_node = next((n for n in nodes if n["id"] == and_id and n["type"] == "logic_and"), None)
    if not and_node:
        return False
    inbound = [e for e in edges if e.get("target") == and_id]
    if len(inbound) < 2:
        return False
    def score(src: str) -> int:
        s = src.lower()
        for i, key in enumerate(("cross", "break", "donch", "macd", "mom", "rsi", "stoch", "buy", "signal")):
            if key in s:
                return 100 - i
        return 0
    inbound_sorted = sorted(inbound, key=lambda e: -score(e.get("source") or ""))
    keep = inbound_sorted[0]
    # reconnect keep -> open
    new_edges = [e for e in edges if e.get("target") != and_id and not (e.get("target") == open_id and e.get("targetHandle") == "condition")]
    new_edges.append({
        "id": f"c16_rm_{keep['id']}",
        "source": keep["source"],
        "target": open_id,
        "sourceHandle": keep.get("sourceHandle") or "result",
        "targetHandle": "condition",
    })
    # drop the and node
    doc["graph"]["nodes"] = [n for n in nodes if n["id"] != and_id]
    doc["graph"]["edges"] = new_edges
    return True


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


def label_counts(trades) -> dict:
    c = defaultdict(int)
    for t in trades or []:
        pnl = t.get("pnl")
        if pnl is None:
            c["open"] += 1
            continue
        p = float(pnl)
        h = t.get("barsHeld")
        h = float(h) if h is not None else None
        if p > 0:
            c["good_weak" if h is not None and h <= 1 else "good"] += 1
        elif p < 0:
            c["bad_noise" if h is not None and h <= 2 else "bad"] += 1
        else:
            c["flat"] += 1
    return dict(c)


def resolve_side_mode(file_name: str, trades: List[dict], fallback: str) -> str:
    if fallback and fallback != "unknown":
        return fallback
    for base in (ITALGO / file_name, SESSION / "scripts" / file_name, C14 / "scripts" / file_name):
        if base.exists():
            sm = (json.loads(base.read_text()).get("meta") or {}).get("side_mode")
            if sm:
                return str(sm)
    if "-ls" in file_name:
        return "long_short"
    has_short = any((t.get("side") or "").lower() in ("sell", "short") for t in trades or [])
    return "long_short" if has_short else "long_only"


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


def main() -> None:
    # copy prior non-promoted from C14
    n = 0
    for p in (C14 / "scripts").glob("*.italgo"):
        if p.name.startswith(PROMO_PREFIXES):
            continue
        shutil.copy(p, SESSION / "scripts" / p.name)
        n += 1
    print("copied", n, flush=True)

    bases = sorted(
        p for p in ITALGO.glob("*.italgo")
        if not p.name.startswith(PROMO_PREFIXES) and "__" not in p.name
    )
    added = 0
    for src in bases:
        name = src.name
        stem = name.replace(".italgo", "")
        if not (SESSION / "scripts" / name).exists():
            shutil.copy(src, SESSION / "scripts" / name)
        base = json.loads(src.read_text())

        out_atr = SESSION / "scripts" / f"{stem}__atrsltp.italgo"
        if not out_atr.exists():
            d = copy.deepcopy(base)
            if add_atr_sl_tp(d):
                d["meta"]["name"] = f"{base['meta'].get('name', '')} +ATR SL/TP"
                save_doc(d, out_atr, kind="add_block_atr_sltp", base=name, extra={"sl_mult": 1.5, "tp_mult": 3.0})
                added += 1

        out_rm = SESSION / "scripts" / f"{stem}__rmfilter.italgo"
        if not out_rm.exists():
            d = copy.deepcopy(base)
            if remove_block_filter(d):
                d["meta"]["name"] = f"{base['meta'].get('name', '')} −filter"
                save_doc(d, out_rm, kind="remove_block_filter", base=name, extra={})
                added += 1
    print("new variants", added, flush=True)

    variants_meta: List[Tuple[str, str, str]] = []
    for p in sorted((SESSION / "scripts").glob("*__*.italgo")):
        kind = infer_kind(p.name)
        base = base_of_variant(p.name)
        if kind and base and (SESSION / "scripts" / base).exists():
            variants_meta.append((base, p.name, kind))
    print("variants", len(variants_meta), flush=True)

    by_key: Dict[Tuple[str, str], Dict[str, dict]] = {}
    for sym in SYMBOLS:
        for tf in TFS:
            csv = RAW / f"MOEX_{sym}_{tf}.csv"
            if not csv.exists():
                print("SKIP", csv.name, flush=True)
                continue
            # reuse C14 bars if present (same CAP logic)
            c14b = C14 / f"bars_{sym}_{tf}.json"
            if c14b.exists():
                bars = json.loads(c14b.read_text())
            else:
                bars = load_csv(csv)
                CAP = {"1m": 40000, "5m": 25000, "10m": 20000, "15m": 18000, "30m": 15000, "1h": 12000}
                if tf in CAP and len(bars) > CAP[tf]:
                    bars = bars[-CAP[tf]:]
            bp = SESSION / f"bars_{sym}_{tf}.json"
            bp.write_text(json.dumps(bars))
            rows = run_engine(SESSION / "scripts", bp, SESSION / f"engine_{sym}_{tf}.jsonl", sym, tf)
            by_key[(sym, tf)] = {r["file"]: r for r in rows if r.get("ok")}
            print(sym, tf, "ok", len(by_key[(sym, tf)]), flush=True)

    pairs = []
    for (sym, tf), by_file in by_key.items():
        bars = json.loads((SESSION / f"bars_{sym}_{tf}.json").read_text())
        for base_name, var_name, kind in variants_meta:
            b, v = by_file.get(base_name), by_file.get(var_name)
            if not b or not v:
                continue
            rb = analyze_trades(b.get("trades"), graph_nodes=b.get("nodes"))
            side = resolve_side_mode(base_name, b.get("trades") or [], "unknown")
            bp_path = ITALGO / base_name
            if bp_path.exists():
                side = (json.loads(bp_path.read_text()).get("meta") or {}).get("side_mode", side) or side

            base_bh = evaluate_vs_buy_hold(bars=bars, trades=b.get("trades") or [], side_mode=side, net_pnl=b["stats"]["netPnl"])
            var_bh = evaluate_vs_buy_hold(bars=bars, trades=v.get("trades") or [], side_mode=side, net_pnl=v["stats"]["netPnl"])

            bpnl, vpnl = b["stats"]["netPnl"], v["stats"]["netPnl"]
            delta = vpnl - bpnl
            bdd = float(b["stats"]["maxDrawdown"] or 0)
            vdd = float(v["stats"]["maxDrawdown"] or 0)
            dd_ok = True if bdd <= 1e-9 else (vdd <= bdd * 1.5 + 1e-9)
            base_edge = float(base_bh.get("edge_vs_bh") or 0.0)
            var_edge = float(var_bh.get("edge_vs_bh") or 0.0)
            delta_edge = var_edge - base_edge
            findings = list(rb.get("findings") or [])
            if var_bh.get("pseudo_buy_hold"):
                findings = list(dict.fromkeys(findings + ["псевдо_buy_hold"]))

            better = (
                delta > 1e-6 and dd_ok and delta_edge > 1e-6
                and bool(var_bh.get("beats_buy_hold"))
                and not bool(var_bh.get("pseudo_buy_hold"))
            )
            pairs.append({
                "symbol": sym, "timeframe": tf, "base": base_name, "variant": var_name, "kind": kind,
                "asset_class": "future" if sym in FUTURES else "equity",
                "side_mode": side,
                "base_pnl": bpnl, "variant_pnl": vpnl, "delta_pnl": delta,
                "better": better, "dd_ok": dd_ok,
                "base_wr": b["stats"]["winRate"], "variant_wr": v["stats"]["winRate"],
                "base_trades": b["stats"]["totalTrades"], "base_dd": bdd, "variant_dd": vdd,
                "base_labels": label_counts(b.get("trades")),
                "findings": findings, "regime": rb.get("regime") or "unknown",
                "buy_hold_pnl": base_bh.get("buy_hold_pnl"),
                "base_edge_vs_bh": base_edge, "variant_edge_vs_bh": var_edge,
                "delta_edge_vs_bh": delta_edge,
                "base_beats_buy_hold": bool(base_bh.get("beats_buy_hold")),
                "variant_beats_buy_hold": bool(var_bh.get("beats_buy_hold")),
                "base_pseudo_buy_hold": bool(base_bh.get("pseudo_buy_hold")),
                "variant_pseudo_buy_hold": bool(var_bh.get("pseudo_buy_hold")),
            })
    print("pairs", len(pairs), "better", sum(1 for p in pairs if p["better"]), flush=True)

    X = np.array([featurize(p) for p in pairs], dtype=float)
    y = np.array([1 if p["better"] else 0 for p in pairs], dtype=int)
    w = np.array([
        1.0 + min(abs(p["delta_pnl"]) / 50.0, 6.0) + min(abs(p.get("delta_edge_vs_bh") or 0) / 50.0, 4.0)
        for p in pairs
    ], dtype=float)
    feature_names = (
        ["base_pnl", "base_wr", "base_trades", "base_dd", "good", "bad", "bad_noise", "good_weak", "good_share", "bad_share",
         "buy_hold_pnl", "base_edge_vs_bh", "base_beats_bh", "base_pseudo_bh"]
        + [f"f_{k}" for k in FINDING_KEYS]
        + [f"regime_{r}" for r in REGIMES]
        + [f"kind_{k}" for k in KINDS]
        + [f"side_{s}" for s in SIDES]
        + [f"sym_{s}" for s in SYMBOLS]
        + [f"tf_{t}" for t in TFS]
        + ["is_future"]
    )

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    preds = np.zeros(len(y)); probas = np.zeros(len(y))
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

    loso = {}
    for hold in SYMBOLS:
        tr = [i for i, p in enumerate(pairs) if not (p["symbol"] == hold and p["timeframe"] == "1d")]
        te = [i for i, p in enumerate(pairs) if p["symbol"] == hold and p["timeframe"] == "1d"]
        if len(te) < 20 or len(set(y[tr])) < 2:
            continue
        clf = lgb.LGBMClassifier(
            n_estimators=180, max_depth=5, learning_rate=0.06, subsample=0.85,
            colsample_bytree=0.85, min_child_samples=6, verbosity=-1, random_state=42,
        )
        clf.fit(X[tr], y[tr], sample_weight=w[tr])
        pred = clf.predict(X[te]); proba = clf.predict_proba(X[te])[:, 1]
        a = float(accuracy_score(y[te], pred))
        try:
            u = float(roc_auc_score(y[te], proba))
        except ValueError:
            u = float("nan")
        loso[hold] = {"accuracy": a, "auc": u, "n": len(te)}

    final = lgb.LGBMClassifier(
        n_estimators=220, max_depth=5, learning_rate=0.06, subsample=0.85,
        colsample_bytree=0.85, min_child_samples=6, verbosity=-1, random_state=42,
    )
    final.fit(X, y, sample_weight=w)
    joblib.dump({
        "model": final, "feature_names": feature_names, "kinds": KINDS,
        "symbols": SYMBOLS, "timeframes": TFS,
        "metrics": {"cv_accuracy": acc, "cv_auc": auc, "n": len(y), "positives": int(y.sum()), "loso_1d": loso},
        "label_rule": "delta>0 & dd_ok & Δedge_vs_bh>0 & variant_beats_BH & !pseudo (§7I)",
    }, SESSION / "models" / "intervention_policy_lgbm.joblib")
    imp = sorted(zip(feature_names, final.feature_importances_.tolist()), key=lambda x: -x[1])

    KIND_TAG = {
        "change_period_15x": "period15x", "change_period_067": "period067",
        "change_period_2x": "period2x", "change_period_05x": "period05x",
        "add_block_ema": "ema50", "add_block_adx": "adx25", "add_block_sma200": "sma200",
        "add_block_rsi50": "rsi50", "add_block_atr_sltp": "atrsltp", "remove_block_filter": "rmfilter",
    }
    key_stats = defaultdict(lambda: {"wins": 0, "n": 0, "sum_delta": 0.0, "sum_edge": 0.0, "by_sym": {}})
    for p in pairs:
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
                out_name = f"36p-{stem}__{KIND_TAG[kind]}.italgo"
                doc = json.loads(src.read_text())
                doc["meta"]["name"] = f"[cross-sym+BH] {doc['meta'].get('name')}"
                doc["meta"]["tags"] = list(dict.fromkeys(
                    (doc["meta"].get("tags") or []) + ["promoted", "c16", "cross-symbol", "beats-buyhold"]
                ))
                doc["meta"]["cross_symbol"] = {
                    "symbols_win": item["symbols_win"], "mean_delta": item["mean_delta"],
                    "mean_delta_edge_vs_bh": item["mean_delta_edge_vs_bh"],
                }
                text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
                (ITALGO / out_name).write_text(text)
                (LIB / out_name).write_text(text)
                (SESSION / "scripts" / out_name).write_text(text)
                promoted.append({"to": out_name, **{k: item[k] for k in ("base", "kind", "mean_delta", "mean_delta_edge_vs_bh", "symbols_win", "n_symbols_win")}})
    stable.sort(key=lambda x: (-x["n_symbols_win"], -x["mean_delta_edge_vs_bh"]))

    kind_stats = defaultdict(lambda: {"n": 0, "wins": 0, "sum_delta": 0.0, "sum_edge": 0.0})
    for p in pairs:
        kind_stats[p["kind"]]["n"] += 1
        kind_stats[p["kind"]]["sum_delta"] += p["delta_pnl"]
        kind_stats[p["kind"]]["sum_edge"] += float(p.get("delta_edge_vs_bh") or 0)
        if p["better"]:
            kind_stats[p["kind"]]["wins"] += 1
    for k, v in kind_stats.items():
        v["mean_delta"] = v["sum_delta"] / max(1, v["n"])
        v["mean_delta_edge"] = v["sum_edge"] / max(1, v["n"])
        v["winrate"] = v["wins"] / max(1, v["n"])

    new_kind_pairs = [p for p in pairs if p["kind"] in ("add_block_atr_sltp", "remove_block_filter")]
    summary = {
        "session": "2026-08-21-c16-atr-sltp",
        "symbols": SYMBOLS, "timeframes": TFS,
        "n_pairs": len(pairs), "n_better": int(y.sum()),
        "new_kinds_n": len(new_kind_pairs),
        "new_kinds_better": sum(1 for p in new_kind_pairs if p["better"]),
        "model": {"cv_accuracy": acc, "cv_auc": auc, "n": len(y), "loso_1d": loso},
        "kind_stats": dict(kind_stats),
        "n_promoted": len(promoted),
        "label_rule": "delta>0 & dd_ok & Δedge_vs_bh>0 & variant_beats_BH & !pseudo (§7I)",
    }
    (SESSION / "results" / "intervention_pairs.json").write_text(json.dumps(pairs, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "results" / "cross_symbol_stable.json").write_text(json.dumps(stable, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "results" / "promoted.json").write_text(json.dumps(promoted, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "results" / "variant_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "models" / "feature_names.json").write_text(json.dumps({
        "feature_names": feature_names, "symbols": SYMBOLS, "timeframes": TFS,
        "metrics": summary["model"], "feature_importance_top": imp[:25],
        "label_rule": summary["label_rule"],
    }, indent=2) + "\n")
    (SESSION / "REPORT.md").write_text("\n".join([
        "# C16 ATR SL/TP + remove-filter (§7I)",
        "",
        f"- Pairs: {len(pairs)} · better: {int(y.sum())} ({100*y.mean():.1f}%)",
        f"- New-kind pairs: {len(new_kind_pairs)} · better: {sum(1 for p in new_kind_pairs if p['better'])}",
        f"- CV acc={acc:.3f} AUC={auc}",
        f"- Promoted 36p-*: {len(promoted)}",
        "",
        "## Kind stats",
        json.dumps(kind_stats, indent=2, ensure_ascii=False),
    ]) + "\n")
    (SESSION / "notes.md").write_text(
        "C16: +add_block_atr_sltp + remove_block_filter; BH-aware labels; 36p-*; all TF×symbols.\n"
    )
    print("MODEL", acc, auc, "promoted", len(promoted), "new_better", sum(1 for p in new_kind_pairs if p["better"]))
    print("kind_stats", {k: {"wr": v["winrate"], "n": v["n"]} for k, v in kind_stats.items()})


if __name__ == "__main__":
    main()
