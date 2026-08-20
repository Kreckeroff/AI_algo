from __future__ import annotations

from typing import Any, Dict, List
from uuid import uuid4


class MemoryStore:
    def __init__(self) -> None:
        self.bars: Dict[str, Any] = {}
        self.graphs: Dict[str, Any] = {}
        self.runs: Dict[str, Any] = {}

    def put_bars(self, payload: dict) -> str:
        item_id = payload.get("dataset_id") or str(uuid4())
        self.bars[item_id] = payload
        return item_id

    def put_graphs(self, graphs: List[dict]) -> str:
        item_id = str(uuid4())
        self.graphs[item_id] = graphs
        return item_id

    def put_runs(self, runs: List[dict]) -> str:
        item_id = str(uuid4())
        self.runs[item_id] = runs
        return item_id


store = MemoryStore()
