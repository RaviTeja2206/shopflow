import math
import uuid
from decimal import Decimal

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.http_client import get_product
from app.core.kafka_producer import (
    TOPIC_ORDER_CANCELLED,
    TOPIC_ORDER_CREATED,
    TOPIC_ORDER_UPDATED,
    publish,
)
from app.core.logging import get_logger
from app.models.order import Order, OrderItem, OrderStatus
from app.schemas.order import OrderCreate, OrderStatusUpdate

logger = get_logger(__name__)


async def _get_order_with_items(db: AsyncSession, order_id: uuid.UUID) -> Order | None:
    """Always load items eagerly — same pattern as product service."""
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
    )
    return result.scalar_one_or_none()


class OrderService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_order(self, user_id: uuid.UUID, data: OrderCreate) -> Order:
        """
        Order creation flow:
        1. Validate all products exist and have sufficient stock
        2. Calculate total
        3. Create order + items in DB (single transaction)
        4. Publish order.created event to Kafka
        5. Return order

        Steps 1-3 are atomic. Step 4 is fire-and-forget after commit.
        If Kafka publish fails, the order still exists — we log the failure
        and a retry mechanism handles it (dead letter queue in production).
        """

        # ── Step 1: Validate products ─────────────────────────
        # Call product service for each item
        # Collect all errors before raising — better UX than failing on first
        validated_items = []
        errors = []

        for item in data.items:
            try:
                product = await get_product(str(item.product_id))
            except httpx.TimeoutException:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Product service unavailable. Please try again.",
                )

            if product is None:
                errors.append(f"Product {item.product_id} not found")
                continue

            if not product.get("is_active"):
                errors.append(f"Product '{product['name']}' is no longer available")
                continue

            if product["stock_quantity"] < item.quantity:
                errors.append(
                    f"Insufficient stock for '{product['name']}': "
                    f"requested {item.quantity}, available {product['stock_quantity']}"
                )
                continue

            validated_items.append({
                "product_id": item.product_id,
                "product_name": product["name"],
                "unit_price": Decimal(str(product["price"])),
                "quantity": item.quantity,
            })

        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"errors": errors},
            )

        # ── Step 2: Calculate total ───────────────────────────
        total = sum(
            item["unit_price"] * item["quantity"]
            for item in validated_items
        )

        # ── Step 3: Persist to DB ─────────────────────────────
        order = Order(
            user_id=user_id,
            status=OrderStatus.PENDING,
            total_amount=total,
            shipping_address=data.shipping_address,
            notes=data.notes,
        )
        self.db.add(order)
        await self.db.flush()  # get order.id before adding items

        for item_data in validated_items:
            self.db.add(OrderItem(
                order_id=order.id,
                product_id=item_data["product_id"],
                product_name=item_data["product_name"],
                unit_price=item_data["unit_price"],
                quantity=item_data["quantity"],
            ))

        await self.db.flush()

        # Reload with items for response
        order = await _get_order_with_items(self.db, order.id)

        logger.info(
            "order_created",
            order_id=str(order.id),
            user_id=str(user_id),
            total=str(total),
            items=len(validated_items),
        )

        # ── Step 4: Publish Kafka event ───────────────────────
        # This happens AFTER the DB write succeeds.
        # The session hasn't committed yet but flush made the data visible
        # within this transaction. We publish optimistically — if the
        # transaction rolls back, the notification service will eventually
        # try to look up an order that doesn't exist and discard the event.
        #
        # Production solution: transactional outbox pattern — write the
        # event to an outbox table in the same transaction, a separate
        # process reads and publishes. Guarantees exactly-once delivery.
        try:
            await publish(
                topic=TOPIC_ORDER_CREATED,
                event={
                    "event_type": "order.created",
                    "order_id": str(order.id),
                    "user_id": str(user_id),
                    "total_amount": str(total),
                    "items_count": len(validated_items),
                    "shipping_address": data.shipping_address,
                },
                key=str(user_id),  # partition by user_id for ordering
            )
        except Exception:
            # Don't fail the order if Kafka is down
            # In production: write to outbox table instead
            logger.error(
                "kafka_publish_failed_order_still_created",
                order_id=str(order.id),
            )

        return order

    async def get_order(self, order_id: uuid.UUID, user_id: uuid.UUID) -> Order:
        order = await _get_order_with_items(self.db, order_id)

        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )

        # Users can only see their own orders
        if order.user_id != user_id:
            # Return 404 not 403 — don't reveal the order exists
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )

        return order

    async def list_orders(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status_filter: OrderStatus | None = None,
    ) -> dict:
        query = (
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.user_id == user_id)
        )

        if status_filter:
            query = query.where(Order.status == status_filter)

        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query)

        offset = (page - 1) * page_size
        query = query.order_by(Order.created_at.desc()).offset(offset).limit(page_size)
        result = await self.db.execute(query)
        orders = result.scalars().all()

        total_pages = math.ceil(total / page_size) if total > 0 else 1

        return {
            "items": orders,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

    async def update_status(
        self,
        order_id: uuid.UUID,
        user_id: uuid.UUID,
        data: OrderStatusUpdate,
    ) -> Order:
        order = await _get_order_with_items(self.db, order_id)

        if not order or order.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )

        # State machine validation — uses the method we built on the model
        if not order.can_transition_to(data.status):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Cannot transition order from "
                    f"'{order.status.value}' to '{data.status.value}'. "
                    f"Invalid state transition."
                ),
            )

        old_status = order.status
        order.status = data.status
        if data.notes:
            order.notes = data.notes

        logger.info(
            "order_status_updated",
            order_id=str(order_id),
            from_status=old_status.value,
            to_status=data.status.value,
        )

        # Publish appropriate Kafka event
        topic = TOPIC_ORDER_CANCELLED if data.status == OrderStatus.CANCELLED else TOPIC_ORDER_UPDATED
        try:
            await publish(
                topic=topic,
                event={
                    "event_type": f"order.{data.status.value}",
                    "order_id": str(order_id),
                    "user_id": str(user_id),
                    "old_status": old_status.value,
                    "new_status": data.status.value,
                },
                key=str(user_id),
            )
        except Exception:
            logger.error("kafka_publish_failed", order_id=str(order_id))

        return order

    async def cancel_order(self, order_id: uuid.UUID, user_id: uuid.UUID) -> Order:
        """Convenience method — cancel is just a status transition."""
        return await self.update_status(
            order_id=order_id,
            user_id=user_id,
            data=OrderStatusUpdate(status=OrderStatus.CANCELLED),
        )
