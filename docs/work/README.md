# Work docs — AI_algo

SA-спеки, backlog, research по AI-слою IT Algo.

| Документ | Суть |
|----------|------|
| [BACKLOG.md](./BACKLOG.md) | Продуктовый backlog модулей |
| [../PRODUCT_VISION.md](../PRODUCT_VISION.md) | Видение |
| [../TRAINING_APPROACH.md](../TRAINING_APPROACH.md) | Обучение A/B, сложности, путь |
| [../AGENT_HANDOFF.md](../AGENT_HANDOFF.md) | Старт нового чата |
| [../PRODUCT_BOUNDARY.md](../PRODUCT_BOUNDARY.md) | AI_algo как отдельный продукт |
| [platform/INTEGRATION_INTERFACES.md](./platform/INTEGRATION_INTERFACES.md) | **Контракты** Inference / Ingest / Train |
| [../superpowers/plans/2026-08-21-ai-algo-roadmap.md](../superpowers/plans/2026-08-21-ai-algo-roadmap.md) | **План действий** Phase 0–6 |
| [`../../openapi/v1.yaml`](../../openapi/v1.yaml) | OpenAPI v1 |
| [`../../schemas/`](../../schemas/) | JSON Schema (envelope, GraphDTO, …) |
| [platform/GRAPH_DTO.md](./platform/GRAPH_DTO.md) | Canonical GraphDTO / composition |
| [`../../scripts/export_schema.md`](../../scripts/export_schema.md) | CSV export columns (v1-basic) |
| [`../../schemas/feature_spec_v1.json`](../../schemas/feature_spec_v1.json) | Feature spec for signal A |
| [../templates/](../templates/) | Шаблоны SA и design |

## Области (папки появятся по мере спек)

| Папка | Модуль |
|-------|--------|
| `compose/` | DSL композиции, режимы |
| `compare/` | Сравнение версий скрипта |
| `builder/` | Конструктор из промпта |
| `signal/` | CPU-модель сигнала |
| `advisor/` | Портфель / советы |
| `platform/` | Gateway, экспорт, квоты, **integration interfaces** |
