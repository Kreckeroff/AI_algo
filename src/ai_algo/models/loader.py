from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_ID = "signal-cpu-v1"


def _candidate_dirs(model_id: str) -> List[Path]:
    env = os.environ.get("AI_ALGO_MODEL_DIR")
    dirs: List[Path] = []
    if env:
        dirs.append(Path(env))
    dirs.append(REPO_ROOT / "models" / "artifacts" / model_id)
    dirs.append(REPO_ROOT / "tests" / "fixtures" / model_id)
    return dirs


@lru_cache(maxsize=4)
def load_signal_bundle(model_id: str = DEFAULT_MODEL_ID) -> Tuple[Any, List[str], str, str]:
    """Return model, feature_names, feature_schema_id, kind."""
    last_err = "model not found"
    for d in _candidate_dirs(model_id):
        model_path = d / "model.joblib"
        meta_path = d / "feature_names.json"
        if not model_path.exists() or not meta_path.exists():
            continue
        blob = joblib.load(model_path)
        meta = json.loads(meta_path.read_text())
        if isinstance(blob, dict) and "model" in blob:
            model = blob["model"]
            kind = blob.get("kind") or meta.get("model_kind") or "unknown"
            schema_id = blob.get("feature_schema_id") or meta["feature_schema_id"]
        else:
            model = blob
            kind = meta.get("model_kind") or "unknown"
            schema_id = meta["feature_schema_id"]
        names = list(meta["feature_names"])
        return model, names, schema_id, kind
    raise FileNotFoundError(last_err)


def predict_signal(
    feature_vector: Dict[str, float],
    model_id: Optional[str] = None,
) -> Dict[str, Any]:
    mid = model_id or DEFAULT_MODEL_ID
    model, names, schema_id, kind = load_signal_bundle(mid)
    missing = [n for n in names if n not in feature_vector]
    if missing:
        return {
            "status": "error",
            "error": {
                "code": "validation_failed",
                "message": "missing features: {m}".format(m=", ".join(missing)),
            },
            "result": {},
            "warnings": [],
        }
    row = pd.DataFrame([{n: float(feature_vector[n]) for n in names}])
    proba = float(model.predict_proba(row)[0][1])
    label = 1 if proba >= 0.5 else 0
    return {
        "status": "ok",
        "error": None,
        "warnings": [],
        "model": {"id": mid, "kind": "lgbm" if kind == "lgbm" else "rules"},
        # hgb/sklearn baselines report as rules in OpenAPI enum
        "result": {
            "p": proba,
            "label": label,
            "feature_schema_id": schema_id,
            "disclaimer": "Signal is a model score, not a promise of profit.",
        },
    }


def clear_model_cache() -> None:
    load_signal_bundle.cache_clear()
