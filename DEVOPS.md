# DevOps Handoff

This guide describes how this application is packaged and operated today. It is a small learning deployment using Docker Compose on one host, not a highly available production platform.

## Architecture

Product Service owns product API operations and the `products` table. Order Service owns order API operations and the `orders` table. Before saving an order, Order Service calls Product Service over HTTP to verify the product. Both services connect to the same MySQL database/schema, but each service has its own SQLAlchemy model and table.

```text
Client -----------------------> product-service:5001 -----> mysql:3306
                                  products API                products table

Client -----------------------> order-service:5002 --------> mysql:3306
                                  |                           orders table
                                  +---- HTTP ----------------> product-service:5001
```

`orders.product_id` is checked through the Product Service API. It is not a MySQL foreign key, and Order Service does not query the product table directly.

## Project Layout

```text
microservices-demo/
|-- .env                         Local Compose variables; keep private
|-- docker-compose.yml           Services, network, health checks, volume
|-- DEVOPS.md                    This operating guide
|-- README.md                    Application and local development guide
|-- product-service/
|   |-- app.py                   Flask application, port 5001
|   |-- models.py                Product SQLAlchemy model
|   |-- requirements.txt         Python dependencies
|   |-- Dockerfile               Product image definition
|   `-- .dockerignore            Product build-context exclusions
`-- order-service/
    |-- app.py                   Flask application, port 5002
    |-- models.py                Order SQLAlchemy model
    |-- requirements.txt         Python dependencies, including requests
    |-- Dockerfile               Order image definition
    `-- .dockerignore            Order build-context exclusions
```

## Containers and Build

| Compose service | Image | Process | Container port | Host mapping |
| --- | --- | --- | --- | --- |
| `product-service` | Built from `product-service/Dockerfile` (`python:3.12-slim`) | Gunicorn `app:app` | `5001` | `5001:5001` |
| `order-service` | Built from `order-service/Dockerfile` (`python:3.12-slim`) | Gunicorn `app:app` | `5002` | `5002:5002` |
| `mysql` | Official `mysql:8.4` image | MySQL server | `3306` | `3306:3306` |

Each Python Dockerfile installs its service's `requirements.txt` and Gunicorn, copies only `app.py` and `models.py`, and runs as a non-root user. The code is copied into the image, not mounted from the host. Rebuild the image after application or dependency changes. The dependency versions and image digests are not pinned, so identical rebuilds are not guaranteed over time.

## Configuration and Secrets

Compose reads `.env` beside `docker-compose.yml` for variable substitution. The Compose file passes these values to MySQL and maps them to the Flask services:

| Variable | Compose value / purpose |
| --- | --- |
| `MYSQL_DATABASE` | Database name; defaults to `microservices_db` |
| `MYSQL_USER` | Required non-root application database user |
| `MYSQL_PASSWORD` | Required application database password |
| `MYSQL_ROOT_PASSWORD` | Required MySQL root password |
| `DB_HOST` | Set to `mysql` in both Flask containers |
| `DB_PORT` | Set to `3306` in both Flask containers |
| `DB_NAME` | Set from `MYSQL_DATABASE` in both Flask containers |
| `DB_USER`, `DB_PASSWORD` | Set from `MYSQL_USER`, `MYSQL_PASSWORD` |
| `PRODUCT_SERVICE_URL` | Set to `http://product-service:5001` for Order Service |

The current `.env` contains weak, reused local credentials. Replace them with different strong values before using this project on EC2 or sharing it. Never commit `.env`; make sure it is covered by the repository's `.gitignore` before staging files. The project currently has no root `.gitignore`. Environment variables are convenient for this demo, but are not a production secrets-management system; container environment values can be inspected by users with Docker access.

An example local `.env` shape is:

```dotenv
MYSQL_DATABASE=microservices_db
MYSQL_USER=your_app_user
MYSQL_PASSWORD=replace_with_a_unique_long_password
MYSQL_ROOT_PASSWORD=replace_with_a_different_unique_long_password
```

Do not use these placeholder values as real credentials. On an EC2 host, create `.env` directly on the instance, restrict its permissions (for example, `chmod 600 .env`), and use a secrets manager for production workloads where available.

## Startup and Database Initialization

Compose starts MySQL and waits for its healthcheck before starting either Flask service. Order Service additionally waits for Product Service's HTTP healthcheck. The MySQL healthcheck runs `mysqladmin ping`; it checks that the database server is responding, not merely that the container process exists.

There are two separate initialization steps:

1. On a new, empty `mysql_data` volume, the MySQL image uses `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_ROOT_PASSWORD` to create the database and users.
2. SQLAlchemy creates each service's table using `db.create_all()` when that service receives its first database-backed request in the Docker deployment.

The second step is intentionally worth knowing: the Dockerfiles start Gunicorn with `app:app`. That does not execute the Python `if __name__ == "__main__"` startup block. A request to `/health` also skips database initialization. Therefore, a healthy container immediately after `docker compose up` does not prove that tables exist or that a database query succeeds. A first request such as `GET /products` or `GET /orders` triggers table creation. If MySQL is unavailable, database-backed endpoints return JSON `503` responses and initialization is retried on later requests.

`db.create_all()` creates missing tables; it does not migrate existing schemas. There is no Alembic migration setup. Plan a schema migration process before making schema changes to a persistent deployment.

The MySQL initialization environment variables are applied only when the data directory is empty. Updating `.env` does not update an account/password stored in an existing `mysql_data` volume. Credentials must match the initialized database, or the MySQL account must be changed deliberately.

The Flask `/health` endpoints only report that the HTTP endpoint responds. They do not check MySQL. Compose's `depends_on: condition: service_healthy` is a startup-order gate; it does not provide ongoing orchestration, failover, or automatic recovery of dependent services if another service fails later.

## Build, Start, and Stop

Run commands from the directory containing `docker-compose.yml`:

```bash
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
docker compose logs
docker compose logs -f product-service
docker compose logs -f order-service
docker compose logs -f mysql
```

`docker compose config --quiet` validates the Compose configuration without printing its resolved values. Avoid sharing the output of plain `docker compose config`, because resolved configuration can include credentials.

After changing code or dependencies:

```bash
docker compose up -d --build
```

Stop containers while preserving the database volume:

```bash
docker compose down
```

`restart: unless-stopped` lets containers restart after many process or Docker-daemon restarts. It does not make the application highly available. `docker compose down -v` deletes the named database volume; use it only when intentionally erasing the local database.

Useful operator commands:

```bash
docker compose ps
docker compose logs --tail=100 product-service
docker compose logs --tail=100 order-service
docker compose logs --tail=100 mysql
docker compose exec mysql sh -c 'exec mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"'
docker volume ls
```

The `docker compose exec` example uses host-shell variables and is intended for Bash. Do not paste passwords into shared logs or support tickets.

## Network and Ports

All three containers join the dedicated `microservices-network`. Compose DNS resolves service names on this network:

- Product Service and Order Service connect to MySQL at `mysql:3306`.
- Order Service calls Product Service at `http://product-service:5001`.
- `localhost` inside a container refers to that same container, not another service. Container-to-container calls must use service names.

The mappings are host-port to container-port: `5001:5001`, `5002:5002`, and `3306:3306`. The Flask containers use `mysql:3306`; they do not use the MySQL host mapping. MySQL's host port is published only for optional local database-client access. Remove its `ports` entry if you do not need that access. On EC2, a published port may be reachable externally if the security group permits it.

If a host port is occupied, change only the left side of the mapping. For example, `5003:5001` makes Product Service available on host port `5003` while it continues listening on container port `5001`.

## API Smoke Tests

These Bash examples work on Linux, macOS, and EC2. In PowerShell, use `curl.exe` instead of the `curl` alias.

```bash
curl -i http://localhost:5001/health
curl -i http://localhost:5001/products
curl -i -X POST http://localhost:5001/products \
  -H 'Content-Type: application/json' \
  -d '{"name":"Laptop","price":50000}'

curl -i http://localhost:5002/health
curl -i http://localhost:5002/orders
```

Replace `1` below with the product `id` returned from the create-product response:

```bash
curl -i http://localhost:5001/products/1
curl -i -X POST http://localhost:5002/orders \
  -H 'Content-Type: application/json' \
  -d '{"product_id":1,"quantity":2}'
curl -i http://localhost:5002/orders/1
```

The order POST is also the integration test for Order Service calling Product Service over the Compose network. It returns `404` for a missing product, `400` for invalid input, `503` if Product Service is unavailable or the database is unavailable, and `502` for an invalid/unexpected Product Service response.

## Persistence and Backups

`mysql_data` is a Docker named volume. It survives `docker compose down` and container rebuilds on the same Docker host. It is not a backup, replication, or disaster-recovery solution. It does not automatically follow the application if an EC2 instance or its storage is lost.

For a basic SQL dump from Bash, run this from the Compose project directory:

```bash
docker compose exec -T mysql sh -c 'exec mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' > mysql-backup.sql
```

Store backups outside the instance and test restoring them. For data that must survive instance failure, use a managed database or a documented backup/snapshot and restore process. Never run `docker compose down -v` as a routine stop command.

## EC2 Deployment Checklist

For a controlled learning deployment on one EC2 Linux instance:

1. Install Docker Engine and the Docker Compose v2 plugin using the instructions for the chosen Linux distribution.
2. Clone the project, create a private `.env` on the instance, and replace the local practice credentials with strong unique values.
3. Run `docker compose config --quiet`, `docker compose up -d --build`, and `docker compose ps`; inspect service logs if a container is not healthy.
4. Restrict inbound security-group rules. Allow SSH only from administrator IPs. For temporary direct API testing, allow ports `5001` and `5002` only from your client IP. Do not allow public inbound access to MySQL port `3306`.
5. Test the health and API endpoints using the instance address only when the corresponding ports are intentionally open.

This Compose file publishes the Flask apps directly and has no HTTPS/TLS, reverse proxy, or load balancer. Before public production use, place an ALB or maintained reverse proxy in front, terminate TLS, expose only necessary public ports (typically `80`/`443`), and keep MySQL private or move it to a managed service such as RDS. The current single-instance setup has no failover or horizontal scaling. A local volume can persist through container updates but is not guaranteed to survive instance/storage loss; arrange external backups or durable managed storage.

## Troubleshooting

| Symptom | Checks |
| --- | --- |
| Container exits or restarts | Run `docker compose ps` and `docker compose logs --tail=200 <service>`. Check environment interpolation and rebuild after code changes. |
| MySQL connection refused | Confirm MySQL is healthy; app `DB_HOST` must be `mysql` and `DB_PORT` must be `3306`, not `localhost` or the published host port. Check `docker compose logs mysql`. |
| Authentication fails | Check `DB_NAME`, `DB_USER`, and `DB_PASSWORD` match the credentials initialized in the existing volume. Updating `.env` does not rewrite MySQL accounts in an existing volume. |
| Tables are missing | Call a database-backed endpoint such as `GET /products` or `GET /orders`; `/health` does not create tables. Check service logs for database errors. |
| Order cannot reach Product Service | Check both containers are running, Order Service uses `PRODUCT_SERVICE_URL=http://product-service:5001`, and both are on the Compose network. |
| API says healthy but database is unavailable | `/health` checks HTTP responsiveness only. Test a real endpoint such as `GET /products` or inspect the MySQL health/logs. |
| Data seems lost | Confirm the same Compose project/volume is being used; do not use `down -v`. Check `docker volume ls`. A new project name can create a differently prefixed volume. |
| Address already in use | Stop the host process or change the left side of a port mapping. Keep the right/container port the same. |
| Works locally but not from EC2 | Check EC2 security-group rules, host firewall, published host ports, and that the container process binds `0.0.0.0`. Do not change inter-container URLs to the EC2 public address. |

## Current Operational Gaps

This is deliberately small, but an operator should know what is not included:

- No CI/CD pipeline, automated test suite, deployment rollback, or image registry workflow.
- No schema migration tool; `create_all()` is not a migration strategy.
- No TLS, reverse proxy, API authentication, secret manager integration, or production-grade secret rotation.
- No scheduled backups, backup verification, metrics, alerting, or centralized logs.
- One MySQL container and one host provide no database failover or high availability.
- Python dependency ranges and image digests are not pinned for reproducible builds.

These are useful next DevOps improvements, but they are intentionally not configured by this project.