from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as rest_router
from app.api.ws import router as ws_router
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Multi-Agent Arena", lifespan=lifespan)

allowed_origins = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rest_router, prefix="/api")
app.include_router(ws_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
