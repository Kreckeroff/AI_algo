"""Backward-compatible import path: ai_algo.store.memory.store """

from ai_algo.store.file_store import (  # noqa: F401
    FileStore,
    MemoryStore,
    create_store,
    reset_store_for_tests,
    store,
)
