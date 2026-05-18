import json

from aiokafka import AIOKafkaProducer

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_producer: AIOKafkaProducer | None = None

# Topic names — single source of truth
TOPIC_ORDER_CREATED = "order.created"
TOPIC_ORDER_UPDATED = "order.updated"
TOPIC_ORDER_CANCELLED = "order.cancelled"


async def get_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            # Wait for all replicas to acknowledge — strongest durability guarantee
            acks="all",
            # Retry up to 3 times on transient failures
            retry_backoff_ms=300,
        )
        await _producer.start()
        logger.info("kafka_producer_started")
    return _producer


async def close_producer():
    global _producer
    if _producer:
        await _producer.stop()
        _producer = None
        logger.info("kafka_producer_stopped")


async def publish(topic: str, event: dict, key: str | None = None) -> None:
    """
    Publish an event to a Kafka topic.

    key: used for partitioning — same key always goes to same partition.
    We use user_id as key so all events for one user go to the same
    partition — guaranteeing ordering of events per user.
    """
    producer = await get_producer()
    try:
        await producer.send_and_wait(topic, value=event, key=key)
        logger.info(
            "kafka_event_published",
            topic=topic,
            key=key,
            event_type=event.get("event_type"),
        )
    except Exception as e:
        # Log but don't crash the request — notification failure
        # should not fail an order creation
        logger.error("kafka_publish_failed", topic=topic, error=str(e))
        raise
