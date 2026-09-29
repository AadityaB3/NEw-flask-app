import os
from urllib.parse import quote_plus

from flask import Flask, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from models import Product, db


app = Flask(__name__)
database_user = quote_plus(os.getenv("DB_USER", ""))
database_password = quote_plus(os.getenv("DB_PASSWORD", ""))
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{database_user}:{database_password}"
    f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '3306')}"
    f"/{os.getenv('DB_NAME', 'microservices_db')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)
database_ready = False


def initialize_database():
    global database_ready
    try:
        db.create_all()
        database_ready = True
        return None
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Database initialization failed")
        return jsonify({"error": "Database connection failed"}), 503


@app.before_request
def ensure_database():
    if request.endpoint == "health" or database_ready:
        return None
    return initialize_database()


@app.get("/health")
def health():
    return jsonify({"service": "product-service", "status": "healthy"})


@app.get("/products")
def list_products():
    try:
        products = Product.query.order_by(Product.id).all()
        return jsonify([product.to_dict() for product in products])
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Database connection failed"}), 503


@app.get("/products/<int:product_id>")
def get_product(product_id):
    try:
        product = db.session.get(Product, product_id)
        if product is None:
            return jsonify({"error": "Product not found"}), 404
        return jsonify(product.to_dict())
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Database connection failed"}), 503


@app.post("/products")
def create_product():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    name = data.get("name")
    price = data.get("price")
    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": "name must be a non-empty string"}), 400
    if isinstance(price, bool) or not isinstance(price, (int, float)) or price < 0:
        return jsonify({"error": "price must be a non-negative number"}), 400

    product = Product(name=name.strip(), price=price)
    try:
        db.session.add(product)
        db.session.commit()
        return jsonify(product.to_dict()), 201
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Database connection failed"}), 503


if __name__ == "__main__":
    with app.app_context():
        initialize_database()
    app.run(host="0.0.0.0", port=5001)