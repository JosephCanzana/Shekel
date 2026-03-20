from datetime import datetime
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app.utils.decorator import role_required
from app.models.product import Product
from app.models.product_bundle import ProductBundle
from app.models.inventory import Inventory
from app.models.stock_in import StockIn
from app.extensions import db
from app.utils.index_helpers import *

stocking_bp = Blueprint("stocking", __name__, url_prefix="/stocking")

@stocking_bp.route("/")
@login_required
@role_required("stocking")
def dashboard():
    return render_template(
        "stocking/dashboard.html",
        time_of_day      = get_time_of_day(),
        stats            = get_stocking_stats(),
        low_stock_items  = get_low_stock_items(),
        recent_stockins  = get_recent_stockins(),
        defects          = get_defects(),
    )


@stocking_bp.route("/stock-in")
@login_required
@role_required("admin", "co-admin", "stocking")
def stock_in():
    return render_template("stocking/stock_in.html")


# ── API: search suggestions ───────────────────────────────────────────────────
@stocking_bp.route("/api/search", methods=["POST"])
@login_required
@role_required("admin", "co-admin", "stocking")
def search():
    query = (request.json or {}).get("query", "").strip()
    if not query:
        return jsonify([])

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
            "product_id":   p.product_id,
            "product_name": p.product_name.capitalize(),
            "product_price": float(p.product_price),
            "stock":        stock,
        })

    return jsonify(results)


# ── API: lookup by barcode or name ────────────────────────────────────────────
@stocking_bp.route("/api/lookup", methods=["POST"])
@login_required
@role_required("admin", "co-admin", "stocking")
def lookup():
    query = (request.json or {}).get("query", "").strip()
    if not query:
        return jsonify({"error": "No search term provided."}), 400

    product           = Product.query.get(query)
    scanned_as_bundle = False

    if not product:
        bundle = ProductBundle.query.get(query)
        if bundle:
            product           = Product.query.get(bundle.product_id)
            scanned_as_bundle = True

    if not product:
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
        "product_id":        product.product_id,
        "product_name":      product.product_name.capitalize(),
        "product_price":     float(product.product_price),
        "stock":             stock,
        "bundle":            bundle_info,
        "scanned_as_bundle": scanned_as_bundle,
    })


# ── API: complete stock-in ────────────────────────────────────────────────────
@stocking_bp.route("/api/complete", methods=["POST"])
@login_required
@role_required("admin", "co-admin", "stocking")
def complete():
    data  = request.json or {}
    items = data.get("items", [])
    notes = data.get("notes", "").strip()

    if not items:
        return jsonify({"error": "No items to receive."}), 400

    received = []
    for item in items:
        product_id = item.get("product_id")
        try:
            qty = int(item.get("qty", 0))
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid quantity for product '{product_id}'."}), 400
        item_notes = item.get("notes", "").strip() or notes

        if qty <= 0:
            continue

        product = Product.query.get(product_id)
        if not product or product.status == "archived":
            return jsonify({"error": f'Product "{product_id}" not found or archived.'}), 400

        # increment inventory
        if product.inventory:
            product.inventory.quantity_available += qty
            product.inventory.last_updated        = datetime.utcnow()
        else:
            db.session.add(Inventory(
                product_id         = product_id,
                quantity_available = qty,
                quantity_defective = 0,
                last_updated       = datetime.utcnow()
            ))

        # log stock-in record
        db.session.add(StockIn(
            product_id        = product_id,
            user_id           = current_user.user_id,
            quantity_received = qty,
            stockin_datetime  = datetime.utcnow(),
            notes             = item_notes or None
        ))

        received.append({
            "product_name": product.product_name.capitalize(),
            "qty":          qty,
            "new_stock":    (product.inventory.quantity_available if product.inventory else qty),
        })

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Failed to save. Please try again."}), 500

    return jsonify({
        "success":  True,
        "received": received,
        "total_items": len(received),
        "total_units": sum(r["qty"] for r in received),
        "recorded_by": current_user.full_name if hasattr(current_user, "full_name") else current_user.username,
        "datetime": datetime.utcnow().strftime("%b %d, %Y %I:%M %p"),
    })