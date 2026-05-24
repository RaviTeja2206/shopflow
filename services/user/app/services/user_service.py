import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.user import RefreshToken, User
from app.schemas.user import UserRegister, UserUpdate

logger = get_logger(__name__)


class UserService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def register(self, data: UserRegister) -> User:
        existing = await self.get_by_email(data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
        )
        self.db.add(user)
        await self.db.flush()
        logger.info("user_registered", user_id=str(user.id), email=user.email)
        return user

    async def login(self, email: str, password: str) -> dict:
        user = await self.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )
        access_token = create_access_token(subject=str(user.id), extra_data={"role": user.role})
        refresh_token = create_refresh_token(subject=str(user.id))
        self.db.add(RefreshToken(
            user_id=user.id,
            token=hash_token(refresh_token),
        ))
        logger.info("user_logged_in", user_id=str(user.id))
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": 30 * 60,
        }

    async def refresh_tokens(self, refresh_token: str) -> dict:
        try:
            payload = decode_token(refresh_token)
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        token_hash = hash_token(refresh_token)
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token == token_hash,
                RefreshToken.is_revoked == False,  # noqa: E712
            )
        )
        db_token = result.scalar_one_or_none()

        if not db_token:
            # Replay attack — commit the revocation BEFORE raising
            # so the rollback in get_db() doesn't undo it
            user_id_str = payload.get("sub")
            if user_id_str:
                await self._revoke_all_tokens_and_commit(uuid.UUID(user_id_str))
                logger.warning(
                    "replay_attack_detected_all_tokens_revoked",
                    user_id=user_id_str,
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token reuse detected. All sessions have been revoked. Please login again.",
            )

        # Rotate — revoke old, issue new
        db_token.is_revoked = True
        user_id = uuid.UUID(payload["sub"])
        refreshed_user = await self.db.get(User, user_id)
        user_role = refreshed_user.role if refreshed_user else "user"

        new_access = create_access_token(subject=str(user_id), extra_data={"role": user_role})
        new_refresh = create_refresh_token(subject=str(user_id))

        self.db.add(RefreshToken(
            user_id=user_id,
            token=hash_token(new_refresh),
        ))

        logger.info("tokens_rotated", user_id=str(user_id))
        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "expires_in": 30 * 60,
        }

    async def logout(self, refresh_token: str, access_token: str) -> None:
        token_hash = hash_token(refresh_token)
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token == token_hash,
                RefreshToken.is_revoked == False,  # noqa: E712
            )
        )
        db_token = result.scalar_one_or_none()
        if not db_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or already revoked token",
            )
        db_token.is_revoked = True

        # Blocklist access token in Redis so it dies immediately
        try:
            payload = decode_token(access_token)
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                ttl = int(exp - datetime.now(timezone.utc).timestamp())
                if ttl > 0:
                    redis = await get_redis()
                    await redis.setex(f"blocklist:{jti}", ttl, "1")
        except JWTError:
            pass

        logger.info("user_logged_out", user_id=str(db_token.user_id))

    async def _revoke_all_tokens_and_commit(self, user_id: uuid.UUID) -> None:
        """
        Explicitly commits the revocation before returning.
        This is intentional — we need this to persist even though
        the calling method will raise an exception (which would
        normally trigger a rollback in get_db).
        """
        await self.db.execute(
            delete(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.is_revoked == False,  # noqa: E712
            )
        )
        await self.db.commit()  # explicit commit — survives the upcoming rollback
        logger.warning("all_tokens_revoked", user_id=str(user_id))

    async def update(self, user_id: uuid.UUID, data: UserUpdate) -> User:
        user = await self.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        if data.email and data.email != user.email:
            existing = await self.get_by_email(data.email)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already taken",
                )
            user.email = data.email
        if data.full_name:
            user.full_name = data.full_name
        logger.info("user_updated", user_id=str(user_id))
        return user
