# Agent training loop — как будем учить модель

| Поле | Значение |
|------|----------|
| **Статус** | каркас готов; цикл по команде пользователя |
| **Дата** | 2026-08-21 |

## Роли

| Кто | Что делает |
|-----|------------|
| **Ты** | Управляешь: «сделай трендовый скрипт», «поменяй период», «сравни», «учи веса» |
| **Агент** | Создаёт/меняет артефакты (`.italgo`, JSON compare, notes), гоняет данные в ingest, потом train |
| **AI_algo** | Хранит датасет на диске, compare/советы, позже `train.py` / Train API |
| **Desktop `ai-train`** | Бэктест + auto-ingest (лаборатория, не прод UI) |

Полированный UI в prod — **после** того, как модель реально работает.

## Цикл одной сессии

```text
1. Агент пишет script_v0.italgo (артефакт)
2. Бэктест (Desktop или позже CLI) → ingest bars/graphs/runs (persist на диск)
3. Ты: «измени X» → агент script_v1.italgo
4. Снова бэктест + compare (одинаковое окно ТФ/from-to)
5. Артефакты: notes.md, compare_result.json, метрики
6. По команде «учи» → export CSV → LightGBM → model.joblib
7. Смотрим OOS / веса / что лучше → следующая итерация
```

Папка сессий: `artifacts/agent_loop/sessions/<id>/`

## Persist

- Ingest пишется в `data/ingest/{bars,graphs,runs}/*.json` (не только RAM).
- Env: `AI_ALGO_DATA_DIR`, `AI_ALGO_STORE=memory` (тесты).
- Export: `python scripts/export_ingest_to_csv.py`

## Когда скажешь «начинай обучать» / «продолжай обучение»

Агент:
1. Создаст сессию в `artifacts/agent_loop/sessions/…`
2. Соберёт/изменит скрипты / grid
3. Накопит прогоны (lab и/или Desktop ingest)
4. Запустит train/BT experiment
5. **Обязательно** сгенерирует `ANALYTICS.html` — полная аналитика + **сравнение с предыдущей сессией** (`scripts/build_training_analytics.py`, см. `AGENTS.md` §3.4)
6. Зафиксирует `REPORT.md` / notes

Без шага 5 сессия не считается завершённой.

## Trade-level learning (§7E)

Каждая train/lab сессия по возможности сохраняет или семплирует **`trades[]`**.

Цель модели/Advisor:

1. Отметить **плохие** сделки (убыток, пила, плохой hold под режим).
2. Предложить **конкретное** улучшение: добавить блок-фильтр / exit **или** сменить `period`.
3. После правки — снова бэктест и compare на metrics **+** trades.

См. backlog §7E / шаг P2.6.

## Мульти-инструмент + рост датасета (§7F)

Постоянное правило (не «когда-нибудь»):

1. Не учить только на одном тикере дольше, чем нужно для sanity-check.
2. Каждая новая сессия — **добавить символы** и/или **расширить набор** (скрипты, вмешательства, TF, lookback, trades).
3. В notes / ANALYTICS: какие `symbol` покрыты, каких не хватает.
4. Лестница: SBER → +GAZP+LKOH (C9) → 6→9→10 equities (C10–C13) → +futures (C14) → другие рынки.
5. Живой индекс сессий: [`TRAINING_SESSION_INDEX.md`](TRAINING_SESSION_INDEX.md) — обновлять после каждой C-волны.

См. backlog §7F / P3.5.

## Дивгэп equities / index (§7H) — backlog дообучения

На акциях и индексе: шорт через дивгэп **не** зарабатывает на падении цены отсечки — дивиденд **списывают** с шорта. Без cash-adjustment / флагов ex-div метрики LS на equities provisional. Дообучение + interventions «flat before ex-div» — **P3.7**.

См. backlog §7H / P3.7.

## Деплой / Advisor live (§7G) — backlog

Пока **не** вшиваем policy в Desktop. Возможны hosting или локальный бандл позже.  
Целевой UX: ИИ постоянно видит правки и действия пользователя — отдельный backlog.  
Текущий приоритет цикла: **сделать модель максимально сильной** (больше тикеров, TF, вмешательств, trade-level).

См. backlog §7G / P3.6 / P5.

