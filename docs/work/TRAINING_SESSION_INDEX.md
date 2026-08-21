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
| **7H** | **Дивгэп:** шорт на акциях/индексе не зарабатывает гэп; дивиденд списывают | **P3.7 / C17** (features+labels) |
| **7I** | **Бить buy&hold** на окне графика (LO / LS) | **P3.8 принято** |

После каждой сессии: `ANALYTICS.html` + compare prev→current + `REPORT.md` / notes.

**Сводная карта всего обучения:** `artifacts/agent_loop/TRAINING_UNIVERSE_MAP.html` (C7→C17 + WF + §7H; regenerate `scripts/build_training_universe_map.py`).  
**Бизнес-аналитика (простым языком):** `artifacts/agent_loop/BUSINESS_ANALYTICS.html` + [`BUSINESS_STATUS.md`](BUSINESS_STATUS.md).

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
| **P3.7** | Div calendar × C14 equities chart window; short pays | annotate session | — |
| **C15** | BH-aware labels/policy (§7I); base BH features | **21614 · 0.77/0.84** | **35p-*** |
| **C16** | +ATR SL/TP + remove-filter; BH labels | **25452 · 0.77/0.84** | **36p-*** |
| **C17** | walk-forward + §7H div features/labels | **25452 · 0.80/0.85** | **37p-*** |
| **B0** | market regime annotate (ADX+ER) on C16 1d+1h | **6552 pairs enriched** | — |
| **C18 / B1** | `add_chop_gate` (ADX>25 ∧ close>SMA50) 1d+1h + B0 feats | **702 · 0.87/0.91** · meanΔ−445 · **0×38p** | — |
| **C18b** | `add_mr_overlay` (trend∧!chop)∨(BB/RSI∧chop) | **364 · 0.92/0.93** · meanΔ−754 · **хуже gate** · **0×38p** | — |
| **B0b** | regime threshold retune (mid→transition) | chop **0.76→0.37** · trend **0.21→0.34**; on high_chop gate/overlay **Δchop>0** | — |
| **C19** | selective apply (chop≥0.38 ∧ P≥0.55) | **1066 · 0.90/0.92** · sel lift **+48** (always −550) | **4×38p-*_sel** |

Актуальная модель: `…/c19-selective-apply/models/intervention_policy_lgbm.joblib`  
Baseline kinds corpus: C17 `37p-*` + C19 selective `38p-*_sel`.
Labeler defaults: `market_regime.py` **B0b**.

### Покрытие данных (после C13)

| Класс | Тикеры | ТФ | Примечание |
|-------|--------|-----|------------|
| Equities | SBER GAZP LKOH ROSN GMKN NVTK TATN PLZL MGNT MTSS | 1m 5m 10m 15m 30m 1h 1d 1w | ROSN: нет 5m/15m/30m |
| Futures | CNYRUBF GLDRUBF IMOEXF | все 8 | **в C14**; **без дивгэпа** (§7H control) |

### Intervention kinds (текущие)

`…periods/filters…` · **`add_block_atr_sltp`** · **`remove_block_filter`** · **`add_chop_gate`** · **`add_mr_overlay`**

Label better (§7I): ΔPnL>0 · DD-ok · Δedge_vs_bh>0 · beats B&H · !pseudo.

### Следующие шаги (не потерять)

1. Wire selective rule into Advisor (§7G later) — пока offline policy.
2. History-window sweep 1d…5y (§7A) — другой ПК.
3. Combo interventions (C).
4. Desktop BT: native B&H + div cash-adjust.
5. **Не** вшивать policy в Desktop (§7G).

---

## Чеклист «сессия закрыта»

- [ ] `REPORT.md` + `notes.md`
- [ ] `ANALYTICS.html` (FULL_MAP style) + compare C7…prev
- [ ] `results/variant_summary.json` + pairs / model
- [ ] Promote `NNp-*` в Desktop `ai-train` при cross-symbol OK
- [ ] Строка в `BACKLOG.md` История + обновление этого индекса
- [ ] Push AI_algo (+ desktop `ai-train` если promotes)
