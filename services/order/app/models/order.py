import enum
import uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Numeric, Integer, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class OrderStatus(str, enum.Enum):
    """
    State machine: PENDING → CONFIRMED → PROCESSING → SHIPPED → DELIVERED
                         ↘ CANCELLED (from PENDING or CONFIRMED only)
    """
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = {"schema": "orders"}

    # We store user_id but don't FK to users schema
    # Services don't share DB constraints — that would couple them
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, schema="orders"),
        default=OrderStatus.PENDING,
        nullable=False,
        index=True,     # we filter orders by status constantly
    )
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    shipping_address: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # One order has many items
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",    # load items automatically with the order
    )

    def __repr__(self):
        return f"<Order {self.id} {self.status.value}>"

    def can_cancel(self) -> bool:
        return self.status in (OrderStatus.PENDING, OrderStatus.CONFIRMED)

    def can_transition_to(self, new_status: OrderStatus) -> bool:
        allowed = {
            OrderStatus.PENDING:    [OrderStatus.CONFIRMED, OrderStatus.CANCELLED],
            OrderStatus.CONFIRMED:  [OrderStatus.PROCESSING, OrderStatus.CANCELLED],
            OrderStatus.PROCESSING: [OrderStatus.SHIPPED],
            OrderStatus.SHIPPED:    [OrderStatus.DELIVERED],
            OrderStatus.DELIVERED:  [],
            OrderStatus.CANCELLED:  [],
        }
        return new_status in allowed[self.status]


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = {"schema": "orders"}

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Again — no FK to products schema. We copy the data we need.
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")

    @property
    def subtotal(self) -> float:
        return float(self.unit_price) * self.quantity

    def __repr__(self):
        return f"<OrderItem {self.product_name} x{self.quantity}>"
