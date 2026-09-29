import os
from urllib.parse import quote_plus

import requests
from flask import Flask, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from models import Order, db


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
product_service_url = os.getenv("PRODUCT_SERVICE_URL", "http://localhost:5001").rstrip("/")


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
    return jsonify({"service": "order-service", "status": "healthy"})


@app.get("/orders")
def list_orders():
    try:
        orders = Order.query.order_by(Order.id).all()
        return jsonify([order.to_dict() for order in orders])
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Database connection failed"}), 503


@app.get("/orders/<int:order_id>")
def get_order(order_id):
    try:
        order = db.session.get(Order, order_id)
        if order is None:
            return jsonify({"error": "Order not found"}), 404
        return jsonify(order.to_dict())
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Database connection failed"}), 503


@app.post("/orders")
def create_order():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    product_id = data.get("product_id")
    quantity = data.get("quantity")
    if isinstance(product_id, bool) or not isinstance(product_id, int) or product_id <= 0:
        return jsonify({"error": "product_id must be a positive integer"}), 400
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        return jsonify({"error": "quantity must be a positive integer"}), 400

    try:
        product_response = requests.get(
            f"{product_service_url}/products/{product_id}", timeout=3
        )
    except requests.RequestException:
        return jsonify({"error": "Product service unavailable"}), 503

    if product_response.status_code == 404:
        return jsonify({"error": "Product not found"}), 404
    if not product_response.ok:
        return jsonify({"error": "Product service returned an error"}), 502
    try:
        product = product_response.json()
    except ValueError:
        return jsonify({"error": "Invalid response from product service"}), 502
    if not isinstance(product, dict) or product.get("id") != product_id:
        return jsonify({"error": "Invalid response from product service"}), 502

    order = Order(product_id=product_id, quantity=quantity)
    try:
        db.session.add(order)
        db.session.commit()
        return jsonify(order.to_dict()), 201
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Database connection failed"}), 503


if __name__ == "__main__":
    with app.app_context():
        initialize_database()
    app.run(host="0.0.0.0", port=5002)