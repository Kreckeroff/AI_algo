import os

# Prefer ephemeral store for pytest unless a test opts into FileStore(tmp_path).
os.environ.setdefault("AI_ALGO_STORE", "memory")
