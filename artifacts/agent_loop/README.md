# Agent loop artifacts

Сюда агент кладёт сессии обучения (скрипты, compare JSON, notes).  
Сырые бары — в `data/ingest/` (gitignore). Веса — `*.joblib` / `models/artifacts/`.

См. [`docs/work/AGENT_TRAINING_LOOP.md`](../../docs/work/AGENT_TRAINING_LOOP.md).

```text
sessions/
  2026-08-21-example/
    README.md          # цель сессии
    script_v0.italgo   # (или symlink / копия из desktop samples)
    script_v1.italgo
    notes.md
    compare_v0_v1.json
```
