# AI_algo — продуктовое видение

| Поле | Значение |
|------|----------|
| **Статус** | ideation |
| **Дата** | 2026-08-20 |
| **Потребитель** | IT Algo Desktop |

---

## Одна фраза

**Отдельный продукт** AI_algo: помогает **собирать**, **улучшать** и **оценивать** торговые скрипты и сигналы — с пониманием композиции индикаторов и режимов рынка, без требования тяжёлого железа.  
IT Algo Desktop подключается по **контрактам** (inference + data + train), без вшивания обучения в релизное ядро.

См. [`PRODUCT_BOUNDARY.md`](PRODUCT_BOUNDARY.md), [`work/platform/INTEGRATION_INTERFACES.md`](work/platform/INTEGRATION_INTERFACES.md).

---

## Модули

```text
┌──────────────────────┐   Inference / Ingest / Train   ┌─────────────────────────────┐
│  it-algo-desktop     │ ◄────────────────────────────► │  AI_algo (отдельный продукт) │
│  UI · graph · backtest│                               │  Builder · Compare · Advisor │
│  = клиент API        │   export ИЛИ dev-integrated    │  Signal · DSL · Registry     │
└──────────────────────┘         обучение               └─────────────────────────────┘
```

| Модуль | Пользовательская ценность | «Своя» модель? |
|--------|---------------------------|----------------|
| **Builder** | Промпт → готовый граф; сам добирает периоды/связки | LLM + DSL; позже ранжировщик графов |
| **Compare** | После правки: стало лучше/хуже + советы | Нет (метрики + LLM-текст) |
| **Advisor** | Советы по портфелю и статистике скриптов | Правила + LLM |
| **Signal** | Оценка направления/режима по рынку | Да, лёгкая tabular на CPU |
| **Composition** | `EMA(RSI)`, мульти-ТФ, режимы тренд/MR | DSL + обучение на составных фичах |

---

## Не цель

- Обучить свой GPT с нуля
- Обещать точность прогноза цены / гарантированную прибыль
- Засунуть все комбинации индикаторов в одну гигантскую сеть

---

## Порядок ценности (черновик)

1. Compare (цикл итерации)
2. Composition DSL (фундамент)
3. Builder + underspecified defaults
4. Signal CPU experiment
5. Portfolio advisor
6. Multi-TF → multi-instrument → graph ranker

Детали задач: [`work/BACKLOG.md`](work/BACKLOG.md).  
Как учить: [`TRAINING_APPROACH.md`](TRAINING_APPROACH.md).
