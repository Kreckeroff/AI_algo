#!/usr/bin/env python3
"""C8 / P3: new interventions + expanded multi-TF lookback + retrain policy.

- Corpus bases 01–26 + 06b (exclude 27p-* promoted)
- Interventions: period×1.5, period×0.67, EMA50, ADX>25, SMA200
- Lookback: ~12 scripts × 1d/1h/1w windows
- Promote clear wins as 28p-*
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
from typing import Any, Dict, List, Optional, Tuple

import joblib
import lightgbm as lgb
import numpy as np
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import LeaveOneOut

ROOT = Path("/Users/kreckeroff/Fintech (startup)/AI_algo")
DESKTOP = ROOT.parent / "it-algo-desktop"
ITALGO = DESKTOP / "docs/work/scripting/samples/ai-train"
SESSION = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c8-p3-expand"
RAW = ROOT / "artifacts/agent_loop/sessions/2026-08-21-multi-indicator-wave/data/raw"
LIB = Path.home() / (
    "Library/Application Support/ru.it-algo.desktop/scripting/"
    "6882ee6d-8a3f-4eda-a4a9-235652c2b455/library/ai-train"
)

sys.path.insert(0, str(ROOT / "src"))
from ai_algo.domain.trade_analysis import analyze_trades  # noqa: E402

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
SESSION.mkdir(parents=True, exist_ok=True)
for sub in ("scripts", "results", "models", "scripts_lookback"):
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


def run_engine(scripts_dir: Path, bars_path: Path, out: Path) -> List[dict]:
    cmd = [
        "cargo",
        "run",
        "-p",
        "backtest",
        "--example",
        "run_ai_train_corpus",
        "--release",
        "--",
        "--dir",
        str(scripts_dir),
        "--bars",
        str(bars_path),
        "--symbol",
        "SBER",
        "--timeframe",
        "1d",
        "--trades",
        "--out",
        str(out),
    ]
    print("RUN", out.name, flush=True)
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


def add_and_filter(doc: dict, *, filter_id: str, build_nodes_edges) -> bool:
    """Wrap existing open.condition with AND(filter, prev)."""
    nodes, edges = doc["graph"]["nodes"], doc["graph"]["edges"]
    ids = {n["id"] for n in nodes}
    open_id = _open_id(ids)
    if not open_id or filter_id in ids or "close" not in ids:
        return False
    cross_edges = [e for e in edges if e.get("target") == open_id and e.get("targetHandle") == "condition"]
    if not cross_edges:
        return False
    extra_nodes, pre_edges, filter_src = build_nodes_edges()
    nodes.extend(extra_nodes)
    buy_and = f"{filter_id}_and"
    nodes.append(
        {"id": buy_and, "type": "logic_and", "position": {"x": 860, "y": 80}, "data": {"label": "Buy+Filter"}}
    )
    edges = [e for e in edges if not (e.get("target") == open_id and e.get("targetHandle") == "condition")]
    edges.extend(pre_edges)
    for ce in cross_edges:
        edges.append(
            {
                "id": f"c8_{ce['id']}_and",
                "source": ce["source"],
                "target": buy_and,
                "sourceHandle": ce.get("sourceHandle") or "result",
                "targetHandle": "conditions",
            }
        )
    edges += [
        {
            "id": f"c8_{filter_id}_to_and",
            "source": filter_src,
            "target": buy_and,
            "sourceHandle": "result",
            "targetHandle": "conditions",
        },
        {
            "id": f"c8_{filter_id}_open",
            "source": buy_and,
            "target": open_id,
            "sourceHandle": "result",
            "targetHandle": "condition",
        },
    ]
    doc["graph"]["edges"] = edges
    return True


def add_ema_filter(doc: dict, period: int = 50) -> bool:
    fid = "ema_filter"

    def build():
        nodes = [
            {
                "id": fid,
                "type": "indicator_ema",
                "position": {"x": 480, "y": 20},
                "data": {"period": period, "label": f"EMA{period}"},
            },
            {"id": "above_ema", "type": "logic_gt", "position": {"x": 700, "y": 20}, "data": {"label": "Close>EMA"}},
        ]
        edges = [
            {"id": "c8_ce", "source": "close", "target": fid, "sourceHandle": "value", "targetHandle": "source"},
            {"id": "c8_ca", "source": "close", "target": "above_ema", "sourceHandle": "value", "targetHandle": "a"},
            {"id": "c8_ea", "source": fid, "target": "above_ema", "sourceHandle": "value", "targetHandle": "b"},
        ]
        return nodes, edges, "above_ema"

    return add_and_filter(doc, filter_id=fid, build_nodes_edges=build)


def add_sma_filter(doc: dict, period: int = 200) -> bool:
    fid = "sma_filter"

    def build():
        nodes = [
            {
                "id": fid,
                "type": "indicator_sma",
                "position": {"x": 480, "y": 20},
                "data": {"period": period, "label": f"SMA{period}"},
            },
            {"id": "above_sma", "type": "logic_gt", "position": {"x": 700, "y": 20}, "data": {"label": "Close>SMA"}},
        ]
        edges = [
            {"id": "c8_cs", "source": "close", "target": fid, "sourceHandle": "value", "targetHandle": "source"},
            {"id": "c8_csa", "source": "close", "target": "above_sma", "sourceHandle": "value", "targetHandle": "a"},
            {"id": "c8_ssa", "source": fid, "target": "above_sma", "sourceHandle": "value", "targetHandle": "b"},
        ]
        return nodes, edges, "above_sma"

    return add_and_filter(doc, filter_id=fid, build_nodes_edges=build)


def add_adx_filter(doc: dict, period: int = 14, min_adx: float = 25.0) -> bool:
    fid = "adx_filter"
    ids = {n["id"] for n in doc["graph"]["nodes"]}
    if "adx" in ids or "adx_ok" in ids:
        return False  # already has ADX gate

    def build():
        nodes = [
            {
                "id": fid,
                "type": "indicator_adx",
                "position": {"x": 480, "y": 20},
                "data": {"period": period, "label": f"ADX{period}"},
            },
            {
                "id": "adx_min_c8",
                "type": "constant",
                "position": {"x": 480, "y": 80},
                "data": {"value": min_adx, "label": str(min_adx)},
            },
            {"id": "adx_ok_c8", "type": "logic_gt", "position": {"x": 700, "y": 20}, "data": {"label": "ADX>min"}},
        ]
        edges = [
            {"id": "c8_hi_adx", "source": "instrument", "target": fid, "sourceHandle": "instrument", "targetHandle": "instrument"},
            {"id": "c8_adx_a", "source": fid, "target": "adx_ok_c8", "sourceHandle": "value", "targetHandle": "a"},
            {"id": "c8_adx_b", "source": "adx_min_c8", "target": "adx_ok_c8", "sourceHandle": "value", "targetHandle": "b"},
        ]
        return nodes, edges, "adx_ok_c8"

    return add_and_filter(doc, filter_id=fid, build_nodes_edges=build)


def save_doc(doc: dict, path: Path, *, kind: str, base: str, extra: dict) -> None:
    doc = copy.deepcopy(doc)
    doc.setdefault("meta", {})
    doc["meta"]["updatedAt"] = NOW
    doc["meta"]["intervention"] = {"kind": kind, "base": base, **extra}
    tags = list(doc["meta"].get("tags") or []) + ["c8", f"intervention:{kind}"]
    doc["meta"]["tags"] = list(dict.fromkeys(tags))
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")


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
    "add_block_ema",
    "add_block_adx",
    "add_block_sma200",
]
REGIMES = ["trend", "mean_reversion", "breakout", "unknown"]
SIDES = ["long_only", "long_short", "unknown"]


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
    return feats


def esc(s: Any) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main() -> None:
    bases = sorted(
        p
        for p in ITALGO.glob("*.italgo")
        if not p.name.startswith("27p-") and not p.name.startswith("28p-")
    )
    print("corpus bases", len(bases), flush=True)

    variants_meta: List[Tuple[str, str, str]] = []
    for src in bases:
        name = src.name
        base = json.loads(src.read_text())
        shutil.copy(src, SESSION / "scripts" / name)
        stem = name.replace(".italgo", "")

        d = copy.deepcopy(base)
        scale_periods(d, 1.5)
        d["meta"]["name"] = f"{base['meta'].get('name', '')} period×1.5"
        save_doc(
            d,
            SESSION / "scripts" / f"{stem}__period15x.italgo",
            kind="change_period_15x",
            base=name,
            extra={"factor": 1.5},
        )
        variants_meta.append((name, f"{stem}__period15x.italgo", "change_period_15x"))

        d = copy.deepcopy(base)
        scale_periods(d, 0.67)
        d["meta"]["name"] = f"{base['meta'].get('name', '')} period×0.67"
        save_doc(
            d,
            SESSION / "scripts" / f"{stem}__period067.italgo",
            kind="change_period_067",
            base=name,
            extra={"factor": 0.67},
        )
        variants_meta.append((name, f"{stem}__period067.italgo", "change_period_067"))

        d = copy.deepcopy(base)
        if add_ema_filter(d, 50):
            d["meta"]["name"] = f"{base['meta'].get('name', '')} +EMA50"
            save_doc(
                d,
                SESSION / "scripts" / f"{stem}__ema50.italgo",
                kind="add_block_ema",
                base=name,
                extra={"block": "indicator_ema", "period": 50},
            )
            variants_meta.append((name, f"{stem}__ema50.italgo", "add_block_ema"))

        d = copy.deepcopy(base)
        if add_adx_filter(d, 14, 25.0):
            d["meta"]["name"] = f"{base['meta'].get('name', '')} +ADX>25"
            save_doc(
                d,
                SESSION / "scripts" / f"{stem}__adx25.italgo",
                kind="add_block_adx",
                base=name,
                extra={"block": "indicator_adx", "period": 14, "min": 25},
            )
            variants_meta.append((name, f"{stem}__adx25.italgo", "add_block_adx"))

        d = copy.deepcopy(base)
        if add_sma_filter(d, 200):
            d["meta"]["name"] = f"{base['meta'].get('name', '')} +SMA200"
            save_doc(
                d,
                SESSION / "scripts" / f"{stem}__sma200.italgo",
                kind="add_block_sma200",
                base=name,
                extra={"block": "indicator_sma", "period": 200},
            )
            variants_meta.append((name, f"{stem}__sma200.italgo", "add_block_sma200"))

    bars_1d = load_csv(RAW / "MOEX_SBER_1d.csv")
    bars_1d_path = SESSION / "bars_sber_1d.json"
    bars_1d_path.write_text(json.dumps(bars_1d))
    rows = run_engine(SESSION / "scripts", bars_1d_path, SESSION / "engine_results.jsonl")
    by_file = {r["file"]: r for r in rows if r.get("ok")}
    print("engine ok", len(by_file), "variants_meta", len(variants_meta), flush=True)

    pairs = []
    for base_name, var_name, kind in variants_meta:
        b, v = by_file.get(base_name), by_file.get(var_name)
        if not b or not v:
            continue
        rb = analyze_trades(b.get("trades"), graph_nodes=b.get("nodes"))
        bp, vp = b["stats"]["netPnl"], v["stats"]["netPnl"]
        delta = vp - bp
        pairs.append(
            {
                "base": base_name,
                "variant": var_name,
                "kind": kind,
                "side_mode": (json.loads((ITALGO / base_name).read_text()).get("meta") or {}).get(
                    "side_mode", "unknown"
                ),
                "base_pnl": bp,
                "variant_pnl": vp,
                "delta_pnl": delta,
                "better": delta > 1e-6,
                "base_wr": b["stats"]["winRate"],
                "variant_wr": v["stats"]["winRate"],
                "base_trades": b["stats"]["totalTrades"],
                "base_dd": b["stats"]["maxDrawdown"],
                "base_labels": dict(label_counts(b.get("trades"))),
                "findings": rb.get("findings") or [],
                "regime": rb.get("regime") or "unknown",
            }
        )
    print("pairs", len(pairs), "better", sum(1 for p in pairs if p["better"]), flush=True)

    X = np.array([featurize(p) for p in pairs], dtype=float)
    y = np.array([1 if p["better"] else 0 for p in pairs], dtype=int)
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
        ]
        + [f"f_{k}" for k in FINDING_KEYS]
        + [f"regime_{r}" for r in REGIMES]
        + [f"kind_{k}" for k in KINDS]
        + [f"side_{s}" for s in SIDES]
    )

    loo = LeaveOneOut()
    preds = np.zeros(len(y))
    probas = np.zeros(len(y))
    for train_idx, test_idx in loo.split(X):
        Xtr, Xte = X[train_idx], X[test_idx]
        ytr = y[train_idx]
        if len(set(ytr)) < 2:
            preds[test_idx] = ytr[0]
            probas[test_idx] = float(ytr[0])
            continue
        clf = lgb.LGBMClassifier(
            n_estimators=80,
            max_depth=3,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            min_child_samples=2,
            verbosity=-1,
            random_state=42,
        )
        clf.fit(Xtr, ytr)
        preds[test_idx] = clf.predict(Xte)[0]
        probas[test_idx] = clf.predict_proba(Xte)[0, 1]

    acc = float(accuracy_score(y, preds)) if len(y) else float("nan")
    try:
        auc = float(roc_auc_score(y, probas))
    except ValueError:
        auc = float("nan")

    final = lgb.LGBMClassifier(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        min_child_samples=2,
        verbosity=-1,
        random_state=42,
    )
    final.fit(X, y)
    model_path = SESSION / "models" / "intervention_policy_lgbm.joblib"
    joblib.dump(
        {
            "model": final,
            "feature_names": feature_names,
            "kinds": KINDS,
            "metrics": {"loo_accuracy": acc, "loo_auc": auc, "n": len(y), "positives": int(y.sum())},
        },
        model_path,
    )
    imp = sorted(zip(feature_names, final.feature_importances_.tolist()), key=lambda x: -x[1])

    policy = []
    for base in sorted({p["base"] for p in pairs}):
        cands = [p for p in pairs if p["base"] == base]
        scored = []
        for p in cands:
            pr = float(final.predict_proba(np.array([featurize(p)]))[0, 1])
            scored.append({**p, "p_better": pr})
        scored.sort(key=lambda x: (x["p_better"], x["delta_pnl"]), reverse=True)
        best = scored[0]
        policy.append(
            {
                "base": base,
                "recommend_kind": best["kind"],
                "p_better": best["p_better"],
                "observed_delta": best["delta_pnl"],
                "observed_better": best["better"],
                "base_pnl": best["base_pnl"],
                "variant_pnl": best["variant_pnl"],
                "variant": best["variant"],
            }
        )

    KIND_TAG = {
        "change_period_15x": "period15x",
        "change_period_067": "period067",
        "add_block_ema": "ema50",
        "add_block_adx": "adx25",
        "add_block_sma200": "sma200",
    }
    PROMOTE_DELTA = 50.0
    promoted = []
    LIB.mkdir(parents=True, exist_ok=True)
    for p in pairs:
        if p["delta_pnl"] >= PROMOTE_DELTA and p["variant_pnl"] > 0:
            src = SESSION / "scripts" / p["variant"]
            stem = p["base"].replace(".italgo", "")
            out_name = f"28p-{stem}__{KIND_TAG[p['kind']]}.italgo"
            doc = json.loads(src.read_text())
            doc["meta"]["name"] = f"[promoted] {doc['meta'].get('name')}"
            doc["meta"]["tags"] = list(dict.fromkeys((doc["meta"].get("tags") or []) + ["promoted", "c8"]))
            text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
            (ITALGO / out_name).write_text(text)
            (LIB / out_name).write_text(text)
            (SESSION / "scripts" / out_name).write_text(text)
            promoted.append(
                {
                    "from": p["base"],
                    "to": out_name,
                    "delta": p["delta_pnl"],
                    "pnl": p["variant_pnl"],
                    "kind": p["kind"],
                }
            )
    print("promoted", len(promoted), flush=True)

    # Expanded lookback shortlist: top by base pnl among trading scripts + fixed breakouts
    base_rows = [(n, by_file[n]) for n in [b.name for b in bases] if n in by_file]
    trading = [n for n, r in base_rows if (r.get("stats") or {}).get("totalTrades", 0) > 0]
    ranked = sorted(trading, key=lambda n: by_file[n]["stats"]["netPnl"], reverse=True)
    look_list = []
    for n in [
        "03-breakout-donchian-volume.italgo",
        "20-donchian-55.italgo",
        "06b-rsi-no-session.italgo",
    ] + ranked:
        if n in by_file and n not in look_list:
            look_list.append(n)
        if len(look_list) >= 12:
            break
    for name in look_list:
        shutil.copy(ITALGO / name, SESSION / "scripts_lookback" / name)
    print("lookback scripts", look_list, flush=True)

    look_rows = []
    tf_files = {"1d": "MOEX_SBER_1d.csv", "1h": "MOEX_SBER_1h.csv", "1w": "MOEX_SBER_1w.csv"}
    win_map = {
        "1d": {"1y": 252, "2y": 504, "5y": 1260, "all": None},
        "1h": {"3m": 24 * 60, "1y": 24 * 250, "all": None},
        "1w": {"2y": 104, "5y": 260, "all": None},
    }
    for tf, fname in tf_files.items():
        bars = load_csv(RAW / fname)
        for wname, n in win_map[tf].items():
            slice_bars = bars if n is None else bars[-min(n, len(bars)) :]
            bp = SESSION / f"bars_{tf}_{wname}.json"
            bp.write_text(json.dumps(slice_bars))
            out = SESSION / f"look_{tf}_{wname}.jsonl"
            rs = run_engine(SESSION / "scripts_lookback", bp, out)
            for r in rs:
                if not r.get("ok"):
                    continue
                look_rows.append(
                    {
                        "file": r["file"],
                        "tf": tf,
                        "window": wname,
                        "bars": len(slice_bars),
                        "stats": r["stats"],
                    }
                )

    (SESSION / "results" / "intervention_pairs.json").write_text(
        json.dumps(pairs, indent=2, ensure_ascii=False) + "\n"
    )
    (SESSION / "results" / "policy_recommendations.json").write_text(
        json.dumps(policy, indent=2, ensure_ascii=False) + "\n"
    )
    (SESSION / "results" / "promoted.json").write_text(json.dumps(promoted, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "results" / "lookback_multitf.json").write_text(json.dumps(look_rows, indent=2) + "\n")
    (SESSION / "models" / "feature_names.json").write_text(
        json.dumps(
            {
                "feature_names": feature_names,
                "model_kind": "lgbm_intervention_policy",
                "metrics": {"loo_accuracy": acc, "loo_auc": auc, "n": len(y), "positives": int(y.sum())},
                "feature_importance_top": imp[:15],
            },
            indent=2,
        )
        + "\n"
    )

    dataset = []
    for p in pairs:
        dataset.append(
            {
                "task": "improve_strategy",
                "features": dict(zip(feature_names, featurize(p))),
                "action": p["kind"],
                "label": "accept_intervention" if p["better"] else "reject_intervention",
                "delta_pnl": p["delta_pnl"],
                "base": p["base"],
            }
        )
    (SESSION / "results" / "advisor_intervention_dataset.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in dataset) + "\n"
    )

    kind_stats: Dict[str, dict] = defaultdict(lambda: {"n": 0, "wins": 0, "sum_delta": 0.0})
    for p in pairs:
        kind_stats[p["kind"]]["n"] += 1
        kind_stats[p["kind"]]["sum_delta"] += p["delta_pnl"]
        if p["better"]:
            kind_stats[p["kind"]]["wins"] += 1
    for k, v in kind_stats.items():
        v["mean_delta"] = v["sum_delta"] / max(1, v["n"])
        v["winrate"] = v["wins"] / max(1, v["n"])

    zero_trade_bases = [
        n for n, r in base_rows if (r.get("stats") or {}).get("totalTrades", 0) == 0
    ]
    summary = {
        "session": "2026-08-21-c8-p3-expand",
        "n_pairs": len(pairs),
        "n_better": int(sum(1 for p in pairs if p["better"])),
        "model": {"loo_accuracy": acc, "loo_auc": auc, "n": len(y)},
        "kind_stats": dict(kind_stats),
        "n_promoted": len(promoted),
        "lookback_cells": len(look_rows),
        "lookback_scripts": look_list,
        "zero_trade_bases": zero_trade_bases,
        "fixes": {
            "donchian_shift": ["03-breakout-donchian-volume.italgo", "20-donchian-55.italgo"],
            "session_1d": "06b-rsi-no-session.italgo (06 remains intraday-only)",
        },
        "top20_by_score": [
            {
                "entry": p["base"],
                "filter": p["kind"],
                "median_pnl": p["delta_pnl"],
                "mean_pnl": p["variant_pnl"],
                "mean_wr": p["variant_wr"],
                "mean_dd": 0,
                "n": 1,
                "regime": p.get("regime"),
            }
            for p in sorted(pairs, key=lambda x: x["delta_pnl"], reverse=True)[:20]
        ],
    }
    (SESSION / "results" / "variant_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    )

    pair_top = sorted(pairs, key=lambda x: x["delta_pnl"], reverse=True)[:20]
    pair_trs = "".join(
        f"<tr><td>{esc(p['base'])}</td><td>{esc(p['kind'])}</td><td>{p['base_pnl']:.1f}</td>"
        f"<td>{p['variant_pnl']:.1f}</td><td style='color:{'#9ad67a' if p['better'] else '#f0a0a0'}'>{p['delta_pnl']:+.1f}</td></tr>"
        for p in pair_top
    )
    pol_trs = "".join(
        f"<tr><td>{esc(p['base'])}</td><td>{esc(p['recommend_kind'])}</td><td>{p['p_better']:.2f}</td>"
        f"<td>{p['observed_delta']:+.1f}</td><td>{'✓' if p['observed_better'] else '✗'}</td></tr>"
        for p in sorted(policy, key=lambda x: -x["p_better"])
    )
    imp_trs = "".join(f"<tr><td>{esc(n)}</td><td>{v}</td></tr>" for n, v in imp[:12])
    prom_trs = "".join(
        f"<tr><td>{esc(p['from'])}</td><td>{esc(p['to'])}</td><td>{p['kind']}</td><td>{p['delta']:+.1f}</td><td>{p['pnl']:.1f}</td></tr>"
        for p in sorted(promoted, key=lambda x: -x["delta"])
    )
    kind_trs = "".join(
        f"<tr><td>{esc(k)}</td><td>{v['n']}</td><td>{v['wins']}</td><td>{v['winrate']:.0%}</td><td>{v['mean_delta']:+.1f}</td></tr>"
        for k, v in sorted(kind_stats.items(), key=lambda kv: -kv[1]["mean_delta"])
    )

    look_html = ""
    for tf in ["1d", "1h", "1w"]:
        rows_tf = [r for r in look_rows if r["tf"] == tf]
        if not rows_tf:
            continue
        wins = sorted({r["window"] for r in rows_tf})
        cell = {(r["file"], r["window"]): r["stats"]["netPnl"] for r in rows_tf}
        vals = list(cell.values()) or [0.0]
        lo, hi = min(vals), max(vals)

        def heat(v, lo=lo, hi=hi):
            t = 0.5 if hi <= lo else max(0, min(1, (v - lo) / (hi - lo)))
            if t < 0.5:
                u = t * 2
                r, g, b = 220, int(80 + 140 * u), int(80 + 140 * u)
            else:
                u = (t - 0.5) * 2
                r, g, b = int(220 - 160 * u), int(220 - 40 * u), int(220 - 160 * u)
            return f"rgb({r},{g},{b})"

        head = "<tr><th>script</th>" + "".join(f"<th>{w}</th>" for w in wins) + "</tr>"
        body = ""
        for f in look_list:
            tds = []
            for w in wins:
                if (f, w) not in cell:
                    tds.append("<td>—</td>")
                else:
                    v = cell[(f, w)]
                    tds.append(f'<td style="background:{heat(v)}"><b>{v:.0f}</b></td>')
            body += f"<tr><td>{esc(f)}</td>{''.join(tds)}</tr>"
        look_html += f"<h3>TF {tf}</h3><table><thead>{head}</thead><tbody>{body}</tbody></table>"

    base_trs = "".join(
        f"<tr><td>{esc(n)}</td><td>{(by_file[n]['stats']['totalTrades'])}</td>"
        f"<td>{by_file[n]['stats']['netPnl']:.1f}</td><td>{by_file[n]['stats']['winRate']:.2f}</td></tr>"
        for n, _ in sorted(base_rows, key=lambda x: -x[1]["stats"]["netPnl"])
    )

    html = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"/>
<title>C8 P3 expand</title>
<style>
body{{margin:0;font-family:IBM Plex Sans,system-ui,sans-serif;background:#0f1419;color:#e8eef4;padding:28px}}
h1{{font-size:1.4rem}} h2,h3{{margin-top:24px}} .sub{{color:#8b9aab;max-width:960px;line-height:1.45}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:16px 0}}
.card{{background:#1a222c;border:1px solid #2a3542;border-radius:10px;padding:12px}}
.k{{color:#8b9aab;font-size:.7rem;text-transform:uppercase}} .v{{font-size:1.25rem;font-weight:600;margin-top:4px}}
table{{border-collapse:collapse;width:100%;background:#1a222c;border:1px solid #2a3542;font-size:.8rem;margin:8px 0 18px}}
th,td{{border:1px solid #2a3542;padding:7px 8px;text-align:center}} th{{background:#121820;color:#8b9aab}}
td:first-child{{text-align:left}}
</style></head><body>
<h1>C8 — P3 expand: новые вмешательства + lookback ×12</h1>
<p class="sub">Donchian HH/LL−1 · 06b без сессии · period×1.5/×0.67 · EMA50 · ADX&gt;25 · SMA200 · LightGBM LOO · promote 28p-*</p>
<div class="grid">
  <div class="card"><div class="k">Pairs</div><div class="v">{len(pairs)}</div></div>
  <div class="card"><div class="k">LOO accuracy</div><div class="v">{acc:.2f}</div></div>
  <div class="card"><div class="k">LOO AUC</div><div class="v">{(auc if auc==auc else float('nan')):.2f}</div></div>
  <div class="card"><div class="k">Promoted</div><div class="v">{len(promoted)}</div></div>
</div>
<h2>Типы вмешательств</h2>
<table><thead><tr><th>kind</th><th>n</th><th>wins</th><th>WR</th><th>mean Δ</th></tr></thead><tbody>{kind_trs}</tbody></table>
<h2>Базовый корпус (после фиксов)</h2>
<table><thead><tr><th>script</th><th>trades</th><th>PnL</th><th>WR</th></tr></thead><tbody>{base_trs}</tbody></table>
<h2>Важность фич</h2>
<table><thead><tr><th>feature</th><th>importance</th></tr></thead><tbody>{imp_trs}</tbody></table>
<h2>Рекомендации политики</h2>
<table><thead><tr><th>base</th><th>recommend</th><th>P(better)</th><th>obs Δ</th><th>obs ok</th></tr></thead><tbody>{pol_trs}</tbody></table>
<h2>Топ улучшений</h2>
<table><thead><tr><th>base</th><th>action</th><th>base PnL</th><th>new</th><th>Δ</th></tr></thead><tbody>{pair_trs}</tbody></table>
<h2>Promoted 28p-*</h2>
<table><thead><tr><th>from</th><th>to</th><th>kind</th><th>Δ</th><th>PnL</th></tr></thead><tbody>{prom_trs or '<tr><td colspan=5>none</td></tr>'}</tbody></table>
<h2>Lookback multi-TF (12 scripts)</h2>
{look_html}
<p class="sub">Model: models/intervention_policy_lgbm.joblib · zero-trade left: {esc(', '.join(zero_trade_bases) or 'none')}</p>
</body></html>
"""
    (SESSION / "ANALYTICS.html").write_text(html)
    (SESSION / "FULL_MAP.html").write_text(html)
    (SESSION / "REPORT.md").write_text(
        "\n".join(
            [
                "# C8 P3 expand",
                "",
                f"- Pairs: {len(pairs)} · better: {sum(1 for p in pairs if p['better'])}",
                f"- LOO acc={acc:.3f} AUC={auc}",
                f"- Promoted: {len(promoted)}",
                f"- Lookback cells: {len(look_rows)} · scripts: {len(look_list)}",
                f"- Zero-trade bases left: {zero_trade_bases or 'none'}",
                "",
                "## Kind stats",
                json.dumps(kind_stats, indent=2, ensure_ascii=False),
                "",
                "## Top promotes",
            ]
            + [f"- `{p['to']}` Δ={p['delta']:+.1f}" for p in sorted(promoted, key=lambda x: -x["delta"])[:15]]
        )
        + "\n"
    )
    (SESSION / "notes.md").write_text(
        "C8/P3: Donchian shift fix + 06b; interventions period×1.5/0.67 EMA ADX SMA200; "
        "expanded lookback 12 scripts; LightGBM policy retrain; promote 28p-*.\n"
    )

    print("MODEL loo_acc", acc, "auc", auc, "n", len(y), "pos", int(y.sum()))
    print("kind_stats", json.dumps(kind_stats, indent=2))
    print("zero_trade", zero_trade_bases)
    print("promoted sample", promoted[:5])


if __name__ == "__main__":
    main()
