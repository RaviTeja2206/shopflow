from app.core.logging import get_logger

logger = get_logger(__name__)


class NotificationService:
    """
    Handles notification events consumed from Kafka.

    In production this would:
    - Send emails via SendGrid/SES
    - Send push notifications via FCM/APNs
    - Send SMS via Twilio
    - Store notification history in DB

    For this project we log structured events — the wiring is identical,
    only the delivery mechanism changes.
    """

    async def handle_order_created(self, event: dict) -> None:
        logger.info(
            "notification_sending",
            type="order_confirmation",
            order_id=event.get("order_id"),
            user_id=event.get("user_id"),
            total=event.get("total_amount"),
        )
        # Simulate email send
        await self._send_email(
            to_user_id=event.get("user_id"),
            subject="Order Confirmed — ShopFlow",
            body=(
                f"Your order #{event.get('order_id')[:8]} has been placed. "
                f"Total: ${event.get('total_amount')}. "
                f"We'll notify you when it ships."
            ),
        )

    async def handle_order_updated(self, event: dict) -> None:
        new_status = event.get("new_status")
        logger.info(
            "notification_sending",
            type="order_status_update",
            order_id=event.get("order_id"),
            user_id=event.get("user_id"),
            new_status=new_status,
        )
        await self._send_email(
            to_user_id=event.get("user_id"),
            subject=f"Order Update — {new_status.title()}",
            body=(
                f"Your order #{event.get('order_id')[:8]} "
                f"is now {new_status}."
            ),
        )

    async def handle_order_cancelled(self, event: dict) -> None:
        logger.info(
            "notification_sending",
            type="order_cancellation",
            order_id=event.get("order_id"),
            user_id=event.get("user_id"),
        )
        await self._send_email(
            to_user_id=event.get("user_id"),
            subject="Order Cancelled — ShopFlow",
            body=f"Your order #{event.get('order_id')[:8]} has been cancelled.",
        )

    async def _send_email(self, to_user_id: str, subject: str, body: str) -> None:
        """
        In production: call SendGrid/SES API here.
        For now: structured log that proves the wiring works.
        """
        logger.info(
            "email_sent",
            to_user_id=to_user_id,
            subject=subject,
            body=body,
        )
