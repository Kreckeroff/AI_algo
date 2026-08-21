# P3.7 / §7H dividend gap annotation

- Cache: `/Users/kreckeroff/Fintech (startup)/AI_algo/data/dividends/moex_equities.json`
- Engine source: C14 equities × 1d, 1h
- Script rows: 4643
- Short trades crossing ex-div: 3899
- Total Δ PnL from cash adjust: 1040407.17
- LS scripts Δ: -25317.19

Rule: short held through `last_buy_date`/`ex_effect_date` pays `dividend_rub`×qty; long receives.
