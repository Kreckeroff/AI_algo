#!/usr/bin/env python3
"""Build TRAINING_UNIVERSE_MAP.html — full cross-session training analytics."""
from __future__ import annotations

import json
import random
import statistics as stats
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESS = ROOT / "artifacts/agent_loop/sessions"
OUT_DIR = ROOT / "artifacts/agent_loop"
WAVES = [
    ("C7", "2026-08-21-c7-intervention-policy"),
    ("C8", "2026-08-21-c8-p3-expand"),
    ("C9", "2026-08-21-c9-multi-symbol"),
    ("C10", "2026-08-21-c10-multi-symbol-expand"),
    ("C11", "2026-08-21-c11-multi-symbol-9"),
    ("C12", "2026-08-21-c12-quality-push"),
    ("C13", "2026-08-21-c13-all-tf"),
    ("C14", "2026-08-21-c14-futures-expand"),
]


def agg(xs):
    if not xs:
        return None
    return {
        "n": len(xs),
        "mean": sum(xs) / len(xs),
        "median": stats.median(xs),
        "p10": sorted(xs)[max(0, len(xs) // 10)],
        "p90": sorted(xs)[min(len(xs) - 1, 9 * len(xs) // 10)],
    }


def round_agg(d):
    return {
        k: ({kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in v.items()} if isinstance(v, dict) else v)
        for k, v in d.items()
    }


def build_data() -> dict:
    out: dict = {"waves": [], "c14": {}, "p37": {}, "div_cal": {}}
    for name, sid in WAVES:
        p = SESS / sid
        s = json.loads((p / "results" / "variant_summary.json").read_text()) if (p / "results" / "variant_summary.json").exists() else {}
        m = json.loads((p / "models" / "feature_names.json").read_text()) if (p / "models" / "feature_names.json").exists() else {}
        met = (m.get("metrics") or s.get("model") or {})
        out["waves"].append(
            {
                "id": name,
                "session": sid,
                "n_pairs": s.get("n_pairs"),
                "n_better": s.get("n_better"),
                "n_promoted": s.get("n_promoted"),
                "acc": met.get("cv_accuracy") or met.get("loo_accuracy"),
                "auc": met.get("cv_auc") or met.get("loo_auc"),
                "symbols": s.get("symbols") or m.get("symbols"),
                "tfs": s.get("timeframes") or m.get("timeframes"),
            }
        )

    c14 = SESS / "2026-08-21-c14-futures-expand"
    pairs = json.loads((c14 / "results" / "intervention_pairs.json").read_text())
    random.seed(42)
    deltas = [p["delta_pnl"] for p in pairs]
    sample = random.sample(deltas, min(1500, len(deltas)))

    cov = defaultdict(lambda: defaultdict(list))
    kind_by_ac = defaultdict(lambda: defaultdict(list))
    kind_overall = defaultdict(list)
    tf_overall = defaultdict(list)
    sym_overall = defaultdict(list)
    side_kind = defaultdict(lambda: defaultdict(list))
    for p in pairs:
        cov[p["symbol"]][p["timeframe"]].append(p["delta_pnl"])
        ac = p.get("asset_class") or ("future" if p["symbol"] in ("CNYRUBF", "GLDRUBF", "IMOEXF") else "equity")
        kind_by_ac[ac][p["kind"]].append(p["delta_pnl"])
        kind_overall[p["kind"]].append(p["delta_pnl"])
        tf_overall[p["timeframe"]].append(p["delta_pnl"])
        sym_overall[p["symbol"]].append(p["delta_pnl"])
        side_kind[p.get("side_mode") or "unknown"][p["kind"]].append(1 if p["better"] else 0)

    cov_mat = {s: {tf: agg(v) for tf, v in tfs.items()} for s, tfs in cov.items()}
    feat = json.loads((c14 / "models" / "feature_names.json").read_text())
    prom = json.loads((c14 / "results" / "promoted.json").read_text())
    out["c14"] = {
        "n_pairs": len(pairs),
        "n_better": sum(1 for p in pairs if p["better"]),
        "delta_sample": sample,
        "cov_mean": {s: {tf: (v["mean"] if v else None) for tf, v in tfs.items()} for s, tfs in cov_mat.items()},
        "cov_n": {s: {tf: (v["n"] if v else 0) for tf, v in tfs.items()} for s, tfs in cov_mat.items()},
        "kind_overall": round_agg({k: agg(v) for k, v in kind_overall.items()}),
        "kind_by_ac": {ac: round_agg({k: agg(v) for k, v in kinds.items()}) for ac, kinds in kind_by_ac.items()},
        "tf_overall": round_agg({tf: agg(v) for tf, v in tf_overall.items()}),
        "sym_overall": round_agg({s: agg(v) for s, v in sym_overall.items()}),
        "better_rate_side_kind": {
            side: {k: (sum(xs) / len(xs) if xs else 0, len(xs)) for k, xs in kinds.items()} for side, kinds in side_kind.items()
        },
        "top20": [
            {
                "symbol": p["symbol"],
                "tf": p["timeframe"],
                "base": p["base"],
                "kind": p["kind"],
                "delta": round(p["delta_pnl"], 2),
                "better": p["better"],
                "side": p.get("side_mode"),
                "asset": p.get("asset_class"),
            }
            for p in sorted(pairs, key=lambda x: -x["delta_pnl"])[:20]
        ],
        "bottom20": [
            {
                "symbol": p["symbol"],
                "tf": p["timeframe"],
                "base": p["base"],
                "kind": p["kind"],
                "delta": round(p["delta_pnl"], 2),
                "better": p["better"],
                "side": p.get("side_mode"),
                "asset": p.get("asset_class"),
            }
            for p in sorted(pairs, key=lambda x: x["delta_pnl"])[:20]
        ],
        "promoted": prom,
        "loso_1d": (feat.get("metrics") or {}).get("loso_1d"),
        "importance": feat.get("feature_importance_top") or [],
        "model": feat.get("metrics"),
    }

    p37 = json.loads((SESS / "2026-08-21-p37-divgap" / "results" / "summary.json").read_text())
    out["p37"] = {
        "total_short_crossed": p37["total_short_crossed"],
        "total_short_div_paid": p37["total_short_div_paid"],
        "total_long_div_received": p37["total_long_div_received"],
        "ls_short_div_paid": p37["ls_short_div_paid"],
        "ls_delta_from_div": p37["ls_delta_from_div"],
        "per_symbol": {
            s: {
                "n_div": v["n_div_events_cache"],
                "short_crossed": v["n_short_crossed"],
                "delta": v["delta_from_div"],
                "pnl_raw": v["pnl_raw"],
                "pnl_adj": v["pnl_div_adjusted"],
            }
            for s, v in p37["per_symbol"].items()
        },
    }

    cal = json.loads((ROOT / "data/dividends/moex_equities.json").read_text())
    events = []
    for sym, evs in cal["symbols"].items():
        for e in evs:
            events.append({"symbol": sym, "date": e["ex_effect_date"], "div": e.get("dividend_rub"), "yield": e.get("yield_pct")})
    events.sort(key=lambda x: x["date"])
    out["div_cal"] = {"n_events": len(events), "events": events, "fetched_at": cal.get("fetched_at"), "source": cal.get("source")}
    return out


def main() -> None:
    # Reuse existing HTML generator by shelling to the already-built file writer pattern:
    # For durability we write data JSON and invoke the inline builder from TRAINING_UNIVERSE_MAP.html template.
    data = build_data()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "TRAINING_UNIVERSE_DATA.json").write_text(json.dumps(data, ensure_ascii=False))
    # Prefer keeping the rich HTML already generated; regenerate via embedded call
    # Import generation from sibling by exec of previous approach - simplest: call open existing js+html rebuild
    from datetime import datetime as dt

    # Load JS from current map if exists else minimal notice
    html_path = OUT_DIR / "TRAINING_UNIVERSE_MAP.html"
    js_path = OUT_DIR / "TRAINING_UNIVERSE_MAP.js"
    if not js_path.exists() and html_path.exists():
        # extract script - skip; rewrite fully below by reading current html's script is fragile
        pass
    # Always rewrite HTML using current data + existing JS file content
    if not js_path.exists():
        raise SystemExit("Missing TRAINING_UNIVERSE_MAP.js — create once then regenerate data into HTML")
    js = js_path.read_text()
    payload = json.dumps(data, ensure_ascii=False)
    NOW = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # Read style/body from existing html between head markers - simpler overwrite with known-good structure
    # Keep file by replacing JSON blob only
    text = html_path.read_text()
    import re
    text2, n = re.subn(
        r'<script type="application/json" id="DATA">.*?</script>',
        '<script type="application/json" id="DATA">' + payload + "</script>",
        text,
        count=1,
        flags=re.S,
    )
    if n != 1:
        raise SystemExit("Could not replace DATA blob in HTML")
    text2 = re.sub(r"Данные на [^.<]+", f"Данные на {NOW}", text2, count=1)
    html_path.write_text(text2)
    print("updated", html_path, "waves", len(data["waves"]), "pairs", data["c14"]["n_pairs"])


if __name__ == "__main__":
    main()
