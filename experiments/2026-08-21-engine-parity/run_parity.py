#!/usr/bin/env python3
"""Parity: same SMA(20)/SMA(50) strategy in Desktop engine vs AI_algo mirror BT."""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.request import Request, urlopen
import uuid

ROOT = Path(__file__).resolve().parents[2]
DESKTOP = Path(os.environ.get("ITALGO_DESKTOP", ROOT.parent / "it-algo-desktop"))
SESSION = ROOT / "artifacts/agent_loop/sessions/2026-08-21-engine-parity"
CSV = (
    ROOT
    / "artifacts/agent_loop/sessions/2026-08-21-multi-indicator-wave/data/raw/MOEX_SBER_1d.csv"
)
ITALGO = DESKTOP / "docs/work/scripting/samples/ai-train/09-sma-cross-20-50.italgo"
BASE = os.environ.get("AI_ALGO_URL", "http://127.0.0.1:8090").rstrip("/")

COMMISSION_PCT = 0.04
SLIPPAGE_PCT = 0.01
FAST, SLOW = 20, 50


def parse_ts(s: str) -> int:
    core = s.strip().replace("T", " ").split("+")[0].split("Z")[0].strip()
    dt = datetime.strptime(core, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


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


def sma_series(closes: List[float], period: int) -> List[float]:
    """Match Desktop RollingMoments::push_sma — NaN until window full."""
    out: List[float] = []
    buf: List[float] = []
    s = 0.0
    for v in closes:
        buf.append(v)
        s += v
        if len(buf) > period:
            s -= buf.pop(0)
        if len(buf) < period:
            out.append(float("nan"))
        else:
            out.append(s / period)
    return out


def apply_slippage(price: float, side: int, pct: float) -> float:
    m = pct / 100.0
    return price * (1.0 + m) if side > 0 else price * (1.0 - m)


@dataclass
class Trade:
    entry_time: int
    exit_time: Optional[int]
    side: str
    qty: float
    entry_price: float
    exit_price: Optional[float]
    pnl: Optional[float]
    bars_held: int


def ai_algo_mirror_bt(bars: List[dict]) -> Tuple[dict, List[Trade]]:
    """Desktop-parity long-only SMA cross: signal on close, fill next open."""
    closes = [b["close"] for b in bars]
    fast = sma_series(closes, FAST)
    slow = sma_series(closes, SLOW)

    pending_open = False
    pending_close = False
    pos_side = 0
    entry_price = 0.0
    entry_time = 0
    bars_held = 0
    qty = 1.0
    trades: List[Trade] = []
    realized = 0.0
    peak = 0.0
    max_dd = 0.0

    for i, bar in enumerate(bars):
        # fills at open
        if pending_close and pos_side != 0:
            px = apply_slippage(bar["open"], -pos_side, SLIPPAGE_PCT)
            pnl = (px - entry_price) if pos_side > 0 else (entry_price - px)
            trades.append(
                Trade(
                    entry_time=entry_time,
                    exit_time=bar["time"],
                    side="buy" if pos_side > 0 else "sell",
                    qty=qty,
                    entry_price=entry_price,
                    exit_price=px,
                    pnl=pnl,
                    bars_held=bars_held,
                )
            )
            realized += pnl
            pos_side = 0
            bars_held = 0
            pending_close = False

        if pending_open and pos_side == 0:
            px = apply_slippage(bar["open"], 1, SLIPPAGE_PCT)
            pos_side = 1
            entry_price = px
            entry_time = bar["time"]
            bars_held = 0
            pending_open = False

        if pos_side != 0:
            bars_held += 1

        # signals from cross (need 2 finite points)
        if i >= 1 and math.isfinite(fast[i]) and math.isfinite(slow[i]) and math.isfinite(fast[i - 1]) and math.isfinite(slow[i - 1]):
            cross_up = fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]
            cross_dn = fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]
            if cross_up and pos_side == 0 and not pending_open:
                pending_open = True
            if cross_dn and pos_side != 0:
                pending_close = True

        unrealized = (bar["close"] - entry_price) if pos_side > 0 else 0.0
        eq = realized + unrealized
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)

    # open position at end — unfinished trade (Desktop behavior)
    if pos_side != 0:
        last = bars[-1]
        trades.append(
            Trade(
                entry_time=entry_time,
                exit_time=None,
                side="buy",
                qty=qty,
                entry_price=entry_price,
                exit_price=None,
                pnl=None,
                bars_held=bars_held,
            )
        )
        unrealized_end = last["close"] - entry_price
    else:
        unrealized_end = 0.0

    closed = [t for t in trades if t.exit_time is not None]
    wins = sum(1 for t in closed if (t.pnl or 0) > 0)
    losses = sum(1 for t in closed if (t.pnl or 0) < 0)
    net = realized + unrealized_end
    wr = (wins / len(closed)) if closed else 0.0
    stats = {
        "totalTrades": len(trades),
        "wins": wins,
        "losses": losses,
        "winRate": wr,
        "netPnl": net,
        "maxDrawdown": max_dd,
        "closedTrades": len(closed),
    }
    return stats, trades


def run_desktop(bars: List[dict]) -> dict:
    SESSION.mkdir(parents=True, exist_ok=True)
    bars_json = SESSION / "bars_sber_1d.json"
    bars_json.write_text(json.dumps(bars), encoding="utf-8")
    out = SESSION / "desktop_09.jsonl"
    cmd = [
        "cargo", "run", "-p", "backtest", "--example", "run_ai_train_corpus", "--release", "--",
        "--dir", str(ITALGO.parent),
        "--bars", str(bars_json),
        "--symbol", "SBER",
        "--timeframe", "1d",
        "--only", "09-sma-cross",
        "--trades",
        "--out", str(out),
    ]
    print(" ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(DESKTOP))
    if r.returncode != 0:
        raise SystemExit(f"cargo failed {r.returncode}")
    line = out.read_text(encoding="utf-8").strip().splitlines()[0]
    return json.loads(line)


def nearly(a: float, b: float, abs_tol: float = 1e-6, rel_tol: float = 1e-9) -> bool:
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))


def compare(desktop: dict, ai_stats: dict, ai_trades: List[Trade]) -> dict:
    ds = desktop["stats"]
    dt = desktop.get("trades") or []
    diffs = []
    for key in ("totalTrades", "wins", "losses", "winRate", "netPnl", "maxDrawdown"):
        dv = ds[key]
        av = ai_stats[key]
        ok = nearly(float(dv), float(av)) if isinstance(dv, float) or isinstance(av, float) else dv == av
        if key in ("winRate", "netPnl", "maxDrawdown"):
            ok = nearly(float(dv), float(av), abs_tol=1e-4)
        if not ok:
            diffs.append({"field": f"stats.{key}", "desktop": dv, "ai_algo": av})

    n = min(len(dt), len(ai_trades))
    for i in range(n):
        d, a = dt[i], ai_trades[i]
        pairs = [
            ("entryTime", d.get("entryTime"), a.entry_time),
            ("exitTime", d.get("exitTime"), a.exit_time),
            ("entryPrice", d.get("entryPrice"), a.entry_price),
            ("exitPrice", d.get("exitPrice"), a.exit_price),
            ("pnl", d.get("pnl"), a.pnl),
        ]
        for name, dv, av in pairs:
            if dv is None and av is None:
                continue
            if dv is None or av is None:
                diffs.append({"field": f"trade[{i}].{name}", "desktop": dv, "ai_algo": av})
                continue
            if isinstance(dv, (int, float)) and isinstance(av, (int, float)):
                if not nearly(float(dv), float(av), abs_tol=1e-4):
                    diffs.append({"field": f"trade[{i}].{name}", "desktop": dv, "ai_algo": av})
            elif dv != av:
                diffs.append({"field": f"trade[{i}].{name}", "desktop": dv, "ai_algo": av})
    if len(dt) != len(ai_trades):
        diffs.append({"field": "trades.len", "desktop": len(dt), "ai_algo": len(ai_trades)})

    return {
        "match": len(diffs) == 0,
        "diffs": diffs,
        "desktop_stats": ds,
        "ai_algo_stats": ai_stats,
        "n_trades_desktop": len(dt),
        "n_trades_ai": len(ai_trades),
    }


def write_graph_dto() -> dict:
    """Canonical AI_algo GraphDTO for the same strategy."""
    return {
        "id": "parity-sma-cross-20-50",
        "format": "graph_dto_v1",
        "symbol": "SBER",
        "timeframe": "1d",
        "nodes": [
            {"id": "close", "type": "source", "source": "close"},
            {"id": "sma_f", "type": "indicator", "kind": "SMA", "period": FAST, "source_node": "close"},
            {"id": "sma_s", "type": "indicator", "kind": "SMA", "period": SLOW, "source_node": "close"},
            {"id": "x_up", "type": "condition", "op": "cross_up", "a": "sma_f", "b": "sma_s"},
            {"id": "x_dn", "type": "condition", "op": "cross_down", "a": "sma_f", "b": "sma_s"},
            {"id": "open_long", "type": "action", "action": "open_market", "side": "buy", "when": "x_up"},
            {"id": "close_long", "type": "action", "action": "close_market", "when": "x_dn"},
        ],
        "engine_rules": {
            "signal_on": "bar_close",
            "fill_on": "next_bar_open",
            "commission_pct": COMMISSION_PCT,
            "slippage_pct": SLIPPAGE_PCT,
            "qty": 1,
            "force_close_eod": False,
            "pnl_unit": "price_points",
        },
        "desktop_script": str(ITALGO),
    }


def ingest(bars: List[dict], ai_stats: dict, graph_dto: dict, desktop: dict) -> None:
    try:
        urlopen(Request(f"{BASE}/v1/health"), timeout=2)
    except Exception:
        print("AI_algo not up — skip ingest")
        return
    slice_bars = bars[-3000:]
    body_bars = {
        "symbol": "SBER",
        "timeframe": "1d",
        "dataset_id": "parity-sma-20-50",
        "bars": [
            {
                "ts": datetime.fromtimestamp(b["time"], tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                "open": b["open"],
                "high": b["high"],
                "low": b["low"],
                "close": b["close"],
                "volume": b["volume"],
            }
            for b in slice_bars
        ],
    }
    gid = str(uuid.uuid4())
    italgo = json.loads(ITALGO.read_text(encoding="utf-8"))
    nodes = italgo["graph"]["nodes"]
    edges = italgo["graph"]["edges"]
    lite = []
    for n in nodes:
        data = {k: v for k, v in (n.get("data") or {}).items() if isinstance(v, (int, float, str, bool)) and k not in ("label", "color")}
        lite.append({"id": n["id"], "type": n["type"], "data": data})

    def post(path, body):
        req = Request(f"{BASE}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())

    post("/v1/ingest/bars", body_bars)
    post("/v1/ingest/graphs", {"graphs": [{"id": gid, "format": "react_flow_v1", "nodes": lite, "edges": edges, "graph_dto": graph_dto}]})
    wr = float(ai_stats["winRate"])
    post(
        "/v1/ingest/runs",
        {
            "runs": [
                {
                    "run_id": str(uuid.uuid4()),
                    "graph_id": gid,
                    "metrics": {
                        "pnl": ai_stats["netPnl"],
                        "max_dd": ai_stats["maxDrawdown"],
                        "winrate": wr,
                        "trades": ai_stats["totalTrades"],
                    },
                    "symbol": "SBER",
                    "timeframe": "1d",
                    "client": {"product": "ai-algo", "env": "dev", "source": "engine-parity"},
                    "parity": {
                        "desktop_netPnl": desktop["stats"]["netPnl"],
                        "match": True,
                    },
                }
            ]
        },
    )


def main() -> int:
    SESSION.mkdir(parents=True, exist_ok=True)
    bars = load_bars(CSV)
    graph_dto = write_graph_dto()
    (SESSION / "graph_dto.json").write_text(json.dumps(graph_dto, indent=2) + "\n", encoding="utf-8")
    (SESSION / "strategy.md").write_text(
        "\n".join(
            [
                "# Parity strategy: SMA Cross 20/50",
                "",
                "- Long-only: SMA(20) cross up SMA(50) → open; cross down → close",
                "- Signal on bar close; fill at **next open**",
                f"- Slippage {SLIPPAGE_PCT}%, commission {COMMISSION_PCT}% (cash only; trade PnL = exit−entry points)",
                "- No force-close at end of data",
                f"- Desktop: `{ITALGO.name}`",
                "- AI_algo: GraphDTO + mirror BT in `run_parity.py`",
                "",
            ]
        ),
        encoding="utf-8",
    )

    desktop = run_desktop(bars)
    ai_stats, ai_trades = ai_algo_mirror_bt(bars)
    result = compare(desktop, ai_stats, ai_trades)

    (SESSION / "desktop_result.json").write_text(json.dumps(desktop, indent=2) + "\n", encoding="utf-8")
    (SESSION / "ai_algo_result.json").write_text(
        json.dumps(
            {
                "stats": ai_stats,
                "trades": [t.__dict__ for t in ai_trades],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (SESSION / "parity_compare.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    if result["match"]:
        ingest(bars, ai_stats, graph_dto, desktop)

    report = [
        "# Engine parity — SMA 20/50",
        "",
        f"- Bars: {len(bars)} SBER 1d",
        f"- Match: **{'YES' if result['match'] else 'NO'}**",
        "",
        "## Stats",
        "",
        "| metric | Desktop | AI_algo |",
        "|--------|---------|---------|",
    ]
    for k in ("totalTrades", "wins", "losses", "winRate", "netPnl", "maxDrawdown"):
        report.append(f"| {k} | {desktop['stats'][k]} | {ai_stats[k]} |")
    if result["diffs"]:
        report += ["", "## Diffs", ""]
        for d in result["diffs"][:30]:
            report.append(f"- `{d['field']}`: desktop={d['desktop']} ai={d['ai_algo']}")
    (SESSION / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))
    return 0 if result["match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
