# Design: Market regime (trend / chop) + dual-structure interventions

**Date:** 2026-08-21  
**Status:** draft for review  
**Repo:** AI_algo  
**Related:** backlog §7 / §7A (regime filters), §7I (B&H), §7H (div), §7G (Desktop wire — out of scope)  
**Voice input:** 2026-08-21 — expand indicators for trend vs chop; switch structure on sawtooth; full history×TF later on another PC

---

## 1. Problem

Training waves C14–C17 improved **intervention ranking** (CV ~0.80) but not **absolute strategy edge**. Current `regime` in `trade_analysis.infer_script_regime` is **script-intent from graph blocks** (EMA stack → `"trend"`), not **market state on bars**.

User hypothesis: when the market is **chop / пила**, a trend-only graph should **change structure** (gate or MR overlay), not only tweak `period`. Without bar-level regime labels, policy weights average trend and chop together and stay weak.

**History×TF full grid (item A)** runs on another machine. This design is **item B only**.

---

## 2. Goals

| ID | Goal | Success signal |
|----|------|----------------|
| G1 | Detect **market** regime on OHLCV: `trend_up` / `trend_down` / `chop` | Stable labels; analytics show PnL split by regime |
| G2 | Annotate existing corpus (C16 engines) with regime features | Report: kind × market_regime × script_type |
| G3 | Add regime features to intervention policy (no variant leak) | Feature importance includes chop metrics |
| G4 | Dual-structure interventions: chop gate, then MR overlay | On high-`chop_share` windows, gate/overlay beats naive period kinds more often |
| G5 | Optional promote tag for regime-aware winners | `38p-*` or tags `regime-gate` / `regime-mr` |

**Non-goals (this spec):**

- Full history-window × all-TF sweep (A — other PC)
- Combo multi-kind search (C — after B0)
- Desktop advisor UI button (§7G / product later)
- Assembling algorithms from scratch (post B decision fork)
- New Desktop indicator blocks not already in engine

---

## 3. Concepts

### 3.1 Two regime axes (must not confuse)

| Axis | Source | Values | Used for |
|------|--------|--------|----------|
| **Script regime** | Graph node types | `trend` / `mean_reversion` / `breakout` / `unknown` | Already exists |
| **Market regime** | Bars (OHLCV) | `trend_up` / `trend_down` / `chop` | **New** |

### 3.2 Dual-structure (intervention shapes)

1. **`add_chop_gate`** — keep trend entries; **AND** with “not chop” (e.g. ADX ≥ threshold or ER ≥ threshold).  
2. **`add_mr_overlay`** — second entry path active **only in chop**; trend path paused or gated in chop.

Phase order: **gate first**, overlay second.

---

## 4. Design — Phase B0 (ground)

### 4.1 Module `ai_algo.domain.market_regime`

**Inputs:** list of bars `{time, open, high, low, close, volume}`.  
**Outputs:**

- `labels: list[str]` — one label per bar (after warm-up `None`/`unknown`)
- `summary: {chop_share, trend_up_share, trend_down_share, n_bars}`
- helpers: `regime_at(ts)`, `segment_stats(from_ts, to_ts)`

**Classifier (v1 — deterministic, CPU-cheap):**

| Signal | Default | Role |
|--------|---------|------|
| ADX(14) | ≥ 25 → trending | Strength |
| Efficiency ratio ER(20) | ≥ 0.4 → trending | Directional efficiency vs path |
| Sign of close − SMA(50) or DI+/DI− | up / down | Side of trend |

**Rule (v1):**

```text
if ADX < 20 or ER < 0.25 → chop
elif ADX >= 25 and ER >= 0.35:
    trend_up if close > SMA50 else trend_down
else → chop   # weak / transition treated as chop for gating
```

Thresholds live in a small config dict; log them in session notes. No ML for the labeler in B0.

**Warm-up:** first `max(period)` bars → `unknown` (excluded from shares or counted separately).

### 4.2 Annotate corpus

Reuse C16 session engines + bars (same as C17):

For each `(symbol, timeframe, script)` with trades:

- map `entryTime` → market regime
- aggregates:
  - `frac_trades_in_chop`
  - `pnl_in_chop` / `pnl_in_trend` (sum of trade pnls; div-adj if equity)
  - window `chop_share` from bars

Write:

- `sessions/2026-08-21-b0-regime-annotate/results/regime_annotation.json` (or parquet later)
- `ANALYTICS_REGIME.html` — heatmaps:
  - mean ΔPnL by kind × `chop_share` bucket (low/mid/high)
  - script_regime × market chop_share
  - base scripts that lose in chop but win in trend (hypotheses candidates)

### 4.3 Policy features (B0 train optional small wave)

Add to featurize (base-only):

- `base_chop_share`
- `base_frac_trades_in_chop`
- `base_pnl_in_chop`
- `base_pnl_in_trend`
- one-hots already have `regime_*` (script)

Retrain can be a light **C18-b0** on existing pairs + new features (no new engine runs required if annotation attaches to pair keys).

**Label:** keep C17 rule (§7I+§7H). Optional diagnostic label `better_in_chop` = improved `pnl_in_chop` without requiring full-window better (report only in B0).

### 4.4 B0 done when

- [x] `market_regime.py` + unit tests on synthetic trend vs flat series
- [x] Annotation over C16 `1d`+`1h` at minimum (all TF nice-to-have)
- [x] Analytics HTML committed under session
- [x] BACKLOG / TRAINING_SESSION_INDEX note: B0 complete; B1 next

---

## 5. Design — Phase B1 (dual-structure)

### 5.1 Graph mutations

**`add_chop_gate`**

- If graph already has ADX filter used as entry gate, skip or strengthen threshold.
- Else: add `indicator_adx` + `logic_gt` (ADX > 25) into `logic_and` before long `position_open_market` condition (mirror short if LS).
- Long-only first if LS wiring is fragile.

**`add_mr_overlay`**

- Requires chop detector in-graph: ADX low **OR** reuse same ADX inverted (`logic_lt`).
- Add MR entry subgraph (reuse pattern from `02-mean-reversion-bb-rsi` stripped) OR-ed with gated trend entry:
  - trend_entry AND not_chop
  - OR (chop AND mr_entry)
- Higher risk of invalid graphs → validate via engine `ok` flag; drop failures.

### 5.2 Training wave **C18** (regime dual)

- Generate `__chopgate` / `__mroverlay` variants on bases (like C16 ATR kinds)
- Engine: start **1d+1h × equities** (cost control); expand if green
- Labels: C17 rule + features from B0
- Promote: cross-symbol + **prefer** wins where `base_chop_share` high and `delta_pnl_in_chop` > 0

### 5.3 B1 done when

- [ ] Both kinds produce runnable italgo for ≥80% of long_only bases
- [ ] Kind stats published; chop-bucket lift vs `change_period_*` documented
- [ ] ≥1 promote path that is regime-tagged (even if n_promoted small)

---

## 6. Approaches considered

| Approach | Pros | Cons |
|----------|------|------|
| **A. Bar ADX/ER labeler + annotate + gate/overlay** (chosen) | Matches voice hypothesis; reuses engines; CPU-cheap | Thresholds heuristic |
| B. Only script-regime advice (status quo+) | Cheap | Does not see market chop |
| C. Learn regime with second LightGBM | Flexible | Needs labels anyway; delays dual-structure |

**Recommendation:** A.

---

## 7. Risks

| Risk | Mitigation |
|------|------------|
| ADX thresholds wrong across TF | Per-TF defaults later; B0 reports sensitivity |
| MR overlay breaks graphs | Gate-only first; validate `ok` |
| Leakage if variant regime features used | Base-only features |
| Confuse with history sweep A | Explicit non-goal; other PC |

---

## 8. File / session layout

```text
src/ai_algo/domain/market_regime.py
tests/test_market_regime.py
experiments/2026-08-21-b0-regime-annotate/run_b0.py
artifacts/.../2026-08-21-b0-regime-annotate/
experiments/2026-08-21-c18-regime-dual/run_c18.py   # B1
docs/superpowers/specs/2026-08-21-regime-dual-structure-design.md  # this file
```

---

## 9. Open points (resolve at implement if needed)

1. Exact ADX/ER defaults per TF — start global, tune after B0 analytics.  
2. Whether C18 includes futures (no div; regime still applies) — **yes for 1d**.  
3. Promote prefix `38p-*` vs tags only — prefer **`38p-*`** if cross-sym bar met.

---

## 9b. B0 empirical note (2026-08-21)

- Mean window `chop_share` on C16 1d+1h ≈ **0.76** with v1 thresholds — most bars look choppy; tune per-TF before over-trusting buckets.
- On `high_chop`: `add_block_ema` / `rsi50` lift `Δpnl_in_chop`; `add_block_adx` strongly negative (supports careful gate design).
- 81 trend-script candidates lose in chop / win in trend.

## 10. Approval

- [x] Direction B chosen by user (2026-08-21)  
- [x] User review of this written spec  
- [ ] Then: implementation plan (writing-plans) → B0 code
