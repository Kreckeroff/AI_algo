from fastapi import FastAPI

from ai_algo.api.health import router as health_router
from ai_algo.api.infer import router as infer_router
from ai_algo.api.ingest import router as ingest_router

app = FastAPI(title="AI_algo", version="0.1.0")
app.include_router(health_router)
app.include_router(infer_router)
app.include_router(ingest_router)
