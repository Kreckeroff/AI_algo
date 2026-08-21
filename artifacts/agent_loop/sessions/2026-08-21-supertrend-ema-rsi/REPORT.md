# Session report — SuperTrend + EMA/RSI

Дата: 2026-08-21T00:38:22.127811+00:00

## Цель
Обучить сигнал-модель A на мульти-инструмент / мульти-ТФ данных и прогнать улучшения скрипта
(фильтр EMA, ATR SL/TP) с вердиктами better/worse/mixed.

## Инструменты
- MOEX акции: SBER, GAZP, LKOH, GMKN, NVTK, ROSN, MGNT, TATN, MTSS, PLZL
- MOEX фьючерсы: GLDRUBF, IMOEXF, CNYRUBF
- US: SPY, ^GSPC (Yahoo) — прокси S&P500 без брокера
- ТФ: 1h, 1d, 1w
- История: ~5 лет (где доступно)

## Signal model
- kind: `lgbm`
- accuracy: **0.5123**
- roc_auc: **0.5186**
- n_train/n_test: 188781 / 80907
- артефакт: `models/model.joblib`

## Варианты скрипта (векторный бэктест)
- **v0**: SuperTrend + RSI cross 50 (база)
- **v1**: + фильтр тренда EMA(50)
- **v2**: + ATR SL 1.5 / TP 3.0

### Агрегаты
```json
{
  "v0": {
    "n": 27,
    "mean_pnl": -393.99568405490396,
    "mean_dd": 1812.0639315682865,
    "mean_wr": 0.436678664599139,
    "mean_trades": 133.1851851851852
  },
  "v1": {
    "n": 27,
    "mean_pnl": -203.97091200086828,
    "mean_dd": 1743.5801066261577,
    "mean_wr": 0.4000583918852106,
    "mean_trades": 104.22222222222223
  },
  "v2": {
    "n": 28,
    "mean_pnl": 60.43527507672996,
    "mean_dd": 747.8832679966517,
    "mean_wr": 0.36974823900013004,
    "mean_trades": 185.75
  }
}
```

### Вердикты v0→v1→v2
```json
[
  {
    "from": "v0",
    "to": "v1",
    "verdict": "better",
    "agg_before": {
      "n": 27,
      "mean_pnl": -393.99568405490396,
      "mean_dd": 1812.0639315682865,
      "mean_wr": 0.436678664599139,
      "mean_trades": 133.1851851851852
    },
    "agg_after": {
      "n": 27,
      "mean_pnl": -203.97091200086828,
      "mean_dd": 1743.5801066261577,
      "mean_wr": 0.4000583918852106,
      "mean_trades": 104.22222222222223
    }
  },
  {
    "from": "v1",
    "to": "v2",
    "verdict": "better",
    "agg_before": {
      "n": 27,
      "mean_pnl": -203.97091200086828,
      "mean_dd": 1743.5801066261577,
      "mean_wr": 0.4000583918852106,
      "mean_trades": 104.22222222222223
    },
    "agg_after": {
      "n": 28,
      "mean_pnl": 60.43527507672996,
      "mean_dd": 747.8832679966517,
      "mean_wr": 0.36974823900013004,
      "mean_trades": 185.75
    }
  }
]
```

## Desktop
`.italgo` для ручного прогона в `ai-train`: `scripts/v0_supertrend_rsi.italgo`,
`scripts/v0_supertrend_di_adx.italgo`. Следующая волна: 10–20 скриптов с другими индикаторами.

## Важно
1. Больше ТФ (5m/15m) когда ISS/Yahoo отдаёт длинную историю
2. Кормить compare_scripts + trade_analysis из Desktop ingest
3. Ранжировщик графов (контур B) на вердиктах вариантов
