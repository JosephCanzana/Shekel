from datetime import datetime
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app.utils.decorator import role_required
from app.utils.index_helpers import *
from app.models.stock_adjustment_request import StockAdjustmentRequest
from app.models.stock_adjustment_detail  import StockAdjustmentDetail
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
    pending = StockAdjustmentRequest.query\
                .filter_by(status="pending")\
                .order_by(StockAdjustmentRequest.submitted_at.asc())\
                .all()
    history = StockAdjustmentRequest.query\
                .filter(StockAdjustmentRequest.status != "pending")\
                .order_by(StockAdjustmentRequest.reviewed_at.desc())\
                .limit(30).all()
    return render_template(
        "admin/requests.html",
        pending_data = [r.to_dict() for r in pending],
        history_data = [r.to_dict() for r in history],
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