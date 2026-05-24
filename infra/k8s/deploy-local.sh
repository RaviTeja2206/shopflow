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

# 3. Deploy infrastructure (postgres, redis, kafka)
echo "Deploying infrastructure..."
kubectl apply -f infra/k8s/postgres/pvc.yaml
kubectl apply -f infra/k8s/postgres/deployment.yaml
kubectl apply -f infra/k8s/postgres/service.yaml
kubectl apply -f infra/k8s/redis/deployment.yaml
kubectl apply -f infra/k8s/redis/service.yaml
kubectl apply -f infra/k8s/kafka/deployment.yaml
kubectl apply -f infra/k8s/kafka/service.yaml

# 4. Wait for infrastructure to be ready
echo "Waiting for postgres..."
kubectl wait --for=condition=ready pod -l app=postgres \
  -n shopflow-production --timeout=120s

echo "Waiting for redis..."
kubectl wait --for=condition=ready pod -l app=redis \
  -n shopflow-production --timeout=60s

echo "Waiting for kafka..."
kubectl wait --for=condition=ready pod -l app=kafka \
  -n shopflow-production --timeout=120s

# 5. Deploy application services
echo "Deploying application services..."
for svc in user product order notification; do
  kubectl apply -f infra/k8s/services/$svc/deployment.yaml
  kubectl apply -f infra/k8s/services/$svc/service.yaml
done

# 6. Apply ingress
echo "Applying ingress..."
kubectl apply -f infra/k8s/ingress.yaml

echo ""
echo "=== Deployment complete! ==="
echo ""
echo "Check status:"
echo "  kubectl get pods -n shopflow-production"
echo ""
echo "Get minikube IP:"
echo "  minikube ip"
echo ""
echo "Open tunnel for ingress (run in separate terminal):"
echo "  minikube tunnel"
