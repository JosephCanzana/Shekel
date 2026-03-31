from datetime import datetime
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app.utils.decorator import role_required
from app.models.product import Product
from app.models.product_bundle import ProductBundle
from app.models.inventory import Inventory
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.extensions import db

cashier_bp = Blueprint("cashier", __name__, url_prefix="/cashier")


@cashier_bp.route("/transaction")
@login_required
@role_required("superadmin", "admin", "cashier")
def transaction():
    return render_template("cashier/transaction.html")


# ── API: search suggestions (dropdown) ───────────────────────────────────────
@cashier_bp.route("/api/search", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "cashier")
def search():
    query = str((request.json or {}).get("query", "")).strip()
    if not query or len(query) < 1:
        return jsonify([])

    # match product name or product_id (barcode) — active only, limit 8
    products = Product.query.filter(
        Product.status == "active",
        db.or_(
            Product.product_name.ilike(f"%{query}%"),
            Product.product_id.ilike(f"%{query}%"),
        )
    ).limit(8).all()

    results = []
    for p in products:
        stock = p.inventory.quantity_available if p.inventory else 0
        results.append({
            "product_id":    p.product_id,
            "product_name":  p.product_name.capitalize(),
            "total_price": float(p.total_price),
            "stock":         stock,
        })

    return jsonify(results)


# ── API: look up a product by barcode or name ─────────────────────────────────
@cashier_bp.route("/api/lookup", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "cashier")
def lookup():
    query = str((request.json or {}).get("query", "")).strip()
    if not query:
        return jsonify({"error": "No search term provided."}), 400

    # 1. exact product barcode
    product = Product.query.get(query)
    scanned_as_bundle = False

    if not product:
        # 2. exact bundle barcode
        bundle = ProductBundle.query.get(query)
        if bundle:
            product = Product.query.get(bundle.product_id)
            scanned_as_bundle = True

    if not product:
        # 3. partial name match (active only)
        product = Product.query.filter(
            Product.product_name.ilike(f"%{query}%"),
            Product.status == "active"
        ).first()

    if not product:
        return jsonify({"error": "Product not found."}), 404

    if product.status == "archived":
        return jsonify({"error": f'"{product.product_name.capitalize()}" is archived.'}), 400

    stock       = product.inventory.quantity_available if product.inventory else 0
    bundle_info = None
    if product.bundle:
        bundle_info = {
            "bundle_id":    product.bundle.bundle_id,
            "bundle_name":  product.bundle.bundle_name,
            "bundle_count": product.bundle.bundle_count,
        }

    return jsonify({
        "product_id":    product.product_id,
        "product_name":  product.product_name.capitalize(),
        "cost_price":    float(product.cost_price),
        "revenue_price": float(product.revenue_price),
        "total_price": float(product.total_price),
        "stock":         stock,
        "bundle":        bundle_info,
        "scanned_as_bundle": scanned_as_bundle
    })


# ── API: complete sale ────────────────────────────────────────────────────────
@cashier_bp.route("/api/charge", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "cashier")
def charge():
    data     = request.json or {}
    items    = data.get("items", [])
    tendered = data.get("tendered")

    if not items:
        return jsonify({"error": "Cart is empty."}), 400

    try:
        tendered = float(tendered)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid payment amount."}), 400

    # ── Step 1: validate everything BEFORE any DB writes ──────────────────
    warnings = []
    for item in items:
        # validate qty type
        try:
            qty = int(item["qty"])
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid quantity for '{item.get('product_id', '?')}'."}), 400

        # validate qty value
        if qty <= 0:
            return jsonify({"error": "Quantity must be greater than zero."}), 400

        product = Product.query.get(item["product_id"])
        if not product:
            return jsonify({"error": f'Product "{item["product_id"]}" not found.'}), 400
        if product.status == "archived":
            return jsonify({"error": f'"{product.product_name.capitalize()}" is archived.'}), 400

        stock = product.inventory.quantity_available if product.inventory else 0
        if qty > stock:
            warnings.append(
                f'"{product.product_name.capitalize()}": only {stock} in stock, selling {qty}.'
            )

    # ── Step 2: compute totals ─────────────────────────────────────────────
    total_unit    = sum(float(i["cost_price"])    * int(i["qty"]) for i in items)
    total_revenue = sum(float(i["revenue_price"]) * int(i["qty"]) for i in items)
    total_amount  = sum(float(i["total_price"]) * int(i["qty"]) for i in items)

    if tendered < total_amount:
        return jsonify({"error": "Cash received is less than the total amount."}), 400

    change = round(tendered - total_amount, 2)

    # ── Step 3: write to DB only after all validation passes ───────────────
    sale = Sale(
        sale_datetime       = datetime.utcnow(),
        user_id             = current_user.user_id,
        total_cost_price    = round(total_unit,    2),
        total_revenue_price = round(total_revenue, 2),
        total_amount        = round(total_amount,  2),
        payment_method      = "cash",
    )
    db.session.add(sale)
    db.session.flush()  # get sale.transaction_id before inserting details

    for item in items:
        qty           = int(item["qty"])
        cost_price    = float(item["cost_price"])
        revenue_price = float(item["revenue_price"])
        price         = float(item["total_price"])

        db.session.add(SaleDetail(
            transaction_id        = sale.transaction_id,
            product_id            = item["product_id"],
            quantity              = qty,
            cost_price_at_sale    = cost_price,
            revenue_price_at_sale = revenue_price,
            price_at_sale         = price,
            subtotal_unit         = round(cost_price    * qty, 2),
            subtotal_revenue      = round(revenue_price * qty, 2),
            subtotal_amount       = round(price         * qty, 2),
        ))

        product = Product.query.get(item["product_id"])
        if product and product.inventory:
            product.inventory.quantity_available = max(
                0, product.inventory.quantity_available - qty
            )
            product.inventory.last_updated = datetime.utcnow()

    db.session.commit()

    return jsonify({
        "ok":             True,
        "transaction_id": sale.transaction_id,
        "total":          round(total_amount, 2),
        "tendered":       tendered,
        "change":         change,
        "warnings":       warnings,
        "items": [
            {
                "product_name":  i["product_name"],
                "qty":           int(i["qty"]),
                "total_price": float(i["total_price"]),
                "subtotal":      round(float(i["total_price"]) * int(i["qty"]), 2),
            }
            for i in items
        ],
        "cashier":  current_user.full_name if hasattr(current_user, "full_name") else current_user.username,
        "datetime": sale.sale_datetime.strftime("%b %d, %Y %I:%M %p"),
    })