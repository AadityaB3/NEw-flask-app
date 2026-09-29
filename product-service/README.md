# Product Service

Flask API for creating and reading products. It listens on port `5001` and creates the `products` table when it can connect to MySQL.

Install dependencies with `python -m pip install -r requirements.txt`. Configure `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`, then run `python app.py`.

Endpoints: `GET /health`, `GET /products`, `GET /products/<id>`, and `POST /products`.