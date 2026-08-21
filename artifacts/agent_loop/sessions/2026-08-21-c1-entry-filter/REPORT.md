# Session report — C1 Entry × Filter × periods

Дата: 2026-08-21T08:50:43.872055+00:00

## Цель
C1 (§7A): entry × filter (ST/ADX/MA/Donchian mid…), periods ∈ [1,200].
Ранжирование (§7C): тренд → PnL first; WR вторичен.

- ТФ: 15m, 1h, 1d
- rows: 12600, cells: 283

## Top-20 (score)
```json
[
  {
    "entry": "roc_momentum|20",
    "filter": "ema|50",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 435.2704339715861,
    "median_pnl": 103.47776184082042,
    "mean_wr": 0.34368742822198195,
    "mean_dd": 328.2287583705357,
    "score": 103.47776184082042
  },
  {
    "entry": "roc_momentum|20",
    "filter": "none",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 495.1415018601178,
    "median_pnl": 95.81999999999866,
    "mean_wr": 0.3476329039741374,
    "mean_dd": 366.4873448428202,
    "score": 95.81999999999866
  },
  {
    "entry": "keltner|20",
    "filter": "ema|100",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 479.34739070638005,
    "median_pnl": 92.52500000000012,
    "mean_wr": 0.4048400017186376,
    "mean_dd": 468.82141764322904,
    "score": 92.52500000000012
  },
  {
    "entry": "roc_momentum|20",
    "filter": "ema|200",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 271.98698535156194,
    "median_pnl": 90.19999999999982,
    "mean_wr": 0.3773272147875416,
    "mean_dd": 385.201068371001,
    "score": 90.19999999999982
  },
  {
    "entry": "donchian|10",
    "filter": "ema|100",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 541.3726509951637,
    "median_pnl": 83.42500000000013,
    "mean_wr": 0.38901907933260926,
    "mean_dd": 488.7420231526693,
    "score": 83.42500000000013
  },
  {
    "entry": "keltner|20",
    "filter": "donchian_mid|20",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 482.59882343982514,
    "median_pnl": 82.4699999999909,
    "mean_wr": 0.38818696176288287,
    "mean_dd": 463.3275216820126,
    "score": 82.4699999999909
  },
  {
    "entry": "roc_momentum|20",
    "filter": "sma|50",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 402.1731266624808,
    "median_pnl": 82.07499999999993,
    "mean_wr": 0.3463523389953875,
    "mean_dd": 297.63564074707074,
    "score": 82.07499999999993
  },
  {
    "entry": "keltner|20",
    "filter": "sma|50",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 526.1256252092634,
    "median_pnl": 80.42500000000001,
    "mean_wr": 0.39571905272263214,
    "mean_dd": 470.2516834193638,
    "score": 80.42500000000001
  },
  {
    "entry": "ema_cross|9_21",
    "filter": "ema|50",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 380.23684776669444,
    "median_pnl": 74.94500000000028,
    "mean_wr": 0.37076617748661994,
    "mean_dd": 337.6229584960937,
    "score": 74.94500000000028
  },
  {
    "entry": "roc_momentum|10",
    "filter": "sma|50",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 334.4676003011067,
    "median_pnl": 72.32499999999987,
    "mean_wr": 0.3570664940254745,
    "mean_dd": 432.5408778599333,
    "score": 72.32499999999987
  },
  {
    "entry": "donchian|20",
    "filter": "ema|100",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 425.13305192057277,
    "median_pnl": 72.09999999999937,
    "mean_wr": 0.3923296489368556,
    "mean_dd": 476.03925061616445,
    "score": 72.09999999999937
  },
  {
    "entry": "roc_momentum|20",
    "filter": "ema|100",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 336.15155247860804,
    "median_pnl": 69.24000000000004,
    "mean_wr": 0.3617375603887126,
    "mean_dd": 332.8621646844774,
    "score": 69.24000000000004
  },
  {
    "entry": "roc_momentum|10",
    "filter": "supertrend|7x2",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 280.01476619466166,
    "median_pnl": 68.90000000000008,
    "mean_wr": 0.4041903791487295,
    "mean_dd": 503.00328226143955,
    "score": 68.90000000000008
  },
  {
    "entry": "keltner|20",
    "filter": "ema|50",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 530.3324353724889,
    "median_pnl": 68.85000000000028,
    "mean_wr": 0.3929068032457304,
    "mean_dd": 477.321865234375,
    "score": 68.85000000000028
  },
  {
    "entry": "keltner|20",
    "filter": "donchian_mid|55",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 482.6753896658761,
    "median_pnl": 68.15000000000038,
    "mean_wr": 0.40152234117139024,
    "mean_dd": 486.0929808640253,
    "score": 68.15000000000038
  },
  {
    "entry": "roc_momentum|10",
    "filter": "ema|20",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 399.71945846121645,
    "median_pnl": 62.72265625000014,
    "mean_wr": 0.3196191529193729,
    "mean_dd": 476.2229461611795,
    "score": 62.72265625000014
  },
  {
    "entry": "keltner|20",
    "filter": "none",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 515.902626453218,
    "median_pnl": 61.650000000000176,
    "mean_wr": 0.3890645298377426,
    "mean_dd": 461.94490821475074,
    "score": 61.650000000000176
  },
  {
    "entry": "keltner|20",
    "filter": "ema|20",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 515.902626453218,
    "median_pnl": 61.650000000000176,
    "mean_wr": 0.3890645298377426,
    "mean_dd": 461.94490821475074,
    "score": 61.650000000000176
  },
  {
    "entry": "ema_cross|12_26",
    "filter": "sma|50",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 394.46952266438757,
    "median_pnl": 60.37500000000005,
    "mean_wr": 0.38359258880705743,
    "mean_dd": 343.5500147298181,
    "score": 60.37500000000005
  },
  {
    "entry": "keltner|20",
    "filter": "ema|200",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 447.70934602864594,
    "median_pnl": 59.88860473632816,
    "mean_wr": 0.4075903994866043,
    "mean_dd": 424.91669056338355,
    "score": 59.88860473632816
  }
]
```

## Лучший фильтр на семейство
```json
{
  "roc_momentum": {
    "entry": "roc_momentum|20",
    "filter": "ema|50",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 435.2704339715861,
    "median_pnl": 103.47776184082042,
    "mean_wr": 0.34368742822198195,
    "mean_dd": 328.2287583705357,
    "score": 103.47776184082042
  },
  "keltner": {
    "entry": "keltner|20",
    "filter": "ema|100",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 479.34739070638005,
    "median_pnl": 92.52500000000012,
    "mean_wr": 0.4048400017186376,
    "mean_dd": 468.82141764322904,
    "score": 92.52500000000012
  },
  "donchian": {
    "entry": "donchian|10",
    "filter": "ema|100",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 541.3726509951637,
    "median_pnl": 83.42500000000013,
    "mean_wr": 0.38901907933260926,
    "mean_dd": 488.7420231526693,
    "score": 83.42500000000013
  },
  "ema_cross": {
    "entry": "ema_cross|9_21",
    "filter": "ema|50",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 380.23684776669444,
    "median_pnl": 74.94500000000028,
    "mean_wr": 0.37076617748661994,
    "mean_dd": 337.6229584960937,
    "score": 74.94500000000028
  },
  "macd_cross": {
    "entry": "macd_cross|12_26_9",
    "filter": "supertrend|7x2",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 264.6253276134671,
    "median_pnl": 43.77499999999962,
    "mean_wr": 0.4167604562295121,
    "mean_dd": 345.21999923851365,
    "score": 43.77499999999962
  },
  "cci": {
    "entry": "cci|14",
    "filter": "sma|50",
    "regime": "other",
    "n": 42,
    "mean_pnl": 21.61082641020254,
    "median_pnl": 36.920000000000044,
    "mean_wr": 0.3856476064472099,
    "mean_dd": 237.28898458426335,
    "score": 33.70238032236054
  },
  "dual_sma_rsi": {
    "entry": "dual_sma_rsi|20_50_rsi14",
    "filter": "supertrend|7x2",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 359.4670562046595,
    "median_pnl": 27.640000000000022,
    "mean_wr": 0.39156094693076055,
    "mean_dd": 269.39696819777714,
    "score": 27.640000000000022
  },
  "rsi_ob_os": {
    "entry": "rsi_ob_os|21",
    "filter": "ema|20",
    "regime": "other",
    "n": 1,
    "mean_pnl": 0.9909999999999979,
    "median_pnl": 0.9909999999999979,
    "mean_wr": 0.875,
    "mean_dd": 0.16900000000000048,
    "score": 22.241
  },
  "stochastic": {
    "entry": "stochastic|14_3",
    "filter": "ema|20",
    "regime": "other",
    "n": 3,
    "mean_pnl": 20.549999999999994,
    "median_pnl": 17.050000000000068,
    "mean_wr": 0.4444444444444444,
    "mean_dd": 25.783333333333378,
    "score": 16.77222222222229
  },
  "adx_di": {
    "entry": "adx_di|14",
    "filter": "ema|200",
    "regime": "trend",
    "n": 42,
    "mean_pnl": 125.4268729654949,
    "median_pnl": 12.414999999999964,
    "mean_wr": 0.37725151134316853,
    "mean_dd": 202.88956418573287,
    "score": 12.414999999999964
  },
  "bb_mean_rev": {
    "entry": "bb_mean_rev|20",
    "filter": "ema|20",
    "regime": "other",
    "n": 23,
    "mean_pnl": 23.287695652173905,
    "median_pnl": 7.3599999999999,
    "mean_wr": 0.42044441066180205,
    "mean_dd": 62.029043478260796,
    "score": 5.882220533090002
  },
  "supertrend_rsi": {
    "entry": "supertrend_rsi|st10_rsi14",
    "filter": "adx|20",
    "regime": "trend",
    "n": 39,
    "mean_pnl": -3.7457638659356243,
    "median_pnl": 5.819999999999979,
    "mean_wr": 0.3705568398329053,
    "mean_dd": 207.457239777394,
    "score": 5.819999999999979
  }
}
```

## Топ lift фильтра vs none
```json
[
  {
    "entry": "bb_mean_rev|20",
    "filter": "ema|20",
    "regime": "other",
    "median_pnl": 7.3599999999999,
    "mean_wr": 0.42044441066180205,
    "n": 23,
    "vs_none": 91.13500000000019
  },
  {
    "entry": "bb_mean_rev|20",
    "filter": "adx|20",
    "regime": "other",
    "median_pnl": 3.8999999999999773,
    "mean_wr": 0.44155200859746313,
    "n": 22,
    "vs_none": 87.67500000000027
  },
  {
    "entry": "bb_mean_rev|20",
    "filter": "ema|50",
    "regime": "other",
    "median_pnl": 1.6500000000000057,
    "mean_wr": 0.3696988088140716,
    "n": 33,
    "vs_none": 85.4250000000003
  },
  {
    "entry": "bb_mean_rev|20",
    "filter": "adx|14",
    "regime": "other",
    "median_pnl": 1.3000000000000114,
    "mean_wr": 0.43772175536881414,
    "n": 17,
    "vs_none": 85.0750000000003
  },
  {
    "entry": "bb_mean_rev|20",
    "filter": "supertrend|14x3",
    "regime": "other",
    "median_pnl": 0.8209999999999873,
    "mean_wr": 0.39442267132921355,
    "n": 34,
    "vs_none": 84.59600000000027
  },
  {
    "entry": "bb_mean_rev|20",
    "filter": "supertrend|10x3",
    "regime": "other",
    "median_pnl": 0.3379999999999974,
    "mean_wr": 0.3848319864985048,
    "n": 31,
    "vs_none": 84.11300000000028
  },
  {
    "entry": "bb_mean_rev|20",
    "filter": "sma|50",
    "regime": "other",
    "median_pnl": 0.1689999999999987,
    "mean_wr": 0.3880146041908117,
    "n": 35,
    "vs_none": 83.94400000000029
  },
  {
    "entry": "bb_mean_rev|20",
    "filter": "donchian_mid|20",
    "regime": "other",
    "median_pnl": 0.08650000000000091,
    "mean_wr": 0.3887543001803838,
    "n": 28,
    "vs_none": 83.86150000000029
  },
  {
    "entry": "bb_mean_rev|20",
    "filter": "supertrend|7x2",
    "regime": "other",
    "median_pnl": 0.003999999999997783,
    "mean_wr": 0.4315934065934066,
    "n": 13,
    "vs_none": 83.77900000000028
  },
  {
    "entry": "bb_mean_rev|20",
    "filter": "ema|100",
    "regime": "other",
    "median_pnl": -0.37099999999998534,
    "mean_wr": 0.3626887853360733,
    "n": 40,
    "vs_none": 83.40400000000031
  },
  {
    "entry": "bb_mean_rev|20",
    "filter": "sma|200",
    "regime": "other",
    "median_pnl": -0.4760000000000044,
    "mean_wr": 0.37957604592170896,
    "n": 41,
    "vs_none": 83.29900000000029
  },
  {
    "entry": "bb_mean_rev|20",
    "filter": "donchian_mid|55",
    "regime": "other",
    "median_pnl": -1.8500000000001364,
    "mean_wr": 0.37548857953239506,
    "n": 39,
    "vs_none": 81.92500000000015
  },
  {
    "entry": "bb_mean_rev|20",
    "filter": "donchian_mid|10",
    "regime": "other",
    "median_pnl": -2.989105224609375,
    "mean_wr": 0.3448637751578928,
    "n": 37,
    "vs_none": 80.78589477539091
  },
  {
    "entry": "rsi_ob_os|7",
    "filter": "ema|50",
    "regime": "other",
    "median_pnl": 6.8549999999999685,
    "mean_wr": 0.37849816791659635,
    "n": 40,
    "vs_none": 80.4800000000005
  },
  {
    "entry": "bb_mean_rev|20",
    "filter": "ema|200",
    "regime": "other",
    "median_pnl": -4.189500000000004,
    "mean_wr": 0.35653637268822497,
    "n": 42,
    "vs_none": 79.58550000000028
  }
]
```
