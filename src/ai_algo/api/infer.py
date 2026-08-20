from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ai_algo.domain.compare import commentary, verdict_from_diff

router = APIRouter(tags=["infer"])

API_VERSION = "2026-08-20"
SUPPORTED_INTENTS = {"compare_scripts"}


class ClientInfo(BaseModel):
    product: str
    app_version: str
    env: str


class InferRequest(BaseModel):
    api_version: str
    request_id: str
    client: ClientInfo
    intent: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    auth: Optional[Dict[str, Any]] = None


def _compare(payload: dict) -> dict:
    before = payload["before"]["backtest_metrics"]
    after = payload["after"]["backtest_metrics"]
    align = payload.get("align") or {}
    align_b = payload["before"].get("run_meta") or align
    align_a = payload["after"].get("run_meta") or align
    # If single align object provided, use for both; mismatch only if both sides have meta
    try:
        if payload["before"].get("run_meta") and payload["after"].get("run_meta"):
            verdict, diff, warnings, suggestions = verdict_from_diff(
                before, after, payload["before"]["run_meta"], payload["after"]["run_meta"]
            )
        else:
            verdict, diff, warnings, suggestions = verdict_from_diff(before, after)
    except ValueError as exc:
        if str(exc) == "align_mismatch":
            return {
                "status": "error",
                "error": {
                    "code": "align_mismatch",
                    "message": "before/after runs are not on the same align window",
                },
                "result": {},
                "warnings": [],
            }
        raise

    return {
        "status": "ok",
        "error": None,
        "warnings": warnings,
        "result": {
            "verdict": verdict,
            "metrics_diff": diff,
            "commentary": commentary(verdict, diff),
            "suggestions": suggestions,
        },
        "model": {"id": "compare-rules-v1", "kind": "rules"},
    }


@router.post("/v1/infer")
def infer(body: InferRequest) -> dict:
    if body.intent not in SUPPORTED_INTENTS:
        return {
            "api_version": API_VERSION,
            "request_id": body.request_id,
            "status": "error",
            "result": {},
            "warnings": [],
            "error": {
                "code": "unsupported_intent",
                "message": "Intent '{intent}' is not supported yet".format(
                    intent=body.intent
                ),
            },
        }

    if body.intent == "compare_scripts":
        out = _compare(body.payload)
        return {
            "api_version": API_VERSION,
            "request_id": body.request_id,
            "status": out["status"],
            "model": out.get("model"),
            "result": out.get("result", {}),
            "warnings": out.get("warnings", []),
            "error": out.get("error"),
        }

    return {
        "api_version": API_VERSION,
        "request_id": body.request_id,
        "status": "error",
        "result": {},
        "warnings": [],
        "error": {
            "code": "not_implemented",
            "message": "Intent '{intent}' accepted but handler not wired".format(
                intent=body.intent
            ),
        },
    }
