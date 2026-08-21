#!/usr/bin/env python3
"""C15 / P3.8: retrain intervention policy with buy&hold-aware labels (§7I).

Reuses C14 engines/bars/pairs — no full re-backtest.
Label better = ΔPnL>0 & DD-ok & edge_vs_bh improves & variant beats B&H
  (for unknown side_mode: treat as long_only if no shorts else long_short).
Promote 35p-* when cross-symbol wins include BH beat.
"""
from __future__ import annotations

import copy
import json
import shutil
import sys
from collections import Counter, defaultdict
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
SESSION = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c15-buyhold-policy"
LIB = Path.home() / (
    "Library/Application Support/ru.it-algo.desktop/scripting/"
    "6882ee6d-8a3f-4eda-a4a9-235652c2b455/library/ai-train"
)

sys.path.insert(0, str(ROOT / "src"))
from ai_algo.domain.buy_hold import evaluate_vs_buy_hold  # noqa: E402

EQUITIES = ["SBER", "GAZP", "LKOH", "ROSN", "GMKN", "NVTK", "TATN", "PLZL", "MGNT", "MTSS"]
FUTURES = ["CNYRUBF", "GLDRUBF", "IMOEXF"]
SYMBOLS = EQUITIES + FUTURES
TFS = ["1m", "5m", "10m", "15m", "30m", "1h", "1d", "1w"]
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

FINDING_KEYS = [
    "пила_короткие_сделки",
    "сверхкороткие_удержания",
    "серия_убытков",
    "перекос_сторон",
    "мало_закрытых_сделок",
    "псевдо_buy_hold",
]
KINDS = [
    "change_period_15x",
    "change_period_067",
    "change_period_2x",
    "change_period_05x",
    "add_block_ema",
    "add_block_adx",
    "add_block_sma200",
    "add_block_rsi50",
]
REGIMES = ["trend", "mean_reversion", "breakout", "unknown"]
SIDES = ["long_only", "long_short", "unknown"]

SESSION.mkdir(parents=True, exist_ok=True)
for sub in ("scripts", "results", "models"):
    (SESSION / sub).mkdir(exist_ok=True)


def resolve_side_mode(file_name: str, trades: List[dict], fallback: str) -> str:
    if fallback and fallback != "unknown":
        return fallback
    for base in (ITALGO / file_name, C14 / "scripts" / file_name):
        if base.exists():
            sm = (json.loads(base.read_text()).get("meta") or {}).get("side_mode")
            if sm:
                return str(sm)
    if "-ls" in file_name or file_name.endswith("-ls.italgo"):
        return "long_short"
    has_short = any((t.get("side") or "").lower() in ("sell", "short") for t in trades or [])
    return "long_short" if has_short else "long_only"


def load_engine_map(sym: str, tf: str) -> Dict[str, dict]:
    path = C14 / f"engine_{sym}_{tf}.jsonl"
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("ok") and r.get("file"):
            out[r["file"]] = r
    return out


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
        float(lab.get("good", 0) + lab.get("good_weak", 0)) / max(1, sum(lab.values()) or 1),
        float(lab.get("bad", 0) + lab.get("bad_noise", 0)) / max(1, sum(lab.values()) or 1),
        # §7I base-only BH context (no variant outcomes — those leak the label)
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
    raw_pairs = json.loads((C14 / "results" / "intervention_pairs.json").read_text())
    print("loaded C14 pairs", len(raw_pairs), flush=True)

    # copy scripts for promote source
    n_copy = 0
    for p in (C14 / "scripts").glob("*.italgo"):
        if p.name.startswith(("27p-", "28p-", "29p-", "30p-", "31p-", "32p-", "33p-", "34p-", "35p-")):
            continue
        shutil.copy(p, SESSION / "scripts" / p.name)
        n_copy += 1
    print("copied scripts", n_copy, flush=True)

    bars_cache: Dict[Tuple[str, str], list] = {}
    eng_cache: Dict[Tuple[str, str], Dict[str, dict]] = {}
    pairs: List[dict] = []

    for i, p in enumerate(raw_pairs):
        sym, tf = p["symbol"], p["timeframe"]
        key = (sym, tf)
        if key not in bars_cache:
            bp = C14 / f"bars_{sym}_{tf}.json"
            bars_cache[key] = json.loads(bp.read_text()) if bp.exists() else []
            eng_cache[key] = load_engine_map(sym, tf)
        bars = bars_cache[key]
        eng = eng_cache[key]
        b = eng.get(p["base"])
        v = eng.get(p["variant"])
        if not b or not v or not bars:
            continue

        side = resolve_side_mode(p["base"], b.get("trades") or [], p.get("side_mode") or "unknown")
        base_bh = evaluate_vs_buy_hold(
            bars=bars, trades=b.get("trades") or [], side_mode=side, net_pnl=b["stats"]["netPnl"]
        )
        var_bh = evaluate_vs_buy_hold(
            bars=bars, trades=v.get("trades") or [], side_mode=side, net_pnl=v["stats"]["netPnl"]
        )
        findings = list(p.get("findings") or [])
        if var_bh.get("pseudo_buy_hold"):
            findings = list(dict.fromkeys(findings + ["псевдо_buy_hold"]))

        base_edge = float(base_bh.get("edge_vs_bh") or 0.0)
        var_edge = float(var_bh.get("edge_vs_bh") or 0.0)
        delta_edge = var_edge - base_edge
        base_beats = bool(base_bh.get("beats_buy_hold"))
        var_beats = bool(var_bh.get("beats_buy_hold"))

        # §7I label: improve PnL+DD and improve edge vs BH; variant must beat B&H
        better_legacy = bool(p.get("better")) and bool(p.get("dd_ok", True))
        better = (
            float(p["delta_pnl"]) > 1e-6
            and bool(p.get("dd_ok", True))
            and delta_edge > 1e-6
            and var_beats
            and not bool(var_bh.get("pseudo_buy_hold"))
        )

        pairs.append(
            {
                **p,
                "side_mode": side,
                "buy_hold_pnl": base_bh.get("buy_hold_pnl"),
                "base_edge_vs_bh": base_edge,
                "variant_edge_vs_bh": var_edge,
                "delta_edge_vs_bh": delta_edge,
                "base_beats_buy_hold": base_beats,
                "variant_beats_buy_hold": var_beats,
                "base_pseudo_buy_hold": bool(base_bh.get("pseudo_buy_hold")),
                "variant_pseudo_buy_hold": bool(var_bh.get("pseudo_buy_hold")),
                "better_legacy": better_legacy,
                "better": better,
                "findings": findings,
            }
        )
        if (i + 1) % 4000 == 0:
            print("enriched", i + 1, flush=True)

    print(
        "pairs",
        len(pairs),
        "better",
        sum(1 for p in pairs if p["better"]),
        "legacy_better",
        sum(1 for p in pairs if p.get("better_legacy")),
        flush=True,
    )

    X = np.array([featurize(p) for p in pairs], dtype=float)
    y = np.array([1 if p["better"] else 0 for p in pairs], dtype=int)
    w = np.array(
        [
            1.0
            + min(abs(p["delta_pnl"]) / 50.0, 6.0)
            + min(abs(p.get("delta_edge_vs_bh") or 0.0) / 50.0, 4.0)
            for p in pairs
        ],
        dtype=float,
    )
    feature_names = (
        [
            "base_pnl",
            "base_wr",
            "base_trades",
            "base_dd",
            "good",
            "bad",
            "bad_noise",
            "good_weak",
            "good_share",
            "bad_share",
            "buy_hold_pnl",
            "base_edge_vs_bh",
            "base_beats_bh",
            "base_pseudo_bh",
        ]
        + [f"f_{k}" for k in FINDING_KEYS]
        + [f"regime_{r}" for r in REGIMES]
        + [f"kind_{k}" for k in KINDS]
        + [f"side_{s}" for s in SIDES]
        + [f"sym_{s}" for s in SYMBOLS]
        + [f"tf_{t}" for t in TFS]
        + ["is_future"]
    )

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    preds = np.zeros(len(y))
    probas = np.zeros(len(y))
    for train_idx, test_idx in skf.split(X, y):
        Xtr, Xte = X[train_idx], X[test_idx]
        ytr, wtr = y[train_idx], w[train_idx]
        if len(set(ytr)) < 2:
            preds[test_idx] = ytr[0]
            probas[test_idx] = float(ytr[0])
            continue
        clf = lgb.LGBMClassifier(
            n_estimators=180,
            max_depth=5,
            learning_rate=0.06,
            subsample=0.85,
            colsample_bytree=0.85,
            min_child_samples=6,
            verbosity=-1,
            random_state=42,
        )
        clf.fit(Xtr, ytr, sample_weight=wtr)
        preds[test_idx] = clf.predict(Xte)
        probas[test_idx] = clf.predict_proba(Xte)[:, 1]

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
        pred = clf.predict(X[te])
        proba = clf.predict_proba(X[te])[:, 1]
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
    joblib.dump(
        {
            "model": final,
            "feature_names": feature_names,
            "kinds": KINDS,
            "symbols": SYMBOLS,
            "timeframes": TFS,
            "metrics": {"cv_accuracy": acc, "cv_auc": auc, "n": len(y), "positives": int(y.sum()), "loso_1d": loso},
            "label_rule": "delta_pnl>0 & dd_ok & delta_edge_vs_bh>0 & variant_beats_buy_hold & not pseudo_bh (§7I)",
        },
        SESSION / "models" / "intervention_policy_lgbm.joblib",
    )
    imp = sorted(zip(feature_names, final.feature_importances_.tolist()), key=lambda x: -x[1])

    # promote on 1d: need BH-aware wins
    key_stats = defaultdict(lambda: {"wins": 0, "n": 0, "sum_delta": 0.0, "sum_edge": 0.0, "by_sym": {}})
    for p in pairs:
        if p["timeframe"] != "1d":
            continue
        k = (p["base"], p["kind"])
        key_stats[k]["n"] += 1
        key_stats[k]["sum_delta"] += p["delta_pnl"]
        key_stats[k]["sum_edge"] += float(p.get("delta_edge_vs_bh") or 0)
        key_stats[k]["by_sym"][p["symbol"]] = {
            "delta": p["delta_pnl"],
            "better": p["better"],
            "variant_pnl": p["variant_pnl"],
            "variant": p["variant"],
            "beats_bh": p.get("variant_beats_buy_hold"),
            "edge": p.get("variant_edge_vs_bh"),
        }
        if p["better"]:
            key_stats[k]["wins"] += 1

    KIND_TAG = {
        "change_period_15x": "period15x",
        "change_period_067": "period067",
        "change_period_2x": "period2x",
        "change_period_05x": "period05x",
        "add_block_ema": "ema50",
        "add_block_adx": "adx25",
        "add_block_sma200": "sma200",
        "add_block_rsi50": "rsi50",
    }
    stable, promoted = [], []
    LIB.mkdir(parents=True, exist_ok=True)
    for (base, kind), st in key_stats.items():
        sym_wins = [
            s
            for s, v in st["by_sym"].items()
            if v["better"] and v["variant_pnl"] > 0 and v.get("beats_bh")
        ]
        mean_delta = st["sum_delta"] / max(1, st["n"])
        mean_edge = st["sum_edge"] / max(1, st["n"])
        if len(sym_wins) >= 6 and mean_delta >= 15 and mean_edge > 0:
            item = {
                "base": base,
                "kind": kind,
                "n_symbols_win": len(sym_wins),
                "symbols_win": sorted(sym_wins),
                "mean_delta": mean_delta,
                "mean_delta_edge_vs_bh": mean_edge,
                "variant": next(iter(st["by_sym"].values()))["variant"],
            }
            stable.append(item)
            src = SESSION / "scripts" / item["variant"]
            if not src.exists():
                src = C14 / "scripts" / item["variant"]
            if src.exists():
                stem = base.replace(".italgo", "")
                out_name = f"35p-{stem}__{KIND_TAG[kind]}.italgo"
                doc = json.loads(src.read_text())
                doc["meta"]["name"] = f"[cross-sym+BH] {doc['meta'].get('name')}"
                doc["meta"]["tags"] = list(
                    dict.fromkeys((doc["meta"].get("tags") or []) + ["promoted", "c15", "cross-symbol", "beats-buyhold"])
                )
                doc["meta"]["cross_symbol"] = {
                    "symbols_win": item["symbols_win"],
                    "mean_delta": item["mean_delta"],
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

    bh_cov = {
        "variant_beats_rate": sum(1 for p in pairs if p.get("variant_beats_buy_hold")) / max(1, len(pairs)),
        "base_beats_rate": sum(1 for p in pairs if p.get("base_beats_buy_hold")) / max(1, len(pairs)),
        "label_pos_rate": float(y.mean()),
        "legacy_pos_rate": sum(1 for p in pairs if p.get("better_legacy")) / max(1, len(pairs)),
    }

    summary = {
        "session": "2026-08-21-c15-buyhold-policy",
        "symbols": SYMBOLS,
        "timeframes": TFS,
        "n_pairs": len(pairs),
        "n_better": int(y.sum()),
        "buyhold": bh_cov,
        "model": {"cv_accuracy": acc, "cv_auc": auc, "n": len(y), "loso_1d": loso},
        "kind_stats": dict(kind_stats),
        "n_stable_cross": len(stable),
        "n_promoted": len(promoted),
        "label_rule": "delta>0 & dd_ok & Δedge_vs_bh>0 & variant_beats_BH & !pseudo (§7I)",
        "top20_by_score": [
            {
                "entry": f"{p['symbol']}:{p['timeframe']}:{p['base']}",
                "filter": p["kind"],
                "median_pnl": p["delta_pnl"],
                "mean_pnl": p["variant_pnl"],
                "mean_wr": p["variant_wr"],
                "mean_dd": p["variant_dd"],
                "edge_vs_bh": p.get("variant_edge_vs_bh"),
                "n": 1,
                "regime": p.get("regime"),
            }
            for p in sorted(pairs, key=lambda x: (x.get("delta_edge_vs_bh") or -1e18), reverse=True)[:20]
        ],
    }
    (SESSION / "results" / "intervention_pairs.json").write_text(json.dumps(pairs, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "results" / "cross_symbol_stable.json").write_text(json.dumps(stable, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "results" / "promoted.json").write_text(json.dumps(promoted, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "results" / "variant_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "models" / "feature_names.json").write_text(
        json.dumps(
            {
                "feature_names": feature_names,
                "symbols": SYMBOLS,
                "timeframes": TFS,
                "metrics": summary["model"],
                "feature_importance_top": imp[:25],
                "label_rule": summary["label_rule"],
                "buyhold": bh_cov,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    (SESSION / "results" / "advisor_intervention_dataset.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "task": "improve_strategy",
                    "features": dict(zip(feature_names, featurize(p))),
                    "action": p["kind"],
                    "label": "accept_intervention" if p["better"] else "reject_intervention",
                    "delta_pnl": p["delta_pnl"],
                    "delta_edge_vs_bh": p.get("delta_edge_vs_bh"),
                    "beats_buy_hold": p.get("variant_beats_buy_hold"),
                    "base": p["base"],
                    "symbol": p["symbol"],
                    "timeframe": p["timeframe"],
                },
                ensure_ascii=False,
            )
            for p in pairs
        )
        + "\n"
    )
    (SESSION / "REPORT.md").write_text(
        "\n".join(
            [
                "# C15 buy&hold-aware policy (§7I / P3.8)",
                "",
                f"- Pairs: {len(pairs)} · better: {int(y.sum())} ({100*y.mean():.1f}%)",
                f"- Legacy better rate: {100*bh_cov['legacy_pos_rate']:.1f}%",
                f"- CV acc={acc:.3f} AUC={auc}",
                f"- Variant beats BH rate: {100*bh_cov['variant_beats_rate']:.1f}%",
                f"- Promoted 35p-*: {len(promoted)} (≥6 symbols, Δ>15, edge↑, beats BH)",
                "",
                "## Kind stats",
                json.dumps(kind_stats, indent=2, ensure_ascii=False),
            ]
        )
        + "\n"
    )
    (SESSION / "notes.md").write_text(
        "C15: BH-aware labels on C14 corpus — better requires Δedge_vs_bh>0 and variant beats buy&hold; 35p-*; §7I.\n"
    )
    print("MODEL", acc, auc, "promoted", len(promoted), "pos_rate", float(y.mean()))
    print("importance_top", imp[:10])


if __name__ == "__main__":
    main()
