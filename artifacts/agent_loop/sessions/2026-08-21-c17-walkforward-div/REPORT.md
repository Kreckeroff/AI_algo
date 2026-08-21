# C17 walk-forward + §7H div features

- Full-window pairs: 25452 · better: 6596 (25.9%)
- Full CV: acc=0.7997013987112997 AUC=0.8462960470186351
- Year-pooled CV (1d+1h): acc=0.7809008533474092 AUC=0.8235399296554509
- Promoted 37p-*: 27

## Walk-forward (1d+1h)
- 2023: OOS acc=0.846 AUC=0.761 (train 4231 → test 3608)
- 2024: OOS acc=0.772 AUC=0.759 (train 7839 → test 6352)
- 2025: OOS acc=0.758 AUC=0.774 (train 14191 → test 6411)
- 2026: OOS acc=0.722 AUC=0.754 (train 20602 → test 6363)

## near_ex_div × side
{
  "near=0|side=long_only": {
    "n": 4450,
    "better": 1445,
    "better_rate": 0.32471910112359553
  },
  "near=0|side=long_short": {
    "n": 1850,
    "better": 537,
    "better_rate": 0.29027027027027025
  },
  "near=1|side=long_only": {
    "n": 9256,
    "better": 2460,
    "better_rate": 0.2657735522904062
  },
  "near=1|side=long_short": {
    "n": 3848,
    "better": 1068,
    "better_rate": 0.27754677754677753
  }
}
