"""
One-time script to create the first admin user.

Usage:
  docker compose run --rm \
    -e ADMIN_EMAIL=admin@shopflow.com \
    -e ADMIN_PASSWORD=Admin123! \
    user-service python scripts/create_admin.py

Or promote an existing user:
  docker compose run --rm \
    -e ADMIN_EMAIL=existing@user.com \
    user-service python scripts/create_admin.py
"""
import asyncio
import os
import uuid

import asyncpg
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ADMIN_EMAIL    = os.environ.get("ADMIN_EMAIL", "admin@shopflow.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin123!")
ADMIN_NAME     = os.environ.get("ADMIN_NAME", "ShopFlow Admin")
DATABASE_URL   = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://shopflow:shopflow_secret@postgres:5432/shopflow",
).replace("postgresql+asyncpg://", "postgresql://")


async def create_admin():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        existing = await conn.fetchrow(
            "SELECT id, role FROM users.users WHERE email = $1",
            ADMIN_EMAIL,
        )
        if existing:
            if existing["role"] == "admin":
                print(f"✅ Admin already exists: {ADMIN_EMAIL}")
            else:
                await conn.execute(
                    "UPDATE users.users SET role = 'admin' WHERE email = $1",
                    ADMIN_EMAIL,
                )
                print(f"✅ Promoted existing user to admin: {ADMIN_EMAIL}")
        else:
            hashed = pwd_context.hash(ADMIN_PASSWORD)
            await conn.execute(
                """
                INSERT INTO users.users
                    (id, email, hashed_password, full_name, is_active, is_verified, role)
                VALUES ($1, $2, $3, $4, true, true, 'admin')
                """,
                uuid.uuid4(), ADMIN_EMAIL, hashed, ADMIN_NAME,
            )
            print(f"✅ Admin created: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
            print("   ⚠️  Change password immediately in production!")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_admin())
