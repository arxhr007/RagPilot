from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import ensure_data_dirs


ensure_data_dirs()

app = FastAPI(
    title="RAGX Adaptive Multi-RAG Orchestrator",
    description="Hackathon MVP for automatic RAG architecture selection and routing.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root():
    return {"name": "RAGX", "status": "ready"}
