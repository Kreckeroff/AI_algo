from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ai_algo.domain.graph_validate import validate_graph
from ai_algo.store import memory as store_mod

router = APIRouter(tags=["ingest"])
API_VERSION = "2026-08-20"


class Bar(BaseModel):
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class IngestBarsRequest(BaseModel):
    dataset_id: Optional[str] = None
    symbol: str
    timeframe: str
    bars: List[Bar]
    indicators: Optional[List[Dict[str, Any]]] = None


class IngestGraphsRequest(BaseModel):
    graphs: List[Dict[str, Any]]


class IngestRunsRequest(BaseModel):
    runs: List[Dict[str, Any]]


@router.post("/v1/ingest/bars")
def ingest_bars(body: IngestBarsRequest) -> dict:
    item_id = store_mod.store.put_bars(body.model_dump())
    return {
        "api_version": API_VERSION,
        "status": "accepted",
        "result": {"id": item_id},
        "error": None,
    }


@router.post("/v1/ingest/graphs")
def ingest_graphs(body: IngestGraphsRequest) -> dict:
    for g in body.graphs:
        err = validate_graph(g, max_depth=2)
        if err:
            return {
                "api_version": API_VERSION,
                "status": "error",
                "result": {},
                "error": {"code": "validation_failed", "message": err},
            }
    item_id = store_mod.store.put_graphs(body.graphs)
    return {
        "api_version": API_VERSION,
        "status": "accepted",
        "result": {"id": item_id},
        "error": None,
    }


@router.post("/v1/ingest/runs")
def ingest_runs(body: IngestRunsRequest) -> dict:
    item_id = store_mod.store.put_runs(body.runs)
    return {
        "api_version": API_VERSION,
        "status": "accepted",
        "result": {"id": item_id},
        "error": None,
    }


@router.get("/v1/ingest/datasets")
def list_datasets() -> dict:
    return {
        "bars": len(store_mod.store.bars),
        "graphs": len(store_mod.store.graphs),
        "runs": len(store_mod.store.runs),
        "persist": type(store_mod.store).__name__,
    }
