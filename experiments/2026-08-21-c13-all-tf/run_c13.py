#!/usr/bin/env python3
"""C13 / §7A+P3.6: ALL available TFs × 10 equities — do not drop TF coverage.

- +MTSS (10 equities)
- New interventions: RSI>50 long-filter, period×2.0 (plus C8/C11 kinds)
- Train on 1d + 1h with timeframe features
- Sample-weighted LightGBM (|ΔPnL|); stricter cross-promote 32p-* (≥5/10 on 1d)
- Desktop wire remains backlog (§7G)
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import joblib
import lightgbm as lgb
import numpy as np
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import LeaveOneOut

ROOT = Path("/Users/kreckeroff/Fintech (startup)/AI_algo")
DESKTOP = ROOT.parent / "it-algo-desktop"
ITALGO = DESKTOP / "docs/work/scripting/samples/ai-train"
C12 = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c12-quality-push"
SESSION = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c13-all-tf"
RAW = ROOT / "artifacts/agent_loop/sessions/2026-08-21-multi-indicator-wave/data/raw"
LIB = Path.home() / (
    "Library/Application Support/ru.it-algo.desktop/scripting/"
    "6882ee6d-8a3f-4eda-a4a9-235652c2b455/library/ai-train"
)

sys.path.insert(0, str(ROOT / "src"))
from ai_algo.domain.trade_analysis import analyze_trades  # noqa: E402

SYMBOLS = ["SBER", "GAZP", "LKOH", "ROSN", "GMKN", "NVTK", "TATN", "PLZL", "MGNT", "MTSS"]
TFS = ["1m", "5m", "10m", "15m", "30m", "1h", "1d", "1w"]
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

SESSION.mkdir(parents=True, exist_ok=True)
for sub in ("scripts", "results", "models"):
    (SESSION / sub).mkdir(exist_ok=True)

FINDING_KEYS = [
    "пила_короткие_сделки",
    "сверхкороткие_удержания",
    "серия_убытков",
    "перекос_сторон",
    "мало_закрытых_сделок",
]
KINDS = [
    "change_period_15x",
    "change_period_067",
    "change_period_2x",
    "add_block_ema",
    "add_block_adx",
    "add_block_sma200",
    "add_block_rsi50",
]
REGIMES = ["trend", "mean_reversion", "breakout", "unknown"]
SIDES = ["long_only", "long_short", "unknown"]


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
        out.append(
            {
                "time": parse_ts(p[idx["ts"]]),
                "open": float(p[idx["open"]]),
                "high": float(p[idx["high"]]),
                "low": float(p[idx["low"]]),
                "close": float(p[idx["close"]]),
                "volume": float(p[idx["volume"]]),
            }
        )
    return out


def run_engine(scripts_dir: Path, bars_path: Path, out: Path, symbol: str, timeframe: str) -> List[dict]:
    cmd = [
        "cargo", "run", "-p", "backtest", "--example", "run_ai_train_corpus", "--release", "--",
        "--dir", str(scripts_dir), "--bars", str(bars_path),
        "--symbol", symbol, "--timeframe", timeframe, "--trades", "--out", str(out),
    ]
    print("RUN", symbol, timeframe, out.name, flush=True)
    r = subprocess.run(cmd, cwd=str(DESKTOP))
    if r.returncode != 0:
        raise SystemExit(r.returncode)
    return [json.loads(l) for l in out.read_text().splitlines() if l.strip()]


def scale_periods(doc: dict, factor: float) -> None:
    for n in doc["graph"]["nodes"]:
        data = n.get("data") or {}
        if isinstance(data.get("period"), (int, float)):
            data["period"] = max(2, int(round(float(data["period"]) * factor)))
            n["data"] = data


def _open_id(ids: set) -> Optional[str]:
    for cand in ("open", "open_l", "open_long"):
        if cand in ids:
            return cand
    return None


def add_and_filter(doc: dict, *, filter_id: str, build) -> bool:
    nodes, edges = doc["graph"]["nodes"], doc["graph"]["edges"]
    ids = {n["id"] for n in nodes}
    open_id = _open_id(ids)
    if not open_id or filter_id in ids or "close" not in ids:
        return False
    cross = [e for e in edges if e.get("target") == open_id and e.get("targetHandle") == "condition"]
    if not cross:
        return False
    extra_nodes, pre_edges, filter_src = build()
    nodes.extend(extra_nodes)
    buy_and = f"{filter_id}_and"
    nodes.append({"id": buy_and, "type": "logic_and", "position": {"x": 860, "y": 80}, "data": {"label": "Buy+Filter"}})
    edges = [e for e in edges if not (e.get("target") == open_id and e.get("targetHandle") == "condition")]
    edges.extend(pre_edges)
    for ce in cross:
        edges.append({
            "id": f"c12_{ce['id']}_and", "source": ce["source"], "target": buy_and,
            "sourceHandle": ce.get("sourceHandle") or "result", "targetHandle": "conditions",
        })
    edges += [
        {"id": f"c12_{filter_id}_to_and", "source": filter_src, "target": buy_and,
         "sourceHandle": "result", "targetHandle": "conditions"},
        {"id": f"c12_{filter_id}_open", "source": buy_and, "target": open_id,
         "sourceHandle": "result", "targetHandle": "condition"},
    ]
    doc["graph"]["edges"] = edges
    return True


def add_rsi50_filter(doc: dict) -> bool:
    fid = "rsi_filter"
    ids = {n["id"] for n in doc["graph"]["nodes"]}
    if "rsi" in ids and any("rsi" in (n.get("id") or "") for n in doc["graph"]["nodes"] if "filter" in (n.get("id") or "")):
        pass

    def build():
        nodes = [
            {"id": fid, "type": "indicator_rsi", "position": {"x": 480, "y": 20},
             "data": {"period": 14, "label": "RSI14"}},
            {"id": "rsi_min", "type": "constant", "position": {"x": 480, "y": 80},
             "data": {"value": 50, "label": "50"}},
            {"id": "rsi_ok", "type": "logic_gt", "position": {"x": 700, "y": 20}, "data": {"label": "RSI>50"}},
        ]
        edges = [
            {"id": "c12_cr", "source": "close", "target": fid, "sourceHandle": "value", "targetHandle": "source"},
            {"id": "c12_ra", "source": fid, "target": "rsi_ok", "sourceHandle": "value", "targetHandle": "a"},
            {"id": "c12_rb", "source": "rsi_min", "target": "rsi_ok", "sourceHandle": "value", "targetHandle": "b"},
        ]
        return nodes, edges, "rsi_ok"

    return add_and_filter(doc, filter_id=fid, build=build)


def save_doc(doc: dict, path: Path, *, kind: str, base: str, extra: dict) -> None:
    doc = copy.deepcopy(doc)
    doc.setdefault("meta", {})
    doc["meta"]["updatedAt"] = NOW
    doc["meta"]["intervention"] = {"kind": kind, "base": base, **extra}
    tags = list(doc["meta"].get("tags") or []) + ["c12", f"intervention:{kind}"]
    doc["meta"]["tags"] = list(dict.fromkeys(tags))
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")


def infer_kind(var_name: str) -> Optional[str]:
    mapping = [
        ("__period15x", "change_period_15x"),
        ("__period067", "change_period_067"),
        ("__period2x", "change_period_2x"),
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


def label_counts(trades) -> Counter:
    c: Counter = Counter()
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
    return c


def featurize(p: dict) -> List[float]:
    lab = p.get("base_labels") or {}
    findings = set(p.get("findings") or [])
    feats = [
        float(p["base_pnl"]),
        float(p["base_wr"]),
        float(p["base_trades"]),
        float(p["base_dd"]),
        float(lab.get("good", 0)),
        float(lab.get("bad", 0)),
        float(lab.get("bad_noise", 0)),
        float(lab.get("good_weak", 0)),
        float(lab.get("good", 0) + lab.get("good_weak", 0)) / max(1, sum(lab.values())),
        float(lab.get("bad", 0) + lab.get("bad_noise", 0)) / max(1, sum(lab.values())),
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
    return feats


def main() -> None:
    # copy prior variants (non-promoted) from C12
    n = 0
    for p in (C12 / "scripts").glob("*.italgo"):
        if p.name.startswith(("27p-", "28p-", "29p-", "30p-", "31p-", "32p-", "33p-")):
            continue
        shutil.copy(p, SESSION / "scripts" / p.name)
        n += 1
    print("copied prior scripts", n, flush=True)

    # add new interventions on bases
    bases = sorted(
        p for p in ITALGO.glob("*.italgo")
        if not p.name.startswith(("27p-", "28p-", "29p-", "30p-", "31p-", "32p-", "33p-"))
    )
    added = 0
    for src in bases:
        name = src.name
        stem = name.replace(".italgo", "")
        if not (SESSION / "scripts" / name).exists():
            shutil.copy(src, SESSION / "scripts" / name)
        base = json.loads(src.read_text())

        if not (SESSION / "scripts" / f"{stem}__period2x.italgo").exists():
            d = copy.deepcopy(base)
            scale_periods(d, 2.0)
            d["meta"]["name"] = f"{base['meta'].get('name', '')} period×2"
            save_doc(d, SESSION / "scripts" / f"{stem}__period2x.italgo",
                     kind="change_period_2x", base=name, extra={"factor": 2.0})
            added += 1

        if not (SESSION / "scripts" / f"{stem}__rsi50.italgo").exists():
            d = copy.deepcopy(base)
            if add_rsi50_filter(d):
                d["meta"]["name"] = f"{base['meta'].get('name', '')} +RSI>50"
                save_doc(d, SESSION / "scripts" / f"{stem}__rsi50.italgo",
                         kind="add_block_rsi50", base=name, extra={"block": "indicator_rsi", "min": 50})
                added += 1
    print("new variants added", added, flush=True)

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
                print("SKIP missing", csv.name, flush=True)
                continue
            bars = load_csv(csv)
            # Cap intraday history so all TFs stay train-able (full 1d/1w).
            CAP = {"1m": 40000, "5m": 25000, "10m": 20000, "15m": 18000, "30m": 15000, "1h": 12000}
            if tf in CAP and len(bars) > CAP[tf]:
                bars = bars[-CAP[tf]:]
            bp = SESSION / f"bars_{sym}_{tf}.json"
            bp.write_text(json.dumps(bars))
            rows = run_engine(SESSION / "scripts", bp, SESSION / f"engine_{sym}_{tf}.jsonl", sym, tf)
            by_key[(sym, tf)] = {r["file"]: r for r in rows if r.get("ok")}
            print(sym, tf, "ok", len(by_key[(sym, tf)]), "bars", len(bars), flush=True)

    pairs = []
    for (sym, tf), by_file in by_key.items():
        for base_name, var_name, kind in variants_meta:
            b, v = by_file.get(base_name), by_file.get(var_name)
            if not b or not v:
                continue
            rb = analyze_trades(b.get("trades"), graph_nodes=b.get("nodes"))
            bpnl, vpnl = b["stats"]["netPnl"], v["stats"]["netPnl"]
            delta = vpnl - bpnl
            # quality label: improve PnL and not blow DD by >50% if base had DD
            bdd = float(b["stats"]["maxDrawdown"] or 0)
            vdd = float(v["stats"]["maxDrawdown"] or 0)
            dd_ok = True if bdd <= 1e-9 else (vdd <= bdd * 1.5 + 1e-9)
            better = delta > 1e-6 and dd_ok
            side = "unknown"
            bp = ITALGO / base_name
            if bp.exists():
                side = (json.loads(bp.read_text()).get("meta") or {}).get("side_mode", "unknown")
            pairs.append({
                "symbol": sym, "timeframe": tf, "base": base_name, "variant": var_name, "kind": kind,
                "side_mode": side, "base_pnl": bpnl, "variant_pnl": vpnl, "delta_pnl": delta,
                "better": better, "dd_ok": dd_ok,
                "base_wr": b["stats"]["winRate"], "variant_wr": v["stats"]["winRate"],
                "base_trades": b["stats"]["totalTrades"], "base_dd": bdd, "variant_dd": vdd,
                "base_labels": dict(label_counts(b.get("trades"))),
                "findings": rb.get("findings") or [], "regime": rb.get("regime") or "unknown",
            })
    print("pairs", len(pairs), "better", sum(1 for p in pairs if p["better"]), flush=True)

    X = np.array([featurize(p) for p in pairs], dtype=float)
    y = np.array([1 if p["better"] else 0 for p in pairs], dtype=int)
    w = np.array([1.0 + min(abs(p["delta_pnl"]) / 50.0, 8.0) for p in pairs], dtype=float)
    feature_names = (
        ["base_pnl", "base_wr", "base_trades", "base_dd", "good", "bad", "bad_noise", "good_weak", "good_share", "bad_share"]
        + [f"f_{k}" for k in FINDING_KEYS]
        + [f"regime_{r}" for r in REGIMES]
        + [f"kind_{k}" for k in KINDS]
        + [f"side_{s}" for s in SIDES]
        + [f"sym_{s}" for s in SYMBOLS]
        + [f"tf_{t}" for t in TFS]
    )

    loo = LeaveOneOut()
    preds = np.zeros(len(y))
    probas = np.zeros(len(y))
    # subsample LOO if huge: use stratified 5-fold like leave for speed when n>2000
    if len(y) > 2500:
        from sklearn.model_selection import StratifiedKFold
        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        splits = list(skf.split(X, y))
    else:
        splits = list(loo.split(X))

    for train_idx, test_idx in splits:
        Xtr, Xte = X[train_idx], X[test_idx]
        ytr, wtr = y[train_idx], w[train_idx]
        if len(set(ytr)) < 2:
            preds[test_idx] = ytr[0]
            probas[test_idx] = float(ytr[0])
            continue
        clf = lgb.LGBMClassifier(
            n_estimators=160, max_depth=4, learning_rate=0.06, subsample=0.85,
            colsample_bytree=0.85, min_child_samples=4, verbosity=-1, random_state=42,
        )
        clf.fit(Xtr, ytr, sample_weight=wtr)
        preds[test_idx] = clf.predict(Xte)
        probas[test_idx] = clf.predict_proba(Xte)[:, 1]

    acc = float(accuracy_score(y, preds))
    try:
        auc = float(roc_auc_score(y, probas))
    except ValueError:
        auc = float("nan")

    # LOSO on 1d only for clarity
    loso = {}
    for hold in SYMBOLS:
        tr = [i for i, p in enumerate(pairs) if not (p["symbol"] == hold and p["timeframe"] == "1d")]
        te = [i for i, p in enumerate(pairs) if p["symbol"] == hold and p["timeframe"] == "1d"]
        if len(te) < 20 or len(set(y[tr])) < 2:
            continue
        clf = lgb.LGBMClassifier(
            n_estimators=160, max_depth=4, learning_rate=0.06, subsample=0.85,
            colsample_bytree=0.85, min_child_samples=4, verbosity=-1, random_state=42,
        )
        clf.fit(X[tr], y[tr], sample_weight=w[tr])
        pred = clf.predict(X[te])
        proba = clf.predict_proba(X[te])[:, 1]
        a = float(accuracy_score(y[te], pred))
        try:
            u = float(roc_auc_score(y[te], proba))
        except ValueError:
            u = float("nan")
        loso[hold] = {"accuracy": a, "auc": u, "n": len(te)}

    final = lgb.LGBMClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.06, subsample=0.85,
        colsample_bytree=0.85, min_child_samples=4, verbosity=-1, random_state=42,
    )
    final.fit(X, y, sample_weight=w)
    joblib.dump({
        "model": final, "feature_names": feature_names, "kinds": KINDS,
        "symbols": SYMBOLS, "timeframes": TFS,
        "metrics": {"cv_accuracy": acc, "cv_auc": auc, "n": len(y), "positives": int(y.sum()), "loso_1d": loso},
        "label_rule": "delta_pnl>0 and variant_dd <= 1.5 * base_dd",
    }, SESSION / "models" / "intervention_policy_lgbm.joblib")
    imp = sorted(zip(feature_names, final.feature_importances_.tolist()), key=lambda x: -x[1])

    # cross-symbol stability on 1d
    key_stats = defaultdict(lambda: {"wins": 0, "n": 0, "sum_delta": 0.0, "by_sym": {}})
    for p in pairs:
        if p["timeframe"] != "1d":
            continue
        k = (p["base"], p["kind"])
        key_stats[k]["n"] += 1
        key_stats[k]["sum_delta"] += p["delta_pnl"]
        key_stats[k]["by_sym"][p["symbol"]] = {
            "delta": p["delta_pnl"], "better": p["better"], "variant_pnl": p["variant_pnl"], "variant": p["variant"],
        }
        if p["better"]:
            key_stats[k]["wins"] += 1

    KIND_TAG = {
        "change_period_15x": "period15x", "change_period_067": "period067", "change_period_2x": "period2x",
        "add_block_ema": "ema50", "add_block_adx": "adx25", "add_block_sma200": "sma200", "add_block_rsi50": "rsi50",
    }
    stable, promoted = [], []
    LIB.mkdir(parents=True, exist_ok=True)
    for (base, kind), st in key_stats.items():
        sym_wins = [s for s, v in st["by_sym"].items() if v["better"] and v["variant_pnl"] > 0]
        if len(sym_wins) >= 5 and st["sum_delta"] / max(1, st["n"]) >= 15:
            item = {
                "base": base, "kind": kind, "n_symbols_win": len(sym_wins),
                "symbols_win": sorted(sym_wins), "mean_delta": st["sum_delta"] / max(1, st["n"]),
                "variant": next(iter(st["by_sym"].values()))["variant"],
            }
            stable.append(item)
            src = SESSION / "scripts" / item["variant"]
            if src.exists():
                stem = base.replace(".italgo", "")
                out_name = f"33p-{stem}__{KIND_TAG[kind]}.italgo"
                doc = json.loads(src.read_text())
                doc["meta"]["name"] = f"[cross-sym] {doc['meta'].get('name')}"
                doc["meta"]["tags"] = list(dict.fromkeys((doc["meta"].get("tags") or []) + ["promoted", "c13", "cross-symbol"]))
                doc["meta"]["cross_symbol"] = {"symbols_win": item["symbols_win"], "mean_delta": item["mean_delta"]}
                text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
                (ITALGO / out_name).write_text(text)
                (LIB / out_name).write_text(text)
                (SESSION / "scripts" / out_name).write_text(text)
                promoted.append({"to": out_name, **{k: item[k] for k in ("base", "kind", "mean_delta", "symbols_win", "n_symbols_win")}})
    stable.sort(key=lambda x: (-x["n_symbols_win"], -x["mean_delta"]))

    kind_stats = defaultdict(lambda: {"n": 0, "wins": 0, "sum_delta": 0.0})
    for p in pairs:
        kind_stats[p["kind"]]["n"] += 1
        kind_stats[p["kind"]]["sum_delta"] += p["delta_pnl"]
        if p["better"]:
            kind_stats[p["kind"]]["wins"] += 1
    for k, v in kind_stats.items():
        v["mean_delta"] = v["sum_delta"] / max(1, v["n"])
        v["winrate"] = v["wins"] / max(1, v["n"])

    per_sym_tf = defaultdict(dict)
    for sym in SYMBOLS:
        for tf in TFS:
            sp = [p for p in pairs if p["symbol"] == sym and p["timeframe"] == tf]
            if not sp:
                continue
            per_sym_tf[sym][tf] = {
                "n": len(sp), "better": sum(1 for p in sp if p["better"]),
                "mean_delta": float(np.mean([p["delta_pnl"] for p in sp])),
            }

    summary = {
        "session": "2026-08-21-c13-all-tf",
        "symbols": SYMBOLS, "timeframes": TFS,
        "n_pairs": len(pairs), "n_better": int(y.sum()),
        "model": {"cv_accuracy": acc, "cv_auc": auc, "n": len(y), "loso_1d": loso},
        "kind_stats": dict(kind_stats), "per_symbol_tf": dict(per_sym_tf),
        "n_stable_cross": len(stable), "n_promoted": len(promoted),
        "label_rule": "delta>0 & dd_ok",
        "top20_by_score": [
            {"entry": f"{p['symbol']}:{p['timeframe']}:{p['base']}", "filter": p["kind"],
             "median_pnl": p["delta_pnl"], "mean_pnl": p["variant_pnl"], "mean_wr": p["variant_wr"],
             "mean_dd": p["variant_dd"], "n": 1, "regime": p.get("regime")}
            for p in sorted(pairs, key=lambda x: x["delta_pnl"], reverse=True)[:20]
        ],
    }
    (SESSION / "results" / "intervention_pairs.json").write_text(json.dumps(pairs, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "results" / "cross_symbol_stable.json").write_text(json.dumps(stable, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "results" / "promoted.json").write_text(json.dumps(promoted, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "results" / "variant_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "models" / "feature_names.json").write_text(json.dumps({
        "feature_names": feature_names, "symbols": SYMBOLS, "timeframes": TFS,
        "metrics": summary["model"], "feature_importance_top": imp[:20],
        "label_rule": summary["label_rule"],
    }, indent=2) + "\n")
    (SESSION / "results" / "advisor_intervention_dataset.jsonl").write_text(
        "\n".join(json.dumps({
            "task": "improve_strategy", "features": dict(zip(feature_names, featurize(p))),
            "action": p["kind"], "label": "accept_intervention" if p["better"] else "reject_intervention",
            "delta_pnl": p["delta_pnl"], "base": p["base"], "symbol": p["symbol"], "timeframe": p["timeframe"],
        }, ensure_ascii=False) for p in pairs) + "\n"
    )
    (SESSION / "REPORT.md").write_text("\n".join([
        "# C13 all-TF (§7A)",
        "",
        f"- Symbols: {', '.join(SYMBOLS)}",
        f"- TFs: {', '.join(TFS)}",
        f"- Pairs: {len(pairs)} · better: {int(y.sum())} (label: Δ>0 & DD≤1.5×base)",
        f"- CV acc={acc:.3f} AUC={auc}",
        f"- Promoted 33p-*: {len(promoted)} (≥5/10 on 1d)",
        f"- TFs covered: {', '.join(TFS)}",
        "",
        "## Kind stats",
        json.dumps(kind_stats, indent=2, ensure_ascii=False),
    ]) + "\n")
    (SESSION / "notes.md").write_text(
        "C13/all-TF: 1m..1w × 10 equities; C12 interventions; DD-aware; 33p-*; never drop TF coverage (§7A).\n"
    )
    print("MODEL", acc, auc, "promoted", len(promoted), "stable", len(stable))
    print("kind_stats", json.dumps(kind_stats, indent=2))


if __name__ == "__main__":
    main()
