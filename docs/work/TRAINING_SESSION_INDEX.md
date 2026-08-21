# Индекс сессий обучения — не терять контекст

| Поле | Значение |
|------|----------|
| **Статус** | живой индекс; обновлять после каждой C-сессии |
| **Дата** | 2026-08-21 |
| **Связано** | [`BACKLOG.md`](BACKLOG.md), [`AGENT_TRAINING_LOOP.md`](AGENT_TRAINING_LOOP.md), [`../TRAINING_APPROACH.md`](../TRAINING_APPROACH.md), `AGENTS.md` |

Папка артефактов: `artifacts/agent_loop/sessions/<id>/`  
Корпус Desktop: `it-algo-desktop/docs/work/scripting/samples/ai-train/` (ветка **`ai-train`**)  
Сырые бары: `…/2026-08-21-multi-indicator-wave/data/raw/MOEX_{SYM}_{TF}.csv`

---

## Обязательные правила (кратко)

| § | Суть | Статус |
|---|------|--------|
| **7A** | Все доступные **ТФ** + whitelist-связки + period 1…200 + history windows | C13: ТФ 1m…1w покрыты |
| **7B** | Desktop индикаторы ∥ lab; не ждать полный каталог | ongoing |
| **7C** | Цель: +WR и макс PnL; **тренд = PnL first** (WR&lt;40% ок) | принято |
| **7D** | `long_only` **и** `long_short` | C4+ |
| **7E** | `trades[]` good/bad → блок / period | C5–C6+ |
| **7F** | Постоянно расширять **тикеры + датасет** | C9→C13: 10 equities |
| **7G** | Деплой policy в Desktop / live actions — **не сейчас** | backlog |
| **7H** | **Дивгэп:** шорт на акциях/индексе не зарабатывает гэп; дивиденд списывают | **P3.7 backlog** |

После каждой сессии: `ANALYTICS.html` + compare prev→current + `REPORT.md` / notes.

---

## Волна C1…C13 (факт)

| ID | Фокус | Ключевой результат | Promote |
|----|--------|-------------------|---------|
| C1 | entry×filter | lab | — |
| C2 | composition | lab | — |
| C3 / C3b | all-TF lab + lookback shortlist | lab | — |
| C4 | side_mode LO/LS | 26 scripts | — |
| C5 / C5b | trade-level + FULL_MAP | labels | — |
| C6 | intervention pairs | ~20 pairs | — |
| C7 | LightGBM policy | LOO ~0.67/0.69 | 27p-* |
| C8 | Donchian/06b + 5 kinds + lookback | 133 pairs | 28p-* |
| C9 | SBER+GAZP+LKOH | 399 pairs ~0.70/0.71 | 29p-* |
| C10 | +ROSN+GMKN+NVTK (6) | 798 ~0.72/0.79 | 30p-* |
| C11 | +TATN+PLZL+MGNT (9) | 1197 ~0.72/0.79 | 31p-* |
| C12 | +MTSS; RSI50/period×2; 1d+1h; DD-aware | 3740 ~0.70/0.78 | 32p-* |
| **C13** | **ALL TF 1m…1w × 10 equities** | **14399 ~0.72/0.80** | **33p-*** |
| **C14** | **+3 futures** × all TF; period×0.5; `is_future` | **21614 ~0.72/0.79** | **34p-*** |

Актуальная модель: `artifacts/.../2026-08-21-c14-futures-expand/models/intervention_policy_lgbm.joblib`

### Покрытие данных (после C13)

| Класс | Тикеры | ТФ | Примечание |
|-------|--------|-----|------------|
| Equities | SBER GAZP LKOH ROSN GMKN NVTK TATN PLZL MGNT MTSS | 1m 5m 10m 15m 30m 1h 1d 1w | ROSN: нет 5m/15m/30m |
| Futures | CNYRUBF GLDRUBF IMOEXF | все 8 | **в C14**; **без дивгэпа** (§7H control) |

### Intervention kinds (текущие)

`change_period_15x` · `change_period_067` · `change_period_2x` · `change_period_05x` · `add_block_ema` · `add_block_adx` · `add_block_sma200` · `add_block_rsi50`

Label better: `ΔPnL > 0` **и** `variant_dd ≤ 1.5 × base_dd`.

### Следующие шаги (не потерять)

1. **C15:** ATR SL/TP / remove-filter kinds; walk-forward по годам.
2. **P3.7 / §7H:** календарь ex-div + cash adjust на equities; LS без adjust = provisional.
3. History-window sweep 1d…5y (§7A) — ещё долг.
4. Walk-forward по годам; больше kinds (SL/TP, remove block).
5. **Не** вшивать policy в Desktop (§7G).

---

## Чеклист «сессия закрыта»

- [ ] `REPORT.md` + `notes.md`
- [ ] `ANALYTICS.html` (FULL_MAP style) + compare C7…prev
- [ ] `results/variant_summary.json` + pairs / model
- [ ] Promote `NNp-*` в Desktop `ai-train` при cross-symbol OK
- [ ] Строка в `BACKLOG.md` История + обновление этого индекса
- [ ] Push AI_algo (+ desktop `ai-train` если promotes)
