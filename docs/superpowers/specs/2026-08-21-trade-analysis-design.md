# Design: разбор исторических сделок в Compare

Дата: 2026-08-21  
Статус: implemented (MVP heuristics)

## Зачем

Пользователь ждёт не только «лучше/хуже по PnL», а **почему** сделки плохие и **как** доработать скрипт  
(пример: тренд → фильтр от «пилы» во флэте; MR → не торговать в сильном тренде).

## Источники данных (IT Algo)

| Источник | Есть? | Где |
|----------|-------|-----|
| Сделки бэктеста | да | `BacktestSnapshot.trades` |
| Брокерская история | да | Finam/Tinkoff SQLite / portfolio commands |
| MVP AI | бэктест | payload `trades[]` в `compare_scripts` |

## Логика MVP

`analyze_trades` + режим по типам блоков → findings + RU suggestions → в `compare` result.

## Дальше

LLM-слой на тех же facts; broker history в `advise`; dual-backtest bridge шлёт trades автоматически.
