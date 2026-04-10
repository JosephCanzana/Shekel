from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required, current_user
from app.utils.decorator import role_required
from app.models.product import Product
from app.models.product_bundle import ProductBundle
from app.models.inventory import Inventory
from app.models.stock_in import StockIn
from app.models.stock_adjustment_request import StockAdjustmentRequest
from app.models.stock_adjustment_detail  import StockAdjustmentDetail
from app.extensions import db
from app.utils.index_helpers import *
from app.utils.helpers import generate_charge_token, _pht_fix
from app.utils.audit import audit

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
@role_required("superadmin", "admin", "stocking")
def stock_in():
    session["stockin_token"] = generate_charge_token()
    return render_template("stocking/stock_in.html", stockin_token=session["stockin_token"])


# ── API: search suggestions ───────────────────────────────────────────────────
@stocking_bp.route("/api/search", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "stocking")
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
            "total_price":  float(p.total_price),
            "stock":        stock,
        })

    return jsonify(results)


# ── API: lookup by barcode or name ────────────────────────────────────────────
@stocking_bp.route("/api/lookup", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "stocking")
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
        "total_price":       float(product.total_price),
        "stock":             stock,
        "bundle":            bundle_info,
        "scanned_as_bundle": scanned_as_bundle,
    })


# ── API: complete stock-in ────────────────────────────────────────────────────
# ─ Branching logic by role:
#   admin / superadmin → direct commit to inventory (existing behaviour)
#   stocking           → creates a pending StockAdjustmentRequest for admin review
@stocking_bp.route("/api/complete", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "stocking")
def complete():
    data  = request.json or {}
    items = data.get("items", [])
    notes = data.get("notes", "").strip()

    # ── idempotency token ─────────────────────────────────────────────────────
    token = data.get("stockin_token")
    if not token or token != session.get("stockin_token"):
        return jsonify({"error": "Duplicate or invalid submission."}), 409
    session.pop("stockin_token", None)

    if not items:
        return jsonify({"error": "No items to receive."}), 400

    is_privileged = current_user.role in ("admin", "superadmin")

    # ══════════════════════════════════════════════════════════════════════════
    # PATH A — admin / superadmin: direct inventory update (unchanged behaviour)
    # ══════════════════════════════════════════════════════════════════════════
    if is_privileged:
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

            # log permanent stock-in record
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
                "new_stock":    product.inventory.quantity_available if product.inventory else qty,
            })

        try:
            names = ", ".join(r["product_name"] for r in received)
            audit(
                "INSERT",
                "Stock_In",
                f"Direct stock-in: {len(received)} product(s) [{names}] by {current_user.full_name}",
                reference_table="StockIn",
                user_id=current_user.user_id
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify({"error": "Failed to save. Please try again."}), 500

        return jsonify({
            "success":     True,
            "mode":        "direct",          # ← tells frontend to show "Complete" receipt
            "received":    received,
            "total_items": len(received),
            "total_units": sum(r["qty"] for r in received),
            "recorded_by": current_user.full_name,
            "datetime":    datetime.utcnow().strftime("%b %d, %Y %I:%M %p"),
        })

    # ══════════════════════════════════════════════════════════════════════════
    # PATH B — stocking role: create pending approval request
    # ══════════════════════════════════════════════════════════════════════════
    req = StockAdjustmentRequest(
        requested_by = current_user.user_id,
        request_type = "stock_in",
        status       = "pending",
        submitted_at = datetime.utcnow()
    )
    db.session.add(req)
    db.session.flush()  # populate req.request_id before inserting details

    submitted = []
    for item in items:
        product_id = item.get("product_id")
        try:
            qty = int(item.get("qty", 0))
        except (ValueError, TypeError):
            db.session.rollback()
            return jsonify({"error": f"Invalid quantity for product '{product_id}'."}), 400

        item_notes = item.get("notes", "").strip() or notes

        if qty <= 0:
            continue

        product = Product.query.get(product_id)
        if not product or product.status == "archived":
            db.session.rollback()
            return jsonify({"error": f'Product "{product_id}" not found or archived.'}), 400

        db.session.add(StockAdjustmentDetail(
            request_id         = req.request_id,
            product_id         = product_id,
            quantity_requested = qty,
            quantity_approved  = None,
            status             = "pending",
            note               = item_notes or None,
        ))

        submitted.append({
            "product_name": product.product_name.capitalize(),
            "qty":          qty,
            "current_stock": product.inventory.quantity_available if product.inventory else 0,
        })

    try:
        audit(
            "INSERT",
            "Stock_In",
            f"Stock-in request #{req.request_id} submitted by {current_user.full_name} with {len(items)} items",
            reference_id=req.request_id,
            reference_table="StockAdjustmentRequest",
            user_id=current_user.user_id
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to submit request. Please try again."}), 500

    return jsonify({
        "success":     True,
        "mode":        "pending",             # ← tells frontend to show "Pending" receipt
        "request_id":  req.request_id,
        "submitted":   submitted,
        "total_items": len(submitted),
        "total_units": sum(s["qty"] for s in submitted),
        "recorded_by": current_user.full_name,
        "datetime":    datetime.utcnow().strftime("%b %d, %Y %I:%M %p"),
    })


@stocking_bp.route("/api/refresh-token", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "stocking")
def refresh_token():
    session["stockin_token"] = generate_charge_token()
    return jsonify({"stockin_token": session["stockin_token"]})


# ── Stocking: view own requests ───────────────────────────────────────────────
@stocking_bp.route("/requests")
@login_required
@role_required("stocking")
def my_requests():
    # ── Stock requests ────────────────────────────────────────────
    pending = StockAdjustmentRequest.query.filter_by(
        requested_by=current_user.user_id,
        status="pending"
    ).order_by(StockAdjustmentRequest.submitted_at.desc()).all()
    history = StockAdjustmentRequest.query.filter(
        StockAdjustmentRequest.requested_by == current_user.user_id,
        StockAdjustmentRequest.status != "pending"
    ).order_by(StockAdjustmentRequest.reviewed_at.desc()).limit(30).all()
 
    # ── This user's defect submissions ────────────────────────────
    def _serialize(detail, defect, product):
        return {
            "detail_id":    detail.defect_detail_id,
            "product_name": product.product_name.capitalize(),
            "product_id":   product.product_id,
            "quantity":     detail.quantity,
            "origin_label": "Customer" if detail.origin == "customer" else "In-Store",
            "reason_label": detail.reason.replace("_", " ").title(),
            "customer_compensation": detail.customer_compensation.replace("_", " ").title(),
            "status":          detail.status,
            "rejection_note":  detail.rejection_note or "",
            "transaction_id":  f"TXN-{detail.transaction_id:05d}" if detail.transaction_id else None,
            "datetime":        to_pht(defect.defect_datetime).strftime("%b %d, %Y %I:%M %p"),
        }
 
    defect_pending = (
        db.session.query(DefectDetail, Defect, Product)
        .join(Defect,  Defect.defect_id     == DefectDetail.defect_id)
        .join(Product, Product.product_id   == DefectDetail.product_id)
        .filter(Defect.user_id          == current_user.user_id)
        .filter(DefectDetail.status     == "submitted")
        .filter(DefectDetail.is_archived == False)
        .order_by(Defect.defect_datetime.desc())
        .all()
    )
 
    defect_history = (
        db.session.query(DefectDetail, Defect, Product)
        .join(Defect,  Defect.defect_id     == DefectDetail.defect_id)
        .join(Product, Product.product_id   == DefectDetail.product_id)
        .filter(Defect.user_id              == current_user.user_id)
        .filter(DefectDetail.status.in_(["active", "rejected"]))
        .filter(DefectDetail.is_archived     == False)
        .order_by(Defect.defect_datetime.desc())
        .limit(30)
        .all()
    )
 
    def _history_dict(r):
        d = _pht_fix(r.to_dict())
        d['details'] = [
            {
                'product_id':         det.product_id,
                'product_name':       Product.query.get(det.product_id).product_name.capitalize(),
                'quantity_requested': det.quantity_requested,
                'quantity_approved':  det.quantity_approved,
                'status':             det.status,
                'rejection_reason':   det.rejection_reason or '',
                'note':               det.note or '',
            }
            for det in r.details
        ]
        return d

    return render_template(
        "stocking/requests.html",
        pending_data    = [_pht_fix(r.to_dict()) for r in pending],
        history_data    = [_history_dict(r) for r in history],
        defect_pending  = [_serialize(d, def_, p) for d, def_, p in defect_pending],
        defect_history  = [_serialize(d, def_, p) for d, def_, p in defect_history],
    )

# ── Stocking: edit a pending request item ─────────────────────────────────────
@stocking_bp.route("/requests/<int:request_id>/edit", methods=["POST"])
@login_required
@role_required("stocking")
def edit_request(request_id):
    req = StockAdjustmentRequest.query.get_or_404(request_id)

    # only own requests, only pending
    if req.requested_by != current_user.user_id:
        return jsonify({"error": "Not authorized."}), 403
    if req.status != "pending":
        return jsonify({"error": "Only pending requests can be edited."}), 409

    data  = request.json or {}
    items = data.get("items", [])  # [{detail_id, qty, notes}]

    for item in items:
        detail = StockAdjustmentDetail.query.get(item.get("detail_id"))
        if not detail or detail.request_id != request_id:
            continue
        try:
            qty = int(item.get("qty", 0))
            if qty <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid quantity for item {item.get('detail_id')}."}), 400

        detail.quantity_requested = qty
        detail.note = (item.get("notes") or "").strip() or detail.note

    try:
        audit(
            "UPDATE",
            "Stock_In",
            f"Edited stock-in request #{req.request_id}",
            reference_id=req.request_id,
            reference_table="StockAdjustmentRequest",
            user_id=current_user.user_id
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to save changes."}), 500

    return jsonify({"ok": True})


# ── Stocking: cancel a pending request ───────────────────────────────────────
@stocking_bp.route("/requests/<int:request_id>/cancel", methods=["POST"])
@login_required
@role_required("stocking")
def cancel_request(request_id):
    req = StockAdjustmentRequest.query.get_or_404(request_id)

    if req.requested_by != current_user.user_id:
        return jsonify({"error": "Not authorized."}), 403
    if req.status != "pending":
        return jsonify({"error": "Only pending requests can be cancelled."}), 409

    try:
        db.session.delete(req)
        audit(
            "DELETE",
            "Stock_In",
            f"Cancelled stock-in request #{req.request_id}",
            reference_id=req.request_id,
            reference_table="StockAdjustmentRequest",
            user_id=current_user.user_id
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to cancel request."}), 500

    return jsonify({"ok": True})