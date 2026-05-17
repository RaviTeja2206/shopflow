from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.redis import get_redis, close_redis
from app.api.v1.router import router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("starting", service=settings.service_name, env=settings.environment)
    await get_redis()  # initialize connection on startup
    yield
    await close_redis()
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
