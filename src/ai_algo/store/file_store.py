from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


def default_data_root() -> Path:
    # src/ai_algo/store/file_store.py → parents[3] = repo root
    return Path(__file__).resolve().parents[3] / "data" / "ingest"


class FileStore:
    """Persist bars/graphs/runs as JSON under data/ingest (survives restart)."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else default_data_root()
        self.bars: Dict[str, Any] = {}
        self.graphs: Dict[str, Any] = {}
        self.runs: Dict[str, Any] = {}
        for kind in ("bars", "graphs", "runs"):
            (self.root / kind).mkdir(parents=True, exist_ok=True)
        self._load_all()

    def _path(self, kind: str, item_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in item_id)[:180]
        return self.root / kind / f"{safe}.json"

    def _load_all(self) -> None:
        for kind, bucket in (
            ("bars", self.bars),
            ("graphs", self.graphs),
            ("runs", self.runs),
        ):
            folder = self.root / kind
            if not folder.exists():
                continue
            for path in folder.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    item_id = data.get("_id") or path.stem
                    bucket[item_id] = data.get("payload", data)
                except (OSError, json.JSONDecodeError):
                    continue

    def _write(self, kind: str, item_id: str, payload: Any) -> None:
        path = self._path(kind, item_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"_id": item_id, "payload": payload}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def put_bars(self, payload: dict) -> str:
        item_id = str(payload.get("dataset_id") or uuid4())
        self.bars[item_id] = payload
        self._write("bars", item_id, payload)
        return item_id

    def put_graphs(self, graphs: List[dict]) -> str:
        item_id = str(uuid4())
        self.graphs[item_id] = graphs
        self._write("graphs", item_id, graphs)
        return item_id

    def put_runs(self, runs: List[dict]) -> str:
        item_id = str(uuid4())
        self.runs[item_id] = runs
        self._write("runs", item_id, runs)
        return item_id


class MemoryStore:
    """Ephemeral store for unit tests."""

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


def create_store():
    mode = os.environ.get("AI_ALGO_STORE", "file").strip().lower()
    if mode == "memory":
        return MemoryStore()
    root = os.environ.get("AI_ALGO_DATA_DIR")
    return FileStore(Path(root) if root else None)


store = create_store()


def reset_store_for_tests(tmp_root: Optional[Path] = None) -> None:
    """Swap global store (tests only)."""
    global store
    if tmp_root is not None:
        store = FileStore(tmp_root)
    else:
        store = MemoryStore()
