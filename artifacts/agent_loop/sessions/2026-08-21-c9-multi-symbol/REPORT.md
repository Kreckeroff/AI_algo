# C9 multi-symbol (§7F)

- Symbols: SBER, GAZP, LKOH
- Pairs: 399 · better: 249
- LOO acc=0.704 AUC=0.7137884872824631
- LOSO: {"SBER": {"accuracy": 0.6691729323308271, "auc": 0.6918414918414919, "n": 133}, "GAZP": {"accuracy": 0.6240601503759399, "auc": 0.6036615536862939, "n": 133}, "LKOH": {"accuracy": 0.6992481203007519, "auc": 0.7002450980392158, "n": 133}}
- Cross-stable: 44 · promoted 29p-*: 44

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
  }
}

## Kind stats
{
  "add_block_ema": {
    "n": 81,
    "wins": 50,
    "sum_delta": 20671.622538999945,
    "mean_delta": 255.2052165308635,
    "winrate": 0.6172839506172839
  },
  "change_period_067": {
    "n": 81,
    "wins": 49,
    "sum_delta": 8625.426775415744,
    "mean_delta": 106.48675031377462,
    "winrate": 0.6049382716049383
  },
  "change_period_15x": {
    "n": 81,
    "wins": 51,
    "sum_delta": 17987.252117754957,
    "mean_delta": 222.06484095993775,
    "winrate": 0.6296296296296297
  },
  "add_block_sma200": {
    "n": 81,
    "wins": 58,
    "sum_delta": 58668.10084563921,
    "mean_delta": 724.2975413041878,
    "winrate": 0.7160493827160493
  },
  "add_block_adx": {
    "n": 75,
    "wins": 41,
    "sum_delta": 19095.540299503504,
    "mean_delta": 254.60720399338004,
    "winrate": 0.5466666666666666
  }
}

## Top cross promotes
- `29p-04-macd-stoch-long-short__sma200.italgo` meanΔ=+2279.6 on GAZP,LKOH
- `29p-23-tema-cross-10-30-ls__sma200.italgo` meanΔ=+2185.2 on LKOH,SBER
- `29p-07-supertrend-di-adx-stack__sma200.italgo` meanΔ=+1761.9 on GAZP,LKOH,SBER
- `29p-25-momentum-cross-0-ls__sma200.italgo` meanΔ=+1711.7 on LKOH,SBER
- `29p-23-tema-cross-10-30-ls__period067.italgo` meanΔ=+1564.7 on LKOH,SBER
- `29p-23-tema-cross-10-30-ls__ema50.italgo` meanΔ=+1558.9 on LKOH,SBER
- `29p-24-rsi-cross-50-ls__sma200.italgo` meanΔ=+1439.9 on GAZP,LKOH,SBER
- `29p-07-supertrend-di-adx-stack__period15x.italgo` meanΔ=+1369.3 on LKOH,SBER
- `29p-21-sma-cross-20-50-ls__adx25.italgo` meanΔ=+1315.4 on GAZP,LKOH,SBER
- `29p-06b-rsi-no-session__adx25.italgo` meanΔ=+1175.3 on GAZP,LKOH
- `29p-04-macd-stoch-long-short__period15x.italgo` meanΔ=+1149.3 on LKOH,SBER
- `29p-04-macd-stoch-long-short__period067.italgo` meanΔ=+1111.4 on LKOH,SBER
- `29p-20-donchian-55__adx25.italgo` meanΔ=+1107.8 on LKOH,SBER
- `29p-22-ema-cross-9-21-ls__sma200.italgo` meanΔ=+1107.2 on GAZP,LKOH
- `29p-11-tema-cross-10-30__sma200.italgo` meanΔ=+1092.6 on LKOH,SBER
