# P3.7 — dividend gap on chart window (§7H)

1. Fetch calendar (Smart-Lab → cache):

```bash
.venv/bin/python scripts/fetch_moex_dividends.py
# → data/dividends/moex_equities.json
```

2. Annotate C14 equity engines (1d+1h) vs chart bar window:

```bash
.venv/bin/python experiments/2026-08-21-p37-divgap/run_p37_annotate.py
# → artifacts/agent_loop/sessions/2026-08-21-p37-divgap/
```

**Rule:** trade open through `last_buy_date` / `ex_effect_date` → short **pays** `dividend_rub`×qty; long **receives**. Futures skipped.

Helpers: `src/ai_algo/domain/dividends.py`
