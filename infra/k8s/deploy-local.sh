#!/bin/bash
set -e

echo "=== Deploying ShopFlow to Minikube ==="

# 1. Create namespaces
echo "Creating namespaces..."
kubectl apply -f infra/k8s/namespaces.yaml

# 2. Apply config and secrets
echo "Applying config and secrets..."
kubectl apply -f infra/k8s/configmap.yaml
kubectl apply -f infra/k8s/secrets-local.yaml

# 3. Deploy infrastructure
echo "Deploying infrastructure..."
kubectl apply -f infra/k8s/postgres/pvc.yaml
kubectl apply -f infra/k8s/postgres/deployment.yaml
kubectl apply -f infra/k8s/postgres/service.yaml
kubectl apply -f infra/k8s/redis/deployment.yaml
kubectl apply -f infra/k8s/redis/service.yaml
kubectl apply -f infra/k8s/kafka/deployment.yaml
kubectl apply -f infra/k8s/kafka/service.yaml

# 4. Wait for postgres (required for migrations)
echo "Waiting for postgres..."
kubectl wait --for=condition=ready pod -l app=postgres \
  -n shopflow-production --timeout=120s

echo "Waiting for redis..."
kubectl wait --for=condition=ready pod -l app=redis \
  -n shopflow-production --timeout=60s

echo "Waiting for kafka..."
kubectl wait --for=condition=ready pod -l app=kafka \
  -n shopflow-production --timeout=120s

# 5. Run migrations
echo ""
echo "Running database migrations..."

# Delete old migration jobs if they exist (jobs are immutable)
kubectl delete job migrate-schemas migrate-user migrate-product migrate-order \
  -n shopflow-production --ignore-not-found

kubectl apply -f infra/k8s/jobs/migrate.yaml

echo "Waiting for schema setup..."
kubectl wait --for=condition=complete job/migrate-schemas \
  -n shopflow-production --timeout=120s

echo "Waiting for user migrations..."
kubectl wait --for=condition=complete job/migrate-user \
  -n shopflow-production --timeout=120s

echo "Waiting for product migrations..."
kubectl wait --for=condition=complete job/migrate-product \
  -n shopflow-production --timeout=120s

echo "Waiting for order migrations..."
kubectl wait --for=condition=complete job/migrate-order \
  -n shopflow-production --timeout=120s

echo "✅ All migrations complete"

# 6. Deploy application services
echo ""
echo "Deploying application services..."
for svc in user product order notification; do
  kubectl apply -f infra/k8s/services/$svc/deployment.yaml
  kubectl apply -f infra/k8s/services/$svc/service.yaml
done

# 7. Apply ingress
echo "Applying ingress..."
kubectl apply -f infra/k8s/ingress.yaml

echo ""
echo "=== Deployment complete! ==="
echo ""
echo "Check status:  kubectl get pods -n shopflow-production"
echo "Run tunnel:    minikube tunnel"
echo "Port-forward:  kubectl port-forward svc/user-service 8001:8000 -n shopflow-production"
