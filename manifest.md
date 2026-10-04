# Kubernetes Manifest Developer Guide

This guide explains what each Kubernetes YAML file does, which settings the Flask services need, and how to build and apply the manifests in this repository.

## What a manifest is

A Kubernetes manifest is a YAML description of a resource you want Kubernetes to create. For example, a `Deployment` says which container image to run and how many replicas to keep running. `kubectl apply` creates or updates resources to match those descriptions.

The manifests in this project currently create the resources in the `default` namespace. Apply the services and their dependencies in the same namespace so references such as `product-db-service` resolve through Kubernetes DNS.

## Prerequisites

- A Kubernetes cluster, such as Docker Desktop Kubernetes, Minikube, or kind.
- `kubectl` configured to use that cluster.
- Docker, for building the service images.
- An Ingress controller if you plan to use either Ingress manifest. An Ingress object alone does not install a controller.

Check that `kubectl` is pointed at the cluster you intend to change:

```sh
kubectl config current-context
kubectl get nodes
```

## Resource map

### Order Service: `order-service/manifests/`

| File | Resource and purpose |
| --- | --- |
| `configMap.yml` | ConfigMap `order-db-config`; holds the non-secret database name `order_db`. |
| `app_secret.yml` | Secret `order-db-secret`; holds MySQL root and application credentials. |
| `pvc.yml` | PersistentVolumeClaim `order-db-pvc`; requests 1 GiB for MySQL data. |
| `DB_deployment.yml` | MySQL Deployment; reads its credentials and database name from the Secret and ConfigMap and mounts the PVC. |
| `DB_service.yml` | ClusterIP Service `order-db-service`; gives the order database a stable in-cluster address on port 3306. |
| `app_deployment.yml` | Order Flask Deployment; runs three replicas on port 5002 and configures its database and Product Service URL. |
| `service.yml` | Service `order-service`; exposes port 5002 as a `LoadBalancer`. |
| `ingress.yml` | Host-based Ingress route for `order-service.local`. |

### Product Service: `product-service/manifests/`

| File | Resource and purpose |
| --- | --- |
| `product-db-config.yml` | ConfigMap `product-db-config`; holds database name `product_db`. |
| `product-db-secret.yml` | Secret `product-db-secret`; holds MySQL root and application credentials. |
| `product-db-pvc.yml` | PersistentVolumeClaim `product-db-pvc`; requests 1 GiB for MySQL data. |
| `product-db-deployment.yml` | MySQL Deployment for Product Service; mounts its PVC and reads the Secret and ConfigMap. |
| `product-db-service.yml` | ClusterIP Service `product-db-service`; stable in-cluster MySQL address on port 3306. |
| `app_deployment.yml` | Product Flask Deployment; runs two replicas on port 5001 and configures its database. |
| `service.yml` | ClusterIP Service `product-service`; provides in-cluster access on port 5001. |
| `ingress.yml` | Host-based Ingress route for `product-service.local`. |

## Application environment

The Deployments provide these environment variables to the containers:

| Variable | Order Service | Product Service | Purpose |
| --- | --- | --- | --- |
| `DB_HOST` | `order-db-service` | `product-db-service` | Database Service name; do not use `localhost` between containers. |
| `DB_PORT` | `3306` | `3306` | MySQL port. |
| `DB_NAME` | From ConfigMap key `MYSQL_DATABASE` (`order_db`) | From ConfigMap key `MYSQL_DATABASE` (`product_db`) | Database/schema name. |
| `DB_USER` | From Secret key `MYSQL_USER` | From Secret key `MYSQL_USER` | Application database user. |
| `DB_PASSWORD` | From Secret key `MYSQL_PASSWORD` | From Secret key `MYSQL_PASSWORD` | Application database password. |
| `PRODUCT_SERVICE_URL` | `http://product-service:5001` | Not used | Order Service calls Product Service using its Kubernetes Service DNS name. |

The MySQL containers also receive `MYSQL_ROOT_PASSWORD`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DATABASE`. The root and application credentials must agree between the database Deployment and the application Deployment's Secret references.

The Kubernetes manifests deliberately configure separate databases for these two services. This differs from the Docker Compose setup documented in `DEVOPS.md`, which describes a shared MySQL database. Orders store a product ID and validate it by calling Product Service; Order Service does not need direct access to the product database.

## Set credentials safely

The checked-in Secret manifests contain example credentials encoded as Base64. Base64 is encoding, not encryption, so replace those values before deploying anywhere shared or persistent. Do not put real credentials in Git.

For a local learning cluster, edit each Secret manifest and use `stringData` so Kubernetes performs the Base64 conversion. For example, replace the `data` block in `app_secret.yml` with local-only values in this shape:

```yaml
stringData:
  MYSQL_ROOT_PASSWORD: replace-with-a-unique-root-password
  MYSQL_USER: replace-with-an-app-user
  MYSQL_PASSWORD: replace-with-a-different-app-password
```

Do the equivalent in `product-db-secret.yml`. Keep `MYSQL_USER` and `MYSQL_PASSWORD` the same between the corresponding database Secret and application Secret reference; the application Deployment references the Secret rather than repeating the values. For a shared or production cluster, use an external secret manager or a protected deployment pipeline instead of committing plaintext Secret YAML.

`MYSQL_DATABASE` is not secret and belongs in the ConfigMap. Keep the referenced ConfigMap and Secret names/keys in the Deployments synchronized if you rename any resources.

## Build images

The Deployments use local image tags `order-service:latest` and `product-service:latest`. Build from the repository root, using each service directory as its Docker build context:

```sh
docker build -t product-service:latest -f product-service/Dockerfile product-service
docker build -t order-service:latest -f order-service/Dockerfile order-service
```

The Kubernetes nodes must be able to access these images. Docker Desktop Kubernetes generally shares the local Docker image store. With Minikube, load each image after building:

```sh
minikube image load product-service:latest
minikube image load order-service:latest
```

With kind, load them into the selected cluster:

```sh
kind load docker-image product-service:latest
kind load docker-image order-service:latest
```

For EKS, a Docker image on your computer is not automatically available to cluster nodes. These Deployments use `imagePullPolicy: Never`, so before applying them you must transfer/import each built image into the container runtime on **every EKS worker node**. Pods will fail with `ErrImageNeverPull` if a scheduled node does not have the image. Newly added or replaced nodes will also need the images, so this approach is fragile for scaling and node replacement; a container registry is the recommended option for EKS.

For registry-based deployment, push tagged images to a registry the nodes can access, update the `image` values in both application Deployments to those registry paths, and change `imagePullPolicy` from `Never` to `IfNotPresent` (or `Always`). Do not expect a remote cluster to see images that exist only on your laptop.

## Apply in dependency order

Run these commands from the repository root. Create configuration, credentials, and storage claims first; then databases; then application workloads and Services; and finally optional Ingress routes.

```sh
# Order database configuration, credentials, and storage
kubectl apply -f order-service/manifests/configMap.yml
kubectl apply -f order-service/manifests/app_secret.yml
kubectl apply -f order-service/manifests/pvc.yml
kubectl apply -f order-service/manifests/DB_deployment.yml
kubectl apply -f order-service/manifests/DB_service.yml

# Product database configuration, credentials, and storage
kubectl apply -f product-service/manifests/product-db-config.yml
kubectl apply -f product-service/manifests/product-db-secret.yml
kubectl apply -f product-service/manifests/product-db-pvc.yml
kubectl apply -f product-service/manifests/product-db-deployment.yml
kubectl apply -f product-service/manifests/product-db-service.yml

# Applications and their Services
kubectl apply -f product-service/manifests/app_deployment.yml
kubectl apply -f product-service/manifests/service.yml
kubectl apply -f order-service/manifests/app_deployment.yml
kubectl apply -f order-service/manifests/service.yml

# Optional external HTTP routing; requires an installed Ingress controller
kubectl apply -f product-service/manifests/ingress.yml
kubectl apply -f order-service/manifests/ingress.yml
```

Order Service calls Product Service, so deploying Product Service first avoids initial connection errors. The API retries that call on later requests; Kubernetes does not guarantee that every dependency is ready just because its Deployment was submitted first.

Check status and troubleshoot using:

```sh
kubectl get pods,services,pvc,ingress
kubectl get deployments
kubectl describe pod <pod-name>
kubectl logs deployment/product-service
kubectl logs deployment/order-service
```

PVCs can remain `Pending` when the cluster has no default StorageClass capable of provisioning them. A database Pod may wait until its claim is bound. Database Deployments currently use a single replica; do not increase replicas for these standalone MySQL containers as a way to create a highly available database.

The MySQL image uses its initialization variables only when `/var/lib/mysql` is empty. Updating a Secret does not change credentials already initialized in a persistent volume; rotate the database account deliberately or recreate the database storage only when its data can be discarded.

## Check access

The Product Service ClusterIP is intended for in-cluster traffic, including Order Service. The Order Service is configured as a `LoadBalancer`, so a local cluster may show `<pending>` unless it provides a load balancer implementation. You can test either API without changing the manifests by forwarding a local port:

```sh
kubectl port-forward service/product-service 5001:5001
kubectl port-forward service/order-service 5002:5002
```

Run one port-forward command per terminal, then use `http://localhost:5001/health` and `http://localhost:5002/health`. The health endpoint checks HTTP responsiveness, not database connectivity. A request to `/products` or `/orders` exercises the database connection.

The Ingress hosts are `product-service.local` and `order-service.local`. To use them, install an Ingress controller, point those hostnames at the controller's address (for a local cluster, this may mean adding entries to your hosts file), and make sure the controller can reach the Services. The current Ingress annotations rewrite requests to `/`; that can interfere with routes such as `/products` and `/orders`. Before relying on Ingress for API paths, remove or correct the rewrite annotation and verify the controller's routing behavior.

## Common edits when creating or changing a manifest

- Use a stable resource name and match the Deployment's pod labels to the Service selector. A selector mismatch leaves the Service with no endpoints.
- Keep container ports, Service `targetPort`, and the Flask port aligned: Product Service uses 5001 and Order Service uses 5002.
- Put non-sensitive settings such as database names in a ConfigMap; put passwords in a Secret or external secret manager.
- Use `valueFrom.configMapKeyRef` and `valueFrom.secretKeyRef` in Deployments so application settings are not duplicated as literals.
- Use a PVC for database files under `/var/lib/mysql`; a container filesystem alone is not durable across Pod replacement.
- Rebuild and load/push a new application image after changing application code. For a non-`latest` tag, update the Deployment image to that exact tag.
- Validate YAML and resources before rollout with `kubectl apply --dry-run=client -f <manifest.yml>`, then inspect rollout status with `kubectl rollout status deployment/<deployment-name>`.

These manifests are a learning setup, not a production baseline. Before production use, add managed secret handling, resource requests and limits, readiness/liveness probes, image tags pinned to versions or digests, database backup and recovery, TLS, and an intentional database migration strategy.