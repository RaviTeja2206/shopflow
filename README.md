# ShopFlow — Production-Grade E-Commerce Microservices Platform

A fully functional e-commerce backend built with microservices architecture, demonstrating production patterns: async Python, event-driven communication, JWT auth with replay attack detection, CI/CD, and Kubernetes deployment.

**Live CI/CD:** [![CI](https://github.com/RaviTeja2206/shopflow/actions/workflows/ci.yml/badge.svg)](https://github.com/RaviTeja2206/shopflow/actions/workflows/ci.yml)

---

## Architecture

                        ┌─────────────────────────────────────────┐
                        │           Kubernetes Cluster            │
                        │                                         │
      Client ──────────▶│  Ingress (nginx)                        │
                        │       │                                 │
                        │  ┌────▼────┐  ┌──────────┐              │
                        │  │  User   │  │ Product  │              │
                        │  │Service  │  │ Service  │              │
                        │  │ :8001   │  │  :8002   │              │
                        │  └────┬────┘  └────┬─────┘              │
                        │       │            │                    │
                        │  ┌────▼────────────▼──────┐             │
                        │  │     Order Service      │             │
                        │  │        :8003           │             │
                        │  └────────────┬───────────┘             │
                        │               │ Kafka                   │
                        │  ┌────────────▼───────────┐             │
                        │  │  Notification Service  │             │
                        │  │        :8004           │             │
                        │  └────────────────────────┘             │
                        │                                         │
                        │  PostgreSQL  Redis  Kafka  Zookeeper    │
                        └─────────────────────────────────────────┘

### Services

| Service | Port | Responsibility |
|---------|------|----------------|
| user-service | 8001 | Auth, JWT, user management |
| product-service | 8002 | Product catalog, categories, inventory |
| order-service | 8003 | Order lifecycle, inter-service HTTP, Kafka producer |
| notification-service | 8004 | Kafka consumer, email notifications |

### Infrastructure

| Component | Purpose |
|-----------|---------|
| PostgreSQL | Primary database with 3 schemas (users, products, orders) |
| Redis | JWT blocklist for immediate token revocation |
| Kafka | Async event bus (order.created, order.updated, order.cancelled) |
| Prometheus + Grafana | Metrics and dashboards |

---

## Key Technical Decisions

### Single Database, Three Schemas
Rather than 3 separate databases, we use one PostgreSQL instance with separate schemas (`users`, `products`, `orders`). This gives logical isolation without the operational complexity of managing multiple databases. Services reference each other by UUID only — no cross-schema foreign keys.

### JWT with Replay Attack Detection
Refresh tokens are stored as SHA-256 hashes (never plaintext). On refresh, the old token is immediately invalidated. If a token is used twice, it triggers `_revoke_all_tokens_and_commit()` — all tokens for that user are revoked and an explicit commit happens *before* raising the HTTP exception (critical: HTTPException triggers SQLAlchemy session rollback, so the commit must happen first).

### Price Snapshotting
When an order is created, `product_name` and `unit_price` are copied into the `OrderItem` row. This ensures historical order accuracy even if the product price changes later.

### Async Throughout
Every service uses FastAPI + SQLAlchemy async + asyncpg. Database queries never block the event loop. Connection pooling is handled per-service with keepalive settings.

### Kafka Partition Key = user_id
Order events are published with `user_id` as the partition key. This guarantees that all events for a given user land on the same partition, preserving ordering for per-user event streams.

---

## Project Structure
    shopflow/
    ├── services/
    │   ├── user/           # Auth, JWT, Redis blocklist
    │   ├── product/        # Catalog, Redis cache-aside
    │   ├── order/          # State machine, HTTP client, Kafka producer
    │   └── notification/   # Kafka consumer
    ├── infra/
    │   └── k8s/            # Kubernetes manifests
    │       ├── postgres/
    │       ├── redis/
    │       ├── kafka/
    │       ├── services/
    │       └── ingress.yaml
    ├── .github/
    │   └── workflows/
    │       ├── ci.yml      # Test → Lint → Build → Push to ghcr.io
    │       └── cd.yml      # Staging → Approval → Production (stub)
    └── docker-compose.yml  # Local development

    Each service follows the same internal structure:
    services/{service}/
    ├── app/
    │   ├── api/v1/router.py
    │   ├── core/          # config, logging, security, redis, dependencies
    │   ├── db/            # base models, session
    │   ├── models/        # SQLAlchemy ORM models
    │   ├── schemas/       # Pydantic request/response schemas
    │   └── services/      # Business logic
    ├── alembic/           # Database migrations
    ├── tests/
    ├── Dockerfile
    ├── requirements.txt
    └── requirements-dev.txt

---

## Running Locally

### Prerequisites
- Docker Desktop
- Docker Compose

### Start all services
```bash
git clone https://github.com/RaviTeja2206/shopflow.git
cd shopflow
cp .env.example .env
docker compose up -d
```

Services available at:
- User: http://localhost:8001/docs
- Product: http://localhost:8002/docs
- Order: http://localhost:8003/docs
- Notification: http://localhost:8004/docs
- Grafana: http://localhost:3000

### Run migrations
```bash
make migrate
```

### Run tests
```bash
make test
# or for a specific service:
docker compose exec user-service python -m pytest tests/ -v
```

---

## Kubernetes (Minikube)

### Prerequisites
```bash
brew install minikube kubectl
minikube start --cpus=4 --memory=5120 --driver=docker
minikube addons enable ingress
```

### Deploy
```bash
# Create secrets file (not committed to git)
cp infra/k8s/secrets.yaml infra/k8s/secrets-local.yaml
# Edit secrets-local.yaml with real values

./infra/k8s/deploy-local.sh
```

### Run migrations on cluster
```bash
kubectl run migrate-user \
  --image=ghcr.io/raviteja2206/shopflow-user:latest \
  --restart=Never \
  --namespace=shopflow-production \
  --env="DATABASE_URL=postgresql+asyncpg://shopflow:PASSWORD@postgres-service:5432/shopflow" \
  --command -- sh -c "alembic upgrade head"
```

### Test the API
```bash
# Port-forward services
kubectl port-forward svc/user-service 8001:8000 -n shopflow-production &
kubectl port-forward svc/order-service 8003:8000 -n shopflow-production &

# Register
curl -X POST http://localhost:8001/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"Secret123","full_name":"Test User"}'

# Login
TOKEN=$(curl -s -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"Secret123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Create order
curl -X POST http://localhost:8003/api/v1/orders/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"items":[{"product_id":"PRODUCT_UUID","quantity":1}],"shipping_address":"123 Main St"}'
```

---

## CI/CD Pipeline
                Push to main
                    │
                    ▼
    ┌─────────────────────────────────────┐
    │  Test Matrix (parallel)             │
    │  ├── pytest user-service (30 tests) │
    │  ├── pytest product-service         │
    │  └── pytest order-service           │
    └───────────────┬─────────────────────┘
                    │ all pass
                    ▼
                    Lint (ruff)
                    │ pass
                    ▼
                    Build & Push to ghcr.io
                    ├── shopflow-user:latest
                    ├── shopflow-product:latest
                    ├── shopflow-order:latest
                    └── shopflow-notification:latest

Docker images: `ghcr.io/raviteja2206/shopflow-{service}:latest`

---

## API Reference

### Authentication Flow
    POST /api/v1/auth/register    # Create account
    POST /api/v1/auth/login       # Get access + refresh tokens
    POST /api/v1/auth/refresh     # Rotate refresh token
    POST /api/v1/auth/logout      # Revoke token (Redis blocklist)
    GET  /api/v1/users/me         # Get current user (requires JWT)

### Products
    GET    /api/v1/products/              # List with filters (category, price, search)
    POST   /api/v1/products/              # Create product
    GET    /api/v1/products/{id}          # Get product
    PUT    /api/v1/products/{id}          # Update product
    DELETE /api/v1/products/{id}          # Soft delete
    GET    /api/v1/categories/            # List categories
    POST   /api/v1/categories/            # Create category

### Orders
    POST /api/v1/orders/              # Create order (validates stock, snapshots prices)
    GET  /api/v1/orders/              # List user's orders
    GET  /api/v1/orders/{id}          # Get order details
    PUT  /api/v1/orders/{id}/status   # Update status (state machine)

---

## Order State Machine
    PENDING ──────────────────────────────────────▶ CANCELLED
    │                                                   ▲
    ▼                                                   │
    CONFIRMED ──────────────────────────────────────────┤
    │                                                   │
    ▼                                                   │
    PROCESSING ─────────────────────────────────────────┤
    │                                                   │
    ▼                                                   │
    SHIPPED                                             │
    │                                                   │
    ▼                                                   │
    DELIVERED                                           │

Invalid transitions are rejected at the model level — `can_transition_to()` is called before any state change.

---

## Testing

```bash
# User service — 30 tests covering:
# - Registration validation
# - Login / wrong password / wrong email
# - Token refresh + rotation
# - Replay attack detection
# - Logout + Redis blocklist
# - JWT claims, hashing, security utilities
docker compose exec user-service python -m pytest tests/ -v
```

Test infrastructure highlights:
- Session-scoped async event loop (prevents asyncpg Future loop mismatch)
- Production-like `get_db` override — each request commits independently
- Multi-path Redis mock covers all import locations
- Separate DELETE statements per table (asyncpg rejects semicolon-joined SQL)

---

## Known Limitations & Production TODOs

These are intentional trade-offs for a portfolio project:

| Gap | Production Solution |
|-----|---------------------|
| K8s migrations | ✅ Implemented as K8s Jobs (infra/k8s/jobs/) |
| Postgres in K8s | AWS RDS (managed, automatic backups) |
| Single postgres replica | RDS Multi-AZ |
| No rate limiting | nginx-ingress rate limit annotations |
| No email sending | AWS SES integration in notification-service |
| CD pipeline stubbed | Requires AWS EKS + Terraform (see infra/k8s/) |
| No distributed tracing | OpenTelemetry + Jaeger |
| HPA untested under load | k6 load tests + HPA verification |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.11 |
| Framework | FastAPI |
| ORM | SQLAlchemy 2.0 (async) |
| Database driver | asyncpg |
| Migrations | Alembic |
| Auth | python-jose (JWT) + passlib (bcrypt) |
| Cache/Blocklist | Redis (redis-py async) |
| Message bus | Apache Kafka (aiokafka) |
| HTTP client | httpx (async) |
| Validation | Pydantic v2 |
| Observability | Prometheus + Grafana |
| Containerization | Docker + Docker Compose |
| Orchestration | Kubernetes (manifests in infra/k8s/) |
| CI/CD | GitHub Actions |
| Registry | GitHub Container Registry (ghcr.io) |
| Linting | ruff |
| Testing | pytest + pytest-asyncio + httpx |

---

## Author

Ravi Teja — [GitHub](https://github.com/RaviTeja2206)