import pytest
import time
from jose import jwt
from app.core.security import (
    hash_password,
    verify_password,
    hash_token,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.config import settings


class TestPasswordHashing:

    def test_hash_is_not_plaintext(self):
        hashed = hash_password("Secret123")
        assert hashed != "Secret123"

    def test_verify_correct_password(self):
        hashed = hash_password("Secret123")
        assert verify_password("Secret123", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("Secret123")
        assert verify_password("WrongPass", hashed) is False

    def test_same_password_different_hashes(self):
        """bcrypt uses random salt — same input, different output each time."""
        hash1 = hash_password("Secret123")
        hash2 = hash_password("Secret123")
        assert hash1 != hash2
        # But both verify correctly
        assert verify_password("Secret123", hash1)
        assert verify_password("Secret123", hash2)


class TestTokenHashing:

    def test_hash_token_deterministic(self):
        """SHA-256 is deterministic — same input always same output."""
        token = "some.jwt.token"
        assert hash_token(token) == hash_token(token)

    def test_different_tokens_different_hashes(self):
        assert hash_token("token.one") != hash_token("token.two")

    def test_hash_is_hex_string(self):
        hashed = hash_token("any.token")
        assert len(hashed) == 64  # SHA-256 = 32 bytes = 64 hex chars
        int(hashed, 16)  # raises ValueError if not valid hex


class TestJWTTokens:

    def test_access_token_contains_correct_claims(self):
        token = create_access_token(subject="user-123")
        payload = decode_token(token)

        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"
        assert "jti" in payload   # unique ID present
        assert "exp" in payload   # expiry present

    def test_refresh_token_type(self):
        token = create_refresh_token(subject="user-123")
        payload = decode_token(token)
        assert payload["type"] == "refresh"

    def test_access_and_refresh_different_jti(self):
        """Every token gets a unique jti — no two tokens are identical."""
        t1 = create_access_token(subject="user-123")
        t2 = create_access_token(subject="user-123")
        assert decode_token(t1)["jti"] != decode_token(t2)["jti"]

    def test_decode_invalid_token_raises(self):
        from jose import JWTError
        with pytest.raises(JWTError):
            decode_token("completely.fake.token")

    def test_decode_wrong_secret_raises(self):
        from jose import JWTError
        token = create_access_token(subject="user-123")
        # Tamper: decode with wrong secret
        with pytest.raises(JWTError):
            jwt.decode(token, "wrong-secret", algorithms=[settings.algorithm])

    def test_extra_data_included_in_token(self):
        token = create_access_token(
            subject="user-123",
            extra_data={"role": "admin"}
        )
        payload = decode_token(token)
        assert payload["role"] == "admin"
