# C10 multi-symbol expand (§7F)

- Symbols: SBER, GAZP, LKOH, ROSN, GMKN, NVTK
- Pairs: 798 · better: 470
- LOO acc=0.723 AUC=0.7887065386611314
- LOSO: {"SBER": {"accuracy": 0.6165413533834586, "auc": 0.7023310023310023, "n": 133}, "GAZP": {"accuracy": 0.7142857142857143, "auc": 0.7236516575952499, "n": 133}, "LKOH": {"accuracy": 0.6541353383458647, "auc": 0.7109068627450981, "n": 133}, "ROSN": {"accuracy": 0.7368421052631579, "auc": 0.7934035730645901, "n": 133}, "GMKN": {"accuracy": 0.6842105263157895, "auc": 0.7560919540229885, "n": 133}, "NVTK": {"accuracy": 0.6917293233082706, "auc": 0.8176229508196722, "n": 133}}
- Cross-stable: 46 · promoted 29p-*: 46

## Per symbol
{
  "SBER": {
    "n": 133,
    "better": 78,
    "mean_delta": 29.948579432817652
  },
  "GAZP": {
    "n": 133,
    "better": 86,
    "mean_delta": 40.67252273396886
  },
  "LKOH": {
    "n": 133,
    "better": 85,
    "mean_delta": 869.5889923994791
  },
  "ROSN": {
    "n": 133,
    "better": 74,
    "mean_delta": 52.370701422287695
  },
  "GMKN": {
    "n": 133,
    "better": 75,
    "mean_delta": 15.034515824013567
  },
  "NVTK": {
    "n": 133,
    "better": 72,
    "mean_delta": 107.01799944692048
  }
}

## Kind stats
{
  "add_block_ema": {
    "n": 162,
    "wins": 98,
    "sum_delta": 38005.20883999992,
    "mean_delta": 234.60005456790074,
    "winrate": 0.6049382716049383
  },
  "change_period_067": {
    "n": 162,
    "wins": 93,
    "sum_delta": 11820.833009503625,
    "mean_delta": 72.96810499693596,
    "winrate": 0.5740740740740741
  },
  "change_period_15x": {
    "n": 162,
    "wins": 81,
    "sum_delta": 14669.931243272085,
    "mean_delta": 90.55513113130917,
    "winrate": 0.5
  },
  "add_block_sma200": {
    "n": 162,
    "wins": 126,
    "sum_delta": 74225.89676111208,
    "mean_delta": 458.1845479080992,
    "winrate": 0.7777777777777778
  },
  "add_block_adx": {
    "n": 150,
    "wins": 72,
    "sum_delta": 9524.360543624183,
    "mean_delta": 63.49573695749456,
    "winrate": 0.48
  }
}

## Top cross promotes
- `30p-23-tema-cross-10-30-ls__sma200.italgo` meanΔ=+1346.8 on GMKN,LKOH,NVTK,ROSN,SBER
- `30p-04-macd-stoch-long-short__sma200.italgo` meanΔ=+1262.8 on GAZP,GMKN,LKOH,NVTK,ROSN
- `30p-25-momentum-cross-0-ls__sma200.italgo` meanΔ=+1215.5 on GMKN,LKOH,NVTK,ROSN,SBER
- `30p-23-tema-cross-10-30-ls__ema50.italgo` meanΔ=+1187.6 on LKOH,NVTK,ROSN,SBER
- `30p-07-supertrend-di-adx-stack__sma200.italgo` meanΔ=+1115.4 on GAZP,GMKN,LKOH,NVTK,ROSN,SBER
- `30p-23-tema-cross-10-30-ls__period067.italgo` meanΔ=+992.7 on LKOH,NVTK,ROSN,SBER
- `30p-04-macd-stoch-long-short__ema50.italgo` meanΔ=+923.5 on GMKN,LKOH,ROSN
- `30p-24-rsi-cross-50-ls__sma200.italgo` meanΔ=+918.0 on GAZP,GMKN,LKOH,NVTK,ROSN,SBER
- `30p-07-supertrend-di-adx-stack__period15x.italgo` meanΔ=+865.5 on LKOH,NVTK,ROSN,SBER
- `30p-25-momentum-cross-0-ls__ema50.italgo` meanΔ=+810.1 on GMKN,LKOH,NVTK,ROSN,SBER
- `30p-12-dema-cross-12-26__sma200.italgo` meanΔ=+793.7 on GMKN,LKOH,ROSN
- `30p-12-dema-cross-12-26__ema50.italgo` meanΔ=+746.1 on GMKN,LKOH,NVTK,ROSN
- `30p-11-tema-cross-10-30__sma200.italgo` meanΔ=+679.1 on GMKN,LKOH,NVTK,ROSN,SBER
- `30p-22-ema-cross-9-21-ls__sma200.italgo` meanΔ=+644.8 on GAZP,GMKN,LKOH,NVTK,ROSN
- `30p-06b-rsi-no-session__adx25.italgo` meanΔ=+610.2 on GAZP,GMKN,LKOH
