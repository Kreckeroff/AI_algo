# AI_algo — план действий (roadmap)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement **одну фазу за раз**. Шаги — checkbox (`- [ ]`).

**Goal:** Вывести AI_algo как отдельный продукт со стабильными контрактами к IT Algo Desktop, затем MVP compare + ingest + CPU-сигнал, затем builder и dev-train.

**Architecture:** Desktop = клиент. AI_algo = inference + ingest + train (+ registry). Обучение: export offline или Train API только в `dev`. CPU-first (LightGBM); LLM только для языка/сборки.

**Tech Stack (MVP):** Python 3.11+ (FastAPI), Pydantic v2, JSON Schema / OpenAPI, LightGBM + joblib, pytest; клиент позже в `it-algo-desktop` (Rust/TS adapter).

**Specs:** [`PRODUCT_BOUNDARY.md`](../../PRODUCT_BOUNDARY.md), [`INTEGRATION_INTERFACES.md`](../../work/platform/INTEGRATION_INTERFACES.md), [`TRAINING_APPROACH.md`](../../TRAINING_APPROACH.md), [`BACKLOG.md`](../../work/BACKLOG.md).

## Global Constraints

- Не обучать LLM с нуля; не обещать прибыль от сигнала.
- `RSI>80` интерпретировать через regime (trend ≠ MR).
- Train из prod-клиента запрещён (`train_forbidden_in_prod`).
- Секреты брокеров не покидают Desktop.
- Коммит/push/tag — только по просьбе пользователя.
- ID фич: `AI-*`. Контракт: `api_version: "2026-08-20"` до bump.

---

## Карта файлов (целевая структура репо)

```text
AI_algo/
├── openapi/v1.yaml                 # Phase 0
├── schemas/                        # GraphDTO, envelope, metrics (JSON Schema)
├── src/ai_algo/
│   ├── app.py                      # FastAPI entry
│   ├── api/                        # health, capabilities, infer, ingest, train
│   ├── domain/                     # GraphDTO, metrics_diff, regimes
│   ├── models/                     # load/save joblib, feature_schema
│   └── train/                      # jobs, walk_forward
├── experiments/                    # offline notebooks/scripts
├── tests/
└── docs/                           # уже есть
```

IT Algo Desktop (отдельный репо, Phase 3+):
- `src/lib/aiAlgoClient.ts` (или Rust reqwest) — HTTP клиент
- UI: кнопка compare / settings endpoint AI

---

## Фазы (обзор)

| Фаза | Результат | Зависит от |
|------|-----------|------------|
| **0** | OpenAPI + JSON Schema + stub server | доки (готовы) |
| **1** | Ingest bars/graphs/runs + `compare_scripts` | Phase 0 |
| **2** | Export датасета + train A (LightGBM) + `signal` | Phase 1 |
| **3** | Адаптер в it-algo-desktop (dev) | Phase 1 (compare) |
| **4** | DSL composition whitelist + `build_script` | Phase 0–1 |
| **5** | Dev-integrated Train API + promote | Phase 2 |
| **6** | Advisor + multi-TF / ranker | позже |

Ниже — детальные задачи **Phase 0 → 2** (ближайший исполняемый горизонт). Phase 3–6 — чеклисты без полного TDD-разворачивания (отдельный plan при старте фазы).

---

### Task 0.1: OpenAPI skeleton

**Files:**
- Create: `openapi/v1.yaml`
- Create: `schemas/envelope.request.json`
- Create: `schemas/envelope.response.json`
- Modify: `docs/work/platform/INTEGRATION_INTERFACES.md` (ссылка на openapi)
- Modify: `docs/work/README.md` (индекс)

**Interfaces:**
- Produces: paths `/v1/health`, `/v1/capabilities`, `/v1/infer`, `/v1/ingest/bars`, `/v1/ingest/graphs`, `/v1/ingest/runs`, `/v1/train/jobs`, `/v1/train/jobs/{id}`
- Envelope fields: `api_version`, `request_id`, `client`, `intent`, `payload` / `status`, `result`, `error`

- [ ] **Step 1:** Создать `openapi/v1.yaml` с paths выше и компонентами `InferRequest`, `InferResponse`, `HealthResponse`, `CapabilitiesResponse` по полям из INTEGRATION_INTERFACES §3–7.
- [ ] **Step 2:** Вынести JSON Schema envelope в `schemas/`.
- [ ] **Step 3:** Проверить валидность: `npx --yes @redocly/cli lint openapi/v1.yaml` (или `swagger-cli validate`).
- [ ] **Step 4:** Обновить ссылки в `INTEGRATION_INTERFACES.md` §12 и `docs/work/README.md`.
- [ ] **Step 5:** Commit — `docs: add OpenAPI v1 and envelope JSON schemas`

---

### Task 0.2: GraphDTO + metrics schemas

**Files:**
- Create: `schemas/graph.dto.json`
- Create: `schemas/backtest_metrics.json`
- Create: `schemas/feature_vector.json`
- Create: `docs/work/platform/GRAPH_DTO.md` (1 страница: node kinds, composition `source_node`, max_depth)

**Interfaces:**
- Produces: `GraphDTO` с `nodes[].kind`, `params`, `source` | `source_node`, `meta.regime`
- Consumes: примеры из INTEGRATION_INTERFACES §5.2–5.3

- [ ] **Step 1:** Зафиксировать в `GRAPH_DTO.md`: MVP node types = `indicator | condition | action`; composition depth ≤ 2; whitelist = `MA(ind)`, plain indicators, `HTF_filter` (stub).
- [ ] **Step 2:** Написать `schemas/graph.dto.json` + пример `schemas/examples/trend_rsi_ema_graph.json` (`EMA` поверх `RSI`, condition `> 80`, `meta.regime: trend`).
- [ ] **Step 3:** `backtest_metrics.json`: обязательные `pnl`, `max_dd`, `winrate`, `trades`; опциональные `sharpe`, `sortino`.
- [ ] **Step 4:** Commit — `docs: define GraphDTO and metrics JSON schemas`

---

### Task 0.3: FastAPI stub (health + capabilities + infer echo)

**Files:**
- Create: `pyproject.toml` (project `ai-algo`, deps: fastapi, uvicorn, pydantic)
- Create: `src/ai_algo/app.py`
- Create: `src/ai_algo/api/health.py`
- Create: `src/ai_algo/api/infer.py` (stub: unknown intent → `unsupported_intent`)
- Create: `tests/test_health.py`
- Create: `README.md` section «Run locally» (или `docs/DEV_SETUP.md`)

**Interfaces:**
- Produces: `GET /v1/health` → `{ "status": "ok" }`; `GET /v1/capabilities` → intents list; `POST /v1/infer` → envelope
- Consumes: OpenAPI field names from Task 0.1

- [ ] **Step 1:** Write failing test `tests/test_health.py` — client get `/v1/health` expect 200 and `status == "ok"`.
- [ ] **Step 2:** Run `pytest tests/test_health.py -v` → FAIL (app missing).
- [ ] **Step 3:** Minimal FastAPI app + router; run test → PASS.
- [ ] **Step 4:** Add `capabilities` returning intents `["compare_scripts"]` only for now; test asserts list contains it.
- [ ] **Step 5:** `POST /v1/infer` with bad intent returns `status: error`, `error.code: unsupported_intent`.
- [ ] **Step 6:** Commit — `feat: FastAPI stub health capabilities infer`
- [ ] **Step 7:** Document run: `uvicorn ai_algo.app:app --reload --port 8090`

---

### Task 1.1: Ingest bars / graphs / runs (in-memory store)

**Files:**
- Create: `src/ai_algo/api/ingest.py`
- Create: `src/ai_algo/store/memory.py`
- Create: `tests/test_ingest.py`
- Modify: `src/ai_algo/app.py` (include router)
- Modify: capabilities → ingest enabled

**Interfaces:**
- Produces: `POST /v1/ingest/bars|graphs|runs` → `{ status: accepted, result: { id } }`
- Consumes: schemas from Task 0.2

- [ ] **Step 1:** Failing tests: post minimal bars payload → 200 accepted; get store size 1 (test helper or list endpoint `GET /v1/ingest/datasets` stub).
- [ ] **Step 2:** Implement memory store + validators (Pydantic models mirroring JSON Schema).
- [ ] **Step 3:** Reject graph with `source_node` depth > 2 → `validation_failed`.
- [ ] **Step 4:** Commit — `feat: ingest bars graphs runs in-memory`

---

### Task 1.2: `compare_scripts` (deterministic metrics + LLM-optional commentary)

**Files:**
- Create: `src/ai_algo/domain/compare.py` — `metrics_diff`, `verdict_from_diff`
- Create: `src/ai_algo/api/infer_compare.py`
- Create: `tests/test_compare.py`
- Modify: `src/ai_algo/api/infer.py` — dispatch `intent == compare_scripts`

**Interfaces:**
- Consumes: `payload.before.backtest_metrics`, `payload.after.backtest_metrics`, `payload.align`
- Produces: `verdict: better|worse|mixed`, `metrics_diff`, `commentary` (template string MVP, no LLM required), `suggestions[]`

**Verdict rules (MVP, зафиксировать в коде и тесте):**
1. Если `align` окна/symbol/commission различаются → `align_mismatch`.
2. Если `after.max_dd` лучше (меньше) и `after.pnl` лучше (больше) → `better`.
3. Если оба хуже → `worse`.
4. Иначе → `mixed`.
5. Если `trades < 5` у любой стороны → warning `low_sample`.

- [ ] **Step 1:** Unit tests for `verdict_from_diff` covering better/worse/mixed/align/low_sample.
- [ ] **Step 2:** Implement `compare.py` to satisfy tests.
- [ ] **Step 3:** Wire `POST /v1/infer` intent; integration test with two metric blobs.
- [ ] **Step 4:** Commentary = f-string from diff (no external LLM in MVP).
- [ ] **Step 5:** Commit — `feat: compare_scripts verdict from metrics`

---

### Task 2.1: Export format + sample dataset + LightGBM train script

**Files:**
- Create: `experiments/2026-08-21-signal-cpu-baseline/README.md`
- Create: `experiments/2026-08-21-signal-cpu-baseline/train.py`
- Create: `experiments/2026-08-21-signal-cpu-baseline/requirements.txt` (lightgbm, pandas, scikit-learn, joblib)
- Create: `schemas/feature_spec_v1.json` — list of feature names
- Create: `scripts/export_schema.md` — колонки CSV для Desktop export

**Interfaces:**
- Produces: `models/artifacts/` gitignored; `feature_spec_v1` id string `v1-basic`
- Label: `y = 1` if `close[t+N] > close[t] * (1+eps)` with `N=10`, `eps=0.001` (configurable CLI)

- [ ] **Step 1:** Document CSV columns in `scripts/export_schema.md` matching TRAINING_APPROACH §2.
- [ ] **Step 2:** Generate synthetic OHLCV+RSI sample in `experiments/.../sample.csv` (small, committed) for CI.
- [ ] **Step 3:** `train.py` — time split 70/30, LightGBM classifier, print AUC + accuracy; save `model.joblib` + `feature_names.json` under gitignored path.
- [ ] **Step 4:** Run train on sample; ensure exit 0.
- [ ] **Step 5:** Commit — `feat: baseline LightGBM train experiment (sample data)`

---

### Task 2.2: `signal` inference from loaded model

**Files:**
- Create: `src/ai_algo/models/loader.py`
- Create: `src/ai_algo/api/infer_signal.py`
- Create: `tests/test_signal.py`
- Modify: capabilities models list

**Interfaces:**
- Consumes: `payload.feature_vector` keys ⊆ `feature_names.json`; optional `model_id`
- Produces: `p`, `label`, `feature_schema_id`, `disclaimer`

- [ ] **Step 1:** Test: missing feature → `validation_failed`.
- [ ] **Step 2:** Test: load fixture model (train tiny in test or commit tiny joblib fixture under `tests/fixtures/`).
- [ ] **Step 3:** Implement loader + infer path.
- [ ] **Step 4:** Commit — `feat: signal inference from joblib model`

---

### Task 3 (чеклист): Desktop adapter

Отдельный репо `it-algo-desktop`. Завести SA `AI-DESKTOP-ADAPTER` там или здесь `docs/work/platform/DESKTOP_ADAPTER_SA_SPEC.md`.

- [ ] Settings: base URL AI_algo (default `http://127.0.0.1:8090`)
- [ ] Client: health + capabilities на старте AI-панели
- [ ] UI: «Спросить ИИ про изменение» → `compare_scripts` с двумя backtest snapshots
- [ ] Export button: bars/graphs/runs → файлы или ingest (dev)
- [ ] Не вызывать `/v1/train/*` если `env=prod`
- [ ] Handoff / BACKLOG Desktop обновить ссылкой на AI_algo

**Отдельный plan:** `docs/superpowers/plans/YYYY-MM-DD-desktop-ai-adapter.md` при старте.

---

### Task 4 (чеклист): Composition + `build_script`

- [ ] SA: `docs/work/compose/AI_COMPOSE_DSL_SA_SPEC.md`
- [ ] Whitelist + regime defaults (trend template)
- [ ] Validator depth/kinds
- [ ] `build_script` MVP: prompt keywords → template graph (rules; LLM later)
- [ ] Example: trend + `EMA(RSI)` + не auto-sell на RSI>80

**Отдельный plan** при старте.

---

### Task 5 (чеклист): Dev-integrated train

- [ ] `POST /v1/train/jobs` real queue (filesystem or sqlite)
- [ ] Reject `client.env=prod`
- [ ] Promote path: copy artifact → registry `prod` pin
- [ ] Desktop dev branch: periodic ingest after backtest

**Отдельный plan** при старте.

---

### Task 6 (чеклист): Advisor / multi-TF / ranker

- [ ] `advise` intent on aggregated metrics
- [ ] HTF features in feature_spec_v2
- [ ] Graph ranker experiment (loop B)

---

## Порядок исполнения (ближайшие 2–3 недели)

```text
Week 1:  Task 0.1 → 0.2 → 0.3 → 1.1 → 1.2     (контракт + compare stub)
Week 2:  Task 2.1 → 2.2                         (первая своя модель + signal)
Week 3:  Task 3 (Desktop adapter, compare UX)   (интеграция)
Later:   Task 4 → 5 → 6
```

## Definition of Done (горизонт Phase 0–2)

- [ ] `openapi/v1.yaml` валиден; schemas в репо
- [ ] Stub server: health, capabilities, ingest, compare, signal
- [ ] pytest зелёный в CI (добавить `.github/workflows/ci.yml` в Task 0.3 или сразу после)
- [ ] Один воспроизводимый LightGBM experiment на sample
- [ ] Docs + Obsidian зеркало обновлены после фазы
- [ ] Desktop ещё может быть без UI — достаточно curl-контракта

## Self-review (плана)

| Spec area | Task coverage |
|-----------|---------------|
| PRODUCT_BOUNDARY | Phase 0–3 |
| Inference intents | 1.2 compare, 2.2 signal; build/advise → Phase 4/6 |
| Ingest bars/graphs/runs | 1.1 |
| Train export vs dev | 2.1 export; 5 dev |
| Composition / regimes | 0.2 + 4 |
| CPU-first | 2.1–2.2 |

Placeholders: нет TBD в шагах Phase 0–2. GraphDTO «1:1 vs canonical» — решение в Task 0.2 (`GRAPH_DTO.md`: canonical, Desktop маппит).

---

## Execution handoff

План сохранён: `docs/superpowers/plans/2026-08-21-ai-algo-roadmap.md`.

Два варианта исполнения:

1. **Subagent-Driven** — по одной задаче (0.1, 0.2, …), ревью между задачами  
2. **Inline** — в этом чате пакетами с чекпоинтами  

С чего начать: **Task 0.1 (OpenAPI)** — фундамент для всего остального.
