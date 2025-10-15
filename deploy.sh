#!/bin/bash

# Lunalytics KOPF Operator Deployment Script

set -e

echo "🚀 Deploying Lunalytics KOPF Operator..."

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl is not installed or not in PATH"
    exit 1
fi

# Check if cluster is accessible
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Cannot access Kubernetes cluster. Please check your kubeconfig."
    exit 1
fi

echo "✅ Kubernetes cluster is accessible"

# Create namespace
echo "🏗️  Creating lunalytics-system namespace..."
kubectl create namespace lunalytics-system --dry-run=client -o yaml | kubectl apply -f -

# Apply CRD
echo "📋 Applying Custom Resource Definition..."
kubectl apply -f deploy/crd.yaml

# Apply RBAC
echo "🔐 Applying RBAC permissions..."
kubectl apply -f deploy/rbac.yaml

# Apply deployment
echo "🚢 Applying operator deployment..."
kubectl apply -f deploy/deployment.yaml

echo "⏳ Waiting for operator to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/lunalytics-operator

echo "✅ Lunalytics KOPF Operator deployed successfully!"

echo ""
echo "📊 Check operator status:"
echo "  kubectl get pods -l app.kubernetes.io/name=lunalytics-operator"
echo ""
echo "📝 View operator logs:"
echo "  kubectl logs -l app.kubernetes.io/name=lunalytics-operator -f"
echo ""
echo "🔧 Check Monitor CRDs:"
echo "  kubectl get monitors"
echo ""
echo "⚠️  Don't forget to update the API token in deploy/deployment.yaml!"
