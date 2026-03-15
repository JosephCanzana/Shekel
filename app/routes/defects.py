from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func
from app.utils.decorator import role_required
from app.models.product import Product
from app.models.product_bundle import ProductBundle
from app.models.inventory import Inventory
from app.models.defect import Defect
from app.models.defect_detail import DefectDetail
from app.extensions import db

defects_bp = Blueprint("defects", __name__, url_prefix="/defects")

REASONS       = ["defect", "damage", "expired", "change_of_mind"]
COMPENSATIONS = ["pending", "loss", "returned", "replacement"]

REASON_LABELS = {
    "defect":        "Defect",
    "damage":        "Damage",
    "expired":       "Expired",
    "change_of_mind":"Change of Mind",
}
COMPENSATION_LABELS = {
    "pending":     "Pending",
    "loss":        "Loss",
    "returned":    "Returned",
    "replacement": "Replacement",
}


# ── Index: products with defect history ──────────────────────────────────────
@defects_bp.route("/")
@login_required
@role_required("admin", "co-admin", "stocking")
def index():
    products_with_defects = (
        db.session.query(
            Product.product_id,
            Product.product_name,
            func.sum(DefectDetail.quantity).label("total_units"),
        )
        .join(DefectDetail, DefectDetail.product_id == Product.product_id)
        .group_by(Product.product_id, Product.product_name)
        .order_by(func.sum(DefectDetail.quantity).desc())
        .all()
    )

    defect_rows = []
    for p in products_with_defects:
        product      = Product.query.get(p.product_id)
        bundle_count = product.bundle.bundle_count if product and product.bundle else None

        defect_rows.append({
            "product_id":   p.product_id,
            "product_name": p.product_name.capitalize(),
            "bundle_count": bundle_count,
            "total_units":  p.total_units,
        })

    return render_template("defects/index.html", defect_rows=defect_rows)


# ── Product defect history ────────────────────────────────────────────────────
@defects_bp.route("/product/<string:product_id>")
@login_required
@role_required("admin", "co-admin", "stocking")
def product_history(product_id):
    product = Product.query.get_or_404(product_id)
    bundle_count = product.bundle.bundle_count if product.bundle else None

    # get all defect details for this product, with defect datetime
    details = (
        db.session.query(DefectDetail, Defect.defect_datetime)
        .join(Defect, Defect.defect_id == DefectDetail.defect_id)
        .filter(DefectDetail.product_id == product_id)
        .order_by(Defect.defect_datetime.desc())
        .all()
    )

    rows = []
    for detail, dt in details:
        bundle_qty = 0
        unit_qty   = detail.quantity
        # if product has bundle, try to infer bundle qty from quantity
        # (stored as total units, bundle_count units per bundle)
        if bundle_count and detail.quantity % bundle_count == 0:
            bundle_qty = detail.quantity // bundle_count
            unit_qty   = 0

        rows.append({
            "defect_detail_id": detail.defect_detail_id,
            "defect_id":        detail.defect_id,
            "date":             dt.strftime("%m-%d-%Y"),
            "bundle_qty":       bundle_qty,
            "unit_qty":         unit_qty,
            "total_units":      detail.quantity,
            "reason":           REASON_LABELS.get(detail.reason, detail.reason),
            "compensation":     COMPENSATION_LABELS.get(detail.compensation, detail.compensation),
            "reason_raw":       detail.reason,
            "compensation_raw": detail.compensation,
        })

    return render_template("defects/product_history.html",
                           product=product,
                           bundle_count=bundle_count,
                           rows=rows)


# ── Edit compensation status ──────────────────────────────────────────────────
@defects_bp.route("/detail/<int:detail_id>/edit", methods=["POST"])
@login_required
@role_required("admin", "co-admin")
def edit_detail(detail_id):
    detail = DefectDetail.query.get_or_404(detail_id)
    new_compensation = request.form.get("compensation", "").strip()
    if new_compensation not in COMPENSATIONS:
        flash("Invalid compensation status.", "danger")
        return redirect(url_for("defects.product_history", product_id=detail.product_id))
    detail.compensation = new_compensation
    db.session.commit()
    flash("Compensation status updated.", "success")
    return redirect(url_for("defects.product_history", product_id=detail.product_id))


@defects_bp.route("/log")
@login_required
@role_required("admin", "co-admin", "stocking")
def log():
    return render_template("defects/log.html")


# ── API: search suggestions ───────────────────────────────────────────────────
@defects_bp.route("/api/search", methods=["POST"])
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
@defects_bp.route("/api/lookup", methods=["POST"])
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
        "unit_price":        float(product.unit_price),
        "revenue_price":     float(product.revenue_price),
        "product_price":     float(product.product_price),
        "stock":             stock,
        "bundle":            bundle_info,
        "scanned_as_bundle": scanned_as_bundle,
    })


# ── API: complete defect log ──────────────────────────────────────────────────
@defects_bp.route("/api/complete", methods=["POST"])
@login_required
@role_required("admin", "co-admin", "stocking")
def complete():
    data  = request.json or {}
    items = data.get("items", [])

    if not items:
        return jsonify({"error": "No items to log."}), 400

    total_unit    = 0
    total_revenue = 0
    total_amount  = 0

    # validate all items first
    for item in items:
        product = Product.query.get(item.get("product_id"))
        if not product or product.status == "archived":
            return jsonify({"error": f'Product "{item.get("product_id")}" not found or archived.'}), 400

        qty = int(item.get("qty", 0))
        if qty <= 0:
            return jsonify({"error": f'Invalid quantity for "{product.product_name}".'}), 400

        stock = product.inventory.quantity_available if product.inventory else 0
        if qty > stock:
            return jsonify({"error": f'"{product.product_name.capitalize()}": only {stock} in stock, cannot log {qty} defects.'}), 400

        if item.get("reason") not in REASONS:
            return jsonify({"error": f'Invalid reason "{item.get("reason")}".'}), 400

        if item.get("compensation") not in COMPENSATIONS:
            return jsonify({"error": f'Invalid compensation "{item.get("compensation")}".'}), 400

        total_unit    += float(product.unit_price)    * qty
        total_revenue += float(product.revenue_price) * qty
        total_amount  += float(product.product_price) * qty

    # save defect header
    defect = Defect(
        defect_datetime     = datetime.utcnow(),
        user_id             = current_user.user_id,
        total_unit_price    = round(total_unit,    2),
        total_revenue_price = round(total_revenue, 2),
        total_amount        = round(total_amount,  2),
    )
    db.session.add(defect)
    db.session.flush()

    logged = []
    for item in items:
        product = Product.query.get(item["product_id"])
        qty     = int(item["qty"])

        db.session.add(DefectDetail(
            defect_id               = defect.defect_id,
            product_id              = product.product_id,
            quantity                = qty,
            reason                  = item["reason"],
            compensation            = item["compensation"],
            unit_price_at_defect    = float(product.unit_price),
            revenue_price_at_defect = float(product.revenue_price),
            price_at_defect         = float(product.product_price),
            subtotal_unit           = round(float(product.unit_price)    * qty, 2),
            subtotal_revenue        = round(float(product.revenue_price) * qty, 2),
            subtotal_amount         = round(float(product.product_price) * qty, 2),
        ))

        # decrement inventory — defective items leave stock
        if product.inventory:
            product.inventory.quantity_available = max(
                0, product.inventory.quantity_available - qty
            )
            # track defective quantity separately
            product.inventory.quantity_defective = (
                product.inventory.quantity_defective or 0
            ) + qty
            product.inventory.last_updated = datetime.utcnow()

        logged.append({
            "product_name": product.product_name.capitalize(),
            "qty":          qty,
            "reason":       item["reason"].replace("_", " ").title(),
            "compensation": item["compensation"].title(),
            "new_stock":    max(0, (product.inventory.quantity_available if product.inventory else 0)),
        })

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to save. Please try again."}), 500

    return jsonify({
        "success":     True,
        "defect_id":   defect.defect_id,
        "logged":      logged,
        "total_items": len(logged),
        "total_units": sum(i["qty"] for i in logged),
        "recorded_by": current_user.full_name if hasattr(current_user, "full_name") else current_user.username,
        "datetime":    datetime.utcnow().strftime("%b %d, %Y %I:%M %p"),
    })