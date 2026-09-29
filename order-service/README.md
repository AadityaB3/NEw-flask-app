# Order Service

Flask API for creating and reading orders. It listens on port `5002` and creates the `orders` table when it can connect to MySQL.

Install dependencies with `python -m pip install -r requirements.txt`. Configure `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, and optionally `PRODUCT_SERVICE_URL`, then run `python app.py`.

Endpoints: `GET /health`, `GET /orders`, `GET /orders/<id>`, and `POST /orders`. Before inserting an order, the service calls `GET <PRODUCT_SERVICE_URL>/products/<product_id>`.