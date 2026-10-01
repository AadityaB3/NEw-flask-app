# Product Service Kubernetes manifests

This directory contains the Kubernetes deployment manifests for the product service.

## Files

- `app_deployment.yml` - Deployment for the Flask product service
- `service.yml` - ClusterIP Service for the product app
- `ingress.yml` - Ingress routing for the product service

## Notes

These manifests expect the shared MySQL resources created for the order-service deployment to already exist:

- `mysql-config` ConfigMap
- `mysql-secret` Secret
- `order-db-service` Service

## Apply

```bash
kubectl apply -f .
```
