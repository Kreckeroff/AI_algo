# Experiment: signal CPU baseline (v1-basic)

| Field | Value |
|-------|-------|
| Date | 2026-08-21 |
| Loop | A (signal) |
| Feature spec | `v1-basic` |
| Model | LightGBM (fallback: sklearn HistGradientBoosting) |

## Hypothesis

Short-horizon direction can be weakly predicted from returns + RSI/ATR/EMA distance on synthetic then real Desktop exports.

## Run

```bash
cd "/Users/kreckeroff/Fintech (startup)/AI_algo"
source .venv/bin/activate
pip install -r experiments/2026-08-21-signal-cpu-baseline/requirements.txt
python experiments/2026-08-21-signal-cpu-baseline/train.py \
  --csv experiments/2026-08-21-signal-cpu-baseline/sample.csv \
  --out models/artifacts/signal-cpu-v1
```

## Metrics

Printed: accuracy + ROC-AUC on time-based 70/30 holdout.

## LightGBM on Mac / Windows

See [`docs/DEV_SETUP.md`](../../docs/DEV_SETUP.md).

- **Mac failure mode:** package installs but `import lightgbm` needs `brew install libomp`.
- **Windows:** pip wheel usually works; install VC++ Redistributable if DLL load fails.
- Use `--require-lgbm` so trainers do not silently diverge to sklearn.
