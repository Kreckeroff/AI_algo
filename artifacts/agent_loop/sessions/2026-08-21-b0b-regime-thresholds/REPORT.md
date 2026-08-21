# B0b regime threshold retune

- New DEFAULTS: `{'adx_period': 14, 'er_period': 20, 'sma_period': 50, 'adx_trend': 20.0, 'adx_chop': 15.0, 'er_trend': 0.28, 'er_chop': 0.15, 'chop_combine': 'or'}`
- Windows mean chop/trend/trans: **0.369 / 0.340 / 0.268** (was 0.764 / 0.213)

## C18 gate re-score (same trades, new labels)
- mean Δchop v1→b0b: -159.6 → **-121.4**
- better_in_chop rate: 0.481 → **0.484**
- high_chop (≥0.40) mean Δchop: 33.64220777917869

## C18b overlay re-score
- mean Δchop v1→b0b: -543.8 → **-184.1**
- better_in_chop rate: 0.264 → **0.495**

Note: graph mutations still use ADX>25; this retune is the **labeler** only.
