#!/usr/bin/env python3
"""C11 / §7F: expand to 9 tickers (+TATN+PLZL+MGNT).

Reuses C8 script variants; expands dataset across instruments; retrains LightGBM
with symbol features; reports cross-symbol stable interventions.
"""
from __future__ import annotations

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
SRC_SCRIPTS = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c10-multi-symbol-expand"
SESSION = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c11-multi-symbol-9"
RAW = ROOT / "artifacts/agent_loop/sessions/2026-08-21-multi-indicator-wave/data/raw"
LIB = Path.home() / (
    "Library/Application Support/ru.it-algo.desktop/scripting/"
    "6882ee6d-8a3f-4eda-a4a9-235652c2b455/library/ai-train"
)

sys.path.insert(0, str(ROOT / "src"))
from ai_algo.domain.trade_analysis import analyze_trades  # noqa: E402

SYMBOLS = ["SBER", "GAZP", "LKOH", "ROSN", "GMKN", "NVTK", "TATN", "PLZL", "MGNT"]
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
    "add_block_ema",
    "add_block_adx",
    "add_block_sma200",
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


def run_engine(scripts_dir: Path, bars_path: Path, out: Path, symbol: str) -> List[dict]:
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
        symbol,
        "--timeframe",
        "1d",
        "--trades",
        "--out",
        str(out),
    ]
    print("RUN", symbol, out.name, flush=True)
    r = subprocess.run(cmd, cwd=str(DESKTOP))
    if r.returncode != 0:
        raise SystemExit(r.returncode)
    return [json.loads(l) for l in out.read_text().splitlines() if l.strip()]


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
    return feats


def esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def infer_kind(var_name: str) -> Optional[str]:
    if "__period15x" in var_name:
        return "change_period_15x"
    if "__period067" in var_name:
        return "change_period_067"
    if "__ema50" in var_name:
        return "add_block_ema"
    if "__adx25" in var_name:
        return "add_block_adx"
    if "__sma200" in var_name:
        return "add_block_sma200"
    return None


def base_of_variant(var_name: str) -> Optional[str]:
    if "__" not in var_name:
        return None
    return var_name.split("__", 1)[0] + ".italgo"


def main() -> None:
    # copy C8 scripts (bases + variants), skip promoted
    src_dir = SRC_SCRIPTS / "scripts"
    n_copy = 0
    for p in src_dir.glob("*.italgo"):
        if p.name.startswith(("27p-", "28p-", "29p-", "30p-", "31p-")):
            continue
        shutil.copy(p, SESSION / "scripts" / p.name)
        n_copy += 1
    print("scripts copied", n_copy, flush=True)

    variants_meta: List[Tuple[str, str, str]] = []
    for p in sorted((SESSION / "scripts").glob("*__*.italgo")):
        kind = infer_kind(p.name)
        base = base_of_variant(p.name)
        if kind and base and (SESSION / "scripts" / base).exists():
            variants_meta.append((base, p.name, kind))
    print("variants", len(variants_meta), flush=True)

    by_sym: Dict[str, Dict[str, dict]] = {}
    for sym in SYMBOLS:
        csv = RAW / f"MOEX_{sym}_1d.csv"
        bars = load_csv(csv)
        bp = SESSION / f"bars_{sym}_1d.json"
        bp.write_text(json.dumps(bars))
        rows = run_engine(SESSION / "scripts", bp, SESSION / f"engine_{sym}.jsonl", sym)
        by_sym[sym] = {r["file"]: r for r in rows if r.get("ok")}
        print(sym, "ok", len(by_sym[sym]), "bars", len(bars), flush=True)

    pairs = []
    for sym in SYMBOLS:
        by_file = by_sym[sym]
        for base_name, var_name, kind in variants_meta:
            b, v = by_file.get(base_name), by_file.get(var_name)
            if not b or not v:
                continue
            rb = analyze_trades(b.get("trades"), graph_nodes=b.get("nodes"))
            bpnl, vpnl = b["stats"]["netPnl"], v["stats"]["netPnl"]
            delta = vpnl - bpnl
            side = "unknown"
            base_path = ITALGO / base_name
            if base_path.exists():
                side = (json.loads(base_path.read_text()).get("meta") or {}).get("side_mode", "unknown")
            pairs.append(
                {
                    "symbol": sym,
                    "base": base_name,
                    "variant": var_name,
                    "kind": kind,
                    "side_mode": side,
                    "base_pnl": bpnl,
                    "variant_pnl": vpnl,
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
        + [f"sym_{s}" for s in SYMBOLS]
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
            n_estimators=100,
            max_depth=3,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            min_child_samples=3,
            verbosity=-1,
            random_state=42,
        )
        clf.fit(Xtr, ytr)
        preds[test_idx] = clf.predict(Xte)[0]
        probas[test_idx] = clf.predict_proba(Xte)[0, 1]

    acc = float(accuracy_score(y, preds))
    try:
        auc = float(roc_auc_score(y, probas))
    except ValueError:
        auc = float("nan")

    # leave-one-symbol-out
    loso = {}
    for hold in SYMBOLS:
        tr = [i for i, p in enumerate(pairs) if p["symbol"] != hold]
        te = [i for i, p in enumerate(pairs) if p["symbol"] == hold]
        if not tr or not te:
            continue
        ytr = y[tr]
        if len(set(ytr)) < 2:
            continue
        clf = lgb.LGBMClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            min_child_samples=3,
            verbosity=-1,
            random_state=42,
        )
        clf.fit(X[tr], ytr)
        pred = clf.predict(X[te])
        proba = clf.predict_proba(X[te])[:, 1]
        a = float(accuracy_score(y[te], pred))
        try:
            u = float(roc_auc_score(y[te], proba))
        except ValueError:
            u = float("nan")
        loso[hold] = {"accuracy": a, "auc": u, "n": len(te)}

    final = lgb.LGBMClassifier(
        n_estimators=120,
        max_depth=3,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        min_child_samples=3,
        verbosity=-1,
        random_state=42,
    )
    final.fit(X, y)
    joblib.dump(
        {
            "model": final,
            "feature_names": feature_names,
            "kinds": KINDS,
            "symbols": SYMBOLS,
            "metrics": {"loo_accuracy": acc, "loo_auc": auc, "n": len(y), "positives": int(y.sum()), "loso": loso},
        },
        SESSION / "models" / "intervention_policy_lgbm.joblib",
    )
    imp = sorted(zip(feature_names, final.feature_importances_.tolist()), key=lambda x: -x[1])

    # cross-symbol stability: (base, kind) better on how many symbols
    key_stats = defaultdict(lambda: {"wins": 0, "n": 0, "sum_delta": 0.0, "by_sym": {}})
    for p in pairs:
        k = (p["base"], p["kind"])
        key_stats[k]["n"] += 1
        key_stats[k]["sum_delta"] += p["delta_pnl"]
        key_stats[k]["by_sym"][p["symbol"]] = {
            "delta": p["delta_pnl"],
            "better": p["better"],
            "variant_pnl": p["variant_pnl"],
            "variant": p["variant"],
        }
        if p["better"]:
            key_stats[k]["wins"] += 1

    stable = []
    for (base, kind), st in key_stats.items():
        sym_wins = [s for s, v in st["by_sym"].items() if v["better"] and v["variant_pnl"] > 0]
        if len(sym_wins) >= 4 and st["sum_delta"] / max(1, st["n"]) >= 20:
            stable.append(
                {
                    "base": base,
                    "kind": kind,
                    "n_symbols_win": len(sym_wins),
                    "symbols_win": sorted(sym_wins),
                    "mean_delta": st["sum_delta"] / max(1, st["n"]),
                    "by_sym": st["by_sym"],
                    "variant": next(iter(st["by_sym"].values()))["variant"],
                }
            )
    stable.sort(key=lambda x: (-x["n_symbols_win"], -x["mean_delta"]))

    KIND_TAG = {
        "change_period_15x": "period15x",
        "change_period_067": "period067",
        "add_block_ema": "ema50",
        "add_block_adx": "adx25",
        "add_block_sma200": "sma200",
    }
    promoted = []
    LIB.mkdir(parents=True, exist_ok=True)
    for s in stable:
        if s["n_symbols_win"] < 4:
            continue
        src = SESSION / "scripts" / s["variant"]
        if not src.exists():
            continue
        stem = s["base"].replace(".italgo", "")
        out_name = f"31p-{stem}__{KIND_TAG[s['kind']]}.italgo"
        doc = json.loads(src.read_text())
        doc["meta"]["name"] = f"[cross-sym] {doc['meta'].get('name')}"
        doc["meta"]["tags"] = list(
            dict.fromkeys((doc["meta"].get("tags") or []) + ["promoted", "c11", "cross-symbol"])
        )
        doc["meta"]["cross_symbol"] = {
            "symbols_win": s["symbols_win"],
            "mean_delta": s["mean_delta"],
            "n_symbols_win": s["n_symbols_win"],
        }
        text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
        (ITALGO / out_name).write_text(text)
        (LIB / out_name).write_text(text)
        (SESSION / "scripts" / out_name).write_text(text)
        promoted.append({"to": out_name, **{k: s[k] for k in ("base", "kind", "mean_delta", "symbols_win", "n_symbols_win")}})

    kind_stats = defaultdict(lambda: {"n": 0, "wins": 0, "sum_delta": 0.0})
    for p in pairs:
        kind_stats[p["kind"]]["n"] += 1
        kind_stats[p["kind"]]["sum_delta"] += p["delta_pnl"]
        if p["better"]:
            kind_stats[p["kind"]]["wins"] += 1
    for k, v in kind_stats.items():
        v["mean_delta"] = v["sum_delta"] / max(1, v["n"])
        v["winrate"] = v["wins"] / max(1, v["n"])

    per_sym = {}
    for sym in SYMBOLS:
        sp = [p for p in pairs if p["symbol"] == sym]
        per_sym[sym] = {
            "n": len(sp),
            "better": sum(1 for p in sp if p["better"]),
            "mean_delta": float(np.mean([p["delta_pnl"] for p in sp])) if sp else 0.0,
        }

    # base coverage: trades per symbol
    coverage = {}
    for sym in SYMBOLS:
        bases = [f for f in by_sym[sym] if "__" not in f and not f.startswith("29p")]
        zero = [f for f in bases if by_sym[sym][f]["stats"]["totalTrades"] == 0]
        coverage[sym] = {
            "n_bases": len(bases),
            "zero_trade": zero,
            "trading": len(bases) - len(zero),
        }

    summary = {
        "session": "2026-08-21-c11-multi-symbol-9",
        "symbols": SYMBOLS,
        "n_pairs": len(pairs),
        "n_better": int(sum(1 for p in pairs if p["better"])),
        "model": {"loo_accuracy": acc, "loo_auc": auc, "n": len(y), "loso": loso},
        "kind_stats": dict(kind_stats),
        "per_symbol": per_sym,
        "coverage": coverage,
        "n_stable_cross": len(stable),
        "n_promoted": len(promoted),
        "top20_by_score": [
            {
                "entry": f"{p['symbol']}:{p['base']}",
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

    (SESSION / "results" / "intervention_pairs.json").write_text(
        json.dumps(pairs, indent=2, ensure_ascii=False) + "\n"
    )
    (SESSION / "results" / "cross_symbol_stable.json").write_text(
        json.dumps(stable, indent=2, ensure_ascii=False) + "\n"
    )
    (SESSION / "results" / "promoted.json").write_text(json.dumps(promoted, indent=2, ensure_ascii=False) + "\n")
    (SESSION / "results" / "variant_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    )
    (SESSION / "models" / "feature_names.json").write_text(
        json.dumps(
            {
                "feature_names": feature_names,
                "symbols": SYMBOLS,
                "metrics": summary["model"],
                "feature_importance_top": imp[:15],
            },
            indent=2,
        )
        + "\n"
    )
    dataset = [
        {
            "task": "improve_strategy",
            "features": dict(zip(feature_names, featurize(p))),
            "action": p["kind"],
            "label": "accept_intervention" if p["better"] else "reject_intervention",
            "delta_pnl": p["delta_pnl"],
            "base": p["base"],
            "symbol": p["symbol"],
        }
        for p in pairs
    ]
    (SESSION / "results" / "advisor_intervention_dataset.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in dataset) + "\n"
    )

    kind_trs = "".join(
        f"<tr><td>{esc(k)}</td><td>{v['n']}</td><td>{v['wins']}</td><td>{v['winrate']:.0%}</td><td>{v['mean_delta']:+.1f}</td></tr>"
        for k, v in sorted(kind_stats.items(), key=lambda kv: -kv[1]["mean_delta"])
    )
    sym_trs = "".join(
        f"<tr><td>{esc(s)}</td><td>{per_sym[s]['n']}</td><td>{per_sym[s]['better']}</td>"
        f"<td>{per_sym[s]['mean_delta']:+.1f}</td><td>{coverage[s]['trading']}/{coverage[s]['n_bases']}</td>"
        f"<td>{esc(', '.join(coverage[s]['zero_trade']) or '—')}</td></tr>"
        for s in SYMBOLS
    )
    loso_trs = "".join(
        f"<tr><td>holdout {esc(s)}</td><td>{v['n']}</td><td>{v['accuracy']:.2f}</td><td>{v['auc'] if v['auc']==v['auc'] else float('nan'):.2f}</td></tr>"
        for s, v in loso.items()
    )
    imp_trs = "".join(f"<tr><td>{esc(n)}</td><td>{v}</td></tr>" for n, v in imp[:12])
    stable_trs = "".join(
        f"<tr><td>{esc(s['base'])}</td><td>{esc(s['kind'])}</td><td>{s['n_symbols_win']}</td>"
        f"<td>{esc(','.join(s['symbols_win']))}</td><td>{s['mean_delta']:+.1f}</td></tr>"
        for s in stable[:25]
    )
    prom_trs = "".join(
        f"<tr><td>{esc(p['base'])}</td><td>{esc(p['to'])}</td><td>{esc(','.join(p['symbols_win']))}</td>"
        f"<td>{p['mean_delta']:+.1f}</td></tr>"
        for p in sorted(promoted, key=lambda x: -x["mean_delta"])
    )
    top = sorted(pairs, key=lambda x: x["delta_pnl"], reverse=True)[:20]
    pair_trs = "".join(
        f"<tr><td>{esc(p['symbol'])}</td><td>{esc(p['base'])}</td><td>{esc(p['kind'])}</td>"
        f"<td>{p['base_pnl']:.0f}</td><td>{p['variant_pnl']:.0f}</td>"
        f"<td style='color:{'#9ad67a' if p['better'] else '#f0a0a0'}'>{p['delta_pnl']:+.0f}</td></tr>"
        for p in top
    )

    html = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"/>
<title>C9 multi-symbol</title>
<style>
body{{margin:0;font-family:IBM Plex Sans,system-ui,sans-serif;background:#0f1419;color:#e8eef4;padding:28px}}
h1{{font-size:1.4rem}} h2{{margin-top:24px}} .sub{{color:#8b9aab;max-width:960px;line-height:1.45}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:16px 0}}
.card{{background:#1a222c;border:1px solid #2a3542;border-radius:10px;padding:12px}}
.k{{color:#8b9aab;font-size:.7rem;text-transform:uppercase}} .v{{font-size:1.25rem;font-weight:600;margin-top:4px}}
table{{border-collapse:collapse;width:100%;background:#1a222c;border:1px solid #2a3542;font-size:.8rem;margin:8px 0 18px}}
th,td{{border:1px solid #2a3542;padding:7px 8px;text-align:center}} th{{background:#121820;color:#8b9aab}}
td:first-child{{text-align:left}}
</style></head><body>
<h1>C11 — 9 тикеров (§7F): SBER + GAZP + LKOH</h1>
<p class="sub">Постоянное правило: расширяем тикеры и растём датасет. Cross-symbol promote → 29p-*. Leave-one-symbol-out = проверка обобщения.</p>
<div class="grid">
  <div class="card"><div class="k">Pairs</div><div class="v">{len(pairs)}</div></div>
  <div class="card"><div class="k">LOO acc</div><div class="v">{acc:.2f}</div></div>
  <div class="card"><div class="k">LOO AUC</div><div class="v">{(auc if auc==auc else float('nan')):.2f}</div></div>
  <div class="card"><div class="k">Cross promote</div><div class="v">{len(promoted)}</div></div>
</div>
<h2>По символам</h2>
<table><thead><tr><th>symbol</th><th>pairs</th><th>better</th><th>mean Δ</th><th>trading bases</th><th>0-trade</th></tr></thead><tbody>{sym_trs}</tbody></table>
<h2>Leave-one-symbol-out</h2>
<table><thead><tr><th>split</th><th>n</th><th>acc</th><th>AUC</th></tr></thead><tbody>{loso_trs}</tbody></table>
<h2>Типы вмешательств (все тикеры)</h2>
<table><thead><tr><th>kind</th><th>n</th><th>wins</th><th>WR</th><th>mean Δ</th></tr></thead><tbody>{kind_trs}</tbody></table>
<h2>Важность фич</h2>
<table><thead><tr><th>feature</th><th>importance</th></tr></thead><tbody>{imp_trs}</tbody></table>
<h2>Стабильные кросс-тикер улучшения (≥2 символа)</h2>
<table><thead><tr><th>base</th><th>kind</th><th>#sym</th><th>wins on</th><th>mean Δ</th></tr></thead><tbody>{stable_trs or '<tr><td colspan=5>none</td></tr>'}</tbody></table>
<h2>Promoted 29p-* (cross-symbol)</h2>
<table><thead><tr><th>from</th><th>to</th><th>symbols</th><th>mean Δ</th></tr></thead><tbody>{prom_trs or '<tr><td colspan=4>none</td></tr>'}</tbody></table>
<h2>Топ Δ (любой тикер)</h2>
<table><thead><tr><th>sym</th><th>base</th><th>kind</th><th>base</th><th>new</th><th>Δ</th></tr></thead><tbody>{pair_trs}</tbody></table>
<p class="sub">Next: +ROSN +GMKN +NVTK · больше TF · больше intervention kinds. Model: models/intervention_policy_lgbm.joblib</p>
</body></html>
"""
    (SESSION / "ANALYTICS.html").write_text(html)
    (SESSION / "FULL_MAP.html").write_text(html)
    (SESSION / "REPORT.md").write_text(
        "\n".join(
            [
                "# C11 multi-symbol 9 (§7F)",
                "",
                f"- Symbols: {', '.join(SYMBOLS)}",
                f"- Pairs: {len(pairs)} · better: {sum(1 for p in pairs if p['better'])}",
                f"- LOO acc={acc:.3f} AUC={auc}",
                f"- LOSO: {json.dumps(loso)}",
                f"- Cross-stable: {len(stable)} · promoted 29p-*: {len(promoted)}",
                "",
                "## Per symbol",
                json.dumps(per_sym, indent=2),
                "",
                "## Kind stats",
                json.dumps(kind_stats, indent=2, ensure_ascii=False),
                "",
                "## Top cross promotes",
            ]
            + [
                f"- `{p['to']}` meanΔ={p['mean_delta']:+.1f} on {','.join(p['symbols_win'])}"
                for p in sorted(promoted, key=lambda x: -x["mean_delta"])[:15]
            ]
        )
        + "\n"
    )
    (SESSION / "notes.md").write_text(
        "C11/§7F: multi-symbol intervention train SBER+GAZP+LKOH; LOSO; cross-symbol 29p-* promote; "
        "ongoing rule: keep expanding instruments + dataset.\n"
    )

    print("MODEL loo", acc, auc, "loso", loso)
    print("promoted", len(promoted), "stable", len(stable))
    print("per_sym", per_sym)


if __name__ == "__main__":
    main()
