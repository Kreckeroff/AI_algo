# C13 — all timeframes (§7A)

Do **not** drop TF coverage. Train intervention policy on every available MOEX equity TF:

`1m, 5m, 10m, 15m, 30m, 1h, 1d, 1w` × 10 tickers (ROSN missing some intraday files → skip those cells).

Intraday bars capped for speed; 1d/1w full. Promote `33p-*` on 1d cross-symbol (≥5/10).

Session: `artifacts/agent_loop/sessions/2026-08-21-c13-all-tf/`
