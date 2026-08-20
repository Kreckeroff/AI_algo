from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

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
