from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_algo.api.health import router as health_router
from ai_algo.api.infer import router as infer_router
from ai_algo.api.ingest import router as ingest_router

app = FastAPI(title="AI_algo", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(infer_router)
app.include_router(ingest_router)
