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
from app.models.sale import Sale
from app.extensions import db

defects_bp = Blueprint("defects", __name__, url_prefix="/defects")

REASONS = ["defect", "damage", "expired", "change_of_mind"]

REASON_LABELS = {
    "defect":           "Defect",
    "damage":           "Damage",
    "expired":          "Expired",
    "change_of_mind":   "Change of Mind",
}

# Customer-facing reasons (item already sold)
CUSTOMER_REASONS  = {"change_of_mind", "defect", "damage"}
# In-store reasons (item still in available stock)
INSTORE_REASONS   = {"defect", "damage", "expired"}
COMPENSATION_LABELS = {
    "pending":  "Pending",
    "loss":     "Loss",
    "returned": "Returned",
}

def is_admin_or_coadmin():
    return current_user.role in ("superadmin", "admin")

def can_review():
    """Admin, co-admin, and stocking can review pending items."""
    return current_user.role in ("superadmin", "admin", "stocking")

def can_set_compensation():
    """Stocking, admin, co-admin can set compensation. Cashier cannot."""
    return current_user.role in ("superadmin", "admin", "stocking")


def _apply_inventory(product_id, qty, compensation, reason=None, previous_compensation=None):
    """
    Apply the correct inventory movement based on compensation, reason, and previous state.

    KEY DISTINCTION — where the item came from:
      change_of_mind: item was already SOLD (deducted from available by the sale).
        - returned  → available +qty  (item comes back to shelf — net zero vs sale)
        - pending   → defective +qty only (item is held for review, no available deduction — already sold)
        - loss      → no movement needed (item was already gone from available via the sale)

      defect/damage/expired: item is STILL IN STORE (in available stock).
        - pending   → available -qty, defective +qty
        - loss      → available -qty
        - returned  → available +qty  (supplier return / restock)

    Status change from pending (review):
        → loss      → defective -qty
        → returned  → defective -qty, available +qty
    """
    inv = Inventory.query.filter_by(product_id=product_id).first()
    if not inv:
        return

    is_sold_item = (reason in CUSTOMER_REASONS)

    if previous_compensation is None:
        # fresh log
        if is_sold_item:
            # item already removed from available by the sale
            if compensation == "returned":
                # customer returns it — put back on shelf
                inv.quantity_available = inv.quantity_available + qty
            elif compensation == "pending":
                # held for review — goes to defective watch, no available change
                inv.quantity_defective = (inv.quantity_defective or 0) + qty
            elif compensation == "loss":
                # already gone from available (via sale) — nothing to move
                pass
        else:
            # item is still in store inventory
            if compensation == "pending":
                inv.quantity_available = max(0, inv.quantity_available - qty)
                inv.quantity_defective = (inv.quantity_defective or 0) + qty
            elif compensation == "loss":
                inv.quantity_available = max(0, inv.quantity_available - qty)
            elif compensation == "returned":
                # supplier return / restock
                inv.quantity_available = inv.quantity_available + qty

    elif previous_compensation == "pending":
        # changing from pending to something else (review action)
        # same logic regardless of reason — item is in defective stock
        if compensation == "loss":
            inv.quantity_defective = max(0, (inv.quantity_defective or 0) - qty)
        elif compensation == "returned":
            inv.quantity_defective = max(0, (inv.quantity_defective or 0) - qty)
            inv.quantity_available = inv.quantity_available + qty

    inv.last_updated = datetime.utcnow()


# ── Index: pending items watch list ──────────────────────────────────────────
@defects_bp.route("/")
@login_required
@role_required("superadmin", "admin", "stocking", "cashier")
def index():
    from app.models.user import User
    page          = request.args.get("page", 1, type=int)
    search        = request.args.get("search", "").strip()
    filter_reason = request.args.get("reason", "")
    per_page      = 15

    query = (
        db.session.query(DefectDetail, Defect, Product, User)
        .join(Defect,  Defect.defect_id   == DefectDetail.defect_id)
        .join(Product, Product.product_id == DefectDetail.product_id)
        .join(User,    User.user_id       == Defect.user_id)
        .filter(DefectDetail.compensation == "pending")
    )
    if search:
        query = query.filter(
            db.or_(Product.product_name.ilike(f"%{search}%"),
                   Product.product_id.ilike(f"%{search}%"))
        )
    if filter_reason:
        query = query.filter(DefectDetail.reason == filter_reason)

    total   = query.count()
    pending = query.order_by(Defect.defect_datetime.desc()) \
                   .offset((page - 1) * per_page).limit(per_page).all()
    pages   = (total + per_page - 1) // per_page

    return render_template("defects/index.html",
                           pending=pending,
                           page=page, pages=pages, total=total,
                           search=search, filter_reason=filter_reason,
                           can_review=can_review(),
                           REASONS=REASONS,
                           REASON_LABELS=REASON_LABELS,
                           COMPENSATION_LABELS=COMPENSATION_LABELS)


# ── Log page ──────────────────────────────────────────────────────────────────
@defects_bp.route("/log")
@login_required
@role_required("superadmin", "admin", "stocking", "cashier")
def log():
    return render_template("defects/log.html",
                           can_set_compensation=can_set_compensation())


# ── History: all records for one product ─────────────────────────────────────
@defects_bp.route("/product/<string:product_id>")
@login_required
@role_required("superadmin", "admin", "stocking", "cashier")
def product_history(product_id):
    from app.models.user import User
    product       = Product.query.get_or_404(product_id)
    page          = request.args.get("page", 1, type=int)
    filter_reason = request.args.get("reason", "")
    filter_comp   = request.args.get("compensation", "")
    per_page      = 15

    query = (
        db.session.query(DefectDetail, Defect, User)
        .join(Defect, Defect.defect_id == DefectDetail.defect_id)
        .join(User,   User.user_id     == Defect.user_id)
        .filter(DefectDetail.product_id == product_id)
    )
    if filter_reason:
        query = query.filter(DefectDetail.reason == filter_reason)
    if filter_comp:
        query = query.filter(DefectDetail.compensation == filter_comp)

    total   = query.count()
    details = query.order_by(Defect.defect_datetime.desc()) \
                   .offset((page - 1) * per_page).limit(per_page).all()
    pages   = (total + per_page - 1) // per_page

    return render_template("defects/product_history.html",
                           product=product,
                           details=details,
                           page=page, pages=pages, total=total,
                           filter_reason=filter_reason,
                           filter_comp=filter_comp,
                           can_review=can_review(),
                           REASONS=REASONS,
                           REASON_LABELS=REASON_LABELS,
                           COMPENSATION_LABELS=COMPENSATION_LABELS)


# ── Review: change pending → loss / returned ──────────────────────────────────
@defects_bp.route("/detail/<int:detail_id>/review", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "stocking")
def review(detail_id):
    detail = DefectDetail.query.get_or_404(detail_id)

    if detail.compensation != "pending":
        flash("Only pending items can be reviewed.", "warning")
        return redirect(url_for("defects.index"))

    new_compensation = request.form.get("compensation", "").strip()
    if new_compensation not in ("loss", "returned"):
        flash("Invalid compensation. Choose loss or returned.", "danger")
        return redirect(url_for("defects.index"))

    _apply_inventory(
        detail.product_id, detail.quantity,
        new_compensation, previous_compensation="pending"
    )

    detail.compensation = new_compensation
    detail.reviewed_by  = current_user.user_id
    detail.reviewed_at  = datetime.utcnow()
    db.session.commit()

    product_name = detail.product.product_name.capitalize()
    reviewer_name = f"{current_user.first_name} {current_user.last_name}".strip().title()
    flash(f'"{product_name}" marked as {COMPENSATION_LABELS[new_compensation]} by {reviewer_name}.', "success")
    return redirect(request.referrer or url_for("defects.index"))


# ── Update review: admin can change compensation on already-resolved items ────
@defects_bp.route("/detail/<int:detail_id>/update", methods=["POST"])
@login_required
@role_required("superadmin")
def update_review(detail_id):
    detail = DefectDetail.query.get_or_404(detail_id)

    new_compensation = request.form.get("compensation", "").strip()
    if new_compensation not in ("pending", "loss", "returned"):
        flash("Invalid compensation.", "danger")
        return redirect(request.referrer or url_for("defects.index"))

    old_compensation = detail.compensation

    if old_compensation == new_compensation:
        flash("No change made — compensation is already set to that value.", "info")
        return redirect(request.referrer or url_for("defects.index"))

    # reverse the old inventory movement, then apply the new one
    inv = Inventory.query.filter_by(product_id=detail.product_id).first()
    if inv:
        # undo old state
        if old_compensation == "pending":
            inv.quantity_available += detail.quantity
            inv.quantity_defective = max(0, (inv.quantity_defective or 0) - detail.quantity)
        elif old_compensation == "loss":
            inv.quantity_available += detail.quantity
        elif old_compensation == "returned":
            inv.quantity_available = max(0, inv.quantity_available - detail.quantity)

        # apply new state
        if new_compensation == "pending":
            inv.quantity_available = max(0, inv.quantity_available - detail.quantity)
            inv.quantity_defective = (inv.quantity_defective or 0) + detail.quantity
        elif new_compensation == "loss":
            inv.quantity_available = max(0, inv.quantity_available - detail.quantity)
        elif new_compensation == "returned":
            inv.quantity_available += detail.quantity

        inv.last_updated = datetime.utcnow()

    detail.compensation = new_compensation
    detail.reviewed_by  = current_user.user_id
    detail.reviewed_at  = datetime.utcnow()
    db.session.commit()

    product_name  = detail.product.product_name.capitalize()
    reviewer_name = f"{current_user.first_name} {current_user.last_name}".strip().title()
    flash(
        f'"{product_name}" compensation updated from {COMPENSATION_LABELS[old_compensation]} '
        f'to {COMPENSATION_LABELS[new_compensation]} by {reviewer_name}.',
        "success"
    )
    return redirect(request.referrer or url_for("defects.index"))


# ── API: search ───────────────────────────────────────────────────────────────
@defects_bp.route("/api/search", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "stocking", "cashier")
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

    return jsonify([{
        "product_id":    p.product_id,
        "product_name":  p.product_name.capitalize(),
        "product_price": float(p.product_price),
        "stock":         p.inventory.quantity_available if p.inventory else 0,
    } for p in products])


# ── API: lookup ───────────────────────────────────────────────────────────────
@defects_bp.route("/api/lookup", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "stocking", "cashier")
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


# ── API: TXN lookup — validate transaction + return remaining returnable qty ──
@defects_bp.route("/api/txn_lookup", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "stocking", "cashier")
def txn_lookup():
    from app.models.sale import Sale
    from app.models.sale_detail import SaleDetail

    raw = (request.json or {}).get("txn_ref", "").strip()
    if not raw:
        return jsonify({"error": "No transaction reference provided."}), 400

    # accept both "TXN-00042" and "42"
    txn_id = raw.upper().replace("TXN-", "")
    try:
        txn_id = int(txn_id)
    except ValueError:
        return jsonify({"error": f'"{raw}" is not a valid transaction reference.'}), 400

    sale = Sale.query.get(txn_id)
    if not sale:
        return jsonify({"error": f'Transaction TXN-{txn_id:05d} not found.'}), 404

    # build list of items sold in this transaction with remaining returnable qty
    items = []
    for sd in sale.sale_details:
        if not sd.product:
            continue

        qty_sold = sd.quantity

        # how many have already been returned/logged against this TXN
        already_returned = (
            db.session.query(db.func.sum(DefectDetail.quantity))
            .filter(
                DefectDetail.transaction_id == txn_id,
                DefectDetail.product_id     == sd.product_id,
            )
            .scalar() or 0
        )

        remaining = max(0, qty_sold - already_returned)

        items.append({
            "product_id":    sd.product_id,
            "product_name":  sd.product.product_name.capitalize(),
            "product_price": float(sd.product.product_price),
            "qty_sold":      qty_sold,
            "already_returned": already_returned,
            "remaining":     remaining,
        })

    return jsonify({
        "txn_id":    txn_id,
        "txn_ref":   f"TXN-{txn_id:05d}",
        "cashier":   f"{sale.user.first_name} {sale.user.last_name}".strip().title() if sale.user else "Unknown",
        "datetime":  sale.sale_datetime.strftime("%b %d, %Y %I:%M %p"),
        "items":     items,
    })


# ── API: complete log ─────────────────────────────────────────────────────────
@defects_bp.route("/api/complete", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "stocking", "cashier")
def complete():
    data  = request.json or {}
    items = data.get("items", [])

    if not items:
        return jsonify({"error": "No items to log."}), 400

    customer_items = [i for i in items if i.get("log_type") == "customer"]
    if customer_items:
        txn_ref_raw = (customer_items[0].get("txn_ref") or "").strip()
        if not txn_ref_raw:
            return jsonify({"error": "Transaction reference is required for customer returns."}), 400

        txn_id_str = txn_ref_raw.upper().replace("TXN-", "")
        try:
            txn_id = int(txn_id_str)
        except ValueError:
            return jsonify({"error": f'"{txn_ref_raw}" is not a valid transaction reference.'}), 400

        sale = Sale.query.get(txn_id)
        if not sale:
            return jsonify({"error": f'Transaction TXN-{txn_id:05d} not found.'}), 404

        # build a map of product_id → remaining returnable qty
        sold_map = {}
        for sd in sale.sale_details:
            already = (
                db.session.query(db.func.sum(DefectDetail.quantity))
                .filter(
                    DefectDetail.transaction_id == txn_id,
                    DefectDetail.product_id     == sd.product_id,
                )
                .scalar() or 0
            )
            sold_map[sd.product_id] = max(0, sd.quantity - already)

        # validate each customer return item against the TXN
        for item in customer_items:
            pid = item.get("product_id")
            qty = int(item.get("qty", 0))
            if pid not in sold_map:
                product = Product.query.get(pid)
                name = product.product_name.capitalize() if product else pid
                return jsonify({"error": f'"{name}" was not part of transaction TXN-{txn_id:05d}.'}), 400
            if qty > sold_map[pid]:
                product = Product.query.get(pid)
                name = product.product_name.capitalize() if product else pid
                remaining = sold_map[pid]
                return jsonify({"error": f'"{name}": only {remaining} unit(s) eligible for return from TXN-{txn_id:05d}.'}), 400

        # stamp all customer items with the normalised txn_ref
        normalised = f"TXN-{txn_id:05d}"
        for item in customer_items:
            item["txn_ref"] = normalised

    # validate all first
    for item in items:
        product = Product.query.get(item.get("product_id"))
        if not product or product.status == "archived":
            return jsonify({"error": f'Product "{item.get("product_id")}" not found.'}), 400

        qty = int(item.get("qty", 0))
        if qty <= 0:
            return jsonify({"error": f'Invalid quantity for "{product.product_name}".'}), 400

        reason = item.get("reason", "")
        if reason not in REASONS:
            return jsonify({"error": f'Invalid reason "{reason}".'}), 400

        # log_type from frontend — 'instore' or 'customer'
        log_type = item.get("log_type", "instore")

        # validate reason is appropriate for log type
        if log_type == "customer" and reason not in CUSTOMER_REASONS:
            return jsonify({"error": f'Reason "{reason}" is not valid for a customer return.'}), 400
        if log_type == "instore" and reason not in INSTORE_REASONS:
            return jsonify({"error": f'Reason "{reason}" is not valid for an in-store log.'}), 400

        # determine compensation
        compensation = item.get("compensation", "pending")

        # cashier cannot set compensation — always auto
        if current_user.role == "cashier":
            compensation = "returned" if reason == "change_of_mind" else "pending"

        # change_of_mind always forces returned (straight back to shelf)
        if reason == "change_of_mind":
            compensation = "returned"

        # defect/damage from customer — always pending for cashier (needs admin review)
        if reason in ("defect", "damage") and current_user.role == "cashier":
            compensation = "pending"

        # validate compensation value
        if compensation not in ("pending", "loss", "returned"):
            return jsonify({"error": f'Invalid compensation "{compensation}".'}), 400

        stock = product.inventory.quantity_available if product.inventory else 0

        # pending/loss pull from available stock — need enough
        if compensation in ("pending", "loss") and qty > stock:
            return jsonify({"error": f'"{product.product_name.capitalize()}": only {stock} in stock.'}), 400
        # returned on fresh log = item coming back (change_of_mind or supplier return)
        # no stock check needed — it's adding back, not deducting

        item["_compensation"] = compensation  # store resolved compensation

    # pre-calculate header totals
    total_unit    = sum(float(Product.query.get(i["product_id"]).unit_price)    * int(i["qty"]) for i in items)
    total_revenue = sum(float(Product.query.get(i["product_id"]).revenue_price) * int(i["qty"]) for i in items)
    total_amount  = sum(float(Product.query.get(i["product_id"]).product_price) * int(i["qty"]) for i in items)

    # save header
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
        product      = Product.query.get(item["product_id"])
        qty          = int(item["qty"])
        reason       = item["reason"]
        compensation = item["_compensation"]

        # txn_ref — store as integer (the raw transaction_id), not the formatted string
        txn_ref_raw = item.get("txn_ref") if reason in CUSTOMER_REASONS else None
        if txn_ref_raw:
            try:
                txn_ref = int(str(txn_ref_raw).upper().replace("TXN-", ""))
            except (ValueError, TypeError):
                txn_ref = None
        else:
            txn_ref = None
        log_type = item.get("log_type", "instore")

        detail = DefectDetail(
            defect_id               = defect.defect_id,
            product_id              = product.product_id,
            quantity                = qty,
            reason                  = reason,
            compensation            = compensation,
            unit_price_at_defect    = float(product.unit_price),
            revenue_price_at_defect = float(product.revenue_price),
            price_at_defect         = float(product.product_price),
            subtotal_unit           = round(float(product.unit_price)    * qty, 2),
            subtotal_revenue        = round(float(product.revenue_price) * qty, 2),
            subtotal_amount         = round(float(product.product_price) * qty, 2),
            transaction_id          = txn_ref,
        )
        db.session.add(detail)

        _apply_inventory(product.product_id, qty, compensation, reason=reason)

        logged.append({
            "product_name": product.product_name.capitalize(),
            "qty":          qty,
            "log_type":     "Customer Return" if log_type == "customer" else "In-Store",
            "reason":       REASON_LABELS[reason],
            "compensation": COMPENSATION_LABELS[compensation],
            "txn_ref":      f"TXN-{txn_ref:05d}" if txn_ref else None,
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
        "recorded_by": f"{current_user.first_name} {current_user.last_name}".strip().title() or current_user.username,
        "datetime":    defect.defect_datetime.strftime("%b %d, %Y %I:%M %p"),
    })


# ── Full history (all records, all statuses) ──────────────────────────────────
@defects_bp.route("/history")
@login_required
@role_required("superadmin", "admin", "stocking", "cashier")
def history():
    from app.models.user import User
    page          = request.args.get("page", 1, type=int)
    search        = request.args.get("search", "").strip()
    filter_reason = request.args.get("reason", "")
    filter_comp   = request.args.get("compensation", "")
    per_page      = 15

    query = (
        db.session.query(DefectDetail, Defect, Product, User)
        .join(Defect,  Defect.defect_id   == DefectDetail.defect_id)
        .join(Product, Product.product_id == DefectDetail.product_id)
        .join(User,    User.user_id       == Defect.user_id)
    )
    if search:
        query = query.filter(
            db.or_(Product.product_name.ilike(f"%{search}%"),
                   Product.product_id.ilike(f"%{search}%"))
        )
    if filter_reason:
        query = query.filter(DefectDetail.reason == filter_reason)
    if filter_comp:
        query = query.filter(DefectDetail.compensation == filter_comp)

    total       = query.count()
    all_details = query.order_by(Defect.defect_datetime.desc()) \
                       .offset((page - 1) * per_page).limit(per_page).all()
    pages       = (total + per_page - 1) // per_page

    return render_template("defects/history.html",
                           all_details=all_details,
                           page=page, pages=pages, total=total,
                           search=search,
                           filter_reason=filter_reason,
                           filter_comp=filter_comp,
                           REASONS=REASONS,
                           REASON_LABELS=REASON_LABELS,
                           COMPENSATION_LABELS=COMPENSATION_LABELS)