# Flask Microservices Demo

## Architecture

This project contains two independent Flask services. Product Service owns product reads and writes on port `5001`; Order Service owns orders on port `5002`. Both use SQLAlchemy and the same MySQL database, with separate tables. Order Service checks products through Product Service's HTTP API and does not read the products table directly.

```text
Client -> Order Service -> Product Service -> MySQL
                  |                         |
                  +------ orders table      +-- products table
```

## Configure MySQL

Install and start MySQL, then create the database:

```sql
CREATE DATABASE microservices_db;
```

Set these environment variables in each service's terminal. Replace the password with your own MySQL password; the application does not contain database credentials.

```powershell
$env:DB_HOST = "localhost"
$env:DB_PORT = "3306"
$env:DB_NAME = "microservices_db"
$env:DB_USER = "root"
$env:DB_PASSWORD = "yourpassword"
```

The default `PRODUCT_SERVICE_URL` is `http://localhost:5001`. Set it explicitly if Product Service is hosted elsewhere:

```powershell
$env:PRODUCT_SERVICE_URL = "http://localhost:5001"
```

Each service creates its table when it starts and connects successfully. If MySQL is temporarily unavailable, it retries initialization on a later API request and returns a JSON `503` for database-dependent requests.

## Install Dependencies

Open a terminal in each service directory and install its requirements:

```powershell
cd product-service
python -m pip install -r requirements.txt
```

In a second terminal, from the project directory:

```powershell
cd order-service
python -m pip install -r requirements.txt
```

## Run Services

In the product-service terminal, set the MySQL variables above and run:

```powershell
python app.py
```

In the order-service terminal, set the same MySQL variables, optionally set `PRODUCT_SERVICE_URL`, and run:

```powershell
python app.py
```

## Test the APIs

Run these commands in PowerShell after both services are running. The examples use `curl.exe` to avoid PowerShell's `curl` alias.

Check service health:

```powershell
curl.exe http://localhost:5001/health
curl.exe http://localhost:5002/health
```

Create and read a product:

```powershell
curl.exe -X POST http://localhost:5001/products -H "Content-Type: application/json" -d '{"name":"Laptop","price":50000}'
curl.exe http://localhost:5001/products
curl.exe http://localhost:5001/products/1
```

Create and read an order. Use an existing product ID:

```powershell
curl.exe -X POST http://localhost:5002/orders -H "Content-Type: application/json" -d '{"product_id":1,"quantity":2}'
curl.exe http://localhost:5002/orders
curl.exe http://localhost:5002/orders/1
```

An order for a missing product returns `404`. An invalid JSON body or invalid field returns `400`; an unreachable Product Service returns `503`. Database connection failures return `503` with a JSON error.

## Service Communication

For `POST /orders`, Order Service sends an HTTP `GET` to `${PRODUCT_SERVICE_URL}/products/<product_id>` before writing anything. A `404` from Product Service is passed back as `404`; a successful product response allows the order to be saved. `PRODUCT_SERVICE_URL` defaults to `http://localhost:5001` for local use and can be changed through the environment.

## Database Tables

- `products`: `id`, `name`, `price`, and `created_at`; stores the catalog managed by Product Service.
- `orders`: `id`, `product_id`, `quantity`, and `created_at`; stores orders managed by Order Service. `product_id` refers to a product checked over HTTP, not a cross-service database relationship.

## Run with Docker Compose

Docker Compose builds both Flask images and starts MySQL. Set these variables in PowerShell before running Compose; replace the sample passwords with your own values:

```powershell
$env:MYSQL_DATABASE = "microservices_db"
$env:MYSQL_USER = "microservices_user"
$env:MYSQL_PASSWORD = "replace-with-a-strong-password"
$env:MYSQL_ROOT_PASSWORD = "replace-with-a-different-strong-password"
```

The Compose file requires the user and both passwords rather than storing credentials in the file. `MYSQL_DATABASE` defaults to `microservices_db`. You can also put these variables in a local `.env` file beside `docker-compose.yml`; do not commit real credentials.

Build and start:

```powershell
docker compose build
docker compose up -d
```

Check containers and logs:

```powershell
docker compose ps
docker compose logs
docker compose logs product-service
docker compose logs order-service
```

Stop the containers while preserving MySQL data:

```powershell
docker compose down
```

After changing application code, rebuild and restart:

```powershell
docker compose up -d --build
```

The named `mysql_data` volume persists the database across `docker compose down` and later `docker compose up`. Do not use `docker compose down -v` unless you intend to delete that data.

## Docker Networking

All three containers join the dedicated `microservices-network`. Docker Compose provides DNS names from service names, so both Flask containers connect to MySQL at `mysql:3306`. Order Service calls Product Service at `http://product-service:5001`, configured through `PRODUCT_SERVICE_URL`. Inside a container, `localhost` means that same container, not another service; use the Compose service name instead.

MySQL is published as `3306:3306` to make it convenient to connect a local database client for debugging. The Flask containers do not use this host mapping. Remove the MySQL `ports` section from `docker-compose.yml` if host access is not needed.

Compose waits for MySQL's healthcheck before starting the Flask services, and waits for Product Service's healthcheck before starting Order Service. The MySQL check verifies that the server responds to `mysqladmin`, not just that its container has started.

## Test Docker APIs

These commands run from the directory containing `docker-compose.yml`. The examples use `curl.exe` for PowerShell:

```powershell
curl.exe http://localhost:5001/health
curl.exe http://localhost:5001/products
curl.exe -X POST http://localhost:5001/products -H "Content-Type: application/json" -d '{"name":"Laptop","price":50000}'

curl.exe http://localhost:5002/health
curl.exe http://localhost:5002/orders
```

Create an order using the `id` returned by Product Service. This request exercises Order Service's call to Product Service over the Compose network before saving the order:

```powershell
curl.exe -X POST http://localhost:5002/orders -H "Content-Type: application/json" -d '{"product_id":1,"quantity":2}'
```

## Docker Troubleshooting

- **A container keeps restarting:** Run `docker compose ps` and `docker compose logs <service-name>` to see the startup error. After fixing configuration or code, use `docker compose up -d --build`.
- **Flask cannot connect to MySQL:** Confirm the Compose values for `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`. For containers, the host must be `mysql`; check `docker compose logs mysql` and wait for its health status.
- **Connection refused:** Use container ports and service DNS names (`mysql:3306` and `product-service:5001`), not `localhost` or the host-published ports. Confirm the target container is running and healthy.
- **Order Service cannot reach Product Service:** Check `docker compose ps` and `docker compose logs product-service order-service`. Both services must share `microservices-network`, and `PRODUCT_SERVICE_URL` must be `http://product-service:5001`.
- **MySQL data appears to disappear:** The volume is named `mysql_data`; use the same Compose project and avoid `docker compose down -v`, which deletes it. Changing MySQL environment credentials does not update users in an already-initialized volume.
- **A port is already in use:** Stop the other process or change the host side of a mapping, for example `5001:5001` to `5003:5001`. Keep the right-hand container port unchanged. MySQL's host mapping can be removed if host access is unnecessary.
- **Application starts before MySQL is ready:** The Flask services depend on MySQL's `service_healthy` status, not merely container startup. Inspect `docker compose ps` and MySQL logs; its healthcheck retries for up to 20 checks after the start period.