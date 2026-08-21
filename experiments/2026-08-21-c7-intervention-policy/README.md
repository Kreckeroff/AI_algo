# C7 — intervention policy model

- Expanded pairs on full 26-script corpus (period×1.5 + EMA50) → 52 labeled outcomes
- LightGBM LOO policy: `models/intervention_policy_lgbm.joblib`
- Promoted clear wins (`ΔPnL≥50` and positive) into Desktop `ai-train` as `27p-*`
- Multi-TF lookback heatmaps: 1d / 1h / 1w

Session: `artifacts/agent_loop/sessions/2026-08-21-c7-intervention-policy/`
