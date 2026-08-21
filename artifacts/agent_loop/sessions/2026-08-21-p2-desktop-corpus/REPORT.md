# P2 Desktop corpus — engine + ingest

- Date: 2026-08-21T09:28:15.855052+00:00
- Symbol/TF: SBER / 1d
- Bars: 1366 from `MOEX_SBER_1d.csv`
- Scripts: 20 (20 ok)
- Ingest OK: 20/20
- AI_algo: `http://127.0.0.1:8090`

## Ranking by net PnL (Desktop engine)

| file | trades | WR | PnL | maxDD |
|------|--------|----|-----|-------|
| `04-macd-stoch-long-short.italgo` | 20 | 0.526 | 165.77 | 148.26 |
| `01-trend-ema-adx-rsi.italgo` | 4 | 0.500 | 127.51 | 59.19 |
| `09-sma-cross-20-50.italgo` | 12 | 0.500 | 102.52 | 51.07 |
| `07-supertrend-di-adx-stack.italgo` | 31 | 0.300 | 82.92 | 177.69 |
| `10-ema-cross-9-21.italgo` | 33 | 0.303 | 47.48 | 103.58 |
| `18-mom-pct-ema50-filter.italgo` | 61 | 0.328 | 43.01 | 66.30 |
| `16-supertrend-rsi-entry.italgo` | 10 | 0.556 | 41.35 | 109.59 |
| `08-cci-regime-trail.italgo` | 44 | 0.455 | 29.73 | 28.22 |
| `03-breakout-donchian-volume.italgo` | 0 | 0.000 | 0.00 | 0.00 |
| `06-session-filter-rsi.italgo` | 0 | 0.000 | 0.00 | 0.00 |
| `20-donchian-55.italgo` | 0 | 0.000 | 0.00 | 0.00 |
| `13-rsi-cross-50.italgo` | 86 | 0.326 | -3.62 | 120.46 |
| `14-cmo-cross-0.italgo` | 86 | 0.326 | -3.62 | 120.46 |
| `15-momentum-cross-0.italgo` | 98 | 0.367 | -18.15 | 130.03 |
| `05-trend-atr-sl-tp.italgo` | 42 | 0.238 | -33.54 | 79.60 |
| `17-supertrend-rsi-tight.italgo` | 17 | 0.562 | -41.40 | 173.71 |
| `02-mean-reversion-bb-rsi.italgo` | 11 | 0.455 | -77.87 | 120.93 |
| `12-dema-cross-12-26.italgo` | 43 | 0.381 | -103.43 | 148.32 |
| `11-tema-cross-10-30.italgo` | 52 | 0.481 | -127.72 | 181.33 |
| `19-bb-rsi-mean-reversion-v2.italgo` | 9 | 0.500 | -241.97 | 269.84 |

## Notes

- Engine: `crates/backtest` (`run_ai_train_corpus` example), not Electron UI.
- Commission 0.04%, slippage 0.01%, capital 100k.
- §7C: for trend scripts PnL-first; WR can be <40%.
