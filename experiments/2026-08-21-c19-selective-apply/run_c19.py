#!/usr/bin/env python3
"""C19: selective apply — gate/overlay only when B0b chop≥THR and model says better."""
from __future__ import annotations

import json
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import lightgbm as lgb
import numpy as np
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold

ROOT = Path("/Users/kreckeroff/Fintech (startup)/AI_algo")
DESKTOP = ROOT.parent / "it-algo-desktop"
ITALGO = DESKTOP / "docs/work/scripting/samples/ai-train"
C18 = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c18-regime-dual"
C18B = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c18b-mr-overlay"
B0B = ROOT / "artifacts/agent_loop/sessions/2026-08-21-b0b-regime-thresholds"
SESSION = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c19-selective-apply"
LIB = Path.home() / (
    "Library/Application Support/ru.it-algo.desktop/scripting/"
    "6882ee6d-8a3f-4eda-a4a9-235652c2b455/library/ai-train"
)

EQUITIES = ["SBER", "GAZP", "LKOH", "ROSN", "GMKN", "NVTK", "TATN", "PLZL", "MGNT", "MTSS"]
FUTURES = ["CNYRUBF", "GLDRUBF", "IMOEXF"]
SYMBOLS = EQUITIES + FUTURES
TFS = ["1d", "1h"]
CHOP_THR = 0.38
PROBA_THR = 0.55
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

SESSION.mkdir(parents=True, exist_ok=True)
for sub in ("results", "models", "scripts"):
    (SESSION / sub).mkdir(exist_ok=True)


def featurize(p: dict) -> List[float]:
    return [
        float(p["base_pnl"]), float(p["base_wr"]), float(p["base_trades"]), float(p["base_dd"]),
        float(p.get("buy_hold_pnl") or 0), float(p.get("base_edge_vs_bh") or 0),
        1.0 if p.get("base_beats_buy_hold") else 0.0,
        float(p.get("window_chop_share") or 0),
        float(p.get("window_trend_share") or 0),
        float(p.get("window_transition_share") or 0),
        float(p.get("base_frac_trades_in_chop") or 0),
        float(p.get("base_pnl_in_chop") or 0),
        float(p.get("base_pnl_in_trend") or 0),
        1.0 if p.get("script_regime") == "trend" else 0.0,
        1.0 if p.get("script_regime") == "breakout" else 0.0,
        1.0 if p.get("script_regime") == "mean_reversion" else 0.0,
        1.0 if p.get("side_mode") == "long_only" else 0.0,
        1.0 if p.get("symbol") in FUTURES else 0.0,
        *[1.0 if p.get("symbol") == s else 0.0 for s in SYMBOLS],
        *[1.0 if p.get("timeframe") == t else 0.0 for t in TFS],
        1.0 if p.get("kind") == "add_chop_gate" else 0.0,
        1.0 if p.get("kind") == "add_mr_overlay" else 0.0,
    ]


FEATURE_NAMES = (
    ["base_pnl", "base_wr", "base_trades", "base_dd", "buy_hold_pnl", "base_edge_vs_bh", "base_beats_bh",
     "window_chop_share", "window_trend_share", "window_transition_share",
     "base_frac_trades_in_chop", "base_pnl_in_chop", "base_pnl_in_trend",
     "script_trend", "script_breakout", "script_mr", "side_lo", "is_future"]
    + [f"sym_{s}" for s in SYMBOLS]
    + [f"tf_{t}" for t in TFS]
    + ["kind_gate", "kind_overlay"]
)


def merge_dataset() -> List[dict]:
    """Join original pairs (PnL/labels) with B0b rescored regime features."""
    out = []
    for session, rescored_name, kind in (
        (C18, "c18_rescored_b0b.json", "add_chop_gate"),
        (C18B, "c18b_rescored_b0b.json", "add_mr_overlay"),
    ):
        orig = json.loads((session / "results" / "intervention_pairs.json").read_text())
        resc = json.loads((B0B / "results" / rescored_name).read_text())
        by_r = {(r["symbol"], r["timeframe"], r["base"]): r for r in resc}
        for p in orig:
            r = by_r.get((p["symbol"], p["timeframe"], p["base"]))
            if not r:
                continue
            row = dict(p)
            row["kind"] = kind
            row["window_chop_share"] = r["window_chop_share"]
            row["window_trend_share"] = r["window_trend_share"]
            row["window_transition_share"] = r.get("window_transition_share", 0.0)
            row["base_frac_trades_in_chop"] = r["base_frac_trades_in_chop"]
            row["delta_pnl_in_chop"] = r["delta_pnl_in_chop"]
            row["delta_pnl_in_trend"] = r["delta_pnl_in_trend"]
            row["better_in_chop"] = r["better_in_chop"]
            # keep base_pnl_in_chop from original if present else 0
            out.append(row)
    return out


def cv_train(pairs: List[dict]) -> Tuple[dict, np.ndarray, np.ndarray, Any]:
    X = np.array([featurize(p) for p in pairs], dtype=float)
    y = np.array([1 if p["better"] else 0 for p in pairs], dtype=int)
    w = np.array([
        1.0 + min(abs(p["delta_pnl"]) / 50.0, 6.0)
        + (2.0 if p.get("window_chop_share", 0) >= CHOP_THR else 0.0)
        for p in pairs
    ], dtype=float)
    metrics: Dict[str, Any] = {"n": len(y), "positives": int(y.sum()), "better_rate": float(y.mean())}
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    preds = np.zeros(len(y))
    probas = np.zeros(len(y))
    for tr, te in skf.split(X, y):
        clf = lgb.LGBMClassifier(
            n_estimators=180, max_depth=4, learning_rate=0.06, subsample=0.85,
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
        n_estimators=220, max_depth=4, learning_rate=0.06, subsample=0.85,
        colsample_bytree=0.85, min_child_samples=5, verbosity=-1, random_state=42,
    )
    final.fit(X, y, sample_weight=w)
    return metrics, preds, probas, final


def simulate(pairs: List[dict], apply_mask: np.ndarray) -> Dict[str, float]:
    base = np.array([p["base_pnl"] for p in pairs], dtype=float)
    var = np.array([p["variant_pnl"] for p in pairs], dtype=float)
    chosen = np.where(apply_mask, var, base)
    return {
        "mean_pnl": float(chosen.mean()),
        "mean_base": float(base.mean()),
        "lift_vs_base": float(chosen.mean() - base.mean()),
        "apply_rate": float(apply_mask.mean()),
        "n_apply": int(apply_mask.sum()),
        "mean_delta_when_applied": float((var[apply_mask] - base[apply_mask]).mean()) if apply_mask.any() else 0.0,
    }


def promote_selective(pairs: List[dict], probas: np.ndarray) -> List[dict]:
    """Promote bases with ≥3 high-chop wins (better∧pnl>0∧beats BH) and mean Δchop>0."""
    _ = probas  # reserved for future model-gated promote
    key_stats = defaultdict(
        lambda: {"wins": 0, "n_high": 0, "sum_delta": 0.0, "sum_d_chop": 0.0, "slots": [], "kind": "", "base": ""}
    )
    for p in pairs:
        if p["window_chop_share"] < CHOP_THR:
            continue
        k = (p["kind"], p["base"])
        st = key_stats[k]
        st["kind"], st["base"] = p["kind"], p["base"]
        st["n_high"] += 1
        st["sum_delta"] += p["delta_pnl"]
        st["sum_d_chop"] += float(p.get("delta_pnl_in_chop") or 0)
        if p["better"] and p["variant_pnl"] > 0 and p.get("variant_beats_buy_hold"):
            st["wins"] += 1
            st["slots"].append(f"{p['symbol']}:{p['timeframe']}")

    promoted = []
    LIB.mkdir(parents=True, exist_ok=True)
    for (kind, base), st in key_stats.items():
        if st["n_high"] < 3:
            continue
        mean_delta = st["sum_delta"] / st["n_high"]
        mean_d_chop = st["sum_d_chop"] / st["n_high"]
        if st["wins"] < 3 or mean_delta < 5 or mean_d_chop <= 0:
            continue
        stem = base.replace(".italgo", "")
        if kind == "add_chop_gate":
            src = C18 / "scripts" / f"{stem}__chopgate.italgo"
            tag = "chopgate"
        else:
            src = C18B / "scripts" / f"{stem}__mroverlay.italgo"
            tag = "mroverlay"
        if not src.exists():
            continue
        out_name = f"38p-{stem}__{tag}_sel.italgo"
        doc = json.loads(src.read_text())
        doc["meta"]["name"] = f"[sel-chop≥{CHOP_THR}] {doc['meta'].get('name')}"
        doc["meta"]["tags"] = list(dict.fromkeys(
            (doc["meta"].get("tags") or []) + ["promoted", "c19", "selective", "regime", tag]
        ))
        doc["meta"]["selective_apply"] = {
            "chop_thr": CHOP_THR, "proba_thr": PROBA_THR,
            "wins": st["wins"], "n_high": st["n_high"],
            "mean_delta": mean_delta, "mean_delta_pnl_in_chop": mean_d_chop,
            "slots": sorted(st["slots"]),
        }
        doc["meta"]["updatedAt"] = NOW
        text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
        (ITALGO / out_name).write_text(text)
        (LIB / out_name).write_text(text)
        (SESSION / "scripts" / out_name).write_text(text)
        promoted.append({
            "to": out_name, "base": base, "kind": kind,
            "wins": st["wins"], "n_high": st["n_high"],
            "mean_delta": mean_delta, "mean_delta_pnl_in_chop": mean_d_chop,
            "slots": sorted(st["slots"]),
        })
    promoted.sort(key=lambda x: (-x["wins"], -x["mean_delta_pnl_in_chop"]))
    return promoted


def main() -> None:
    pairs = merge_dataset()
    print("pairs", len(pairs), "gate", sum(1 for p in pairs if p["kind"] == "add_chop_gate"),
          "overlay", sum(1 for p in pairs if p["kind"] == "add_mr_overlay"), flush=True)

    metrics, preds, probas, model = cv_train(pairs)
    print("MODEL", metrics, flush=True)

    chop = np.array([p["window_chop_share"] for p in pairs], dtype=float)
    better = np.array([1 if p["better"] else 0 for p in pairs], dtype=bool)

    policies = {
        "never": np.zeros(len(pairs), dtype=bool),
        "always": np.ones(len(pairs), dtype=bool),
        f"high_chop>={CHOP_THR}": chop >= CHOP_THR,
        f"model>={PROBA_THR}": probas >= PROBA_THR,
        f"sel chop&model": (chop >= CHOP_THR) & (probas >= PROBA_THR),
        "oracle high_chop&better": (chop >= CHOP_THR) & better,
    }
    sims = {name: simulate(pairs, mask) for name, mask in policies.items()}

    # per-kind selective
    by_kind = {}
    for kind in ("add_chop_gate", "add_mr_overlay"):
        idx = np.array([p["kind"] == kind for p in pairs])
        sub_pairs = [p for p, m in zip(pairs, idx) if m]
        sub_probas = probas[idx]
        sub_chop = chop[idx]
        sub_better = better[idx]
        by_kind[kind] = {
            "n": len(sub_pairs),
            "always": simulate(sub_pairs, np.ones(len(sub_pairs), dtype=bool)),
            "sel": simulate(sub_pairs, (sub_chop >= CHOP_THR) & (sub_probas >= PROBA_THR)),
            "oracle": simulate(sub_pairs, (sub_chop >= CHOP_THR) & sub_better),
        }

    promoted = promote_selective(pairs, probas)
    print("promoted", len(promoted), flush=True)

    imp = sorted(zip(FEATURE_NAMES, model.feature_importances_.tolist()), key=lambda x: -x[1])
    joblib.dump({
        "model": model, "feature_names": list(FEATURE_NAMES),
        "kinds": ["add_chop_gate", "add_mr_overlay"],
        "metrics": metrics, "chop_thr": CHOP_THR, "proba_thr": PROBA_THR,
        "label_rule": "C17 better; selective apply if chop>=THR and P>=PROBA",
        "defaults_note": "B0b regime features",
    }, SESSION / "models" / "intervention_policy_lgbm.joblib")

    summary = {
        "session": "2026-08-21-c19-selective-apply",
        "chop_thr": CHOP_THR,
        "proba_thr": PROBA_THR,
        "n_pairs": len(pairs),
        "model": metrics,
        "policies": sims,
        "by_kind": by_kind,
        "n_promoted": len(promoted),
        "feature_importance_top": imp[:20],
    }
    (SESSION / "results" / "pairs_merged.json").write_text(json.dumps(pairs, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "results" / "promoted.json").write_text(json.dumps(promoted, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "results" / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "models" / "feature_names.json").write_text(json.dumps({
        "feature_names": list(FEATURE_NAMES), "metrics": metrics, "importance": imp[:25],
    }, indent=2) + "\n")

    sel = sims["sel chop&model"]
    oracle = sims["oracle high_chop&better"]
    report = [
        "# C19 selective apply",
        "",
        f"- Pairs: {len(pairs)} (gate+overlay) · CHOP_THR={CHOP_THR} · PROBA_THR={PROBA_THR}",
        f"- CV: {metrics['cv_accuracy']:.3f} / {metrics['cv_auc']:.3f}",
        f"- Always apply lift: {sims['always']['lift_vs_base']:.1f}",
        f"- Selective (chop∧model) lift: **{sel['lift_vs_base']:.1f}** (apply {sel['apply_rate']:.1%}, n={sel['n_apply']})",
        f"- Oracle (chop∧better) lift: {oracle['lift_vs_base']:.1f}",
        f"- Gate sel lift: {by_kind['add_chop_gate']['sel']['lift_vs_base']:.1f}",
        f"- Overlay sel lift: {by_kind['add_mr_overlay']['sel']['lift_vs_base']:.1f}",
        f"- Promoted 38p-*_sel: {len(promoted)}",
    ]
    (SESSION / "REPORT.md").write_text("\n".join(report) + "\n")
    (SESSION / "notes.md").write_text(
        f"C19: apply gate/overlay only if B0b window_chop>={CHOP_THR} and P(better)>={PROBA_THR}.\n"
    )

    prom_rows = "".join(
        f"<tr><td class='f'>{p['to']}</td><td>{p['kind'].replace('add_','')}</td>"
        f"<td>{p['wins']}</td><td>{p['mean_delta']:.1f}</td><td>{p['mean_delta_pnl_in_chop']:.1f}</td></tr>"
        for p in promoted[:25]
    )
    html = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"/><title>C19 selective</title>
<style>
body{{font-family:IBM Plex Sans,system-ui,sans-serif;background:#0f1419;color:#e8eef4;padding:28px}}
.card{{background:#1a222c;border:1px solid #2a3542;border-radius:10px;padding:12px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.k{{color:#8b9aab;font-size:.68rem;text-transform:uppercase}} .v{{font-size:1.1rem;font-weight:600;margin-top:4px}}
table{{border-collapse:collapse;width:100%;font-size:.75rem;background:#1a222c;margin-top:14px}}
th,td{{border:1px solid #2a3542;padding:6px;text-align:right}} td.f,th{{text-align:left;color:#8b9aab}}
.pos{{color:#6dcea4}} .neg{{color:#e07a7a}}
</style></head><body>
<h1>C19 — selective apply</h1>
<div class="grid">
<div class="card"><div class="k">CV AUC</div><div class="v">{metrics['cv_auc']:.3f}</div></div>
<div class="card"><div class="k">Always lift</div><div class="v {'neg' if sims['always']['lift_vs_base']<0 else 'pos'}">{sims['always']['lift_vs_base']:.0f}</div></div>
<div class="card"><div class="k">Selective lift</div><div class="v {'pos' if sel['lift_vs_base']>0 else 'neg'}">{sel['lift_vs_base']:.0f}</div></div>
<div class="card"><div class="k">38p sel</div><div class="v">{len(promoted)}</div></div>
</div>
<table><thead><tr><th>policy</th><th>lift</th><th>apply%</th><th>meanΔ applied</th></tr></thead><tbody>
{''.join(f"<tr><td class='f'>{n}</td><td>{s['lift_vs_base']:.1f}</td><td>{100*s['apply_rate']:.0f}%</td><td>{s['mean_delta_when_applied']:.1f}</td></tr>" for n,s in sims.items())}
</tbody></table>
<table><thead><tr><th>promoted</th><th>kind</th><th>wins</th><th>meanΔ</th><th>meanΔchop</th></tr></thead>
<tbody>{prom_rows or '<tr><td colspan=5>none</td></tr>'}</tbody></table>
</body></html>"""
    (SESSION / "ANALYTICS.html").write_text(html)
    print(json.dumps({"model": metrics, "sel": sel, "oracle": oracle, "n_promoted": len(promoted)}, indent=2))


if __name__ == "__main__":
    main()
