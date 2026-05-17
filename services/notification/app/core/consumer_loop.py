import asyncio
from aiokafka.errors import KafkaConnectionError
from app.core.kafka_consumer import get_consumer, TOPICS
from app.services.notification_service import NotificationService
from app.core.logging import get_logger

logger = get_logger(__name__)

# Map topic names to handler methods
HANDLERS = {
    "order.created":   "handle_order_created",
    "order.updated":   "handle_order_updated",
    "order.cancelled": "handle_order_cancelled",
}


async def consume_loop() -> None:
    """
    Infinite loop that reads messages from Kafka and dispatches to handlers.

    This runs as a background asyncio task — it doesn't block the FastAPI
    server. Both the HTTP server and this loop share the same event loop.

    Key concepts demonstrated:
    - Consumer group: multiple instances of notification-service share work
    - Each partition is assigned to exactly one consumer in the group
    - If one instance dies, Kafka rebalances partitions to survivors
    - auto_offset_reset=earliest: on first run, read all historical messages
    - After that, only new messages are consumed
    """
    service = NotificationService()

    while True:
        try:
            consumer = await get_consumer()
            logger.info("consumer_loop_started")

            async for message in consumer:
                try:
                    event = message.value
                    topic = message.topic
                    event_type = event.get("event_type", "unknown")

                    logger.info(
                        "kafka_message_received",
                        topic=topic,
                        event_type=event_type,
                        partition=message.partition,
                        offset=message.offset,
                        order_id=event.get("order_id"),
                    )

                    # Dispatch to the right handler
                    handler_name = HANDLERS.get(topic)
                    if handler_name:
                        handler = getattr(service, handler_name)
                        await handler(event)
                    else:
                        logger.warning("no_handler_for_topic", topic=topic)

                except Exception as e:
                    # Log and continue — don't crash the consumer loop
                    # In production: send to Dead Letter Queue (DLQ)
                    logger.error(
                        "message_processing_failed",
                        error=str(e),
                        topic=message.topic,
                        offset=message.offset,
                    )
                    continue

        except KafkaConnectionError:
            logger.warning("kafka_connection_lost_retrying_in_5s")
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("consumer_loop_cancelled")
            break
        except Exception as e:
            logger.error("consumer_loop_error", error=str(e))
            await asyncio.sleep(5)
