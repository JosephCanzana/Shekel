from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required, current_user
from app.utils.decorator import role_required
from app.models.product import Product
from app.models.product_bundle import ProductBundle
from app.models.inventory import Inventory
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.extensions import db
from app.utils.helpers import generate_charge_token
from app.utils.audit import audit
from app.utils.helpers import to_pht

cashier_bp = Blueprint("cashier", __name__, url_prefix="/cashier")


@cashier_bp.route("/transaction")
@login_required
@role_required("superadmin", "admin", "cashier")
def transaction():
    session["charge_token"] = generate_charge_token()
    return render_template("cashier/transaction.html",
                           charge_token=session["charge_token"])


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

    token = data.get("charge_token")
    if not token or token != session.get("charge_token"):
        return jsonify({"error": "Duplicate or invalid submission"}), 409
    session.pop("charge_token", None)
    

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

    audit(
        "INSERT",
        "Sales",
        f"Sale #{sale.transaction_id} — ₱{sale.total_amount:.2f} processed by {current_user.full_name}",
        reference_id=sale.transaction_id,
        reference_table="Sale",
        user_id=current_user.user_id
    )


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

@cashier_bp.route("/api/refresh-token", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "cashier")
def refresh_token():
    session["charge_token"] = generate_charge_token()
    return jsonify({"charge_token": session["charge_token"]})
# ═══════════════════════════════════════════════════════════════════════════════
# SALES HISTORY  (cashier — own transactions only)
# ═══════════════════════════════════════════════════════════════════════════════

@cashier_bp.route("/sales")
@login_required
@role_required("superadmin", "admin", "cashier")
def sales_history():
    from sqlalchemy  import func
    from datetime    import date as _date, timedelta

    PER_PAGE = 50

    page      = request.args.get("page",      1,  type=int)
    q         = request.args.get("q",         "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to   = request.args.get("date_to",   "").strip()

    qry = (
        Sale.query
        .filter(Sale.user_id == current_user.user_id)
        .order_by(Sale.sale_datetime.desc())
    )

    if q:
        try:
            qry = qry.filter(Sale.transaction_id == int(q))
        except ValueError:
            pass

    if date_from:
        try:
            qry = qry.filter(
                Sale.sale_datetime >= datetime.strptime(date_from, "%Y-%m-%d")
            )
        except ValueError:
            date_from = ""

    if date_to:
        try:
            qry = qry.filter(
                Sale.sale_datetime
                <= datetime.strptime(date_to, "%Y-%m-%d")
                           .replace(hour=23, minute=59, second=59)
            )
        except ValueError:
            date_to = ""

    sales = qry.paginate(page=page, per_page=PER_PAGE, error_out=False)

    # ── Period stats (scoped to this cashier) ────────────────────────────
    uid         = current_user.user_id
    today_dt    = datetime.combine(_date.today(), datetime.min.time())
    week_dt     = today_dt - timedelta(days=today_dt.weekday())
    month_dt    = today_dt.replace(day=1)
    year_dt     = today_dt.replace(month=1, day=1)

    def _period(start):
        row = db.session.query(
            func.count(Sale.transaction_id),
            func.coalesce(func.sum(Sale.total_amount),        0),
            func.coalesce(func.sum(Sale.total_cost_price),    0),
            func.coalesce(func.sum(Sale.total_revenue_price), 0),
        ).filter(
            Sale.user_id        == uid,
            Sale.sale_datetime  >= start,
        ).first()
        return dict(
            count  = int(row[0]),
            sales  = float(row[1]),
            cost   = float(row[2]),
            profit = float(row[3]),
        )

    stats = dict(
        today = _period(today_dt),
        week  = _period(week_dt),
        month = _period(month_dt),
        year  = _period(year_dt),
    )

    filters = dict(q=q, date_from=date_from, date_to=date_to)

    return render_template(
        "sales/history.html",
        sales     = sales,
        filters   = filters,
        stats     = stats,
        all_users = [],
        is_admin  = False,
    )


@cashier_bp.route("/sales/<int:transaction_id>")
@login_required
@role_required("superadmin", "admin", "cashier")
def sale_detail(transaction_id):
    sale = Sale.query.get_or_404(transaction_id)

    # Cashiers can only view their own transactions
    if current_user.role == "cashier" and sale.user_id != current_user.user_id:
        return jsonify({"error": "Not authorised."}), 403

    u = sale.user
    details = [
        {
            "product_id":   d.product_id,
            "product_name": d.product.product_name.capitalize() if d.product else d.product_id,
            "quantity":     d.quantity,
            "price":        float(d.price_at_sale),
            "subtotal":     float(d.subtotal_amount),
        }
        for d in sale.sale_details
    ]

    return jsonify({
        "transaction_id":      sale.transaction_id,
        "sale_datetime":       to_pht(sale.sale_datetime).strftime("%B %d, %Y  %I:%M:%S %p PHT")
                               if sale.sale_datetime else "—",
        "total_amount":        float(sale.total_amount),
        "total_cost_price":    float(sale.total_cost_price),
        "total_revenue_price": float(sale.total_revenue_price),
        "payment_method":      sale.payment_method or "cash",
        "cashier": {
            "name": f"{u.first_name} {u.last_name}".strip().title() if u else "—",
            "role": u.role.title() if u else "—",
            "id":   u.user_id if u else None,
        },
        "items": details,
    })