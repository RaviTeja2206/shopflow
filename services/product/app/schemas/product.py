import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Reusable type — Decimal with max 10 digits, 2 decimal places, must be > 0
Price = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]


# ── Category schemas ──────────────────────────────────────────
class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=100)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    created_at: datetime


# ── Product schemas ───────────────────────────────────────────
class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")  # rejects unknown fields like "stock"

    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    price: Price
    stock_quantity: int = Field(ge=0, default=0)
    category_id: uuid.UUID | None = None
    image_url: str | None = None


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")  # rejects unknown fields

    name: str | None = Field(None, min_length=2, max_length=255)
    description: str | None = None
    price: Price | None = None
    stock_quantity: int | None = Field(None, ge=0)
    category_id: uuid.UUID | None = None
    image_url: str | None = None
    is_active: bool | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    price: Decimal
    stock_quantity: int
    is_active: bool
    image_url: str | None
    category_id: uuid.UUID | None
    category: CategoryResponse | None
    created_at: datetime
    updated_at: datetime


# ── Pagination schema ─────────────────────────────────────────
class PaginatedProducts(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool
