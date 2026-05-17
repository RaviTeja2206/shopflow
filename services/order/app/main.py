from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.kafka_producer import get_producer, close_producer
from app.core.http_client import get_http_client, close_http_client
from app.api.v1.router import router

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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)
app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.service_name}
