import pytest
from httpx import AsyncClient


class TestRegister:

    async def test_register_success(self, client: AsyncClient, user_data, redis_mock):
        response = await client.post("/api/v1/auth/register", json=user_data)

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == user_data["email"]
        assert data["full_name"] == user_data["full_name"]
        assert "id" in data
        assert "hashed_password" not in data  # never exposed
        assert "password" not in data         # never exposed

    async def test_register_duplicate_email(self, client: AsyncClient, user_data, redis_mock):
        # Register once
        await client.post("/api/v1/auth/register", json=user_data)
        # Register again with same email
        response = await client.post("/api/v1/auth/register", json=user_data)

        assert response.status_code == 409
        assert "already registered" in response.json()["detail"]

    async def test_register_weak_password(self, client: AsyncClient, redis_mock):
        response = await client.post("/api/v1/auth/register", json={
            "email": "test@shopflow.com",
            "password": "weakpass",   # no uppercase, no digit
            "full_name": "Test User",
        })
        assert response.status_code == 422

    async def test_register_short_password(self, client: AsyncClient, redis_mock):
        response = await client.post("/api/v1/auth/register", json={
            "email": "test@shopflow.com",
            "password": "Ab1",         # too short
            "full_name": "Test User",
        })
        assert response.status_code == 422

    async def test_register_invalid_email(self, client: AsyncClient, redis_mock):
        response = await client.post("/api/v1/auth/register", json={
            "email": "not-an-email",
            "password": "Secret123",
            "full_name": "Test User",
        })
        assert response.status_code == 422


class TestLogin:

    async def test_login_success(self, client: AsyncClient, user_data, redis_mock):
        await client.post("/api/v1/auth/register", json=user_data)
        response = await client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"],
        })

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 1800  # 30 minutes

    async def test_login_wrong_password(self, client: AsyncClient, user_data, redis_mock):
        await client.post("/api/v1/auth/register", json=user_data)
        response = await client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": "WrongPass123",
        })

        assert response.status_code == 401
        # Same error for wrong email and wrong password — security requirement
        assert response.json()["detail"] == "Invalid credentials"

    async def test_login_wrong_email(self, client: AsyncClient, redis_mock):
        response = await client.post("/api/v1/auth/login", json={
            "email": "nobody@shopflow.com",
            "password": "Secret123",
        })

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"


class TestTokenRefresh:

    async def test_refresh_success(self, client: AsyncClient, user_data, redis_mock):
        await client.post("/api/v1/auth/register", json=user_data)
        login = await client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"],
        })
        refresh_token = login.json()["refresh_token"]

        response = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token
        })

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        # New refresh token must be different from old one
        assert data["refresh_token"] != refresh_token

    async def test_refresh_token_replay_attack(self, client: AsyncClient, user_data, redis_mock):
        """
        Using a refresh token twice should:
        1. First use → success
        2. Second use → 401 AND all sessions revoked
        """
        await client.post("/api/v1/auth/register", json=user_data)
        login = await client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"],
        })
        refresh_token_1 = login.json()["refresh_token"]

        # First use — success, get token 2
        first = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token_1
        })
        assert first.status_code == 200
        refresh_token_2 = first.json()["refresh_token"]

        # Second use of token 1 — replay attack detected
        replay = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token_1
        })
        assert replay.status_code == 401
        assert "reuse detected" in replay.json()["detail"]

        # Token 2 also revoked — all sessions nuked
        third = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token_2
        })
        assert third.status_code == 401

    async def test_refresh_invalid_token(self, client: AsyncClient, redis_mock):
        response = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": "totally.fake.token"
        })
        assert response.status_code == 401


class TestLogout:

    async def test_logout_success(self, client: AsyncClient, user_data, redis_mock):
        await client.post("/api/v1/auth/register", json=user_data)
        login = await client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"],
        })
        tokens = login.json()

        response = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert response.status_code == 200

    async def test_logout_revoked_token_rejected(self, client: AsyncClient, user_data, redis_mock):
        await client.post("/api/v1/auth/register", json=user_data)
        login = await client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"],
        })
        tokens = login.json()

        # Logout once
        await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        # Logout again with same token — should fail
        response = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert response.status_code == 401


class TestGetCurrentUser:

    async def test_get_me_success(self, client: AsyncClient, user_data, redis_mock):
        await client.post("/api/v1/auth/register", json=user_data)
        login = await client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"],
        })
        access_token = login.json()["access_token"]

        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == user_data["email"]

    async def test_get_me_no_token(self, client: AsyncClient, redis_mock):
        response = await client.get("/api/v1/users/me")
        assert response.status_code == 403  # No auth header at all

    async def test_get_me_invalid_token(self, client: AsyncClient, redis_mock):
        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer fake.token.here"},
        )
        assert response.status_code == 401

    async def test_get_me_blocklisted_token(self, client: AsyncClient, user_data, redis_mock):
        """
        Simulates a token that was blocklisted in Redis after logout.
        The token signature is valid but Redis says it's revoked.
        """
        await client.post("/api/v1/auth/register", json=user_data)
        login = await client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"],
        })
        access_token = login.json()["access_token"]

        # Simulate Redis saying this token's jti is blocklisted
        redis_mock.exists.return_value = True

        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 401
        assert "revoked" in response.json()["detail"]
