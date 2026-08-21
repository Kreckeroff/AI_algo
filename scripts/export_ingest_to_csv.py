#!/usr/bin/env python3
"""Export persisted ingest bars → CSV for LightGBM train experiments."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "ingest",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "processed" / "bars_export.csv",
    )
    args = ap.parse_args()
    bars_dir = args.data_dir / "bars"
    if not bars_dir.exists():
        raise SystemExit(f"No bars dir: {bars_dir}")

    rows = []
    for path in sorted(bars_dir.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        payload = doc.get("payload", doc)
        symbol = payload.get("symbol", "")
        timeframe = payload.get("timeframe", "")
        for b in payload.get("bars") or []:
            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "ts": b.get("ts"),
                    "open": b.get("open"),
                    "high": b.get("high"),
                    "low": b.get("low"),
                    "close": b.get("close"),
                    "volume": b.get("volume"),
                }
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise SystemExit("No bars to export — run Desktop ai-train backtests with auto-ingest first.")
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["symbol", "timeframe", "ts", "open", "high", "low", "close", "volume"],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows → {args.out}")


if __name__ == "__main__":
    main()
