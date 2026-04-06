from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, url_for
from flask_login import login_required, current_user
from app.utils.decorator import role_required
from app.utils.index_helpers import *
from app.models.stock_adjustment_request import StockAdjustmentRequest
from app.models.stock_adjustment_detail  import StockAdjustmentDetail
from app.models.defect_detail import DefectDetail
from app.models.defect import Defect
from app.models.product import Product
from app.models.user import User
from app.utils.helpers import to_pht, _pht_fix
from app.models.inventory import Inventory
from app.models.stock_in  import StockIn
from app.extensions import db

admin_bp = Blueprint("admin", __name__, url_prefix='/admin')


@admin_bp.route("/")
@login_required
@role_required("superadmin", "admin")
def dashboard():
    stats   = get_admin_stats()
    pending = StockAdjustmentRequest.query\
                .filter_by(status="pending")\
                .order_by(StockAdjustmentRequest.submitted_at.asc())\
                .limit(3).all()
    return render_template(
        "admin/dashboard.html",
        time_of_day              = get_time_of_day(),
        stats                    = stats,
        recent_transactions      = stats["recent_transactions"],
        low_stock_items          = get_low_stock_items(),
        defects                  = get_defects(),
        pending_requests_preview = [r.to_dict() for r in pending],
    )


# ── Approval page ─────────────────────────────────────────────────────────────
@admin_bp.route("/requests")
@login_required
@role_required("superadmin", "admin")
def requests_page():
    # ── Stock requests ────────────────────────────────────────────
    pending = StockAdjustmentRequest.query\
        .filter_by(status="pending")\
        .order_by(StockAdjustmentRequest.submitted_at.asc())\
        .all()
    history = StockAdjustmentRequest.query\
        .filter(StockAdjustmentRequest.status != "pending")\
        .order_by(StockAdjustmentRequest.reviewed_at.desc())\
        .limit(30).all()
 
    # ── Defect submitted items awaiting approval ───────────────────
    defect_rows = (
        db.session.query(DefectDetail, Defect, Product, User)
        .join(Defect,   Defect.defect_id     == DefectDetail.defect_id)
        .join(Product,  Product.product_id   == DefectDetail.product_id)
        .join(User,     User.user_id         == Defect.user_id)
        .filter(DefectDetail.status     == "submitted")
        .filter(DefectDetail.is_deleted == False)
        .order_by(Defect.defect_datetime.asc())
        .all()
    )
 
    defect_data = [
        {
            "detail_id":    detail.defect_detail_id,
            "product_id":   product.product_id,
            "product_name": product.product_name.capitalize(),
            "quantity":     detail.quantity,
            "origin":       detail.origin,
            "origin_label": "Customer" if detail.origin == "customer" else "In-Store",
            "reason":       detail.reason,
            "reason_label": detail.reason.replace("_", " ").title(),
            "customer_compensation": detail.customer_compensation.replace("_", " ").title(),
            "transaction_id": f"TXN-{detail.transaction_id:05d}" if detail.transaction_id else None,
            "logged_by":    f"{user.first_name} {user.last_name}".strip().title(),
            "logged_role":  user.role,
            "datetime":     to_pht(defect.defect_datetime).strftime("%b %d, %Y %I:%M %p"),
            "approve_url":  url_for("defects.approve",     detail_id=detail.defect_detail_id),
            "reject_url":   url_for("defects.reject",      detail_id=detail.defect_detail_id),
            "delete_url":   url_for("defects.soft_delete", detail_id=detail.defect_detail_id),
        }
        for detail, defect, product, user in defect_rows
    ]
    # ── Supplier comp proposals from stocking ─────────────────────────
    proposal_rows = (
        db.session.query(DefectDetail, Defect, Product, User)
        .join(Defect,   Defect.defect_id     == DefectDetail.defect_id)
        .join(Product,  Product.product_id   == DefectDetail.product_id)
        .join(User,     User.user_id         == Defect.user_id)
        .filter(DefectDetail.status                        == "active")
        .filter(DefectDetail.supplier_compensation         == "pending")
        .filter(DefectDetail.proposed_supplier_compensation != None)
        .filter(DefectDetail.is_deleted                   == False)
        .order_by(Defect.defect_datetime.asc())
        .all()
    )

    proposal_data = [
        {
            "detail_id":    detail.defect_detail_id,
            "product_name": product.product_name.capitalize(),
            "product_id":   product.product_id,
            "quantity":     detail.quantity,
            "origin_label": "Customer" if detail.origin == "customer" else "In-Store",
            "reason_label": detail.reason.replace("_", " ").title(),
            "proposed":     detail.proposed_supplier_compensation.replace("_", " ").title(),
            "proposed_raw": detail.proposed_supplier_compensation,
            "logged_by":    f"{user.first_name} {user.last_name}".strip().title(),
            "datetime":     to_pht(defect.defect_datetime).strftime("%b %d, %Y %I:%M %p"),
            "approve_url":  url_for("defects.review",      detail_id=detail.defect_detail_id),
            "reject_url":   url_for("defects.clear_proposal", detail_id=detail.defect_detail_id),
        }
        for detail, defect, product, user in proposal_rows
    ]

    defect_history_rows = (
        db.session.query(DefectDetail, Defect, Product, User)
        .join(Defect,   Defect.defect_id     == DefectDetail.defect_id)
        .join(Product,  Product.product_id   == DefectDetail.product_id)
        .join(User,     User.user_id         == Defect.user_id)
        .filter(DefectDetail.status.in_(["active", "rejected"]))
        .filter(DefectDetail.is_deleted == False)
        .order_by(Defect.defect_datetime.desc())
        .limit(30).all()
    )

    defect_history = [
        {
            "product_name":          product.product_name.capitalize(),
            "quantity":              detail.quantity,
            "origin_label":          "Customer" if detail.origin == "customer" else "In-Store",
            "reason_label":          detail.reason.replace("_", " ").title(),
            "customer_compensation": detail.customer_compensation.replace("_", " ").title(),
            "supplier_compensation": detail.supplier_compensation.replace("_", " ").title(),
            "status":                detail.status,
            "logged_by":             f"{user.first_name} {user.last_name}".strip().title(),
            "rejection_note":        detail.rejection_note or "",
            "datetime":              to_pht(defect.defect_datetime).strftime("%b %d, %Y %I:%M %p"),
        }
        for detail, defect, product, user in defect_history_rows
    ]
 
    return render_template(
        "admin/requests.html",
        pending_data = [_pht_fix(r.to_dict()) for r in pending],
        history_data = [_pht_fix(r.to_dict()) for r in history],
        defect_data  = defect_data,
        proposal_data=proposal_data,
        defect_history=defect_history
        )

# ── Review API ────────────────────────────────────────────────────────────────
# Accepts per-item decisions: approve (with optional partial qty) or reject
# On approve → writes to Inventory + StockIn log immediately
@admin_bp.route("/requests/<int:request_id>/review", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def review_request(request_id):
    req = StockAdjustmentRequest.query.get_or_404(request_id)

    if req.status != "pending":
        return jsonify({"error": "This request has already been reviewed."}), 409

    data      = request.json or {}
    decisions = data.get("decisions", [])

    if not decisions:
        return jsonify({"error": "No decisions provided."}), 400

    decision_map = {d["detail_id"]: d for d in decisions}

    for detail in req.details:
        decision = decision_map.get(detail.detail_id)
        if not decision:
            continue

        action = decision.get("action")

        product = detail.product
        
        if action == "approve":
            # default to full requested qty; admin may lower (partial approval)
            raw_qty = decision.get("quantity_approved")
            try:
                qty = int(raw_qty) if raw_qty is not None else detail.quantity_requested
                if qty <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                return jsonify({"error": f"Invalid quantity for '{detail.product.product_name}'."}), 400

            detail.approve(qty)
            if detail.request.request_type == "adjustment":
                # set absolute value, not increment
                if product and product.status != "archived":
                    if product.inventory:
                        product.inventory.quantity_available = qty  # ← set, not +=
                        product.inventory.last_updated        = datetime.utcnow()
            else:

                # apply to inventory
                if product and product.status != "archived":
                    if product.inventory:
                        product.inventory.quantity_available += qty
                        product.inventory.last_updated        = datetime.utcnow()
                    else:
                        db.session.add(Inventory(
                            product_id         = detail.product_id,
                            quantity_available = qty,
                            quantity_defective = 0,
                            last_updated       = datetime.utcnow()
                        ))

                    # permanent stock-in record
                    db.session.add(StockIn(
                        product_id        = detail.product_id,
                        user_id           = current_user.user_id,
                        quantity_received = qty,
                        stockin_datetime  = datetime.utcnow(),
                        notes             = detail.note or None
                    ))

        elif action == "reject":
            reason = (decision.get("rejection_reason") or "").strip() or None
            detail.reject(reason)

    req.reviewed_by = current_user.user_id
    req.reviewed_at = datetime.utcnow()
    req.recompute_status()

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to save. Please try again."}), 500

    return jsonify({
        "success":        True,
        "request_id":     req.request_id,
        "status":         req.status,
        "approved_count": req.approved_count,
        "rejected_count": req.rejected_count,
    })


@admin_bp.route("/reports")
@login_required
@role_required("superadmin")
def reports():
    return "reports"


@admin_bp.route("/audit_logs")
@login_required
@role_required("superadmin")
def audit_logs():
    return "logs"


