#!/usr/bin/env python3
"""Train baseline signal model A on exported CSV (time-based split)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import accuracy_score, roc_auc_score

FEATURE_SPEC_ID = "v1-basic"
FEATURES = [
    "ret_1",
    "ret_5",
    "rsi_14",
    "atr_14",
    "ema_dist_50",
    "volume_z",
]
LABEL = "y_up"


def build_model(prefer_lgbm: bool = True, allow_fallback: bool = True):
    """Prefer LightGBM; on macOS needs Homebrew libomp (see docs/DEV_SETUP.md)."""
    if prefer_lgbm:
        try:
            import lightgbm as lgb

            return lgb.LGBMClassifier(
                n_estimators=80,
                learning_rate=0.05,
                num_leaves=15,
                subsample=0.9,
                colsample_bytree=0.9,
                random_state=42,
                verbose=-1,
            ), "lgbm"
        except Exception as exc:
            msg = str(exc)
            hint = ""
            if "libomp" in msg or "lib_lightgbm" in msg:
                hint = (
                    "\nHint (macOS): brew install libomp\n"
                    "LightGBM looks for /opt/homebrew/opt/libomp/lib/libomp.dylib\n"
                    "See docs/DEV_SETUP.md (Mac + Windows training).\n"
                )
            print("LightGBM unavailable: {e}{h}".format(e=exc, h=hint))
            if not allow_fallback:
                raise SystemExit(2) from exc
    from sklearn.ensemble import HistGradientBoostingClassifier

    print("Using HistGradientBoostingClassifier fallback")
    return (
        HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, random_state=42),
        "hgb",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument(
        "--require-lgbm",
        action="store_true",
        help="Fail if LightGBM cannot load (no sklearn fallback)",
    )
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    missing = [c for c in FEATURES + [LABEL] if c not in df.columns]
    if missing:
        raise SystemExit("missing columns: {m}".format(m=missing))

    df = df.dropna(subset=FEATURES + [LABEL]).reset_index(drop=True)
    split = int(len(df) * args.train_ratio)
    if split < 20 or len(df) - split < 10:
        raise SystemExit("not enough rows for time split")

    train, test = df.iloc[:split], df.iloc[split:]
    x_train, y_train = train[FEATURES], train[LABEL].astype(int)
    x_test, y_test = test[FEATURES], test[LABEL].astype(int)

    model, kind = build_model(prefer_lgbm=True, allow_fallback=not args.require_lgbm)
    model.fit(x_train, y_train)
    proba = model.predict_proba(x_test)[:, 1]
    pred = (proba >= 0.5).astype(int)
    acc = accuracy_score(y_test, pred)
    try:
        auc = roc_auc_score(y_test, proba)
    except ValueError:
        auc = float("nan")

    args.out.mkdir(parents=True, exist_ok=True)
    model_path = args.out / "model.joblib"
    meta_path = args.out / "feature_names.json"
    joblib.dump({"model": model, "kind": kind, "feature_schema_id": FEATURE_SPEC_ID}, model_path)
    meta_path.write_text(
        json.dumps(
            {
                "feature_schema_id": FEATURE_SPEC_ID,
                "feature_names": FEATURES,
                "model_kind": kind,
                "metrics": {"accuracy": acc, "roc_auc": auc, "n_train": len(train), "n_test": len(test)},
            },
            indent=2,
        )
        + "\n"
    )
    print("kind={kind} accuracy={acc:.4f} roc_auc={auc:.4f}".format(kind=kind, acc=acc, auc=auc))
    print("wrote", model_path)
    print("wrote", meta_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
