import pytest


class TestHealth:
    async def test_health(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "product-service"


class TestCategories:
    async def test_create_category(self, client, admin_headers, category_data):
        response = await client.post("/api/v1/categories/", json=category_data, headers=admin_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Electronics"
        assert data["slug"] == "electronics"
        assert "id" in data

    async def test_create_category_slug_generated(self, client, admin_headers):
        response = await client.post("/api/v1/categories/",
            json={"name": "Home Garden", "description": "Home products"},
            headers=admin_headers)
        assert response.status_code == 201
        assert response.json()["slug"] == "home-garden"

    async def test_create_category_missing_name(self, client, admin_headers):
        response = await client.post("/api/v1/categories/",
            json={"description": "No name"}, headers=admin_headers)
        assert response.status_code == 422

    async def test_create_category_name_too_short(self, client, admin_headers):
        response = await client.post("/api/v1/categories/",
            json={"name": "A"}, headers=admin_headers)
        assert response.status_code == 422

    async def test_create_category_user_forbidden(self, client, user_headers, category_data):
        response = await client.post("/api/v1/categories/", json=category_data, headers=user_headers)
        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"

    async def test_create_category_no_token_forbidden(self, client, category_data):
        response = await client.post("/api/v1/categories/", json=category_data)
        assert response.status_code == 403

    async def test_list_categories_empty(self, client, user_headers):
        response = await client.get("/api/v1/categories/", headers=user_headers)
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_categories(self, client, admin_headers, user_headers, category_data):
        await client.post("/api/v1/categories/", json=category_data, headers=admin_headers)
        response = await client.get("/api/v1/categories/", headers=user_headers)
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["name"] == "Electronics"


class TestProducts:
    async def test_create_product_without_category(self, client, redis_mock, admin_headers, product_data):
        response = await client.post("/api/v1/products/", json=product_data, headers=admin_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "MacBook Pro"
        assert data["stock_quantity"] == 10
        assert data["category"] is None

    async def test_create_product_with_category(self, client, redis_mock, admin_headers, product_data, category_data):
        cat = await client.post("/api/v1/categories/", json=category_data, headers=admin_headers)
        category_id = cat.json()["id"]
        product_data["category_id"] = category_id
        response = await client.post("/api/v1/products/", json=product_data, headers=admin_headers)
        assert response.status_code == 201
        assert response.json()["category"]["name"] == "Electronics"

    async def test_create_product_user_forbidden(self, client, redis_mock, user_headers, product_data):
        response = await client.post("/api/v1/products/", json=product_data, headers=user_headers)
        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"

    async def test_create_product_rejects_unknown_field(self, client, redis_mock, admin_headers):
        response = await client.post("/api/v1/products/", json={
            "name": "Test", "price": "99.99", "stock": 10,
        }, headers=admin_headers)
        assert response.status_code == 422

    async def test_create_product_invalid_price(self, client, redis_mock, admin_headers):
        response = await client.post("/api/v1/products/", json={
            "name": "Test", "price": "-10.00", "stock_quantity": 5,
        }, headers=admin_headers)
        assert response.status_code == 422

    async def test_create_product_name_too_short(self, client, redis_mock, admin_headers):
        response = await client.post("/api/v1/products/", json={
            "name": "A", "price": "99.99",
        }, headers=admin_headers)
        assert response.status_code == 422

    async def test_get_product(self, client, redis_mock, admin_headers, user_headers, product_data):
        created = await client.post("/api/v1/products/", json=product_data, headers=admin_headers)
        product_id = created.json()["id"]
        response = await client.get(f"/api/v1/products/{product_id}", headers=user_headers)
        assert response.status_code == 200
        assert response.json()["name"] == "MacBook Pro"

    async def test_get_product_not_found(self, client, redis_mock, user_headers):
        response = await client.get(
            "/api/v1/products/00000000-0000-0000-0000-000000000000",
            headers=user_headers)
        assert response.status_code == 404

    async def test_list_products_empty(self, client, redis_mock, user_headers):
        response = await client.get("/api/v1/products/", headers=user_headers)
        assert response.status_code == 200
        assert response.json()["total"] == 0

    async def test_list_products(self, client, redis_mock, admin_headers, user_headers, product_data):
        await client.post("/api/v1/products/", json=product_data, headers=admin_headers)
        await client.post("/api/v1/products/", json={
            "name": "iPhone 15", "price": "999.99", "stock_quantity": 5,
        }, headers=admin_headers)
        response = await client.get("/api/v1/products/", headers=user_headers)
        assert response.status_code == 200
        assert response.json()["total"] == 2

    async def test_list_products_no_token(self, client, redis_mock):
        response = await client.get("/api/v1/products/")
        assert response.status_code == 403

    async def test_update_product(self, client, redis_mock, admin_headers, product_data, category_data):
        cat = await client.post("/api/v1/categories/", json=category_data, headers=admin_headers)
        category_id = cat.json()["id"]
        created = await client.post("/api/v1/products/", json=product_data, headers=admin_headers)
        product_id = created.json()["id"]
        response = await client.put(f"/api/v1/products/{product_id}", json={
            "name": "MacBook Pro M3", "price": "1499.99",
            "stock_quantity": 20, "category_id": category_id,
        }, headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["name"] == "MacBook Pro M3"

    async def test_update_product_user_forbidden(self, client, redis_mock, admin_headers, user_headers, product_data):
        created = await client.post("/api/v1/products/", json=product_data, headers=admin_headers)
        product_id = created.json()["id"]
        response = await client.put(f"/api/v1/products/{product_id}", json={
            "name": "Hacked", "price": "1.00", "stock_quantity": 1,
        }, headers=user_headers)
        assert response.status_code == 403

    async def test_delete_product(self, client, redis_mock, admin_headers, product_data):
        created = await client.post("/api/v1/products/", json=product_data, headers=admin_headers)
        product_id = created.json()["id"]
        response = await client.delete(f"/api/v1/products/{product_id}", headers=admin_headers)
        assert response.status_code == 204
        list_response = await client.get("/api/v1/products/", headers=admin_headers)
        assert list_response.json()["total"] == 0

    async def test_delete_product_user_forbidden(self, client, redis_mock, admin_headers, user_headers, product_data):
        created = await client.post("/api/v1/products/", json=product_data, headers=admin_headers)
        product_id = created.json()["id"]
        response = await client.delete(f"/api/v1/products/{product_id}", headers=user_headers)
        assert response.status_code == 403

    async def test_list_products_filter_by_category(self, client, redis_mock, admin_headers, user_headers, category_data):
        cat = await client.post("/api/v1/categories/", json=category_data, headers=admin_headers)
        category_id = cat.json()["id"]
        await client.post("/api/v1/products/", json={
            "name": "MacBook Pro", "price": "1299.99",
            "stock_quantity": 5, "category_id": category_id,
        }, headers=admin_headers)
        await client.post("/api/v1/products/", json={
            "name": "Running Shoes", "price": "99.99", "stock_quantity": 10,
        }, headers=admin_headers)
        response = await client.get(f"/api/v1/products/?category_id={category_id}", headers=user_headers)
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["items"][0]["name"] == "MacBook Pro"
