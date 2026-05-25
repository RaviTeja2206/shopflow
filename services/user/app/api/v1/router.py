import uuid

from fastapi import APIRouter, Depends, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import (
    MessageResponse,
    PaginatedUsers,
    RoleUpdate,
    TokenRefresh,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
    UserUpdate,
)
from app.services.user_service import UserService

router = APIRouter()
bearer_scheme = HTTPBearer()


@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    return await UserService(db).register(data)


@router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    return await UserService(db).login(data.email, data.password)


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(data: TokenRefresh, db: AsyncSession = Depends(get_db)):
    return await UserService(db).refresh_tokens(data.refresh_token)


@router.post("/auth/logout", response_model=MessageResponse)
async def logout(
    data: TokenRefresh,
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    await UserService(db).logout(data.refresh_token, credentials.credentials)
    return {"message": "Successfully logged out"}


@router.get("/users/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/users/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await UserService(db).update(current_user.id, data)


# ── Admin user management ─────────────────────────────────────

@router.get("/admin/users", response_model=PaginatedUsers)
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, min_length=2),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await UserService(db).list_users(page=page, page_size=page_size, search=search)


@router.patch("/admin/users/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: uuid.UUID,
    data: RoleUpdate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await UserService(db).update_role(
        target_user_id=user_id,
        new_role=data.role,
        requesting_user_id=current_user.id,
    )
