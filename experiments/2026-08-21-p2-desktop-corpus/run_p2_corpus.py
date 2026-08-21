#!/usr/bin/env python3
"""P2: run Desktop ai-train .italgo corpus via Rust backtest + ingest to AI_algo."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DESKTOP = Path(os.environ.get("ITALGO_DESKTOP", ROOT.parent / "it-algo-desktop"))
SESSION = ROOT / "artifacts/agent_loop/sessions/2026-08-21-p2-desktop-corpus"
RAW_CSV = (
    ROOT
    / "artifacts/agent_loop/sessions/2026-08-21-multi-indicator-wave/data/raw/MOEX_SBER_1d.csv"
)
ITALGO_DIR = DESKTOP / "docs/work/scripting/samples/ai-train"
BASE = os.environ.get("AI_ALGO_URL", "http://127.0.0.1:8090").rstrip("/")
API_VERSION = "2026-08-20"
MAX_BARS = 3000


def parse_ts(s: str) -> int:
    s = s.strip().replace("T", " ")
    # 2021-08-23 00:00:00+00:00
    core = s.split("+")[0].split("Z")[0].strip()
    dt = datetime.strptime(core, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def csv_to_bars(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    hdr = [h.strip() for h in lines[0].split(",")]
    idx = {h: i for i, h in enumerate(hdr)}
    bars = []
    for line in lines[1:]:
        parts = line.split(",")
        bars.append(
            {
                "time": parse_ts(parts[idx["ts"]]),
                "open": float(parts[idx["open"]]),
                "high": float(parts[idx["high"]]),
                "low": float(parts[idx["low"]]),
                "close": float(parts[idx["close"]]),
                "volume": float(parts[idx["volume"]]),
            }
        )
    return bars


def post(path: str, body: dict) -> dict:
    req = Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ingest_row(row: dict, bars: list[dict], symbol: str, timeframe: str) -> dict:
    if not row.get("ok"):
        return {"ok": False, "file": row.get("file"), "error": row.get("error")}
    stats = row["stats"]
    wr = float(stats.get("winRate") or 0)
    if wr > 1:
        wr = wr / 100.0
    slice_bars = bars[-MAX_BARS:]
    ingest_bars = [
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
    nodes = row.get("nodes") or []
    edges = row.get("edges") or []
    lite_nodes = []
    for n in nodes:
        data = {}
        raw = n.get("data") or {}
        for k, v in raw.items():
            if k in ("label", "color", "chart", "series"):
                continue
            if isinstance(v, (int, float, str, bool)):
                data[k] = v
        lite_nodes.append({"id": n.get("id"), "type": n.get("type"), "data": data})
    graph_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    bars_res = post(
        "/v1/ingest/bars",
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": ingest_bars,
            "dataset_id": f"p2-desktop-{symbol}-{timeframe}",
        },
    )
    graphs_res = post(
        "/v1/ingest/graphs",
        {"graphs": [{"id": graph_id, "format": "react_flow_v1", "nodes": lite_nodes, "edges": edges}]},
    )
    if graphs_res.get("status") == "error":
        return {
            "ok": False,
            "file": row.get("file"),
            "error": graphs_res.get("error"),
            "barsId": (bars_res.get("result") or {}).get("id"),
        }
    metrics = {
        "pnl": float(stats.get("netPnl") or 0),
        "max_dd": float(stats.get("maxDrawdown") or 0),
        "winrate": wr,
        "trades": int(stats.get("totalTrades") or 0),
    }
    from_ts = slice_bars[0]["time"] if slice_bars else None
    to_ts = slice_bars[-1]["time"] if slice_bars else None
    align = f"{symbol}|{timeframe}|{from_ts}|{to_ts}"
    runs_res = post(
        "/v1/ingest/runs",
        {
            "runs": [
                {
                    "run_id": run_id,
                    "graph_id": graph_id,
                    "metrics": metrics,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "align_key": align,
                    "window": {"from": from_ts, "to": to_ts},
                    "client": {"product": "it-algo-desktop", "env": "dev", "source": "p2-corpus"},
                    "script_file": row.get("file"),
                    "script_name": row.get("name"),
                    "api_version": API_VERSION,
                }
            ]
        },
    )
    return {
        "ok": runs_res.get("status") != "error",
        "file": row.get("file"),
        "name": row.get("name"),
        "metrics": metrics,
        "barsId": (bars_res.get("result") or {}).get("id"),
        "graphsId": (graphs_res.get("result") or {}).get("id"),
        "runsId": (runs_res.get("result") or {}).get("id"),
        "error": runs_res.get("error"),
    }


def main() -> int:
    SESSION.mkdir(parents=True, exist_ok=True)
    symbol, timeframe = "SBER", "1d"
    bars = csv_to_bars(RAW_CSV)
    bars_json = SESSION / "bars_sber_1d.json"
    bars_json.write_text(json.dumps(bars), encoding="utf-8")
    results_jsonl = SESSION / "engine_results.jsonl"

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
        str(ITALGO_DIR),
        "--bars",
        str(bars_json),
        "--symbol",
        symbol,
        "--timeframe",
        timeframe,
        "--out",
        str(results_jsonl),
    ]
    print("running:", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=str(DESKTOP), check=False)
    if proc.returncode != 0:
        print("cargo failed", proc.returncode, file=sys.stderr)
        return proc.returncode

    rows = []
    for line in results_jsonl.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))

    ingest_out = []
    for row in rows:
        try:
            ingest_out.append(ingest_row(row, bars, symbol, timeframe))
        except Exception as e:  # noqa: BLE001
            ingest_out.append({"ok": False, "file": row.get("file"), "error": str(e)})

    (SESSION / "ingest_results.json").write_text(
        json.dumps(ingest_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    ok_rows = [r for r in rows if r.get("ok")]
    ok_rows_sorted = sorted(ok_rows, key=lambda r: float(r["stats"]["netPnl"]), reverse=True)
    lines = [
        "# P2 Desktop corpus — engine + ingest",
        "",
        f"- Date: {datetime.now(timezone.utc).isoformat()}",
        f"- Symbol/TF: {symbol} / {timeframe}",
        f"- Bars: {len(bars)} from `{RAW_CSV.name}`",
        f"- Scripts: {len(rows)} ({len(ok_rows)} ok)",
        f"- Ingest OK: {sum(1 for x in ingest_out if x.get('ok'))}/{len(ingest_out)}",
        f"- AI_algo: `{BASE}`",
        "",
        "## Ranking by net PnL (Desktop engine)",
        "",
        "| file | trades | WR | PnL | maxDD |",
        "|------|--------|----|-----|-------|",
    ]
    for r in ok_rows_sorted:
        s = r["stats"]
        lines.append(
            f"| `{r['file']}` | {s['totalTrades']} | {s['winRate']:.3f} | {s['netPnl']:.2f} | {s['maxDrawdown']:.2f} |"
        )
    fails = [r for r in rows if not r.get("ok")]
    if fails:
        lines += ["", "## Failures", ""]
        for r in fails:
            lines.append(f"- `{r.get('file')}`: {r.get('error')}")
    lines += [
        "",
        "## Notes",
        "",
        "- Engine: `crates/backtest` (`run_ai_train_corpus` example), not Electron UI.",
        "- Commission 0.04%, slippage 0.01%, capital 100k.",
        "- §7C: for trend scripts PnL-first; WR can be <40%.",
        "",
    ]
    (SESSION / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:40]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
