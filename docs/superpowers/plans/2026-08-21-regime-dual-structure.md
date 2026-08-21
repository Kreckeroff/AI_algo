# Regime Dual-Structure (B0→B1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Label market regime (trend vs chop) on bars, annotate the C16 corpus, publish regime analytics; then add chop-gate / MR-overlay interventions (C18).

**Architecture:** Deterministic ADX+ER bar classifier in `market_regime.py`; offline annotation of existing engine dumps (no full re-engine for B0); B1 mutates italgo graphs and runs a focused 1d+1h train wave.

**Tech Stack:** Python 3.9+, numpy (optional), existing LightGBM train patterns, pytest, C16 `engine_*.jsonl` + `bars_*.json`.

**Spec:** `docs/superpowers/specs/2026-08-21-regime-dual-structure-design.md`

## Global Constraints

- History×TF full grid (item A) is **out of scope** (other PC).
- Combo multi-kind search (item C) is **after** B0.
- Desktop §7G wiring is **out of scope**.
- Regime features must be **base-only** (no variant leak).
- Prefer long_only for first graph mutations if LS wiring fails validation.

---

## File map

| File | Responsibility |
|------|----------------|
| `src/ai_algo/domain/market_regime.py` | Bar → trend_up/trend_down/chop |
| `tests/test_market_regime.py` | Synthetic trend vs flat tests |
| `experiments/2026-08-21-b0-regime-annotate/run_b0.py` | Annotate C16 engines |
| `artifacts/.../2026-08-21-b0-regime-annotate/` | results + ANALYTICS_REGIME.html |
| `experiments/2026-08-21-c18-regime-dual/run_c18.py` | B1 (later) |

---

## Task 1: `market_regime` module + tests

**Files:**
- Create: `src/ai_algo/domain/market_regime.py`
- Create: `tests/test_market_regime.py`

- [x] Step 1: Write failing tests — synthetic uptrend series → mostly `trend_up`; sideways noise → mostly `chop`
- [x] Step 2: Implement `classify_bars`, `summarize`, `regime_at_time`
- [x] Step 3: `pytest tests/test_market_regime.py` passes
- [x] Step 4: Commit

## Task 2: B0 annotation runner + analytics

**Files:**
- Create: `experiments/2026-08-21-b0-regime-annotate/run_b0.py`
- Create session under `artifacts/agent_loop/sessions/2026-08-21-b0-regime-annotate/`

- [x] Step 1: Load C16 bars + engines for `1d` and `1h` (all symbols)
- [x] Step 2: For each script with trades, attach `regime_at_entry`, `frac_trades_in_chop`, `pnl_in_chop` / `pnl_in_trend`, window `chop_share`
- [x] Step 3: Join with C17 pairs (same symbol/tf/base/variant) → kind × chop_bucket lift table
- [x] Step 4: Write `results/*.json` + `ANALYTICS_REGIME.html`
- [x] Step 5: Update BACKLOG / TRAINING_SESSION_INDEX (B0 done)
- [x] Step 6: Commit + push

## Task 3: B1 chop_gate (C18) — after B0 green

**Files:**
- Create: `experiments/2026-08-21-c18-regime-dual/run_c18.py`

- [x] Step 1: Implement `add_chop_gate` graph mutation (ADX>25 ∧ close>SMA50 into open AND)
- [x] Step 2: Generate variants; engine 1d+1h equities+futures
- [x] Step 3: Train with B0 features; promote `38p-*` if criteria met → **0 promoted** (mean Δchop &lt; 0)
- [x] Finding: ranker strong on when gate helps; absolute lift negative → proceed to `add_mr_overlay`
- [ ] Step 4: Commit + push (по просьбе)

## Task 4: B1 MR overlay — only if gate shows chop lift

- [x] Step 1: `add_mr_overlay` mutation + validate `ok` (14/27 bases; LS+MR skipped)
- [x] Step 2: Retrain / promote / analytics delta vs gate-only → **worse than gate**; 0×38p
- [x] Finding: B1 dual-structure = good ranker, bad absolute Δ; next = threshold tune or selective apply

---

## Verification

```bash
cd AI_algo && .venv/bin/pytest tests/test_market_regime.py -q
.venv/bin/python experiments/2026-08-21-b0-regime-annotate/run_b0.py
open artifacts/agent_loop/sessions/2026-08-21-b0-regime-annotate/ANALYTICS_REGIME.html
```
