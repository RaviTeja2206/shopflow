from fastapi import APIRouter, Depends, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.user import (
    UserRegister, UserLogin, UserUpdate,
    UserResponse, TokenResponse, TokenRefresh, MessageResponse,
)
from app.services.user_service import UserService
from app.core.dependencies import get_current_user
from app.models.user import User

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
