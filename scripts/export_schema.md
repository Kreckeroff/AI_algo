# Desktop → AI_algo CSV export schema (v1-basic)

One row = one bar. Time-ordered ascending. No look-ahead in feature columns.

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| `symbol` | string | yes | e.g. SBER |
| `timeframe` | string | yes | e.g. 5m |
| `ts` | ISO8601 string | yes | bar open/close time (document which) |
| `open` | float | yes | |
| `high` | float | yes | |
| `low` | float | yes | |
| `close` | float | yes | |
| `volume` | float | yes | |
| `ret_1` | float | yes | `(close[t]/close[t-1])/close[t-1]` |
| `ret_5` | float | yes | return over 5 bars |
| `rsi_14` | float | yes | RSI(14) |
| `atr_14` | float | yes | ATR(14) |
| `ema_dist_50` | float | yes | `(close - EMA50) / close` |
| `volume_z` | float | yes | z-score of volume vs rolling window |
| `y_up` | 0/1 | train only | label; omit for live inference export |

Feature list source of truth: [`schemas/feature_spec_v1.json`](../schemas/feature_spec_v1.json) (`feature_schema_id`: `v1-basic`).

Export path options:
1. File drop → `data/raw/` (gitignored) then offline `train.py`
2. `POST /v1/ingest/bars` (+ indicators map) then later train job
