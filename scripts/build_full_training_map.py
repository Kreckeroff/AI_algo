#!/usr/bin/env python3
"""Rebuild FULL_MAP.html for C5b-style session (strategies / trades / blocks / Q-Q / heatmaps).

Usage:
  .venv/bin/python scripts/build_full_training_map.py \
    --session artifacts/agent_loop/sessions/2026-08-21-c5b-full-analytics \
    --c5 artifacts/agent_loop/sessions/2026-08-21-c5-trade-level
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=Path, required=True)
    ap.add_argument("--c5", type=Path, default=ROOT / "artifacts/agent_loop/sessions/2026-08-21-c5-trade-level")
    args = ap.parse_args()
    # Re-run the analytics generator embedded in experiment if present
    gen = ROOT / "experiments/2026-08-21-c5b-full-analytics/generate_map.py"
    if gen.exists():
        return subprocess.call([sys.executable, str(gen), "--session", str(args.session), "--c5", str(args.c5)])
    print("Open FULL_MAP.html in session; regenerate via experiments/2026-08-21-c5b-full-analytics/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
