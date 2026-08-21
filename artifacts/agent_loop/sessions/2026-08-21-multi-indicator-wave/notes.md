# Notes — next train waves

## Done
- Wave 1: SuperTrend+RSI family, EMA filter only, ATR exits
- Wave 2: 12 entry families, still EMA50 as the only v1 filter

## Agreed product rule (2026-08-21)
- **Filters ≠ only EMA.** SuperTrend is a common *trend filter*: ST sets direction, another block is entry-only.
- Catalog filters: SuperTrend, ADX+DI, MA slope, Donchian mid, Keltner mid, HTF…
- Cross all entry families × filter toolkit (budgeted grid).
- Also composition families: `EMA(RSI)`, `SMA(RSI)`, etc.
- **Periods ≠ only 50.** Sweep inside **1…200** (validator `max_period=200`). Later expand trials to **300**, then **400**.
- **Reuse backtest engine:** vectorized lab for sweeps → Desktop engine validates shortlist (same metrics contract).
- **Parallel tracks:** user expands Desktop indicator catalog + tests; train lab continues on current whitelist; only stable indicators join next AI waves (§7B).

See backlog §7A–§7B, TRAINING_APPROACH §5.
