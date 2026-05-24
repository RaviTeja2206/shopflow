import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin, get_current_user_id
from app.db.session import get_db
from app.schemas.product import (
    CategoryCreate,
    CategoryResponse,
    PaginatedProducts,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)
from app.services.product_service import ProductService

router = APIRouter()


# ── Categories ────────────────────────────────────────────────

@router.post(
    "/categories/",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create category (admin only)",
)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(get_current_admin),   # admin only
):
    return await ProductService(db).create_category(data)


@router.get(
    "/categories/",
    response_model=list[CategoryResponse],
    summary="List categories (any authenticated user)",
)
async def list_categories(
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(get_current_user_id),  # any authenticated user
):
    return await ProductService(db).list_categories()


# ── Products ──────────────────────────────────────────────────

@router.get(
    "/products/",
    response_model=PaginatedProducts,
    summary="List products (any authenticated user)",
)
async def list_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None, min_length=2),
    min_price: Decimal | None = Query(default=None, gt=0),
    max_price: Decimal | None = Query(default=None, gt=0),
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(get_current_user_id),  # any authenticated user
):
    return await ProductService(db).list_products(
        page=page,
        page_size=page_size,
        category_id=category_id,
        search=search,
        min_price=min_price,
        max_price=max_price,
    )


@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Get product (any authenticated user)",
)
async def get_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(get_current_user_id),  # any authenticated user
):
    return await ProductService(db).get_by_id(product_id)


@router.post(
    "/products/",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create product (admin only)",
)
async def create_product(
    data: ProductCreate,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(get_current_admin),   # admin only
):
    return await ProductService(db).create_product(data)


@router.put(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Update product (admin only)",
)
async def update_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(get_current_admin),   # admin only
):
    return await ProductService(db).update_product(product_id, data)


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete product (admin only)",
)
async def delete_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(get_current_admin),   # admin only
):
    await ProductService(db).delete_product(product_id)
