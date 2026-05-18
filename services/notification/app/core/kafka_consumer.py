import json

from aiokafka import AIOKafkaConsumer

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

TOPICS = [
    "order.created",
    "order.updated",
    "order.cancelled",
]

_consumer: AIOKafkaConsumer | None = None


async def get_consumer() -> AIOKafkaConsumer:
    global _consumer
    if _consumer is None:
        _consumer = AIOKafkaConsumer(
            *TOPICS,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_consumer_group,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            # Start from earliest unread message for this consumer group
            auto_offset_reset="earliest",
            # Commit offsets automatically every 5 seconds
            # In production use manual commits for exactly-once processing
            enable_auto_commit=True,
            auto_commit_interval_ms=5000,
        )
        await _consumer.start()
        logger.info("kafka_consumer_started", topics=TOPICS, group=settings.kafka_consumer_group)
    return _consumer


async def close_consumer():
    global _consumer
    if _consumer:
        await _consumer.stop()
        _consumer = None
        logger.info("kafka_consumer_stopped")
