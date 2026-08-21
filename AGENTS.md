# AI_algo — инструкция для агента

Этот файл — **обязательный playbook** при любой работе в репозитории `AI_algo`.

**Новый чат:** начать с [`docs/AGENT_HANDOFF.md`](docs/AGENT_HANDOFF.md).

---

## 1. Контекст продукта

| Репозиторий | Роль |
|-------------|------|
| **AI_algo** (этот) | Видение AI, SA-спеки, обучение моделей, эксперименты, контракты |
| **it-algo-desktop** | Desktop: конструктор, бэктест, UI интеграции AI |
| **it-algo-site** | Квоты / API (если облачный AI) |
| **fintech-web** | Архив — только референс |

**Продукт:** отдельный AI_algo (скрипты, сигналы, советы). **Клиент v1:** IT Algo Desktop — только через integration interfaces.

**Obsidian (зеркало заметок):** `/Users/kreckeroff/мое хранилище/projects/ai-algo/`

---

## 2. Архитектурные принципы (не нарушать)

1. **Не одна нейросеть** — модули A (сигнал), B (сборка), сравнение версий, аналитик, **разбор сделок**.
2. **CPU-first** — первая своя модель: LightGBM / логрег; без GPU-требования для MVP.
3. **Не обучать LLM с нуля** — готовый LLM API или локальная 7–8B для языка/сборки.
4. **DSL композиции** — индикаторы могут вкладываться (`EMA(RSI)`); whitelist + max глубина.
5. **Режимы рынка** — `RSI>80` в тренде ≠ sell; интерпретация зависит от regime.
6. **Нет look-ahead** — фичи только из прошлого относительно метки; сплит по времени.
7. **Вердикты на цифрах** — «лучше/хуже» только из сопоставимых метрик бэктеста, без выдуманных чисел.
8. **Секреты / ключи API** — только в `.env` (gitignore); не коммитить датасеты с PII без нужды.
9. **Минимальный diff** — не рефакторить несвязанное.
10. **Отдельный продукт** — Desktop не содержит обучение; связь только по контрактам (`docs/PRODUCT_BOUNDARY.md`, `docs/work/platform/INTEGRATION_INTERFACES.md`).
11. **Обучение:** export датасетов **или** train API только в `dev` — не из prod-клиента.

---

## 3. Workflow (обязательный порядок)

```
1. Brainstorm / уточнение цели
2. Design spec     → docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md
3. Review с пользователем
4. Implementation plan → docs/superpowers/plans/YYYY-MM-DD-<topic>.md
5. SA-спека фичи   → docs/work/{area}/{FEATURE}_SA_SPEC.md  (если продукт/контракт)
6. Обновить индексы → docs/work/README.md, BACKLOG.md, AGENT_HANDOFF.md
7. Эксперимент/код → experiments/ или будущий src/ (минимальный diff)
8. Коммит / push   → только по явной просьбе пользователя
```

### 3.1 Когда писать спеку

- Новая фича AI / контракт с Desktop — **до или вместе с кодом**, не после.
- Чистый research-эксперимент — достаточно design + plan; SA — когда есть продуктовый контракт.
- Статусы: `Черновик` → `В разработке` → `Принято` / `Эксперимент закрыт`.

### 3.2 Шаблоны

| Тип | Шаблон |
|-----|--------|
| SA фичи | [`docs/templates/FEATURE_SA_SPEC_TEMPLATE.md`](docs/templates/FEATURE_SA_SPEC_TEMPLATE.md) |
| Design (superpowers) | [`docs/templates/DESIGN_SPEC_TEMPLATE.md`](docs/templates/DESIGN_SPEC_TEMPLATE.md) |

### 3.3 ID фич

Префикс `AI-{NAME}` (пример: `AI-SCRIPT-COMPARE`, `AI-COMPOSE-DSL`, `AI-SIGNAL-CPU`).

---

## 4. Два контура обучения (не путать)

| ID | Название | Вход | Выход | Стек |
|----|----------|------|-------|------|
| **A** | Сигнал | фичи на баре (в т.ч. составные) | вероятность / режим | LightGBM, CPU |
| **B** | Сборка стратегии | промпт + режим + каталог | граф блоков + периоды | LLM + DSL + whitelist; позже ранжировщик |

Подробно: [`docs/TRAINING_APPROACH.md`](docs/TRAINING_APPROACH.md).

---

## 5. Типичные запросы пользователя

| Запрос | Действие агента |
|--------|-----------------|
| «Что в бэклоге?» | `docs/work/BACKLOG.md` |
| «Обучи модель / эксперимент» | TRAINING_APPROACH + `experiments/` + design при новой метке/фичах |
| «Спека на фичу X» | шаблон SA → `docs/work/…` |
| «Синхронизируй Obsidian» | обновить `мое хранилище/projects/ai-algo/` |
| «Интеграция в Desktop» | контракт в SA + задача/ссылка в it-algo-desktop (не ломать Desktop без спеки) |

---

## 6. Запреты

- Не коммитить / push / force-push без просьбы
- Не обещать в UI «гарантированную прибыль» от модели A
- Не зашивать «RSI>80 = всегда sell»
- Не тащить секреты Desktop / брокерские ключи в этот репо
- Не раздувать scope: сначала single-symbol, один TF, whitelist composition

---

## 7. Карта модулей (черновик)

| ID | Модуль | Приоритет | Док |
|----|--------|-----------|-----|
| AI-SCRIPT-COMPARE | Сравнение версий лучше/хуже | P0 must | BACKLOG §2 |
| AI-COMPOSE-DSL | Композиция индикаторов + режимы | P0 foundation | BACKLOG §7 |
| AI-SCRIPT-BUILDER | Конструктор из промпта + defaults | P0 | BACKLOG §1 |
| AI-SIGNAL-CPU | Лёгкая модель сигнала | P2 experiment | BACKLOG §6 |
| AI-PORTFOLIO-ADVISOR | Аналитик портфеля | P1 | BACKLOG §3 |
| AI-PLATFORM | Gateway, экспорт данных, квоты | сквозной | BACKLOG §5 |
| AI-PLATFORM-IFACE | Контракты Inference/Ingest/Train | P0 foundation | `work/platform/INTEGRATION_INTERFACES.md` |

Полный бэклог: [`docs/work/BACKLOG.md`](docs/work/BACKLOG.md).
