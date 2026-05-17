import uuid
from decimal import Decimal
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.product import (
    CategoryCreate, CategoryResponse,
    ProductCreate, ProductUpdate, ProductResponse,
    PaginatedProducts,
)
from app.services.product_service import ProductService

router = APIRouter()


# ── Categories ────────────────────────────────────────────────

@router.post("/categories/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
):
    service = ProductService(db)
    return await service.create_category(data)


@router.get("/categories/", response_model=list[CategoryResponse])
async def list_categories(db: AsyncSession = Depends(get_db)):
    service = ProductService(db)
    return await service.list_categories()


# ── Products ──────────────────────────────────────────────────

@router.get("/products/", response_model=PaginatedProducts)
async def list_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None, min_length=2),
    min_price: Decimal | None = Query(default=None, gt=0),
    max_price: Decimal | None = Query(default=None, gt=0),
    db: AsyncSession = Depends(get_db),
):
    service = ProductService(db)
    return await service.list_products(
        page=page,
        page_size=page_size,
        category_id=category_id,
        search=search,
        min_price=min_price,
        max_price=max_price,
    )


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    service = ProductService(db)
    return await service.get_by_id(product_id)


@router.post("/products/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    data: ProductCreate,
    db: AsyncSession = Depends(get_db),
):
    service = ProductService(db)
    return await service.create_product(data)


@router.put("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    db: AsyncSession = Depends(get_db),
):
    service = ProductService(db)
    return await service.update_product(product_id, data)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    service = ProductService(db)
    await service.delete_product(product_id)
