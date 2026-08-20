# Dev setup — AI_algo API + training (Mac & Windows)

## API (inference)

```bash
cd "/Users/kreckeroff/Fintech (startup)/AI_algo"   # or your clone path
python3 -m venv .venv
# Windows: py -3 -m venv .venv && .venv\Scripts\activate
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -e ".[dev]"
pip install -r experiments/2026-08-21-signal-cpu-baseline/requirements.txt
pytest -v
uvicorn ai_algo.app:app --reload --port 8090
```

- Health: `GET http://127.0.0.1:8090/v1/health`
- OpenAPI UI: `http://127.0.0.1:8090/docs`
- Intents: `compare_scripts`, `signal`

Python: **3.9+** (3.11+ preferred). On this Mac default was 3.9.6 from CLT.

---

## Why LightGBM failed on Mac (root cause)

`pip install lightgbm` **succeeds**, but `import lightgbm` fails with:

```text
Library not loaded: @rpath/libomp.dylib
Reason: tried: '/opt/homebrew/opt/libomp/lib/libomp.dylib' (no such file)
```

LightGBM’s macOS wheel links against **OpenMP** (`libomp`). Homebrew package was missing → silent fallback to sklearn in `train.py`.

### Fix (macOS Apple Silicon / Homebrew)

```bash
brew install libomp
# verify:
ls /opt/homebrew/opt/libomp/lib/libomp.dylib
python -c "import lightgbm; print(lightgbm.__version__)"
```

`libomp` is keg-only; LightGBM already looks at `/opt/homebrew/opt/libomp/lib/` — after install, import works without extra `export` for runtime.

Intel Mac / older Homebrew prefix: `/usr/local/opt/libomp/lib/libomp.dylib`.

### Train requiring LightGBM

```bash
python experiments/2026-08-21-signal-cpu-baseline/train.py \
  --csv experiments/2026-08-21-signal-cpu-baseline/sample.csv \
  --out models/artifacts/signal-cpu-v1 \
  --require-lgbm
```

Without `--require-lgbm`, missing OpenMP falls back to `HistGradientBoostingClassifier` and prints a hint.

---

## Windows (training)

1. Install **Python 3.11+** from python.org (64-bit) or Store; enable “Add to PATH”.
2. Install **Microsoft Visual C++ Redistributable** (x64) if wheels fail to load native DLLs — usually needed for scientific stacks.
3. In PowerShell:

```powershell
cd path\to\AI_algo
py -3.11 -m venv .venv
.\.venv\Scripts\activate
python -m pip install -U pip setuptools wheel
pip install -e ".[dev]"
pip install -r experiments/2026-08-21-signal-cpu-baseline/requirements.txt
python -c "import lightgbm; print(lightgbm.__version__)"
python experiments/2026-08-21-signal-cpu-baseline/train.py `
  --csv experiments/2026-08-21-signal-cpu-baseline/sample.csv `
  --out models/artifacts/signal-cpu-v1 `
  --require-lgbm
```

Official LightGBM Windows wheels typically **bundle** OpenMP — no Homebrew equivalent. If import fails:

- Confirm 64-bit Python matches the wheel
- Install [VC++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)
- Avoid mixing conda `libomp` paths with pip blindly; prefer one environment manager

WSL2 (Ubuntu) alternative: `sudo apt install libgomp1` then pip install lightgbm.

---

## Cross-platform checklist (Mac + Win trainers)

| Check | Mac | Windows |
|-------|-----|---------|
| pip install lightgbm | yes | yes |
| OpenMP runtime | `brew install libomp` | usually in wheel / VC++ redist |
| Verify | `python -c "import lightgbm"` | same |
| Train | `--require-lgbm` in CI/team scripts | same |
| Artifacts | `models/artifacts/` (gitignored) | same; share via registry later |

Team rule: **prefer `--require-lgbm`** for shared experiments so Mac/Win produce the same model family.
