from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.router import router
from app.core.config import settings
from app.core.http_client import close_http_client, get_http_client
from app.core.kafka_producer import close_producer, get_producer
from app.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("starting", service=settings.service_name, env=settings.environment)

    # Warm up connections on startup
    await get_http_client()
    await get_producer()

    yield

    # Clean shutdown
    await close_producer()
    await close_http_client()
    logger.info("shutting down", service=settings.service_name)


app = FastAPI(
    title=f"ShopFlow — {settings.service_name}",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)
app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.service_name}
