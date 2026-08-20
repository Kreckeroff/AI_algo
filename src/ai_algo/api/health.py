from fastapi import APIRouter

router = APIRouter(tags=["health"])

API_VERSION = "2026-08-20"


@router.get("/v1/health")
def health() -> dict:
    return {"status": "ok", "build": "0.1.0"}


@router.get("/v1/capabilities")
def capabilities() -> dict:
    return {
        "api_version": API_VERSION,
        "intents": ["compare_scripts"],
        "models": [],
        "composition": {"max_depth": 2, "whitelist": ["MA(ind)", "HTF_filter"]},
        "train": {"enabled": False, "env_only": ["dev"]},
        "ingest": True,
    }
