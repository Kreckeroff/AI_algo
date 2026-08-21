# Перенос контекста в новый чат (handoff) — AI_algo

| Поле | Значение |
|------|----------|
| **Назначение** | Стартовая точка для нового чата с агентом |
| **Обновлено** | 2026-08-21 (после C13 + §7H) |
| **API** | `uvicorn ai_algo.app:app --port 8090` · intents: compare_scripts (+ trade_analysis), signal |
| **Репо** | `Kreckeroff/AI_algo` |
| **Путь** | `/Users/kreckeroff/Fintech (startup)/AI_algo` |
| **Ветка** | `main` |

> **Первое сообщение в новом чате (скопировать):**
>
> Работаем над **AI_algo** — AI-слой для IT Algo Desktop.  
> Путь: `/Users/kreckeroff/Fintech (startup)/AI_algo`.  
> Сначала прочитай `docs/AGENT_HANDOFF.md`, затем `AGENTS.md` и `docs/work/BACKLOG.md`.  
> Не коммить/push без просьбы. CPU-first, не одна большая нейросеть.
>
> ```bash
> cd "/Users/kreckeroff/Fintech (startup)/AI_algo"
> git fetch origin && git checkout main && git pull --ff-only origin main
> ```

---

## 1. Репозитории и пути

| Репо | Путь | GitHub | Роль |
|------|------|--------|------|
| **AI_algo** | `…/AI_algo` | `Kreckeroff/AI_algo` | спеки, обучение, эксперименты |
| **it-algo-desktop** | `…/it-algo-desktop` | `Kreckeroff/it-algo-desktop` | UI + engine + интеграция (**AI только ветка `ai-train`**) |
| **it-algo-site** | `…/it-algo-site` | `Kreckeroff/it-algo-site` | квоты / API |
| **Obsidian** | `…/мое хранилище/projects/ai-algo/` | — | личное зеркало доков |

---

## 2. Как работаем с агентом

1. Читать: `AGENTS.md` → этот файл → `BACKLOG.md` → `TRAINING_APPROACH.md` / `PRODUCT_VISION.md`.
2. Новая фича: design (`docs/superpowers/specs/`) → plan → SA (`docs/work/`) → код/эксперимент.
3. Коммит/push — только по просьбе.
4. Существенные решения дублировать в Obsidian `projects/ai-algo/` (кратко + ссылка на git-файл).

### Типичные запросы

| Запрос | Куда смотреть |
|--------|----------------|
| Бэклог / приоритеты | `docs/work/BACKLOG.md` |
| Как учим модель | `docs/TRAINING_APPROACH.md` |
| Контракты с Desktop | `docs/PRODUCT_BOUNDARY.md`, `docs/work/platform/INTEGRATION_INTERFACES.md` |
| План действий | `docs/superpowers/plans/2026-08-21-ai-algo-roadmap.md` |
| Модули продукта | `docs/PRODUCT_VISION.md` |
| Standalone UX + Desktop из коробки | `docs/work/STANDALONE_PRODUCT_UX.md`, backlog §9 |
| Entry×Filter / SuperTrend-фильтр / EMA(RSI) | backlog §7A, `docs/TRAINING_APPROACH.md` |
| Параллель: новые индикаторы Desktop + train | backlog §7B |
| Цель: PnL / WR по режиму (тренд = PnL first) | `PRODUCT_VISION.md`, backlog §7C |
| После обучения: ANALYTICS.html | `AGENTS.md` §3.4, `scripts/build_training_analytics.py` |
| Разбор сделок | `src/ai_algo/domain/trade_analysis.py` |
| Цикл обучения (агент) | `docs/work/AGENT_TRAINING_LOOP.md` |
| **Индекс C-сессий / покрытие** | `docs/work/TRAINING_SESSION_INDEX.md` |
| Дивгэп / short cash | backlog §7H / P3.7 |

---

## 3. Текущее состояние (2026-08-21)

- FastAPI: health, capabilities, ingest с **persist** (`data/ingest/`), infer `compare_scripts` + `signal`.
- Compare: метрики + graph + **trade_analysis**; запрет разного ТФ/окна.
- Desktop: только **`ai-train`** — лаборатория обучения (прод UI позже). **§7G деплой policy — backlog.**
- Цикл обучения: [`AGENT_TRAINING_LOOP.md`](work/AGENT_TRAINING_LOOP.md). Индекс волн: [`TRAINING_SESSION_INDEX.md`](work/TRAINING_SESSION_INDEX.md).
- **Последняя train-волна: C16** — +ATR SL/TP + remove-filter; 25.5k pairs; CV≈0.77/0.84; `36p-*`.
- Next: walk-forward + div features in label (§7H).
- Export: `python scripts/export_ingest_to_csv.py`
- Команда **«продолжай обучение»** → следующая C-сессия + ANALYTICS + обновление индекса.
- Целевой UX (чат, сборщик, dual release): [`STANDALONE_PRODUCT_UX.md`](work/STANDALONE_PRODUCT_UX.md) — после зрелости моделей.

**Данные сделок:** бэктест `BacktestSnapshot.trades`; брокерская история — позже в Advisor.

---

## 4. Открытые продуктовые вопросы

См. конец [`docs/work/BACKLOG.md`](work/BACKLOG.md).
