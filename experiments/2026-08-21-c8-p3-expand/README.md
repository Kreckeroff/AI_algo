# C8 — P3 expand

- Fixed 0-trade Donchian (`math_shift` HH/LL−1) + `06b-rsi-no-session` for 1d
- Interventions: period×1.5, period×0.67, EMA50, ADX>25, SMA200
- LightGBM intervention policy retrain (LOO)
- Multi-TF lookback on 12 scripts (1d / 1h / 1w)
- Promoted clear wins as `28p-*` into Desktop `ai-train`

Session: `artifacts/agent_loop/sessions/2026-08-21-c8-p3-expand/`
