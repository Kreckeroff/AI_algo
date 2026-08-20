from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ai_algo.domain.compare import commentary, graph_change_notes, verdict_from_diff
from ai_algo.models.loader import predict_signal

router = APIRouter(tags=["infer"])

API_VERSION = "2026-08-20"
SUPPORTED_INTENTS = {"compare_scripts", "signal"}


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
    try:
        if payload["before"].get("run_meta") and payload["after"].get("run_meta"):
            verdict, diff, warnings, suggestions = verdict_from_diff(
                before,
                after,
                payload["before"]["run_meta"],
                payload["after"]["run_meta"],
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

    graph_notes = graph_change_notes(payload.get("before", {}).get("graph"), payload.get("after", {}).get("graph"))
    text = commentary(verdict, diff)
    if graph_notes:
        text = text + " Graph changes: " + "; ".join(graph_notes) + "."
        for note in graph_notes[:2]:
            suggestions.append("Review change: " + note)

    return {
        "status": "ok",
        "error": None,
        "warnings": warnings,
        "result": {
            "verdict": verdict,
            "metrics_diff": diff,
            "graph_changes": graph_notes,
            "commentary": text,
            "suggestions": suggestions[:5],
        },
        "model": {"id": "compare-rules-v1", "kind": "rules"},
    }


def _signal(payload: dict) -> dict:
    fv = payload.get("feature_vector")
    if isinstance(fv, dict) and "values" in fv:
        values = fv["values"]
    elif isinstance(fv, dict):
        values = fv
    else:
        return {
            "status": "error",
            "error": {
                "code": "validation_failed",
                "message": "payload.feature_vector required",
            },
            "result": {},
            "warnings": [],
        }
    return predict_signal(values, model_id=payload.get("model_id"))


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
    elif body.intent == "signal":
        out = _signal(body.payload)
    else:
        out = {
            "status": "error",
            "error": {"code": "not_implemented", "message": body.intent},
            "result": {},
            "warnings": [],
        }

    return {
        "api_version": API_VERSION,
        "request_id": body.request_id,
        "status": out["status"],
        "model": out.get("model"),
        "result": out.get("result", {}),
        "warnings": out.get("warnings", []),
        "error": out.get("error"),
    }
