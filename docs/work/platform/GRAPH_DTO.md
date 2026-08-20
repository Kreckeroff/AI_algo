# GraphDTO — canonical script graph for AI_algo

| Поле | Значение |
|------|----------|
| **Статус** | MVP |
| **Дата** | 2026-08-21 |
| **Schema** | [`schemas/graph.dto.json`](../../../schemas/graph.dto.json) |
| **Решение** | Canonical DSL в AI_algo; Desktop маппит React Flow ↔ GraphDTO |

---

## Node types (MVP)

| `type` | Назначение |
|--------|------------|
| `indicator` | Индикатор (`kind`: RSI, EMA, SMA, ATR, …) |
| `condition` | Сравнение / cross |
| `action` | Сигнал входа/выхода / риск (stub) |

## Composition

- Индикатор может брать `source`: `open|high|low|close|hl2|hlc3|ohlc4` **или** `source_node`: id другого `indicator`.
- **max_depth** вложенности по `source_node` ≤ **2** (A → B → C запрещено глубже).
- Whitelist MVP: plain indicators; `MA(ind)` / `EMA|SMA` с `source_node`; `HTF_filter` (stub meta).

## Regime

`meta.regime`: `trend | mr | breakout | unknown`  
В `trend` высокий RSI — сила тренда, не авто-sell.

## Пример

См. [`schemas/examples/trend_rsi_ema_graph.json`](../../../schemas/examples/trend_rsi_ema_graph.json).
