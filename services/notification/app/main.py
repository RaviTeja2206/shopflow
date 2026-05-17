import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.kafka_consumer import close_consumer
from app.core.consumer_loop import consume_loop
from app.api.v1.router import router

logger = get_logger(__name__)

# Background task handle — kept so we can cancel it on shutdown
_consumer_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _consumer_task
    setup_logging()
    logger.info("starting", service=settings.service_name)

    # Start consumer as background asyncio task
    # It runs concurrently with the HTTP server on the same event loop
    _consumer_task = asyncio.create_task(consume_loop())
    logger.info("consumer_task_started")

    yield

    # Graceful shutdown — cancel consumer task first, then close connection
    if _consumer_task:
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass

    await close_consumer()
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
