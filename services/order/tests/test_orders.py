import uuid
import pytest
from tests.conftest import TEST_PRODUCT_ID, TEST_USER_ID


class TestHealth:
    async def test_health(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "order-service"


class TestAuth:
    async def test_jwt_rejects_malformed_token(self):
        """JWT dependency rejects malformed tokens directly."""
        from app.core.dependencies import get_current_user_id
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        creds = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="invalid.token.here"
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(creds)
        assert exc_info.value.status_code == 401

    async def test_jwt_rejects_refresh_token(self):
        """JWT with type=refresh is rejected — only access tokens allowed."""
        from app.core.dependencies import get_current_user_id
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials
        from jose import jwt
        from app.core.config import settings
        from datetime import datetime, timedelta, timezone

        payload = {
            "sub": str(TEST_USER_ID),
            "type": "refresh",
            "jti": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        }
        token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(creds)
        assert exc_info.value.status_code == 401


class TestCreateOrder:
    async def test_create_order_success(
        self, client, auth_headers, order_payload, product_mock, kafka_mock
    ):
        response = await client.post(
            "/api/v1/orders/", json=order_payload, headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "pending"
        assert data["user_id"] == str(TEST_USER_ID)
        assert data["shipping_address"] == order_payload["shipping_address"]
        assert len(data["items"]) == 1
        assert data["items"][0]["product_name"] == "MacBook Pro"
        assert data["items"][0]["quantity"] == 2
        assert float(data["total_amount"]) == pytest.approx(2599.98)

    async def test_create_order_publishes_kafka_event(
        self, client, auth_headers, order_payload, product_mock, kafka_mock
    ):
        await client.post(
            "/api/v1/orders/", json=order_payload, headers=auth_headers
        )
        kafka_mock.assert_called_once()
        call_kwargs = kafka_mock.call_args.kwargs
        assert call_kwargs["topic"] == "order.created"
        assert call_kwargs["event"]["event_type"] == "order.created"

    async def test_create_order_insufficient_stock(
        self, client, auth_headers, kafka_mock, mock_product
    ):
        mock_product["stock_quantity"] = 1
        from unittest.mock import patch, AsyncMock
        with patch(
            "app.services.order_service.get_product",
            new_callable=AsyncMock,
            return_value=mock_product,
        ):
            response = await client.post(
                "/api/v1/orders/",
                json={
                    "items": [{"product_id": str(TEST_PRODUCT_ID), "quantity": 5}],
                    "shipping_address": "123 Main St, Hyderabad, Telangana 500001",
                },
                headers=auth_headers,
            )
        assert response.status_code == 422
        assert "Insufficient stock" in str(response.json())

    async def test_create_order_product_not_found(
        self, client, auth_headers, kafka_mock
    ):
        from unittest.mock import patch, AsyncMock
        with patch(
            "app.services.order_service.get_product",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = await client.post(
                "/api/v1/orders/",
                json={
                    "items": [{"product_id": str(uuid.uuid4()), "quantity": 1}],
                    "shipping_address": "123 Main St, Hyderabad, Telangana 500001",
                },
                headers=auth_headers,
            )
        assert response.status_code == 422
        assert "not found" in str(response.json()).lower()

    async def test_create_order_missing_shipping_address(
        self, client, auth_headers, product_mock, kafka_mock
    ):
        response = await client.post(
            "/api/v1/orders/",
            json={"items": [{"product_id": str(TEST_PRODUCT_ID), "quantity": 1}]},
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_create_order_empty_items(
        self, client, auth_headers, product_mock, kafka_mock
    ):
        response = await client.post(
            "/api/v1/orders/",
            json={
                "items": [],
                "shipping_address": "123 Main St, Hyderabad, Telangana 500001",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_create_order_inactive_product(
        self, client, auth_headers, kafka_mock, mock_product
    ):
        mock_product["is_active"] = False
        from unittest.mock import patch, AsyncMock
        with patch(
            "app.services.order_service.get_product",
            new_callable=AsyncMock,
            return_value=mock_product,
        ):
            response = await client.post(
                "/api/v1/orders/",
                json={
                    "items": [{"product_id": str(TEST_PRODUCT_ID), "quantity": 1}],
                    "shipping_address": "123 Main St, Hyderabad, Telangana 500001",
                },
                headers=auth_headers,
            )
        assert response.status_code == 422
        assert "no longer available" in str(response.json())


class TestGetOrder:
    async def test_get_order(
        self, client, auth_headers, order_payload, product_mock, kafka_mock
    ):
        created = await client.post(
            "/api/v1/orders/", json=order_payload, headers=auth_headers
        )
        order_id = created.json()["id"]
        response = await client.get(
            f"/api/v1/orders/{order_id}", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["id"] == order_id

    async def test_get_order_not_found(self, client, auth_headers):
        response = await client.get(
            f"/api/v1/orders/{uuid.uuid4()}", headers=auth_headers
        )
        assert response.status_code == 404

    async def test_get_order_isolation(
        self, client, auth_headers, order_payload, product_mock, kafka_mock
    ):
        """Returns 404 (not 403) for another user's order — avoids leaking existence."""
        from app.core.dependencies import get_current_user_id
        from app.main import app as _app

        created = await client.post(
            "/api/v1/orders/", json=order_payload, headers=auth_headers
        )
        order_id = created.json()["id"]

        other_user_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        _app.dependency_overrides[get_current_user_id] = lambda: other_user_id

        try:
            response = await client.get(
                f"/api/v1/orders/{order_id}", headers=auth_headers
            )
            assert response.status_code == 404
        finally:
            _app.dependency_overrides[get_current_user_id] = lambda: TEST_USER_ID


class TestListOrders:
    async def test_list_orders_empty(self, client, auth_headers):
        response = await client.get("/api/v1/orders/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_orders(
        self, client, auth_headers, order_payload, product_mock, kafka_mock
    ):
        await client.post(
            "/api/v1/orders/", json=order_payload, headers=auth_headers
        )
        await client.post(
            "/api/v1/orders/", json=order_payload, headers=auth_headers
        )
        response = await client.get("/api/v1/orders/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["total"] == 2

    async def test_list_orders_filter_by_status(
        self, client, auth_headers, order_payload, product_mock, kafka_mock
    ):
        await client.post(
            "/api/v1/orders/", json=order_payload, headers=auth_headers
        )
        response = await client.get(
            "/api/v1/orders/?status_filter=pending", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["total"] == 1


class TestOrderStateMachine:
    async def test_confirm_order(
        self, client, auth_headers, order_payload, product_mock, kafka_mock
    ):
        created = await client.post(
            "/api/v1/orders/", json=order_payload, headers=auth_headers
        )
        order_id = created.json()["id"]
        response = await client.patch(
            f"/api/v1/orders/{order_id}/status",
            json={"status": "confirmed"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"

    async def test_invalid_state_transition(
        self, client, auth_headers, order_payload, product_mock, kafka_mock
    ):
        created = await client.post(
            "/api/v1/orders/", json=order_payload, headers=auth_headers
        )
        order_id = created.json()["id"]
        response = await client.patch(
            f"/api/v1/orders/{order_id}/status",
            json={"status": "shipped"},
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert "Invalid state transition" in response.json()["detail"]

    async def test_cancel_order(
        self, client, auth_headers, order_payload, product_mock, kafka_mock
    ):
        created = await client.post(
            "/api/v1/orders/", json=order_payload, headers=auth_headers
        )
        order_id = created.json()["id"]
        response = await client.delete(
            f"/api/v1/orders/{order_id}", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    async def test_cannot_cancel_delivered_order(
        self, client, auth_headers, order_payload, product_mock, kafka_mock
    ):
        created = await client.post(
            "/api/v1/orders/", json=order_payload, headers=auth_headers
        )
        order_id = created.json()["id"]
        for status in ["confirmed", "processing", "shipped", "delivered"]:
            await client.patch(
                f"/api/v1/orders/{order_id}/status",
                json={"status": status},
                headers=auth_headers,
            )
        response = await client.delete(
            f"/api/v1/orders/{order_id}", headers=auth_headers
        )
        assert response.status_code == 422
