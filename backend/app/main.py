"""
FastAPI application entrypoint.

Two routers:
  - /api/storefront/*   write path  (Postgres)
  - /api/admin/*        read path   (ClickHouse + Postgres)

OpenAPI docs at /docs (Swagger UI) and /redoc — auto-generated from the
Pydantic models in app/models.py.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_pg_pool, close_pg_pool
from .routers import storefront, admin

log = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup: initialising Postgres pool")
    init_pg_pool()
    yield
    log.info("shutdown: closing Postgres pool")
    close_pg_pool()


app = FastAPI(
    title="CDC Pipeline — Storefront & Admin API",
    description=(
        "Backend for a synthetic coffee storefront. Writes orders to Postgres, "
        "which the existing CDC pipeline (Debezium → Kafka → PySpark) streams "
        "into ClickHouse. Read endpoints serve the admin dashboard from the "
        "warehouse so it shows the *result* of the pipeline."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(storefront.router, prefix="/api/storefront", tags=["storefront"])
app.include_router(admin.router,       prefix="/api/admin",      tags=["admin"])


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": "cdc-pipeline-backend",
        "docs": "/docs",
        "storefront_api": "/api/storefront",
        "admin_api": "/api/admin",
    }


@app.get("/healthz", tags=["meta"])
def healthz() -> dict:
    """Kubernetes/Compose-style liveness probe — no DB calls, just process-alive check."""
    return {"status": "ok"}
