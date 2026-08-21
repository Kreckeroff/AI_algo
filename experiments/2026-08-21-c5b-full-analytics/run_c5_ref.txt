#!/usr/bin/env python3
"""C5 / P2.6: trade-level dataset — good/bad labels + block/period interventions."""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ai_algo.domain.trade_analysis import analyze_trades  # noqa: E402

DESKTOP = Path(__import__("os").environ.get("ITALGO_DESKTOP", ROOT.parent / "it-algo-desktop"))
SESSION = ROOT / "artifacts/agent_loop/sessions/2026-08-21-c5-trade-level"
ITALGO = DESKTOP / "docs/work/scripting/samples/ai-train"
CSV = ROOT / "artifacts/agent_loop/sessions/2026-08-21-multi-indicator-wave/data/raw/MOEX_SBER_1d.csv"
BASE = __import__("os").environ.get("AI_ALGO_URL", "http://127.0.0.1:8090").rstrip("/")


def parse_ts(s: str) -> int:
    core = s.strip().replace("T", " ").split("+")[0].split("Z")[0].strip()
    return int(datetime.strptime(core, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())


def load_bars(path: Path) -> List[dict]:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
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


def label_trade(t: dict) -> str:
    pnl = t.get("pnl")
    if pnl is None:
        return "open"
    try:
        p = float(pnl)
    except (TypeError, ValueError):
        return "unknown"
    hold = t.get("barsHeld")
    if hold is None:
        hold = t.get("bars_held")
    try:
        h = float(hold) if hold is not None else None
    except (TypeError, ValueError):
        h = None
    if p > 0:
        if h is not None and h <= 1:
            return "good_weak"  # tiny scalp win — weak signal
        return "good"
    if p < 0:
        if h is not None and h <= 2:
            return "bad_noise"
        return "bad"
    return "flat"


def classify_interventions(suggestions: List[str]) -> List[str]:
    kinds = []
    blob = " ".join(suggestions).lower()
    if any(k in blob for k in ("фильтр", "блок", "adx", "ema", "добавь", "супертенд", "session", "пауза", "cooldown", "trail", "sl", "tp")):
        kinds.append("add_block")
    if any(k in blob for k in ("период", "period", "увеличьте период", "ослаб")):
        kinds.append("change_period")
    if any(k in blob for k in ("сторон", "шорт", "long", "short", "перекос")):
        kinds.append("side_mode")
    if not kinds and suggestions:
        kinds.append("review_graph")
    return list(dict.fromkeys(kinds))


def run_engine(bars_json: Path, out_jsonl: Path, only: Optional[str] = None, trades: bool = True) -> List[dict]:
    cmd = [
        "cargo", "run", "-p", "backtest", "--example", "run_ai_train_corpus", "--release", "--",
        "--dir", str(ITALGO),
        "--bars", str(bars_json),
        "--symbol", "SBER",
        "--timeframe", "1d",
        "--out", str(out_jsonl),
    ]
    if only:
        cmd.extend(["--only", only])
    if trades:
        cmd.append("--trades")
    print(" ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(DESKTOP))
    if r.returncode != 0:
        raise SystemExit(f"cargo failed {r.returncode}")
    rows = []
    for line in out_jsonl.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def enrich_row(row: dict) -> dict:
    path = ITALGO / row.get("file", "")
    side_mode = "unknown"
    if path.exists():
        meta = json.loads(path.read_text(encoding="utf-8")).get("meta") or {}
        side_mode = meta.get("side_mode") or "unknown"
    row["side_mode"] = side_mode
    trades = row.get("trades") or []
    labeled = []
    for t in trades:
        lab = label_trade(t)
        labeled.append({**t, "label": lab})
    row["trades_labeled"] = labeled
    counts = Counter(t["label"] for t in labeled)
    row["label_counts"] = dict(counts)
    report = analyze_trades(trades, graph_nodes=row.get("nodes"))
    row["trade_report"] = report
    row["intervention_kinds"] = classify_interventions(report.get("suggestions") or [])
    return row


def write_improve_variants(scripts_dir: Path) -> List[Path]:
    """Create period + filter interventions for a weak long_only script (momentum)."""
    base = json.loads((ITALGO / "15-momentum-cross-0.italgo").read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out_paths = []

    # period 10 → 20
    p20 = json.loads(json.dumps(base))
    p20["meta"]["name"] = "Momentum Cross 0 period20 (C5)"
    p20["meta"]["updatedAt"] = now
    p20["meta"]["tags"] = list(dict.fromkeys((p20["meta"].get("tags") or []) + ["c5", "intervention:change_period"]))
    p20["meta"]["intervention"] = {"kind": "change_period", "from": 10, "to": 20, "base": "15-momentum-cross-0.italgo"}
    for n in p20["graph"]["nodes"]:
        if n.get("id") == "osc":
            n["data"]["period"] = 20
            n["data"]["label"] = "Mom20"
    path = scripts_dir / "15b-momentum-period20.italgo"
    path.write_text(json.dumps(p20, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_paths.append(path)

    # add EMA50 filter (long only when close > EMA)
    filt = json.loads(json.dumps(base))
    filt["meta"]["name"] = "Momentum + EMA50 filter (C5)"
    filt["meta"]["updatedAt"] = now
    filt["meta"]["tags"] = list(dict.fromkeys((filt["meta"].get("tags") or []) + ["c5", "intervention:add_block"]))
    filt["meta"]["intervention"] = {"kind": "add_block", "block": "indicator_ema", "period": 50, "base": "15-momentum-cross-0.italgo"}
    nodes = filt["graph"]["nodes"]
    edges = filt["graph"]["edges"]
    # insert ema + above + and before open
    nodes.extend(
        [
            {"id": "ema50", "type": "indicator_ema", "position": {"x": 480, "y": 40}, "data": {"period": 50, "label": "EMA50"}},
            {"id": "above", "type": "logic_gt", "position": {"x": 700, "y": 40}, "data": {"label": "Close>EMA"}},
            {"id": "buy", "type": "logic_and", "position": {"x": 860, "y": 100}, "data": {"label": "Buy"}},
        ]
    )
    # rewire: cross_up+above → buy → open; keep cross_dn → close
    edges = [e for e in edges if not (e.get("source") == "cross_up" and e.get("target") == "open")]
    n = len(edges)
    def E(i, s, t, sh, th):
        return {"id": f"c5e{i}", "source": s, "target": t, "sourceHandle": sh, "targetHandle": th}
    edges += [
        E(1, "close", "ema50", "value", "source"),
        E(2, "close", "above", "value", "a"),
        E(3, "ema50", "above", "value", "b"),
        E(4, "cross_up", "buy", "result", "conditions"),
        E(5, "above", "buy", "result", "conditions"),
        E(6, "buy", "open", "result", "condition"),
        E(7, "ema50", "chart", "value", "series"),
    ]
    filt["graph"]["edges"] = edges
    path = scripts_dir / "15c-momentum-ema50-filter.italgo"
    path.write_text(json.dumps(filt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_paths.append(path)
    return out_paths


def run_scripts_dir(bars_json: Path, scripts_dir: Path, out_jsonl: Path) -> List[dict]:
    cmd = [
        "cargo", "run", "-p", "backtest", "--example", "run_ai_train_corpus", "--release", "--",
        "--dir", str(scripts_dir),
        "--bars", str(bars_json),
        "--symbol", "SBER",
        "--timeframe", "1d",
        "--trades",
        "--out", str(out_jsonl),
    ]
    print(" ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(DESKTOP))
    if r.returncode != 0:
        raise SystemExit(f"cargo variants failed {r.returncode}")
    return [json.loads(l) for l in out_jsonl.read_text().splitlines() if l.strip()]


def post_ingest(rows: List[dict], bars: List[dict]) -> List[dict]:
    out = []
    try:
        urlopen(Request(f"{BASE}/v1/health"), timeout=2)
    except Exception:
        return [{"ok": False, "reason": "ai_algo_down"}]
    slice_bars = bars[-3000:]
    ibars = [
        {
            "ts": datetime.fromtimestamp(b["time"], tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "open": b["open"],
            "high": b["high"],
            "low": b["low"],
            "close": b["close"],
            "volume": b["volume"],
        }
        for b in slice_bars
    ]

    def post(path: str, body: dict) -> dict:
        req = Request(
            f"{BASE}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    for row in rows:
        if not row.get("ok"):
            continue
        gid = str(uuid.uuid4())
        rid = str(uuid.uuid4())
        nodes = row.get("nodes") or []
        edges = row.get("edges") or []
        lite = []
        for n in nodes:
            data = {
                k: v
                for k, v in (n.get("data") or {}).items()
                if isinstance(v, (int, float, str, bool)) and k not in ("label", "color")
            }
            lite.append({"id": n.get("id"), "type": n.get("type"), "data": data})
        s = row["stats"]
        wr = float(s["winRate"])
        if wr > 1:
            wr /= 100.0
        # persist trades on the run for train (§7E)
        trades_payload = []
        for t in row.get("trades_labeled") or row.get("trades") or []:
            trades_payload.append(
                {
                    "entryTime": t.get("entryTime") or t.get("entry_time"),
                    "exitTime": t.get("exitTime") or t.get("exit_time"),
                    "side": t.get("side"),
                    "qty": t.get("qty"),
                    "entryPrice": t.get("entryPrice") or t.get("entry_price"),
                    "exitPrice": t.get("exitPrice") or t.get("exit_price"),
                    "pnl": t.get("pnl"),
                    "barsHeld": t.get("barsHeld") or t.get("bars_held"),
                    "label": t.get("label"),
                }
            )
        try:
            post("/v1/ingest/bars", {"symbol": "SBER", "timeframe": "1d", "bars": ibars, "dataset_id": "c5-trade-level"})
            post("/v1/ingest/graphs", {"graphs": [{"id": gid, "format": "react_flow_v1", "nodes": lite, "edges": edges}]})
            post(
                "/v1/ingest/runs",
                {
                    "runs": [
                        {
                            "run_id": rid,
                            "graph_id": gid,
                            "metrics": {
                                "pnl": s["netPnl"],
                                "max_dd": s["maxDrawdown"],
                                "winrate": wr,
                                "trades": s["totalTrades"],
                            },
                            "trades": trades_payload,
                            "trade_report": row.get("trade_report"),
                            "intervention_kinds": row.get("intervention_kinds"),
                            "side_mode": row.get("side_mode"),
                            "script_file": row.get("file"),
                            "symbol": "SBER",
                            "timeframe": "1d",
                            "client": {"product": "it-algo-desktop", "env": "dev", "source": "c5-trade-level"},
                        }
                    ]
                },
            )
            out.append({"ok": True, "file": row.get("file"), "trades": len(trades_payload)})
        except Exception as e:  # noqa: BLE001
            out.append({"ok": False, "file": row.get("file"), "error": str(e)})
    return out


def main() -> int:
    SESSION.mkdir(parents=True, exist_ok=True)
    scripts_dir = SESSION / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    results = SESSION / "results"
    results.mkdir(exist_ok=True)

    bars = load_bars(CSV)
    bars_json = SESSION / "bars_sber_1d.json"
    bars_json.write_text(json.dumps(bars), encoding="utf-8")

    corpus_out = SESSION / "engine_results.jsonl"
    rows = run_engine(bars_json, corpus_out, trades=True)
    rows = [enrich_row(r) for r in rows if r.get("ok")]

    # trade-level flat dataset
    flat = []
    for r in rows:
        for t in r.get("trades_labeled") or []:
            flat.append(
                {
                    "script": r["file"],
                    "side_mode": r.get("side_mode"),
                    "label": t.get("label"),
                    "pnl": t.get("pnl"),
                    "side": t.get("side"),
                    "barsHeld": t.get("barsHeld"),
                    "entryTime": t.get("entryTime"),
                    "exitTime": t.get("exitTime"),
                }
            )
    (results / "trades_labeled.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in flat) + ("\n" if flat else ""),
        encoding="utf-8",
    )

    label_tot = Counter(x["label"] for x in flat)
    interventions = Counter()
    for r in rows:
        for k in r.get("intervention_kinds") or []:
            interventions[k] += 1

    # improve loop on momentum
    variants = write_improve_variants(scripts_dir)
    # also copy base into scripts dir for same runner
    base_copy = scripts_dir / "15-momentum-cross-0.italgo"
    base_copy.write_text((ITALGO / "15-momentum-cross-0.italgo").read_text(encoding="utf-8"), encoding="utf-8")
    var_out = SESSION / "improve_results.jsonl"
    var_rows = run_scripts_dir(bars_json, scripts_dir, var_out)
    var_rows = [enrich_row(r) for r in var_rows if r.get("ok")]

    def stats_line(r: dict) -> str:
        s = r["stats"]
        lc = r.get("label_counts") or {}
        return (
            f"`{r['file']}` pnl={s['netPnl']:.2f} wr={s['winRate']:.3f} trades={s['totalTrades']} "
            f"labels={dict(lc)} interventions={r.get('intervention_kinds')}"
        )

    improve_compare = {
        "base": next((r for r in var_rows if r["file"].startswith("15-momentum-cross-0")), None),
        "change_period": next((r for r in var_rows if "period20" in r["file"]), None),
        "add_block": next((r for r in var_rows if "ema50" in r["file"]), None),
    }
    # serialize without huge nodes for summary
    def slim(r: Optional[dict]) -> Optional[dict]:
        if not r:
            return None
        return {
            "file": r["file"],
            "stats": r["stats"],
            "label_counts": r.get("label_counts"),
            "trade_report": r.get("trade_report"),
            "intervention_kinds": r.get("intervention_kinds"),
        }

    improve_slim = {k: slim(v) for k, v in improve_compare.items()}

    ingest = post_ingest(rows + var_rows, bars)

    summary = {
        "session": "2026-08-21-c5-trade-level",
        "kind": "trade_level_p26",
        "n_scripts": len(rows),
        "n_trades_labeled": len(flat),
        "label_totals": dict(label_tot),
        "intervention_hint_counts": dict(interventions),
        "improve_loop": improve_slim,
        "top20_by_score": [
            {
                "entry": r["file"],
                "filter": r.get("side_mode"),
                "median_pnl": r["stats"]["netPnl"],
                "mean_pnl": r["stats"]["netPnl"],
                "mean_wr": r["stats"]["winRate"],
                "mean_dd": r["stats"]["maxDrawdown"],
                "n": r["stats"]["totalTrades"],
                "regime": (r.get("trade_report") or {}).get("regime"),
                "bad_trades": (r.get("label_counts") or {}).get("bad", 0)
                + (r.get("label_counts") or {}).get("bad_noise", 0),
            }
            for r in sorted(rows, key=lambda x: x["stats"]["netPnl"], reverse=True)
        ],
    }
    (results / "variant_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (results / "script_trade_reports.json").write_text(
        json.dumps(
            [
                {
                    "file": r["file"],
                    "side_mode": r.get("side_mode"),
                    "stats": r["stats"],
                    "label_counts": r.get("label_counts"),
                    "trade_report": r.get("trade_report"),
                    "intervention_kinds": r.get("intervention_kinds"),
                }
                for r in rows
            ],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (SESSION / "ingest_results.json").write_text(json.dumps(ingest, indent=2) + "\n", encoding="utf-8")

    # rewrite engine jsonl without full node dumps for size? keep as-is from cargo; write enriched slim
    (SESSION / "engine_enriched.json").write_text(
        json.dumps([slim(r) for r in rows], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# C5 trade-level (§7E / P2.6)",
        "",
        f"- Scripts: {len(rows)}",
        f"- Labeled trades: {len(flat)} → {dict(label_tot)}",
        f"- Intervention hints: {dict(interventions)}",
        "",
        "## Improve loop (15 momentum)",
        "",
    ]
    for k, v in improve_slim.items():
        if not v:
            lines.append(f"- {k}: missing")
            continue
        s = v["stats"]
        lines.append(
            f"- **{k}** `{v['file']}`: pnl={s['netPnl']:.2f} wr={s['winRate']:.3f} "
            f"labels={v.get('label_counts')} kinds={v.get('intervention_kinds')}"
        )
        sug = (v.get("trade_report") or {}).get("suggestions") or []
        for s1 in sug[:2]:
            lines.append(f"  - {s1}")
    lines += ["", "## Notes", "", "- good/bad from pnl (+ hold heuristics)", "- interventions classified: add_block / change_period / side_mode", ""]
    (SESSION / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (SESSION / "notes.md").write_text(
        "P2.6: persist trades with labels; analyze_trades → intervention kinds; A/B period vs EMA filter on momentum.\n",
        encoding="utf-8",
    )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
