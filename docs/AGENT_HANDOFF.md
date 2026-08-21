# Перенос контекста в новый чат (handoff) — AI_algo

| Поле | Значение |
|------|----------|
| **Назначение** | Стартовая точка для нового чата с агентом |
| **Обновлено** | 2026-08-21 |
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
| Разбор сделок | `src/ai_algo/domain/trade_analysis.py` |

---

## 3. Текущее состояние (2026-08-21)

- FastAPI: health, capabilities, ingest (RAM), infer `compare_scripts` + `signal`.
- Compare: метрики + graph notes + **`trade_analysis`** (пила / streak / sides / режим скрипта).
- Desktop интеграция — ветка **`ai-train`** (не `main` прода): compare UI, auto-ingest, samples.
- Следующее: авто-бэктест bridge (Desktop orchestrates dual backtest), затем `build_script`.

**Данные сделок в Desktop:**
- Бэктест: `BacktestSnapshot.trades` (уже в UI статистики).
- Брокер: Finam/Tinkoff history SQLite (`get_finam_trades_history`) — для Advisor позже.

---

## 4. Открытые продуктовые вопросы

См. конец [`docs/work/BACKLOG.md`](work/BACKLOG.md).
