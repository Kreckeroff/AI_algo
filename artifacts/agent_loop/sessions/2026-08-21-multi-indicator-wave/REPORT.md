# Session report — Multi-indicator wave (max TFs)

Дата: 2026-08-21T02:12:10.451081+00:00

## Цель
Максимум таймфреймов + 12 семейств индикаторов с улучшением v0→v1→v2,
сигнал-модель A на расширенных фичах.

## Таймфреймы
- MOEX native: 1m, 10m, 1h, 1d, 1w, 1M
- MOEX derived (из 1m): 5m, 15m, 30m
- Yahoo: 5m, 15m, 30m, 1h, 1d, 1w
- Lookback по ТФ (короче для интрадея): см. `models/feature_names.json`

Файлов по ТФ: `{"1m": 12, "10m": 13, "1h": 13, "1d": 15, "1w": 15, "1M": 13, "5m": 14, "15m": 14, "30m": 12}`

## Инструменты
- MOEX акции: SBER, GAZP, LKOH, GMKN, NVTK, ROSN, MGNT, TATN, MTSS, PLZL
- MOEX фьючерсы: GLDRUBF, IMOEXF, CNYRUBF
- US: SPY, ^GSPC (Yahoo)

## Signal model
- kind: `lgbm`
- schema: `v2-multi`
- accuracy: **0.5201**
- roc_auc: **0.5242**
- n_train/n_test: 281980 / 120849
- timeframes in train: 10m, 15m, 1M, 1d, 1h, 1m, 1w, 30m, 5m

## Семейства (v0 base → v1 EMA50 filter → v2 ATR SL/TP)

- `supertrend_rsi`
- `ema_cross`
- `macd_cross`
- `bb_mean_rev`
- `rsi_ob_os`
- `stochastic`
- `adx_di`
- `donchian`
- `keltner`
- `cci`
- `dual_sma_rsi`
- `roc_momentum`

### Ranking by v2 mean PnL
```json
[
  {
    "family": "donchian",
    "mean_pnl_v2": 383.7328725967407,
    "mean_dd_v2": 439.9223057047525,
    "n": 96
  },
  {
    "family": "macd_cross",
    "mean_pnl_v2": 340.5738864694698,
    "mean_dd_v2": 302.2495164704975,
    "n": 95
  },
  {
    "family": "keltner",
    "mean_pnl_v2": 340.01148306783057,
    "mean_dd_v2": 445.5776354039511,
    "n": 96
  },
  {
    "family": "roc_momentum",
    "mean_pnl_v2": 321.41306932035377,
    "mean_dd_v2": 375.7552015147108,
    "n": 94
  },
  {
    "family": "ema_cross",
    "mean_pnl_v2": 309.057531117757,
    "mean_dd_v2": 332.9127105738323,
    "n": 96
  },
  {
    "family": "dual_sma_rsi",
    "mean_pnl_v2": 177.49183697509775,
    "mean_dd_v2": 221.7338824782598,
    "n": 84
  },
  {
    "family": "stochastic",
    "mean_pnl_v2": 40.345784623887674,
    "mean_dd_v2": 143.58069269816085,
    "n": 72
  },
  {
    "family": "cci",
    "mean_pnl_v2": 12.812324827515972,
    "mean_dd_v2": 153.17446255453524,
    "n": 77
  },
  {
    "family": "adx_di",
    "mean_pnl_v2": -1.477756012672315,
    "mean_dd_v2": 252.02767198003718,
    "n": 86
  },
  {
    "family": "bb_mean_rev",
    "mean_pnl_v2": -4.394303856743729,
    "mean_dd_v2": 132.64479437255855,
    "n": 72
  },
  {
    "family": "supertrend_rsi",
    "mean_pnl_v2": -28.35370481979021,
    "mean_dd_v2": 337.14371507085747,
    "n": 86
  }
]
```

### Aggregates (per family)
```json
{
  "supertrend_rsi": {
    "v0": {
      "n": 81,
      "mean_pnl": -187.71390115921574,
      "mean_dd": 727.1051182725695,
      "mean_wr": 0.41428084680862054,
      "mean_trades": 62.77777777777778
    },
    "v1": {
      "n": 81,
      "mean_pnl": -111.34674355890711,
      "mean_dd": 696.706280074508,
      "mean_wr": 0.3842713786669639,
      "mean_trades": 51.79012345679013
    },
    "v2": {
      "n": 86,
      "mean_pnl": -28.35370481979021,
      "mean_dd": 337.14371507085747,
      "mean_wr": 0.36238520215604786,
      "mean_trades": 91.40697674418605
    }
  },
  "ema_cross": {
    "v0": {
      "n": 96,
      "mean_pnl": 392.89406165313693,
      "mean_dd": 503.9950361531576,
      "mean_wr": 0.30014117692851544,
      "mean_trades": 169.64583333333334
    },
    "v1": {
      "n": 93,
      "mean_pnl": 308.78816740958894,
      "mean_dd": 534.8472466817877,
      "mean_wr": 0.2966461833074067,
      "mean_trades": 108.88172043010752
    },
    "v2": {
      "n": 96,
      "mean_pnl": 309.057531117757,
      "mean_dd": 332.9127105738323,
      "mean_wr": 0.3616792442726629,
      "mean_trades": 128.21875
    }
  },
  "macd_cross": {
    "v0": {
      "n": 96,
      "mean_pnl": 147.71122749582983,
      "mean_dd": 621.0862818298334,
      "mean_wr": 0.3487575635219266,
      "mean_trades": 303.5208333333333
    },
    "v1": {
      "n": 87,
      "mean_pnl": 217.7236330426096,
      "mean_dd": 547.1013383761001,
      "mean_wr": 0.28068511282698777,
      "mean_trades": 75.22988505747126
    },
    "v2": {
      "n": 95,
      "mean_pnl": 340.5738864694698,
      "mean_dd": 302.2495164704975,
      "mean_wr": 0.36738844338641585,
      "mean_trades": 127.09473684210526
    }
  },
  "bb_mean_rev": {
    "v0": {
      "n": 87,
      "mean_pnl": -307.90736759440085,
      "mean_dd": 874.0307524470186,
      "mean_wr": 0.6070011751190254,
      "mean_trades": 92.58620689655173
    },
    "v1": {
      "n": 54,
      "mean_pnl": 73.13623034215878,
      "mean_dd": 415.6729532606337,
      "mean_wr": 0.43413827614622924,
      "mean_trades": 15.148148148148149
    },
    "v2": {
      "n": 72,
      "mean_pnl": -4.394303856743729,
      "mean_dd": 132.64479437255855,
      "mean_wr": 0.3808122067533777,
      "mean_trades": 27.208333333333332
    }
  },
  "rsi_ob_os": {
    "v0": {
      "n": 84,
      "mean_pnl": -283.2231421973817,
      "mean_dd": 745.6025717773437,
      "mean_wr": 0.5961519904000413,
      "mean_trades": 32.48809523809524
    },
    "v1": {
      "n": 0
    },
    "v2": {
      "n": 3,
      "mean_pnl": 25.96666666666668,
      "mean_dd": 17.016666666666662,
      "mean_wr": 0.4666666666666666,
      "mean_trades": 5.0
    }
  },
  "stochastic": {
    "v0": {
      "n": 87,
      "mean_pnl": -116.56193744387582,
      "mean_dd": 775.6488317422102,
      "mean_wr": 0.6165478180941886,
      "mean_trades": 79.7816091954023
    },
    "v1": {
      "n": 45,
      "mean_pnl": -32.93999728732644,
      "mean_dd": 503.03682694227433,
      "mean_wr": 0.37902841432924006,
      "mean_trades": 14.088888888888889
    },
    "v2": {
      "n": 72,
      "mean_pnl": 40.345784623887674,
      "mean_dd": 143.58069269816085,
      "mean_wr": 0.39815823925247723,
      "mean_trades": 22.444444444444443
    }
  },
  "adx_di": {
    "v0": {
      "n": 91,
      "mean_pnl": 166.99241787485036,
      "mean_dd": 677.3227964645217,
      "mean_wr": 0.37521250066139183,
      "mean_trades": 59.84615384615385
    },
    "v1": {
      "n": 82,
      "mean_pnl": 3.471233190025168,
      "mean_dd": 658.239925590701,
      "mean_wr": 0.3593311391869352,
      "mean_trades": 26.78048780487805
    },
    "v2": {
      "n": 86,
      "mean_pnl": -1.477756012672315,
      "mean_dd": 252.02767198003718,
      "mean_wr": 0.3407541701327145,
      "mean_trades": 44.5
    }
  },
  "donchian": {
    "v0": {
      "n": 90,
      "mean_pnl": 328.78725010850707,
      "mean_dd": 508.6733854736328,
      "mean_wr": 0.37365037669020074,
      "mean_trades": 88.74444444444444
    },
    "v1": {
      "n": 87,
      "mean_pnl": 277.0242475642064,
      "mean_dd": 482.5649764614761,
      "mean_wr": 0.37136490371954417,
      "mean_trades": 86.19540229885058
    },
    "v2": {
      "n": 96,
      "mean_pnl": 383.7328725967407,
      "mean_dd": 439.9223057047525,
      "mean_wr": 0.38792017089154096,
      "mean_trades": 167.5
    }
  },
  "keltner": {
    "v0": {
      "n": 92,
      "mean_pnl": 204.3510931794536,
      "mean_dd": 562.4293628354282,
      "mean_wr": 0.3601744506942806,
      "mean_trades": 79.66304347826087
    },
    "v1": {
      "n": 92,
      "mean_pnl": 237.80894035803732,
      "mean_dd": 567.4497467677905,
      "mean_wr": 0.3596365887233556,
      "mean_trades": 77.71739130434783
    },
    "v2": {
      "n": 96,
      "mean_pnl": 340.01148306783057,
      "mean_dd": 445.5776354039511,
      "mean_wr": 0.38261156387497625,
      "mean_trades": 147.26041666666666
    }
  },
  "cci": {
    "v0": {
      "n": 88,
      "mean_pnl": -359.90439267800065,
      "mean_dd": 764.6235243225095,
      "mean_wr": 0.6038589570636748,
      "mean_trades": 104.36363636363636
    },
    "v1": {
      "n": 55,
      "mean_pnl": 104.01063373579503,
      "mean_dd": 469.4286848632812,
      "mean_wr": 0.39767265216957437,
      "mean_trades": 23.145454545454545
    },
    "v2": {
      "n": 77,
      "mean_pnl": 12.812324827515972,
      "mean_dd": 153.17446255453524,
      "mean_wr": 0.38494256261469456,
      "mean_trades": 36.03896103896104
    }
  },
  "dual_sma_rsi": {
    "v0": {
      "n": 84,
      "mean_pnl": 314.11361806815046,
      "mean_dd": 465.7773988240558,
      "mean_wr": 0.361420605953992,
      "mean_trades": 67.55952380952381
    },
    "v1": {
      "n": 83,
      "mean_pnl": 316.38876844585405,
      "mean_dd": 461.77140355857,
      "mean_wr": 0.3651718789662717,
      "mean_trades": 58.13253012048193
    },
    "v2": {
      "n": 84,
      "mean_pnl": 177.49183697509775,
      "mean_dd": 221.7338824782598,
      "mean_wr": 0.38049924785691264,
      "mean_trades": 71.57142857142857
    }
  },
  "roc_momentum": {
    "v0": {
      "n": 96,
      "mean_pnl": 207.9844324035656,
      "mean_dd": 624.8530913848871,
      "mean_wr": 0.33017717143496966,
      "mean_trades": 586.7916666666666
    },
    "v1": {
      "n": 87,
      "mean_pnl": 221.24137148100698,
      "mean_dd": 495.78323627761307,
      "mean_wr": 0.26651960985367806,
      "mean_trades": 121.03448275862068
    },
    "v2": {
      "n": 94,
      "mean_pnl": 321.41306932035377,
      "mean_dd": 375.7552015147108,
      "mean_wr": 0.34412352581381656,
      "mean_trades": 182.4255319148936
    }
  }
}
```

### Verdicts (sample / full in results/variant_summary.json)
```json
[
  {
    "family": "supertrend_rsi",
    "from": "v0",
    "to": "v1",
    "verdict": "better",
    "agg_before": {
      "n": 81,
      "mean_pnl": -187.71390115921574,
      "mean_dd": 727.1051182725695,
      "mean_wr": 0.41428084680862054,
      "mean_trades": 62.77777777777778
    },
    "agg_after": {
      "n": 81,
      "mean_pnl": -111.34674355890711,
      "mean_dd": 696.706280074508,
      "mean_wr": 0.3842713786669639,
      "mean_trades": 51.79012345679013
    }
  },
  {
    "family": "supertrend_rsi",
    "from": "v1",
    "to": "v2",
    "verdict": "better",
    "agg_before": {
      "n": 81,
      "mean_pnl": -111.34674355890711,
      "mean_dd": 696.706280074508,
      "mean_wr": 0.3842713786669639,
      "mean_trades": 51.79012345679013
    },
    "agg_after": {
      "n": 86,
      "mean_pnl": -28.35370481979021,
      "mean_dd": 337.14371507085747,
      "mean_wr": 0.36238520215604786,
      "mean_trades": 91.40697674418605
    }
  },
  {
    "family": "ema_cross",
    "from": "v0",
    "to": "v1",
    "verdict": "worse",
    "agg_before": {
      "n": 96,
      "mean_pnl": 392.89406165313693,
      "mean_dd": 503.9950361531576,
      "mean_wr": 0.30014117692851544,
      "mean_trades": 169.64583333333334
    },
    "agg_after": {
      "n": 93,
      "mean_pnl": 308.78816740958894,
      "mean_dd": 534.8472466817877,
      "mean_wr": 0.2966461833074067,
      "mean_trades": 108.88172043010752
    }
  },
  {
    "family": "ema_cross",
    "from": "v1",
    "to": "v2",
    "verdict": "better",
    "agg_before": {
      "n": 93,
      "mean_pnl": 308.78816740958894,
      "mean_dd": 534.8472466817877,
      "mean_wr": 0.2966461833074067,
      "mean_trades": 108.88172043010752
    },
    "agg_after": {
      "n": 96,
      "mean_pnl": 309.057531117757,
      "mean_dd": 332.9127105738323,
      "mean_wr": 0.3616792442726629,
      "mean_trades": 128.21875
    }
  },
  {
    "family": "macd_cross",
    "from": "v0",
    "to": "v1",
    "verdict": "better",
    "agg_before": {
      "n": 96,
      "mean_pnl": 147.71122749582983,
      "mean_dd": 621.0862818298334,
      "mean_wr": 0.3487575635219266,
      "mean_trades": 303.5208333333333
    },
    "agg_after": {
      "n": 87,
      "mean_pnl": 217.7236330426096,
      "mean_dd": 547.1013383761001,
      "mean_wr": 0.28068511282698777,
      "mean_trades": 75.22988505747126
    }
  },
  {
    "family": "macd_cross",
    "from": "v1",
    "to": "v2",
    "verdict": "better",
    "agg_before": {
      "n": 87,
      "mean_pnl": 217.7236330426096,
      "mean_dd": 547.1013383761001,
      "mean_wr": 0.28068511282698777,
      "mean_trades": 75.22988505747126
    },
    "agg_after": {
      "n": 95,
      "mean_pnl": 340.5738864694698,
      "mean_dd": 302.2495164704975,
      "mean_wr": 0.36738844338641585,
      "mean_trades": 127.09473684210526
    }
  },
  {
    "family": "bb_mean_rev",
    "from": "v0",
    "to": "v1",
    "verdict": "better",
    "agg_before": {
      "n": 87,
      "mean_pnl": -307.90736759440085,
      "mean_dd": 874.0307524470186,
      "mean_wr": 0.6070011751190254,
      "mean_trades": 92.58620689655173
    },
    "agg_after": {
      "n": 54,
      "mean_pnl": 73.13623034215878,
      "mean_dd": 415.6729532606337,
      "mean_wr": 0.43413827614622924,
      "mean_trades": 15.148148148148149
    }
  },
  {
    "family": "bb_mean_rev",
    "from": "v1",
    "to": "v2",
    "verdict": "mixed",
    "agg_before": {
      "n": 54,
      "mean_pnl": 73.13623034215878,
      "mean_dd": 415.6729532606337,
      "mean_wr": 0.43413827614622924,
      "mean_trades": 15.148148148148149
    },
    "agg_after": {
      "n": 72,
      "mean_pnl": -4.394303856743729,
      "mean_dd": 132.64479437255855,
      "mean_wr": 0.3808122067533777,
      "mean_trades": 27.208333333333332
    }
  },
  {
    "family": "stochastic",
    "from": "v0",
    "to": "v1",
    "verdict": "better",
    "agg_before": {
      "n": 87,
      "mean_pnl": -116.56193744387582,
      "mean_dd": 775.6488317422102,
      "mean_wr": 0.6165478180941886,
      "mean_trades": 79.7816091954023
    },
    "agg_after": {
      "n": 45,
      "mean_pnl": -32.93999728732644,
      "mean_dd": 503.03682694227433,
      "mean_wr": 0.37902841432924006,
      "mean_trades": 14.088888888888889
    }
  },
  {
    "family": "stochastic",
    "from": "v1",
    "to": "v2",
    "verdict": "better",
    "agg_before": {
      "n": 45,
      "mean_pnl": -32.93999728732644,
      "mean_dd": 503.03682694227433,
      "mean_wr": 0.37902841432924006,
      "mean_trades": 14.088888888888889
    },
    "agg_after": {
      "n": 72,
      "mean_pnl": 40.345784623887674,
      "mean_dd": 143.58069269816085,
      "mean_wr": 0.39815823925247723,
      "mean_trades": 22.444444444444443
    }
  },
  {
    "family": "adx_di",
    "from": "v0",
    "to": "v1",
    "verdict": "mixed",
    "agg_before": {
      "n": 91,
      "mean_pnl": 166.99241787485036,
      "mean_dd": 677.3227964645217,
      "mean_wr": 0.37521250066139183,
      "mean_trades": 59.84615384615385
    },
    "agg_after": {
      "n": 82,
      "mean_pnl": 3.471233190025168,
      "mean_dd": 658.239925590701,
      "mean_wr": 0.3593311391869352,
      "mean_trades": 26.78048780487805
    }
  },
  {
    "family": "adx_di",
    "from": "v1",
    "to": "v2",
    "verdict": "mixed",
    "agg_before": {
      "n": 82,
      "mean_pnl": 3.471233190025168,
      "mean_dd": 658.239925590701,
      "mean_wr": 0.3593311391869352,
      "mean_trades": 26.78048780487805
    },
    "agg_after": {
      "n": 86,
      "mean_pnl": -1.477756012672315,
      "mean_dd": 252.02767198003718,
      "mean_wr": 0.3407541701327145,
      "mean_trades": 44.5
    }
  },
  {
    "family": "donchian",
    "from": "v0",
    "to": "v1",
    "verdict": "mixed",
    "agg_before": {
      "n": 90,
      "mean_pnl": 328.78725010850707,
      "mean_dd": 508.6733854736328,
      "mean_wr": 0.37365037669020074,
      "mean_trades": 88.74444444444444
    },
    "agg_after": {
      "n": 87,
      "mean_pnl": 277.0242475642064,
      "mean_dd": 482.5649764614761,
      "mean_wr": 0.37136490371954417,
      "mean_trades": 86.19540229885058
    }
  },
  {
    "family": "donchian",
    "from": "v1",
    "to": "v2",
    "verdict": "better",
    "agg_before": {
      "n": 87,
      "mean_pnl": 277.0242475642064,
      "mean_dd": 482.5649764614761,
      "mean_wr": 0.37136490371954417,
      "mean_trades": 86.19540229885058
    },
    "agg_after": {
      "n": 96,
      "mean_pnl": 383.7328725967407,
      "mean_dd": 439.9223057047525,
      "mean_wr": 0.38792017089154096,
      "mean_trades": 167.5
    }
  },
  {
    "family": "keltner",
    "from": "v0",
    "to": "v1",
    "verdict": "better",
    "agg_before": {
      "n": 92,
      "mean_pnl": 204.3510931794536,
      "mean_dd": 562.4293628354282,
      "mean_wr": 0.3601744506942806,
      "mean_trades": 79.66304347826087
    },
    "agg_after": {
      "n": 92,
      "mean_pnl": 237.80894035803732,
      "mean_dd": 567.4497467677905,
      "mean_wr": 0.3596365887233556,
      "mean_trades": 77.71739130434783
    }
  },
  {
    "family": "keltner",
    "from": "v1",
    "to": "v2",
    "verdict": "better",
    "agg_before": {
      "n": 92,
      "mean_pnl": 237.80894035803732,
      "mean_dd": 567.4497467677905,
      "mean_wr": 0.3596365887233556,
      "mean_trades": 77.71739130434783
    },
    "agg_after": {
      "n": 96,
      "mean_pnl": 340.01148306783057,
      "mean_dd": 445.5776354039511,
      "mean_wr": 0.38261156387497625,
      "mean_trades": 147.26041666666666
    }
  },
  {
    "family": "cci",
    "from": "v0",
    "to": "v1",
    "verdict": "better",
    "agg_before": {
      "n": 88,
      "mean_pnl": -359.90439267800065,
      "mean_dd": 764.6235243225095,
      "mean_wr": 0.6038589570636748,
      "mean_trades": 104.36363636363636
    },
    "agg_after": {
      "n": 55,
      "mean_pnl": 104.01063373579503,
      "mean_dd": 469.4286848632812,
      "mean_wr": 0.39767265216957437,
      "mean_trades": 23.145454545454545
    }
  },
  {
    "family": "cci",
    "from": "v1",
    "to": "v2",
    "verdict": "mixed",
    "agg_before": {
      "n": 55,
      "mean_pnl": 104.01063373579503,
      "mean_dd": 469.4286848632812,
      "mean_wr": 0.39767265216957437,
      "mean_trades": 23.145454545454545
    },
    "agg_after": {
      "n": 77,
      "mean_pnl": 12.812324827515972,
      "mean_dd": 153.17446255453524,
      "mean_wr": 0.38494256261469456,
      "mean_trades": 36.03896103896104
    }
  },
  {
    "family": "dual_sma_rsi",
    "from": "v0",
    "to": "v1",
    "verdict": "better",
    "agg_before": {
      "n": 84,
      "mean_pnl": 314.11361806815046,
      "mean_dd": 465.7773988240558,
      "mean_wr": 0.361420605953992,
      "mean_trades": 67.55952380952381
    },
    "agg_after": {
      "n": 83,
      "mean_pnl": 316.38876844585405,
      "mean_dd": 461.77140355857,
      "mean_wr": 0.3651718789662717,
      "mean_trades": 58.13253012048193
    }
  },
  {
    "family": "dual_sma_rsi",
    "from": "v1",
    "to": "v2",
    "verdict": "mixed",
    "agg_before": {
      "n": 83,
      "mean_pnl": 316.38876844585405,
      "mean_dd": 461.77140355857,
      "mean_wr": 0.3651718789662717,
      "mean_trades": 58.13253012048193
    },
    "agg_after": {
      "n": 84,
      "mean_pnl": 177.49183697509775,
      "mean_dd": 221.7338824782598,
      "mean_wr": 0.38049924785691264,
      "mean_trades": 71.57142857142857
    }
  },
  {
    "family": "roc_momentum",
    "from": "v0",
    "to": "v1",
    "verdict": "better",
    "agg_before": {
      "n": 96,
      "mean_pnl": 207.9844324035656,
      "mean_dd": 624.8530913848871,
      "mean_wr": 0.33017717143496966,
      "mean_trades": 586.7916666666666
    },
    "agg_after": {
      "n": 87,
      "mean_pnl": 221.24137148100698,
      "mean_dd": 495.78323627761307,
      "mean_wr": 0.26651960985367806,
      "mean_trades": 121.03448275862068
    }
  },
  {
    "family": "roc_momentum",
    "from": "v1",
    "to": "v2",
    "verdict": "better",
    "agg_before": {
      "n": 87,
      "mean_pnl": 221.24137148100698,
      "mean_dd": 495.78323627761307,
      "mean_wr": 0.26651960985367806,
      "mean_trades": 121.03448275862068
    },
    "agg_after": {
      "n": 94,
      "mean_pnl": 321.41306932035377,
      "mean_dd": 375.7552015147108,
      "mean_wr": 0.34412352581381656,
      "mean_trades": 182.4255319148936
    }
  }
]
```

## Артефакты
- `models/model.joblib`, `models/feature_names.json`
- `results/script_variants_backtest.json`, `results/variant_summary.json`
- `data/processed/features_v2.csv`
