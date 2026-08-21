# C5 trade-level (§7E / P2.6)

- Scripts: 26
- Labeled trades: 1243 → {'good': 397, 'bad': 478, 'open': 12, 'bad_noise': 318, 'good_weak': 38}
- Intervention hints: {'add_block': 26, 'change_period': 9, 'side_mode': 1}

## Improve loop (15 momentum)

- **base** `15-momentum-cross-0.italgo`: pnl=-18.15 wr=0.367 labels={'good_weak': 7, 'bad_noise': 35, 'good': 29, 'bad': 27} kinds=['add_block', 'change_period']
  - Медиана удержания очень мала — похоже на шум/overtrading. Увеличьте период сигналов, добавьте подтверждение на старшем ТФ или logic_hold.
  - Длинная серия убытков подряд. Добавьте паузу после N убытков (блок «2 убытка подряд» / cooldown) или уменьшите размер после просадки.
- **change_period** `15b-momentum-period20.italgo`: pnl=-34.23 wr=0.293 labels={'bad_noise': 21, 'good': 15, 'bad': 20, 'good_weak': 2, 'open': 1} kinds=['add_block']
  - Длинная серия убытков подряд. Добавьте паузу после N убытков (блок «2 убытка подряд» / cooldown) или уменьшите размер после просадки.
- **add_block** `15c-momentum-ema50-filter.italgo`: pnl=43.01 wr=0.328 labels={'bad_noise': 24, 'good_weak': 3, 'bad': 17, 'good': 17} kinds=['add_block', 'change_period']
  - Медиана удержания очень мала — похоже на шум/overtrading. Увеличьте период сигналов, добавьте подтверждение на старшем ТФ или logic_hold.
  - Длинная серия убытков подряд. Добавьте паузу после N убытков (блок «2 убытка подряд» / cooldown) или уменьшите размер после просадки.

## Notes

- good/bad from pnl (+ hold heuristics)
- interventions classified: add_block / change_period / side_mode

