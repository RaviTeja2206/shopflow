import uuid
import math
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from app.models.product import Product, Category
from app.schemas.product import ProductCreate, ProductUpdate, CategoryCreate
from app.core.redis import Cache
from app.core.logging import get_logger

logger = get_logger(__name__)


def slugify(text: str) -> str:
    return text.lower().strip().replace(" ", "-").replace("_", "-")


async def _get_product_with_category(db: AsyncSession, product_id: uuid.UUID) -> Product:
    """
    Single reusable query that always loads category relationship.
    Avoids MissingGreenlet error by eagerly loading the relationship
    while the session is still open.
    """
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.category))
        .where(Product.id == product_id)
    )
    return result.scalar_one_or_none()


class ProductService:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Categories ────────────────────────────────────────────

    async def create_category(self, data: CategoryCreate) -> Category:
        slug = slugify(data.name)
        existing = await self.db.execute(
            select(Category).where(Category.slug == slug)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Category '{data.name}' already exists",
            )
        category = Category(
            name=data.name,
            slug=slug,
            description=data.description,
        )
        self.db.add(category)
        await self.db.flush()
        await Cache.delete("categories:all")
        logger.info("category_created", category_id=str(category.id))
        return category

    async def list_categories(self) -> list:
        cached = await Cache.get("categories:all")
        if cached:
            return cached

        result = await self.db.execute(
            select(Category).order_by(Category.name)
        )
        categories = result.scalars().all()

        data = [
            {
                "id": str(c.id),
                "name": c.name,
                "slug": c.slug,
                "description": c.description,
                "created_at": str(c.created_at),
            }
            for c in categories
        ]
        await Cache.set("categories:all", data)
        return categories

    # ── Products ──────────────────────────────────────────────

    async def get_by_id(self, product_id: uuid.UUID) -> Product:
        cache_key = f"product:{product_id}"
        cached = await Cache.get(cache_key)
        if cached:
            return cached

        product = await _get_product_with_category(self.db, product_id)
        if not product or not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )
        return product

    async def list_products(
        self,
        page: int = 1,
        page_size: int = 20,
        category_id: uuid.UUID | None = None,
        search: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
    ) -> dict:
        cache_key = f"list:p{page}:s{page_size}:cat{category_id}:q{search}:min{min_price}:max{max_price}"
        cached = await Cache.get(cache_key)
        if cached:
            return cached

        query = (
            select(Product)
            .options(selectinload(Product.category))
            .where(Product.is_active == True)  # noqa: E712
        )

        if category_id:
            query = query.where(Product.category_id == category_id)
        if search:
            query = query.where(
                or_(
                    Product.name.ilike(f"%{search}%"),
                    Product.description.ilike(f"%{search}%"),
                )
            )
        if min_price:
            query = query.where(Product.price >= min_price)
        if max_price:
            query = query.where(Product.price <= max_price)

        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query)

        offset = (page - 1) * page_size
        query = query.order_by(Product.created_at.desc()).offset(offset).limit(page_size)
        result = await self.db.execute(query)
        products = result.scalars().all()

        total_pages = math.ceil(total / page_size) if total > 0 else 1

        response = {
            "items": products,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

        if not search:
            await Cache.set(cache_key, {
                **response,
                "items": [],
            }, ttl=60)

        return response

    async def create_product(self, data: ProductCreate) -> Product:
        if data.category_id:
            cat = await self.db.get(Category, data.category_id)
            if not cat:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Category not found",
                )

        slug = slugify(data.name)
        base_slug = slug
        counter = 1
        while True:
            existing = await self.db.execute(
                select(Product).where(Product.slug == slug)
            )
            if not existing.scalar_one_or_none():
                break
            slug = f"{base_slug}-{counter}"
            counter += 1

        product = Product(
            name=data.name,
            slug=slug,
            description=data.description,
            price=data.price,
            stock_quantity=data.stock_quantity,
            category_id=data.category_id,
            image_url=data.image_url,
        )
        self.db.add(product)

        # flush gives us the generated ID without committing
        await self.db.flush()

        # Reload with category relationship eagerly loaded
        # Must happen BEFORE session closes — this is why we can't
        # just return the product object directly after flush
        product = await _get_product_with_category(self.db, product.id)

        await Cache.delete_pattern("list:*")
        logger.info("product_created", product_id=str(product.id))
        return product

    async def update_product(self, product_id: uuid.UUID, data: ProductUpdate) -> Product:
        product = await _get_product_with_category(self.db, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(product, field, value)

        await Cache.delete(f"product:{product_id}")
        await Cache.delete_pattern("list:*")
        logger.info("product_updated", product_id=str(product_id))
        return product

    async def delete_product(self, product_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(Product).where(Product.id == product_id)
        )
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        product.is_active = False
        await Cache.delete(f"product:{product_id}")
        await Cache.delete_pattern("list:*")
        logger.info("product_soft_deleted", product_id=str(product_id))
