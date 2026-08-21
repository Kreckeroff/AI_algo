#!/usr/bin/env python3
"""C18b / B1: add_mr_overlay — trend gated + BB/RSI MR in chop; 1d+1h; 38p-*."""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import lightgbm as lgb
import numpy as np
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold

ROOT = Path("/Users/kreckeroff/Fintech (startup)/AI_algo")
DESKTOP = ROOT.parent / "it-algo-desktop"
ITALGO = DESKTOP / "docs/work/scripting/samples/ai-train"
C16 = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c16-atr-sltp"
C18 = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c18-regime-dual"
B0 = ROOT / "artifacts/agent_loop/sessions/2026-08-21-b0-regime-annotate"
SESSION = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c18b-mr-overlay"
LIB = Path.home() / (
    "Library/Application Support/ru.it-algo.desktop/scripting/"
    "6882ee6d-8a3f-4eda-a4a9-235652c2b455/library/ai-train"
)

sys.path.insert(0, str(ROOT / "src"))
from ai_algo.domain.buy_hold import evaluate_vs_buy_hold  # noqa: E402
from ai_algo.domain.dividends import adjust_trades, events_in_window, load_dividend_cache  # noqa: E402
from ai_algo.domain.market_regime import annotate_trades, classify_bars, summarize_regimes  # noqa: E402
from ai_algo.domain.trade_analysis import infer_script_regime  # noqa: E402

EQUITIES = ["SBER", "GAZP", "LKOH", "ROSN", "GMKN", "NVTK", "TATN", "PLZL", "MGNT", "MTSS"]
FUTURES = ["CNYRUBF", "GLDRUBF", "IMOEXF"]
SYMBOLS = EQUITIES + FUTURES
TFS = ["1d", "1h"]
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PROMO = tuple(f"{i}p-" for i in range(27, 40))
KIND = "add_mr_overlay"

SESSION.mkdir(parents=True, exist_ok=True)
for sub in ("scripts", "results", "models"):
    (SESSION / sub).mkdir(exist_ok=True)


def add_mr_overlay(doc: dict) -> bool:
    """Dual entry: (orig ∧ ADX>25) ∨ (BB/RSI MR ∧ ADX<25); MR exit OR'd into close."""
    nodes, edges = doc["graph"]["nodes"], doc["graph"]["edges"]
    ids = {n["id"] for n in nodes}
    if "mroverlay_or" in ids or "mr_buy_c18b" in ids:
        return False
    if "close" not in ids or "instrument" not in ids:
        return False

    opens = [
        n for n in nodes
        if n["type"] == "position_open_market"
        and (n.get("data") or {}).get("direction", "buy") == "buy"
    ]
    closes = [n for n in nodes if n["type"] == "position_close_market"]
    # long_only single open only (LS wiring fragile)
    if len(opens) != 1 or len(closes) != 1:
        return False
    # skip pure MR bases — already that structure
    sreg = infer_script_regime(nodes)
    if sreg == "mean_reversion":
        return False

    open_id = opens[0]["id"]
    close_id = closes[0]["id"]
    open_conds = [e for e in edges if e.get("target") == open_id and e.get("targetHandle") == "condition"]
    close_conds = [e for e in edges if e.get("target") == close_id and e.get("targetHandle") == "condition"]
    if not open_conds or not close_conds:
        return False

    # ADX
    adx_id = "adx" if "adx" in ids else "adx_c18b"
    if adx_id not in ids and "adx" not in ids:
        nodes.append({
            "id": adx_id, "type": "indicator_adx", "position": {"x": 420, "y": 520},
            "data": {"period": 14, "label": "ADX14"},
        })
        edges.append({
            "id": "c18b_inst_adx", "source": "instrument", "target": adx_id,
            "sourceHandle": "instrument", "targetHandle": "instrument",
        })
    else:
        adx_id = "adx" if "adx" in ids else adx_id

    extra_nodes = [
        {"id": "adx_min_c18b", "type": "constant", "position": {"x": 420, "y": 600},
         "data": {"value": 25, "label": "25"}},
        {"id": "not_chop_c18b", "type": "logic_gt", "position": {"x": 640, "y": 520},
         "data": {"label": "ADX>25"}},
        {"id": "is_chop_c18b", "type": "logic_lt", "position": {"x": 640, "y": 600},
         "data": {"label": "ADX<25"}},
        # MR subgraph (unique ids)
        {"id": "bb_l_c18b", "type": "indicator_bb_lower", "position": {"x": 420, "y": 680},
         "data": {"period": 20, "mult": 2, "label": "BB−"}},
        {"id": "bb_m_c18b", "type": "indicator_bb", "position": {"x": 420, "y": 760},
         "data": {"period": 20, "mult": 2, "label": "BB mid"}},
        {"id": "rsi_c18b", "type": "indicator_rsi", "position": {"x": 420, "y": 840},
         "data": {"period": 14, "label": "RSI14"}},
        {"id": "rsi_lo_c18b", "type": "constant", "position": {"x": 420, "y": 920},
         "data": {"value": 30, "label": "30"}},
        {"id": "touch_lo_c18b", "type": "logic_lt", "position": {"x": 640, "y": 680},
         "data": {"label": "Close<BB−"}},
        {"id": "rsi_os_c18b", "type": "logic_lt", "position": {"x": 640, "y": 840},
         "data": {"label": "RSI<30"}},
        {"id": "mr_buy_c18b", "type": "logic_and", "position": {"x": 820, "y": 760},
         "data": {"label": "MR buy"}},
        {"id": "mr_in_chop_c18b", "type": "logic_and", "position": {"x": 980, "y": 720},
         "data": {"label": "MR∧chop"}},
        {"id": "trend_gated_c18b", "type": "logic_and", "position": {"x": 980, "y": 520},
         "data": {"label": "Trend∧!chop"}},
        {"id": "mroverlay_or", "type": "logic_or", "position": {"x": 1140, "y": 600},
         "data": {"label": "Trend∨MR"}},
        {"id": "cross_mid_c18b", "type": "logic_cross_up", "position": {"x": 640, "y": 760},
         "data": {"label": "×BB mid"}},
        {"id": "exit_or_c18b", "type": "logic_or", "position": {"x": 1140, "y": 800},
         "data": {"label": "Exit∨MR"}},
    ]
    nodes.extend(extra_nodes)

    extra_edges = [
        {"id": "c18b_adx_a", "source": adx_id, "target": "not_chop_c18b",
         "sourceHandle": "value", "targetHandle": "a"},
        {"id": "c18b_adx_b", "source": "adx_min_c18b", "target": "not_chop_c18b",
         "sourceHandle": "value", "targetHandle": "b"},
        {"id": "c18b_chop_a", "source": adx_id, "target": "is_chop_c18b",
         "sourceHandle": "value", "targetHandle": "a"},
        {"id": "c18b_chop_b", "source": "adx_min_c18b", "target": "is_chop_c18b",
         "sourceHandle": "value", "targetHandle": "b"},
        {"id": "c18b_c_bbl", "source": "close", "target": "bb_l_c18b",
         "sourceHandle": "value", "targetHandle": "source"},
        {"id": "c18b_c_bbm", "source": "close", "target": "bb_m_c18b",
         "sourceHandle": "value", "targetHandle": "source"},
        {"id": "c18b_c_rsi", "source": "close", "target": "rsi_c18b",
         "sourceHandle": "value", "targetHandle": "source"},
        {"id": "c18b_tl_a", "source": "close", "target": "touch_lo_c18b",
         "sourceHandle": "value", "targetHandle": "a"},
        {"id": "c18b_tl_b", "source": "bb_l_c18b", "target": "touch_lo_c18b",
         "sourceHandle": "value", "targetHandle": "b"},
        {"id": "c18b_rs_a", "source": "rsi_c18b", "target": "rsi_os_c18b",
         "sourceHandle": "value", "targetHandle": "a"},
        {"id": "c18b_rs_b", "source": "rsi_lo_c18b", "target": "rsi_os_c18b",
         "sourceHandle": "value", "targetHandle": "b"},
        {"id": "c18b_mr1", "source": "touch_lo_c18b", "target": "mr_buy_c18b",
         "sourceHandle": "result", "targetHandle": "conditions"},
        {"id": "c18b_mr2", "source": "rsi_os_c18b", "target": "mr_buy_c18b",
         "sourceHandle": "result", "targetHandle": "conditions"},
        {"id": "c18b_mic1", "source": "mr_buy_c18b", "target": "mr_in_chop_c18b",
         "sourceHandle": "result", "targetHandle": "conditions"},
        {"id": "c18b_mic2", "source": "is_chop_c18b", "target": "mr_in_chop_c18b",
         "sourceHandle": "result", "targetHandle": "conditions"},
        {"id": "c18b_cm_a", "source": "close", "target": "cross_mid_c18b",
         "sourceHandle": "value", "targetHandle": "a"},
        {"id": "c18b_cm_b", "source": "bb_m_c18b", "target": "cross_mid_c18b",
         "sourceHandle": "value", "targetHandle": "b"},
    ]

    # rewire open: orig sources → trend_gated with not_chop
    edges = [e for e in edges if not (e.get("target") == open_id and e.get("targetHandle") == "condition")]
    for i, ce in enumerate(open_conds):
        edges.append({
            "id": f"c18b_tg_src_{i}", "source": ce["source"], "target": "trend_gated_c18b",
            "sourceHandle": ce.get("sourceHandle") or "result", "targetHandle": "conditions",
        })
    edges.append({
        "id": "c18b_tg_adx", "source": "not_chop_c18b", "target": "trend_gated_c18b",
        "sourceHandle": "result", "targetHandle": "conditions",
    })
    edges += extra_edges
    edges += [
        {"id": "c18b_or1", "source": "trend_gated_c18b", "target": "mroverlay_or",
         "sourceHandle": "result", "targetHandle": "conditions"},
        {"id": "c18b_or2", "source": "mr_in_chop_c18b", "target": "mroverlay_or",
         "sourceHandle": "result", "targetHandle": "conditions"},
        {"id": "c18b_open", "source": "mroverlay_or", "target": open_id,
         "sourceHandle": "result", "targetHandle": "condition"},
    ]

    # rewire close: orig ∨ MR mid cross
    edges = [e for e in edges if not (e.get("target") == close_id and e.get("targetHandle") == "condition")]
    for i, ce in enumerate(close_conds):
        edges.append({
            "id": f"c18b_ex_src_{i}", "source": ce["source"], "target": "exit_or_c18b",
            "sourceHandle": ce.get("sourceHandle") or "result", "targetHandle": "conditions",
        })
    edges += [
        {"id": "c18b_ex_mr", "source": "cross_mid_c18b", "target": "exit_or_c18b",
         "sourceHandle": "result", "targetHandle": "conditions"},
        {"id": "c18b_close", "source": "exit_or_c18b", "target": close_id,
         "sourceHandle": "result", "targetHandle": "condition"},
    ]

    doc["graph"]["edges"] = edges
    return True


def save_doc(doc: dict, path: Path, *, base: str) -> None:
    doc = copy.deepcopy(doc)
    doc.setdefault("meta", {})
    doc["meta"]["updatedAt"] = NOW
    doc["meta"]["intervention"] = {
        "kind": KIND, "base": base, "adx_chop": 25, "bb": 20, "rsi_os": 30,
    }
    tags = list(doc["meta"].get("tags") or []) + ["c18b", "b1", f"intervention:{KIND}"]
    doc["meta"]["tags"] = list(dict.fromkeys(tags))
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")


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


def resolve_side(file_name: str) -> str:
    p = ITALGO / file_name
    if p.exists():
        sm = (json.loads(p.read_text()).get("meta") or {}).get("side_mode")
        if sm:
            return str(sm)
    return "long_short" if "-ls" in file_name else "long_only"


def buy_hold_div(bars, events, use_div: bool):
    if not bars or len(bars) < 2:
        return None
    raw = float(bars[-1]["close"]) - float(bars[0]["open"])
    if not use_div:
        return raw
    cash = sum(
        float(e.get("dividend_rub") or 0)
        for e in events_in_window(events, int(bars[0]["time"]), int(bars[-1]["time"]))
    )
    return raw + cash


def featurize(p: dict) -> List[float]:
    return [
        float(p["base_pnl"]), float(p["base_wr"]), float(p["base_trades"]), float(p["base_dd"]),
        float(p.get("buy_hold_pnl") or 0), float(p.get("base_edge_vs_bh") or 0),
        1.0 if p.get("base_beats_buy_hold") else 0.0,
        float(p.get("window_chop_share") or 0),
        float(p.get("base_frac_trades_in_chop") or 0),
        float(p.get("base_pnl_in_chop") or 0),
        float(p.get("base_pnl_in_trend") or 0),
        1.0 if p.get("script_regime") == "trend" else 0.0,
        1.0 if p.get("script_regime") == "breakout" else 0.0,
        1.0 if p.get("script_regime") == "unknown" else 0.0,
        1.0 if p.get("side_mode") == "long_only" else 0.0,
        1.0 if p.get("symbol") in FUTURES else 0.0,
        *[1.0 if p.get("symbol") == s else 0.0 for s in SYMBOLS],
        *[1.0 if p.get("timeframe") == t else 0.0 for t in TFS],
    ]


FEATURE_NAMES = (
    ["base_pnl", "base_wr", "base_trades", "base_dd", "buy_hold_pnl", "base_edge_vs_bh", "base_beats_bh",
     "window_chop_share", "base_frac_trades_in_chop", "base_pnl_in_chop", "base_pnl_in_trend",
     "script_trend", "script_breakout", "script_unknown", "side_lo", "is_future"]
    + [f"sym_{s}" for s in SYMBOLS]
    + [f"tf_{t}" for t in TFS]
)


def main() -> None:
    events_by_sym = load_dividend_cache()
    b0_ann = {}
    for rec in json.loads((B0 / "results" / "script_annotations.json").read_text()):
        b0_ann[(rec["symbol"], rec["timeframe"], rec["file"])] = rec

    bases = sorted(
        p for p in ITALGO.glob("*.italgo")
        if not p.name.startswith(PROMO) and "__" not in p.name
    )
    for old in (SESSION / "scripts").glob("*.italgo"):
        old.unlink()

    n_ok = 0
    failed = []
    for src in bases:
        base_doc = json.loads(src.read_text())
        shutil.copy(src, SESSION / "scripts" / src.name)
        d = copy.deepcopy(base_doc)
        if add_mr_overlay(d):
            d["meta"]["name"] = f"{base_doc['meta'].get('name', '')} +mr_overlay"
            out = SESSION / "scripts" / f"{src.stem}__mroverlay.italgo"
            save_doc(d, out, base=src.name)
            n_ok += 1
        else:
            failed.append(src.name)
    print("bases", len(bases), "mroverlay", n_ok, "skip", failed, flush=True)

    pairs = []
    engine_fail = 0
    for sym in SYMBOLS:
        for tf in TFS:
            bars_src = C16 / f"bars_{sym}_{tf}.json"
            if not bars_src.exists():
                print("SKIP", sym, tf, flush=True)
                continue
            bars = json.loads(bars_src.read_text())
            bp = SESSION / f"bars_{sym}_{tf}.json"
            bp.write_text(json.dumps(bars))
            rows = run_engine(SESSION / "scripts", bp, SESSION / f"engine_{sym}_{tf}.jsonl", sym, tf)
            by_file = {r["file"]: r for r in rows if r.get("ok")}
            for r in rows:
                if not r.get("ok") and "__mroverlay" in (r.get("file") or ""):
                    engine_fail += 1
            labels = classify_bars(bars)
            win = summarize_regimes(labels)
            print(sym, tf, "ok", len(by_file), "chop_share", round(win["chop_share"], 2), flush=True)

            for src in bases:
                base_name = src.name
                var_name = f"{src.stem}__mroverlay.italgo"
                b, v = by_file.get(base_name), by_file.get(var_name)
                if not b or not v:
                    continue
                side = resolve_side(base_name)
                use_div = sym in EQUITIES
                b_trades = list(b.get("trades") or [])
                v_trades = list(v.get("trades") or [])
                if use_div and sym in events_by_sym:
                    b_trades, _ = adjust_trades(b_trades, events_by_sym[sym])
                    v_trades, _ = adjust_trades(v_trades, events_by_sym[sym])
                    for t in b_trades:
                        if t.get("pnl_div_adjusted") is not None:
                            t["pnl"] = t["pnl_div_adjusted"]
                    for t in v_trades:
                        if t.get("pnl_div_adjusted") is not None:
                            t["pnl"] = t["pnl_div_adjusted"]

                bpnl = float(sum(float(t["pnl"]) for t in b_trades if t.get("pnl") is not None))
                vpnl = float(sum(float(t["pnl"]) for t in v_trades if t.get("pnl") is not None))
                if not use_div:
                    bpnl = float(b["stats"]["netPnl"])
                    vpnl = float(v["stats"]["netPnl"])
                delta = vpnl - bpnl
                bdd = float(b["stats"]["maxDrawdown"] or 0)
                vdd = float(v["stats"]["maxDrawdown"] or 0)
                dd_ok = True if bdd <= 1e-9 else (vdd <= bdd * 1.5 + 1e-9)

                bh = buy_hold_div(bars, events_by_sym.get(sym, []), use_div)
                base_bh = evaluate_vs_buy_hold(bars=bars, trades=b_trades, side_mode=side, net_pnl=bpnl)
                var_bh = evaluate_vs_buy_hold(bars=bars, trades=v_trades, side_mode=side, net_pnl=vpnl)
                if bh is not None:
                    base_bh = dict(base_bh)
                    var_bh = dict(var_bh)
                    base_bh["buy_hold_pnl"] = bh
                    var_bh["buy_hold_pnl"] = bh
                    if side == "long_only":
                        base_cmp = float(base_bh.get("long_trades_pnl") or 0)
                        var_cmp = float(var_bh.get("long_trades_pnl") or 0)
                    else:
                        base_cmp, var_cmp = bpnl, vpnl
                    base_bh["edge_vs_bh"] = base_cmp - bh
                    var_bh["edge_vs_bh"] = var_cmp - bh
                    base_bh["beats_buy_hold"] = base_cmp > bh
                    var_bh["beats_buy_hold"] = var_cmp > bh

                base_edge = float(base_bh.get("edge_vs_bh") or 0)
                var_edge = float(var_bh.get("edge_vs_bh") or 0)
                delta_edge = var_edge - base_edge
                better = (
                    delta > 1e-6 and dd_ok and delta_edge > 1e-6
                    and bool(var_bh.get("beats_buy_hold"))
                    and not bool(var_bh.get("pseudo_buy_hold"))
                )

                b_reg = annotate_trades(b_trades, bars, labels)
                v_reg = annotate_trades(v_trades, bars, labels)
                b0 = b0_ann.get((sym, tf, base_name), {})
                sreg = b0.get("script_regime") or infer_script_regime(b.get("nodes"))
                closed_b = [t for t in b_trades if t.get("pnl") is not None]
                wr = (sum(1 for t in closed_b if float(t["pnl"]) > 0) / len(closed_b)) if closed_b else 0.0

                pairs.append({
                    "symbol": sym, "timeframe": tf, "base": base_name, "variant": var_name, "kind": KIND,
                    "asset_class": "future" if sym in FUTURES else "equity",
                    "side_mode": side, "script_regime": sreg,
                    "base_pnl": bpnl, "variant_pnl": vpnl, "delta_pnl": delta,
                    "better": better, "dd_ok": dd_ok,
                    "base_wr": wr, "base_trades": float(len(closed_b)),
                    "base_dd": bdd, "variant_dd": vdd,
                    "buy_hold_pnl": base_bh.get("buy_hold_pnl"),
                    "base_edge_vs_bh": base_edge, "variant_edge_vs_bh": var_edge,
                    "delta_edge_vs_bh": delta_edge,
                    "base_beats_buy_hold": bool(base_bh.get("beats_buy_hold")),
                    "variant_beats_buy_hold": bool(var_bh.get("beats_buy_hold")),
                    "window_chop_share": win["chop_share"],
                    "base_frac_trades_in_chop": b_reg["frac_trades_in_chop"],
                    "base_pnl_in_chop": b_reg["pnl_in_chop"],
                    "base_pnl_in_trend": b_reg["pnl_in_trend"],
                    "delta_pnl_in_chop": v_reg["pnl_in_chop"] - b_reg["pnl_in_chop"],
                    "delta_pnl_in_trend": v_reg["pnl_in_trend"] - b_reg["pnl_in_trend"],
                    "better_in_chop": (v_reg["pnl_in_chop"] - b_reg["pnl_in_chop"]) > 1e-6,
                })

    print(
        "pairs", len(pairs), "better", sum(1 for p in pairs if p["better"]),
        "better_in_chop", sum(1 for p in pairs if p["better_in_chop"]),
        "engine_fail_mroverlay", engine_fail, flush=True,
    )
    if len(pairs) < 30:
        raise SystemExit("too few pairs")

    X = np.array([featurize(p) for p in pairs], dtype=float)
    y = np.array([1 if p["better"] else 0 for p in pairs], dtype=int)
    w = np.array([
        1.0 + min(abs(p["delta_pnl"]) / 50.0, 6.0)
        + min(abs(p.get("delta_pnl_in_chop") or 0) / 50.0, 4.0)
        for p in pairs
    ], dtype=float)

    metrics: Dict[str, Any] = {"n": len(y), "positives": int(y.sum()), "better_rate": float(y.mean())}
    if len(set(y.tolist())) >= 2:
        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        preds = np.zeros(len(y))
        probas = np.zeros(len(y))
        for tr, te in skf.split(X, y):
            clf = lgb.LGBMClassifier(
                n_estimators=160, max_depth=4, learning_rate=0.06, subsample=0.85,
                colsample_bytree=0.85, min_child_samples=5, verbosity=-1, random_state=42,
            )
            clf.fit(X[tr], y[tr], sample_weight=w[tr])
            preds[te] = clf.predict(X[te])
            probas[te] = clf.predict_proba(X[te])[:, 1]
        metrics["cv_accuracy"] = float(accuracy_score(y, preds))
        try:
            metrics["cv_auc"] = float(roc_auc_score(y, probas))
        except ValueError:
            metrics["cv_auc"] = float("nan")
        final = lgb.LGBMClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.06, subsample=0.85,
            colsample_bytree=0.85, min_child_samples=5, verbosity=-1, random_state=42,
        )
        final.fit(X, y, sample_weight=w)
        imp = sorted(zip(FEATURE_NAMES, final.feature_importances_.tolist()), key=lambda x: -x[1])
        joblib.dump({
            "model": final, "feature_names": list(FEATURE_NAMES), "kinds": [KIND],
            "symbols": SYMBOLS, "timeframes": TFS, "metrics": metrics,
            "label_rule": "C17-style + chop features; kind=add_mr_overlay",
        }, SESSION / "models" / "intervention_policy_lgbm.joblib")
    else:
        metrics["cv_accuracy"] = float("nan")
        metrics["cv_auc"] = float("nan")
        imp = []

    key_stats = defaultdict(lambda: {"wins": 0, "n": 0, "sum_delta": 0.0, "sum_d_chop": 0.0, "by_sym": {}})
    for p in pairs:
        if p["timeframe"] != "1d":
            continue
        k = p["base"]
        key_stats[k]["n"] += 1
        key_stats[k]["sum_delta"] += p["delta_pnl"]
        key_stats[k]["sum_d_chop"] += float(p.get("delta_pnl_in_chop") or 0)
        key_stats[k]["by_sym"][p["symbol"]] = {
            "delta": p["delta_pnl"], "better": p["better"], "variant_pnl": p["variant_pnl"],
            "beats_bh": p.get("variant_beats_buy_hold"), "d_chop": p.get("delta_pnl_in_chop"),
            "variant": p["variant"],
        }
        if p["better"]:
            key_stats[k]["wins"] += 1

    promoted = []
    LIB.mkdir(parents=True, exist_ok=True)
    for base, st in key_stats.items():
        sym_wins = [
            s for s, v in st["by_sym"].items()
            if v["better"] and v["variant_pnl"] > 0 and v.get("beats_bh")
        ]
        mean_delta = st["sum_delta"] / max(1, st["n"])
        mean_d_chop = st["sum_d_chop"] / max(1, st["n"])
        if len(sym_wins) >= 5 and mean_delta >= 10 and mean_d_chop > 0:
            variant = next(iter(st["by_sym"].values()))["variant"]
            src = SESSION / "scripts" / variant
            if not src.exists():
                continue
            out_name = f"38p-{base.replace('.italgo', '')}__mroverlay.italgo"
            doc = json.loads(src.read_text())
            doc["meta"]["name"] = f"[regime-mr] {doc['meta'].get('name')}"
            doc["meta"]["tags"] = list(dict.fromkeys(
                (doc["meta"].get("tags") or []) + ["promoted", "c18b", "mr-overlay", "regime"]
            ))
            doc["meta"]["cross_symbol"] = {
                "symbols_win": sorted(sym_wins), "mean_delta": mean_delta,
                "mean_delta_pnl_in_chop": mean_d_chop,
            }
            text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
            (ITALGO / out_name).write_text(text)
            (LIB / out_name).write_text(text)
            (SESSION / "scripts" / out_name).write_text(text)
            promoted.append({
                "to": out_name, "base": base, "kind": KIND,
                "mean_delta": mean_delta, "mean_delta_pnl_in_chop": mean_d_chop,
                "symbols_win": sorted(sym_wins), "n_symbols_win": len(sym_wins),
            })
    promoted.sort(key=lambda x: (-x["n_symbols_win"], -x["mean_delta_pnl_in_chop"]))

    # vs C18 gate on overlapping bases
    gate_cmp = None
    gate_path = C18 / "results" / "intervention_pairs.json"
    if gate_path.exists():
        gate = json.loads(gate_path.read_text())
        g_by = {(p["symbol"], p["timeframe"], p["base"]): p for p in gate}
        both = []
        for p in pairs:
            g = g_by.get((p["symbol"], p["timeframe"], p["base"]))
            if not g:
                continue
            both.append({
                "symbol": p["symbol"], "tf": p["timeframe"], "base": p["base"],
                "d_overlay": p["delta_pnl"], "d_gate": g["delta_pnl"],
                "d_chop_overlay": p["delta_pnl_in_chop"], "d_chop_gate": g.get("delta_pnl_in_chop"),
            })
        if both:
            gate_cmp = {
                "n_overlap": len(both),
                "mean_d_overlay": float(np.mean([x["d_overlay"] for x in both])),
                "mean_d_gate": float(np.mean([x["d_gate"] for x in both])),
                "mean_d_chop_overlay": float(np.mean([x["d_chop_overlay"] for x in both])),
                "mean_d_chop_gate": float(np.mean([x["d_chop_gate"] for x in both if x["d_chop_gate"] is not None])),
                "overlay_wins_vs_gate": sum(1 for x in both if x["d_overlay"] > x["d_gate"]),
            }

    summary = {
        "session": "2026-08-21-c18b-mr-overlay",
        "kind": KIND,
        "n_pairs": len(pairs),
        "n_better": int(y.sum()),
        "n_better_in_chop": sum(1 for p in pairs if p["better_in_chop"]),
        "mean_delta": float(np.mean([p["delta_pnl"] for p in pairs])),
        "mean_delta_pnl_in_chop": float(np.mean([p["delta_pnl_in_chop"] for p in pairs])),
        "model": metrics,
        "n_promoted": len(promoted),
        "vs_chop_gate": gate_cmp,
        "feature_importance_top": imp[:20],
        "n_overlay_ok_bases": n_ok,
        "engine_fail_mroverlay_rows": engine_fail,
    }

    (SESSION / "results" / "intervention_pairs.json").write_text(json.dumps(pairs, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "results" / "promoted.json").write_text(json.dumps(promoted, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "results" / "variant_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "models" / "feature_names.json").write_text(json.dumps({
        "feature_names": list(FEATURE_NAMES), "metrics": metrics, "importance": imp[:25],
    }, indent=2) + "\n")

    vs = ""
    if gate_cmp:
        vs = (
            f"- vs gate (n={gate_cmp['n_overlap']}): meanΔ overlay {gate_cmp['mean_d_overlay']:.1f} "
            f"vs gate {gate_cmp['mean_d_gate']:.1f}; Δchop {gate_cmp['mean_d_chop_overlay']:.1f} "
            f"vs {gate_cmp['mean_d_chop_gate']:.1f}; overlay>gate {gate_cmp['overlay_wins_vs_gate']}"
        )
    (SESSION / "REPORT.md").write_text("\n".join([
        "# C18b / B1 mr_overlay",
        "",
        f"- Overlay bases: {n_ok} · pairs: {len(pairs)} · better: {int(y.sum())} ({100*y.mean():.1f}%)",
        f"- better_in_chop: {sum(1 for p in pairs if p['better_in_chop'])}",
        f"- mean ΔPnL: {summary['mean_delta']:.1f} · mean Δchop: {summary['mean_delta_pnl_in_chop']:.1f}",
        f"- CV: {metrics.get('cv_accuracy')} / {metrics.get('cv_auc')}",
        f"- Promoted 38p-*: {len(promoted)}",
        vs,
    ]) + "\n")
    (SESSION / "notes.md").write_text(
        "C18b: add_mr_overlay = (trend∧ADX>25) ∨ (BB/RSI MR ∧ ADX<25); exit ∨ BB mid cross; skip MR bases & LS.\n"
    )

    prom_rows = "".join(
        f"<tr><td class='f'>{p['to']}</td><td>{p['mean_delta']:.1f}</td>"
        f"<td>{p['mean_delta_pnl_in_chop']:.1f}</td><td>{p['n_symbols_win']}</td></tr>"
        for p in promoted[:20]
    )
    cmp_html = ""
    if gate_cmp:
        cmp_html = (
            f"<div class='card'><div class='k'>vs gate meanΔ</div>"
            f"<div class='v'>{gate_cmp['mean_d_overlay']:.0f} / {gate_cmp['mean_d_gate']:.0f}</div></div>"
        )
    html = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"/><title>C18b mr_overlay</title>
<style>
body{{font-family:IBM Plex Sans,system-ui,sans-serif;background:#0f1419;color:#e8eef4;padding:28px}}
.card{{background:#1a222c;border:1px solid #2a3542;border-radius:10px;padding:12px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.k{{color:#8b9aab;font-size:.68rem;text-transform:uppercase}} .v{{font-size:1.1rem;font-weight:600;margin-top:4px}}
table{{border-collapse:collapse;width:100%;font-size:.75rem;background:#1a222c;margin-top:12px}}
th,td{{border:1px solid #2a3542;padding:6px;text-align:right}} td.f,th{{text-align:left;color:#8b9aab}}
</style></head><body>
<h1>C18b — add_mr_overlay</h1>
<div class="grid">
<div class="card"><div class="k">Pairs</div><div class="v">{len(pairs)}</div></div>
<div class="card"><div class="k">Better</div><div class="v">{int(y.sum())} ({100*y.mean():.0f}%)</div></div>
<div class="card"><div class="k">Mean Δchop</div><div class="v">{summary['mean_delta_pnl_in_chop']:.1f}</div></div>
<div class="card"><div class="k">38p</div><div class="v">{len(promoted)}</div></div>
{cmp_html}
</div>
<table><thead><tr><th>promoted</th><th>mean Δ</th><th>mean Δchop</th><th>n win</th></tr></thead>
<tbody>{prom_rows or '<tr><td colspan=4>none</td></tr>'}</tbody></table>
</body></html>"""
    (SESSION / "ANALYTICS.html").write_text(html)
    print("MODEL", metrics, "promoted", len(promoted), "vs_gate", gate_cmp, flush=True)


if __name__ == "__main__":
    main()
