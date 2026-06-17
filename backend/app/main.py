from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import ensure_data_dirs


ensure_data_dirs()

app = FastAPI(
    title="RAGPilot Adaptive Multi-RAG Orchestrator",
    description="Automatic RAG architecture selection and routing for mixed datasets.",
    version="0.1.0",
)


@app.exception_handler(KeyError)
async def dataset_not_found_handler(request: Request, exc: KeyError) -> JSONResponse:
    # store.get() raises KeyError for unknown/expired dataset ids; surface as 404.
    return JSONResponse(status_code=404, content={"detail": str(exc).strip('"')})

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
    return {"name": "RAGPilot", "status": "ready"}
