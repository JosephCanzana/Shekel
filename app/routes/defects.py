from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import login_required, current_user
from app.utils.decorator import role_required
from app.models.product import Product
from app.models.product_bundle import ProductBundle
from app.models.inventory import Inventory
from app.models.defect import Defect
from app.models.defect_detail import DefectDetail
from app.models.sale import Sale
from app.extensions import db
from app.utils.helpers import generate_charge_token
from app.utils.audit import audit

defects_bp = Blueprint("defects", __name__, url_prefix="/defects")


# ── Constants ─────────────────────────────────────────────────────────────────
PHT_OFFSET = timedelta(hours=8)
REASONS = ["damaged", "expired", "change_of_mind"]

REASON_LABELS = {
    "damaged":        "Damaged",
    "expired":        "Expired",
    "change_of_mind": "Change of Mind",
}

CUSTOMER_COMP_LABELS = {
    "full_refund":        "Full Refund",
    "partial_refund":     "Partial Refund",
    "exchange_same":      "Exchange – Same Item",
    "exchange_different": "Exchange – Different Item",
    "none":               "None",
}

SUPPLIER_COMP_LABELS = {
    "pending":        "Pending",
    "loss":           "Loss",
    "same_item":      "Same Item",
    "different_item": "Different Item",
    "money":          "Cash Reimbursement",
    "none":           "N/A",
}

STATUS_LABELS = {
    "submitted": "Submitted",
    "active":    "Active",
    "rejected":  "Rejected",
}

INSTORE_REASONS      = {"damaged", "expired"}
CUSTOMER_REASONS     = {"change_of_mind", "damaged", "expired"}
VALID_CUSTOMER_COMPS = {"full_refund", "partial_refund", "exchange_same", "exchange_different", "none"}
VALID_SUPPLIER_COMPS = {"pending", "loss", "same_item", "different_item", "money", "none"}
RESOLVABLE_SUP_COMPS = {"loss", "same_item", "different_item", "money"}


# ── Role helpers ──────────────────────────────────────────────────────────────

def can_approve():
    return current_user.role in ("superadmin", "admin")

def can_delete():
    return current_user.role in ("superadmin", "admin")

def can_review():
    return current_user.role in ("superadmin", "admin")

def can_propose():
    return current_user.role == "stocking"

def can_set_compensation():
    return current_user.role in ("superadmin", "admin", "stocking")

def is_admin():
    return current_user.role in ("superadmin", "admin")


# ── Inventory helpers ─────────────────────────────────────────────────────────

def _apply_inventory_on_activate(detail):
    """
    Apply inventory movement when a submitted record is approved and goes active.

    Customer + change_of_mind → A+          (item returns to shelf)
    Customer + damaged/expired → D+          (item goes to defective watch; A unchanged — already sold)
    In-store + pending         → A− D+       (pulled from available, held in defective)
    In-store + other           → A−          (pulled from available, no defective watch)
    """
    inv = Inventory.query.filter_by(product_id=detail.product_id).first()
    if not inv:
        return

    qty = detail.quantity

    if detail.origin == "customer":
        if detail.reason == "change_of_mind":
            inv.quantity_available += qty
        else:
            inv.quantity_defective = (inv.quantity_defective or 0) + qty
    else:
        inv.quantity_available = max(0, inv.quantity_available - qty)
        if detail.supplier_compensation == "pending":
            inv.quantity_defective = (inv.quantity_defective or 0) + qty

    inv.last_updated = datetime.utcnow()


def _apply_supplier_decision(detail, new_sup_comp):
    """
    Apply inventory movement when supplier compensation is resolved from pending.

    loss           → D−          (item discarded / supplier absorbs; no restock)
    same_item      → D− A+       (supplier brings replacement; item leaves defective)
    different_item → D− A+       (same as above, different product)
    money          → D−          (supplier pays cash; item is gone)
    """
    inv = Inventory.query.filter_by(product_id=detail.product_id).first()
    if not inv:
        return

    qty = detail.quantity

    if new_sup_comp == "loss":
        inv.quantity_defective = max(0, (inv.quantity_defective or 0) - qty)
    elif new_sup_comp in ("same_item", "different_item"):
        inv.quantity_defective = max(0, (inv.quantity_defective or 0) - qty)
        inv.quantity_available += qty
    elif new_sup_comp == "money":
        inv.quantity_defective = max(0, (inv.quantity_defective or 0) - qty)

    inv.last_updated = datetime.utcnow()


def _undo_supplier_decision(detail, old_sup_comp):
    """Reverse a previously applied supplier compensation (for update_review)."""
    inv = Inventory.query.filter_by(product_id=detail.product_id).first()
    if not inv:
        return

    qty = detail.quantity

    if old_sup_comp == "loss":
        inv.quantity_defective = (inv.quantity_defective or 0) + qty
    elif old_sup_comp in ("same_item", "different_item"):
        inv.quantity_defective = (inv.quantity_defective or 0) + qty
        inv.quantity_available = max(0, inv.quantity_available - qty)
    elif old_sup_comp == "money":
        inv.quantity_defective = (inv.quantity_defective or 0) + qty

    inv.last_updated = datetime.utcnow()


def _reverse_all_inventory(detail):
    """
    Fully reverse all inventory changes for an active record (used on soft delete).
    Submitted / rejected records never touched inventory — nothing to reverse.

    Net effects per state, and their reversals:

    customer + change_of_mind + any        → net A+     → undo A−
    customer + damaged/expired + pending   → net D+     → undo D−
    customer + damaged/expired + loss/money→ net  0     → nothing
    customer + damaged/expired + same/diff → net A+     → undo A−

    in_store + pending                     → net A− D+  → undo A+ D−
    in_store + loss/money                  → net A−     → undo A+   (D net 0)
    in_store + same/diff                   → net  0     → nothing   (A− D+ D− A+ = 0)
    """
    if detail.status != "active":
        return

    inv = Inventory.query.filter_by(product_id=detail.product_id).first()
    if not inv:
        return

    qty = detail.quantity
    sc  = detail.supplier_compensation

    if detail.origin == "customer":
        if detail.reason == "change_of_mind":
            inv.quantity_available = max(0, inv.quantity_available - qty)
        else:
            if sc == "pending":
                inv.quantity_defective = max(0, (inv.quantity_defective or 0) - qty)
            elif sc in ("loss", "money"):
                pass  # net 0
            elif sc in ("same_item", "different_item"):
                inv.quantity_available = max(0, inv.quantity_available - qty)
    else:
        inv.quantity_available += qty
        if sc == "pending":
            inv.quantity_defective = max(0, (inv.quantity_defective or 0) - qty)
        elif sc in ("loss", "money"):
            pass  # D net 0 already
        elif sc in ("same_item", "different_item"):
            inv.quantity_available = max(0, inv.quantity_available - qty)

    inv.last_updated = datetime.utcnow()


# ── Page routes ───────────────────────────────────────────────────────────────

@defects_bp.route("/")
@login_required
@role_required("superadmin", "admin", "stocking", "cashier")
def index():
    from app.models.user import User
    page          = request.args.get("page", 1, type=int)
    search        = request.args.get("search", "").strip()
    filter_reason = request.args.get("reason", "")
    per_page      = 15
    date_from = request.args.get("date_from", "").strip()
    date_to   = request.args.get("date_to",   "").strip()

    # Submitted queue — admin / superadmin only
    submitted_items = []
    if is_admin():
        sub_q = (
            db.session.query(DefectDetail, Defect, Product, User)
            .join(Defect,  Defect.defect_id   == DefectDetail.defect_id)
            .join(Product, Product.product_id == DefectDetail.product_id)
            .join(User,    User.user_id       == Defect.user_id)
            .filter(DefectDetail.status      == "submitted")
            .filter(DefectDetail.is_archived == False)
            .filter(Defect.is_archived       == False)
        )

        # ── parse dates ───────────────────────────────────────────────────────
        parsed_from = None
        parsed_to   = None

        if date_from:
            try:
                parsed_from = datetime.strptime(date_from, "%Y-%m-%d") - PHT_OFFSET
            except ValueError:
                flash("Invalid 'Date From' format.", "error")

        if date_to:
            try:
                parsed_to = datetime.strptime(date_to, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                ) - PHT_OFFSET
            except ValueError:
                flash("Invalid 'Date To' format.", "error")

        # ── reject reversed range ─────────────────────────────────────────────
        if parsed_from and parsed_to and parsed_from > parsed_to:
            flash("'Date From' cannot be later than 'Date To'.", "error")
            parsed_from = None
            parsed_to   = None

        if parsed_from:
            sub_q = sub_q.filter(Defect.defect_datetime >= parsed_from)
        if parsed_to:
            sub_q = sub_q.filter(Defect.defect_datetime <= parsed_to)

        if search:
            sub_q = sub_q.filter(db.or_(
                Product.product_name.ilike(f"%{search}%"),
                Product.product_id.ilike(f"%{search}%"),
            ))
        if filter_reason:
            sub_q = sub_q.filter(DefectDetail.reason == filter_reason)

        submitted_items = sub_q.order_by(Defect.defect_datetime.asc()).all()

    # Watch list — active records with supplier compensation still pending
    watch_q = (
        db.session.query(DefectDetail, Defect, Product, User)
        .join(Defect,  Defect.defect_id   == DefectDetail.defect_id)
        .join(Product, Product.product_id == DefectDetail.product_id)
        .join(User,    User.user_id       == Defect.user_id)
        .filter(DefectDetail.status               == "active")
        .filter(DefectDetail.supplier_compensation == "pending")
        .filter(DefectDetail.is_archived           == False)
        .filter(Defect.is_archived                 == False)
    )
    if date_from:
        try:
            sub_q   = sub_q.filter(Defect.defect_datetime >= datetime.strptime(date_from, "%Y-%m-%d"))
            watch_q = watch_q.filter(Defect.defect_datetime >= datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            pass
    if date_to:
        try:
            sub_q   = sub_q.filter(Defect.defect_datetime < datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59))
            watch_q = watch_q.filter(Defect.defect_datetime < datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59))
        except ValueError:
            pass
    if search:
        watch_q = watch_q.filter(db.or_(
            Product.product_name.ilike(f"%{search}%"),
            Product.product_id.ilike(f"%{search}%"),
        ))
    if filter_reason:
        watch_q = watch_q.filter(DefectDetail.reason == filter_reason)

    total   = watch_q.count()
    pending = watch_q.order_by(Defect.defect_datetime.desc()) \
                     .offset((page - 1) * per_page).limit(per_page).all()
    pages   = (total + per_page - 1) // per_page

    return render_template(
        "defects/index.html",
        submitted_items=submitted_items,
        pending=pending,
        page=page, pages=pages, total=total,
        search=search, filter_reason=filter_reason,
        date_from=date_from,
        date_to=date_to,
        can_approve=can_approve(),
        can_review=can_review(),
        can_delete=can_delete(),
        can_propose=can_propose(),
        REASONS=REASONS,
        REASON_LABELS=REASON_LABELS,
        SUPPLIER_COMP_LABELS=SUPPLIER_COMP_LABELS,
        STATUS_LABELS=STATUS_LABELS,
    )


@defects_bp.route("/log")
@login_required
@role_required("superadmin", "admin", "stocking", "cashier")
def log():
    session["defect_token"] = generate_charge_token()
    return render_template(
        "defects/log.html",
        can_set_compensation=can_set_compensation(),
        is_admin=is_admin(),
        defect_token=session["defect_token"],
    )


@defects_bp.route("/history")
@login_required
@role_required("superadmin", "admin", "stocking", "cashier")
def history():
    from app.models.user import User
    page          = request.args.get("page", 1, type=int)
    search        = request.args.get("search", "").strip()
    filter_reason = request.args.get("reason", "")
    filter_status = request.args.get("status", "")
    filter_origin  = request.args.get("origin", "")
    show_archived  = request.args.get("show_archived", "0") == "1"
    per_page       = 15
    per_page      = 15
    date_from = request.args.get("date_from", "").strip()
    date_to   = request.args.get("date_to",   "").strip()

    query = (
        db.session.query(DefectDetail, Defect, Product, User)
        .join(Defect,  Defect.defect_id   == DefectDetail.defect_id)
        .join(Product, Product.product_id == DefectDetail.product_id)
        .join(User,    User.user_id       == Defect.user_id)
    )
    if not show_archived:
        query = query.filter(DefectDetail.is_archived == False)
        query = query.filter(Defect.is_archived       == False)

    if date_from:
        try:
            query = query.filter(Defect.defect_datetime >= datetime.strptime(date_from, "%Y-%m-%d") - PHT_OFFSET)
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(Defect.defect_datetime <= datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59) - PHT_OFFSET)
        except ValueError:
            pass

    if search:
        query = query.filter(db.or_(
            Product.product_name.ilike(f"%{search}%"),
            Product.product_id.ilike(f"%{search}%"),
        ))
    if filter_reason:
        query = query.filter(DefectDetail.reason == filter_reason)
    if filter_status:
        query = query.filter(DefectDetail.status == filter_status)
    if filter_origin:
        query = query.filter(DefectDetail.origin == filter_origin)

    total       = query.count()
    all_details = query.order_by(Defect.defect_datetime.desc()) \
                       .offset((page - 1) * per_page).limit(per_page).all()
    pages       = (total + per_page - 1) // per_page

    return render_template(
        "defects/history.html",
        all_details=all_details,
        page=page, pages=pages, total=total,
        search=search,
        filter_reason=filter_reason,
        filter_status=filter_status,
        filter_origin=filter_origin,
        show_archived=show_archived, 
        date_from=date_from,
        date_to=date_to,
        can_delete=can_delete(),
        REASONS=REASONS,
        REASON_LABELS=REASON_LABELS,
        CUSTOMER_COMP_LABELS=CUSTOMER_COMP_LABELS,
        SUPPLIER_COMP_LABELS=SUPPLIER_COMP_LABELS,
        STATUS_LABELS=STATUS_LABELS,
    )


@defects_bp.route("/product/<string:product_id>")
@login_required
@role_required("superadmin", "admin", "stocking", "cashier")
def product_history(product_id):
    from app.models.user import User
    product       = Product.query.get_or_404(product_id)
    page          = request.args.get("page", 1, type=int)
    filter_reason = request.args.get("reason", "")
    filter_status  = request.args.get("status", "")
    date_from     = request.args.get("date_from", "").strip()
    date_to       = request.args.get("date_to",   "").strip()
    show_archived  = request.args.get("show_archived", "0") == "1"
    per_page       = 15

    query = (
        db.session.query(DefectDetail, Defect, User)
        .join(Defect, Defect.defect_id == DefectDetail.defect_id)
        .join(User,   User.user_id     == Defect.user_id)
        .filter(DefectDetail.product_id == product_id)
    )
    if not show_archived:
        query = query.filter(DefectDetail.is_archived == False)
        query = query.filter(Defect.is_archived       == False)
    if date_from:
        try:
            query = query.filter(Defect.defect_datetime >= datetime.strptime(date_from, "%Y-%m-%d") - PHT_OFFSET)
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(Defect.defect_datetime <= datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59) - PHT_OFFSET)
        except ValueError:
            pass
    if filter_reason:
        query = query.filter(DefectDetail.reason == filter_reason)
    if filter_status:
        query = query.filter(DefectDetail.status == filter_status)

    total   = query.count()
    details = query.order_by(Defect.defect_datetime.desc()) \
                   .offset((page - 1) * per_page).limit(per_page).all()
    pages   = (total + per_page - 1) // per_page

    return render_template(
        "defects/product_history.html",
        product=product,
        details=details,
        page=page, pages=pages, total=total,
        filter_reason=filter_reason,
        filter_status=filter_status,
        date_from=date_from,
        date_to=date_to,
        show_archived=show_archived,
        can_delete=can_delete(),
        can_review=can_review(),
        can_propose=can_propose(),
        REASONS=REASONS,
        REASON_LABELS=REASON_LABELS,
        CUSTOMER_COMP_LABELS=CUSTOMER_COMP_LABELS,
        SUPPLIER_COMP_LABELS=SUPPLIER_COMP_LABELS,
        STATUS_LABELS=STATUS_LABELS,
    )


# ── Approval actions ──────────────────────────────────────────────────────────

@defects_bp.route("/detail/<int:detail_id>/approve", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def approve(detail_id):
    detail = DefectDetail.query.get_or_404(detail_id)

    if detail.is_archived:
        flash("Record has been deleted.", "warning")
        return redirect(url_for("defects.index"))

    if detail.status != "submitted":
        flash("Only submitted items can be approved.", "warning")
        return redirect(url_for("defects.index"))

    detail.status      = "active"
    detail.reviewed_by = current_user.user_id
    detail.reviewed_at = datetime.utcnow()

    _apply_inventory_on_activate(detail)
    audit(
        "UPDATE",
        "Defects",
        f"Approved defect for '{detail.product.product_name.capitalize()}'",
        reference_id=detail.defect_detail_id,
        reference_table="DefectDetail",
        user_id=current_user.user_id
    )
    db.session.commit()

    name     = detail.product.product_name.capitalize()
    reviewer = f"{current_user.first_name} {current_user.last_name}".strip().title()
    flash(f'"{name}" approved by {reviewer} — added to watch list.', "success")
    return redirect(request.referrer or url_for("defects.index"))


@defects_bp.route("/detail/<int:detail_id>/reject", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def reject(detail_id):
    detail = DefectDetail.query.get_or_404(detail_id)

    if detail.is_archived:
        flash("Record has been deleted.", "warning")
        return redirect(url_for("defects.index"))

    if detail.status != "submitted":
        flash("Only submitted items can be rejected.", "warning")
        return redirect(url_for("defects.index"))

    rejection_note = request.form.get("rejection_note", "").strip()
    if not rejection_note:
        flash("A rejection note is required.", "danger")
        return redirect(request.referrer or url_for("defects.index"))

    detail.status         = "rejected"
    detail.rejection_note = rejection_note
    detail.reviewed_by    = current_user.user_id
    detail.reviewed_at    = datetime.utcnow()
    # No inventory change — submitted records never touched inventory

    audit(
        "UPDATE",
        "Defects",
        f"Rejected defect for '{detail.product.product_name.capitalize()}'",
        reference_id=detail.defect_detail_id,
        reference_table="DefectDetail",
        user_id=current_user.user_id
    )
    db.session.commit()

    name     = detail.product.product_name.capitalize()
    reviewer = f"{current_user.first_name} {current_user.last_name}".strip().title()
    flash(f'"{name}" rejected by {reviewer}.', "warning")
    return redirect(request.referrer or url_for("defects.index"))


@defects_bp.route("/detail/<int:detail_id>/review", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "stocking")
def review(detail_id):
    detail = DefectDetail.query.get_or_404(detail_id)

    if detail.is_archived:
        flash("Record has been deleted.", "warning")
        return redirect(url_for("defects.index"))

    if detail.status != "active" or detail.supplier_compensation != "pending":
        flash("Only active items with pending supplier compensation can be reviewed.", "warning")
        return redirect(url_for("defects.index"))

    new_sup_comp = request.form.get("supplier_compensation", "").strip()
    if new_sup_comp not in RESOLVABLE_SUP_COMPS:
        flash("Invalid supplier compensation.", "danger")
        return redirect(url_for("defects.index"))

    _apply_supplier_decision(detail, new_sup_comp)
    detail.supplier_compensation = new_sup_comp
    detail.proposed_supplier_compensation = None
    detail.reviewed_by           = current_user.user_id
    detail.reviewed_at           = datetime.utcnow()
    audit(
        "UPDATE",
        "Defects",
        f"Reviewed supplier compensation for '{detail.product.product_name.capitalize()}' → {new_sup_comp}",
        reference_id=detail.defect_detail_id,
        reference_table="DefectDetail",
        user_id=current_user.user_id
    )
    db.session.commit()

    name     = detail.product.product_name.capitalize()
    reviewer = f"{current_user.first_name} {current_user.last_name}".strip().title()
    flash(f'"{name}" supplier comp set to {SUPPLIER_COMP_LABELS[new_sup_comp]} by {reviewer}.', "success")
    return redirect(request.referrer or url_for("defects.index"))


@defects_bp.route("/detail/<int:detail_id>/update", methods=["POST"])
@login_required
@role_required("superadmin")
def update_review(detail_id):
    detail = DefectDetail.query.get_or_404(detail_id)

    if detail.is_archived:
        flash("Record has been deleted.", "warning")
        return redirect(request.referrer or url_for("defects.index"))

    if detail.status != "active":
        flash("Only active records can be updated.", "warning")
        return redirect(request.referrer or url_for("defects.index"))

    new_sup_comp = request.form.get("supplier_compensation", "").strip()
    if new_sup_comp not in VALID_SUPPLIER_COMPS:
        flash("Invalid supplier compensation.", "danger")
        return redirect(request.referrer or url_for("defects.index"))

    old_sup_comp = detail.supplier_compensation

    if old_sup_comp == new_sup_comp:
        flash("No change made.", "info")
        return redirect(request.referrer or url_for("defects.index"))

    # Undo old effect, apply new effect
    if old_sup_comp in RESOLVABLE_SUP_COMPS:
        _undo_supplier_decision(detail, old_sup_comp)
    if new_sup_comp in RESOLVABLE_SUP_COMPS:
        _apply_supplier_decision(detail, new_sup_comp)

    detail.supplier_compensation = new_sup_comp
    detail.reviewed_by           = current_user.user_id
    detail.reviewed_at           = datetime.utcnow()
    audit(
        "UPDATE",
        "Defects",
        f"Updated supplier compensation for '{detail.product.product_name.capitalize()}' "
        f"{old_sup_comp} → {new_sup_comp}",
        reference_id=detail.defect_detail_id,
        reference_table="DefectDetail",
        user_id=current_user.user_id
    )
    db.session.commit()

    name     = detail.product.product_name.capitalize()
    reviewer = f"{current_user.first_name} {current_user.last_name}".strip().title()
    flash(
        f'"{name}" supplier comp updated: '
        f'{SUPPLIER_COMP_LABELS[old_sup_comp]} → {SUPPLIER_COMP_LABELS[new_sup_comp]} by {reviewer}.',
        "success",
    )
    return redirect(request.referrer or url_for("defects.index"))


@defects_bp.route("/detail/<int:detail_id>/archive", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def archive_detail(detail_id):
    detail = DefectDetail.query.get_or_404(detail_id)

    if detail.is_archived:
        flash("Record already deleted.", "warning")
        return redirect(request.referrer or url_for("defects.index"))

    _reverse_all_inventory(detail)

    detail.is_archived = True
    detail.archived_by  = current_user.user_id
    detail.archived_at  = datetime.utcnow()
    audit(
        "DELETE",
        "Defects",
        f"Archived defect record for '{detail.product.product_name.capitalize()}'",
        reference_id=detail.defect_detail_id,
        reference_table="DefectDetail",
        user_id=current_user.user_id
    )
    db.session.commit()

    name     = detail.product.product_name.capitalize()
    reviewer = f"{current_user.first_name} {current_user.last_name}".strip().title()
    flash(f'"{name}" record deleted by {reviewer}. Inventory reversed.', "success")
    return redirect(request.referrer or url_for("defects.index"))


@defects_bp.route("/detail/<int:detail_id>/unarchive", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def unarchive_detail(detail_id):
    detail = DefectDetail.query.get_or_404(detail_id)

    if not detail.is_archived:
        flash("Record is not archived.", "warning")
        return redirect(request.referrer or url_for("defects.history"))

    # Restore inventory based on the record's status and compensation
    if detail.status == "active":
        _apply_inventory_on_activate(detail)

    detail.is_archived = False
    detail.archived_by  = None
    detail.archived_at  = None
    audit(
        "UPDATE",
        "Defects",
        f"Restored archived defect record for '{detail.product.product_name.capitalize()}'",
        reference_id=detail.defect_detail_id,
        reference_table="DefectDetail",
        user_id=current_user.user_id
    )
    db.session.commit()

    name     = detail.product.product_name.capitalize()
    reviewer = f"{current_user.first_name} {current_user.last_name}".strip().title()
    flash(f'"{name}" record restored by {reviewer}. Inventory re-applied.', "success")
    return redirect(request.referrer or url_for("defects.history"))


@defects_bp.route("/defect/<int:defect_id>/delete", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def soft_delete_header(defect_id):
    defect = Defect.query.get_or_404(defect_id)

    if defect.is_archived:
        flash("Record already deleted.", "warning")
        return redirect(request.referrer or url_for("defects.index"))

    now = datetime.utcnow()

    for detail in defect.defect_details:
        if detail.is_archived:
            continue
        _reverse_all_inventory(detail)
        detail.is_archived = True
        detail.archived_by  = current_user.user_id
        detail.archived_at  = now

    defect.is_archived = True
    defect.archived_by  = current_user.user_id
    defect.archived_at  = now
    audit(
        "DELETE",
        "Defects",
        f"Archived defect log #{defect.defect_id} and all its items",
        reference_id=defect.defect_id,
        reference_table="Defect",
        user_id=current_user.user_id
    )
    db.session.commit()

    reviewer = f"{current_user.first_name} {current_user.last_name}".strip().title()
    flash(f"Defect log #{defect_id} and all its items deleted by {reviewer}. Inventory reversed.", "success")
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
        "product_id":   p.product_id,
        "product_name": p.product_name.capitalize(),
        "total_price":  float(p.total_price),
        "stock":        p.inventory.quantity_available if p.inventory else 0,
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
        "cost_price":        float(product.cost_price),
        "revenue_price":     float(product.revenue_price),
        "total_price":       float(product.total_price),
        "stock":             stock,
        "bundle":            bundle_info,
        "scanned_as_bundle": scanned_as_bundle,
    })


# ── API: TXN lookup ───────────────────────────────────────────────────────────

@defects_bp.route("/api/txn_lookup", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "stocking", "cashier")
def txn_lookup():
    raw = (request.json or {}).get("txn_ref", "").strip()
    if not raw:
        return jsonify({"error": "No transaction reference provided."}), 400

    txn_id = raw.upper().replace("TXN-", "")
    try:
        txn_id = int(txn_id)
    except ValueError:
        return jsonify({"error": f'"{raw}" is not a valid transaction reference.'}), 400

    sale = Sale.query.get(txn_id)
    if not sale:
        return jsonify({"error": f'Transaction TXN-{txn_id:05d} not found.'}), 404

    items = []
    for sd in sale.sale_details:
        if not sd.product:
            continue

        already_returned = (
            db.session.query(db.func.sum(DefectDetail.quantity))
            .filter(
                DefectDetail.transaction_id == txn_id,
                DefectDetail.product_id     == sd.product_id,
                DefectDetail.is_archived     == False,
                DefectDetail.status.in_(["submitted", "active"]),
            )
            .scalar() or 0
        )
        remaining = max(0, sd.quantity - already_returned)

        items.append({
            "product_id":       sd.product_id,
            "product_name":     sd.product.product_name.capitalize(),
            "total_price":      float(sd.product.total_price),
            "qty_sold":         sd.quantity,
            "already_returned": already_returned,
            "remaining":        remaining,
        })

    return jsonify({
        "txn_id":   txn_id,
        "txn_ref":  f"TXN-{txn_id:05d}",
        "cashier":  f"{sale.user.first_name} {sale.user.last_name}".strip().title() if sale.user else "Unknown",
        "datetime": sale.sale_datetime.strftime("%b %d, %Y %I:%M %p"),
        "items":    items,
    })


# ── API: complete log ─────────────────────────────────────────────────────────

@defects_bp.route("/api/complete", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "stocking", "cashier")
def complete():
    data  = request.json or {}
    items = data.get("items", [])

    token = data.get("defect_token")
    if not token or token != session.get("defect_token"):
        return jsonify({"error": "Duplicate or invalid submission."}), 409
    session.pop("defect_token", None)

    if not items:
        return jsonify({"error": "No items to log."}), 400

    # ── Validate customer TXN ─────────────────────────────────────────────────
    customer_items = [i for i in items if i.get("log_type") == "customer"]
    txn_id = None

    if customer_items:
        needs_txn = [i for i in customer_items if i.get("reason") != "change_of_mind"]
        if needs_txn:
            txn_ref_raw = (customer_items[0].get("txn_ref") or "").strip()
            if not txn_ref_raw:
                return jsonify({"error": "Transaction reference required for customer returns."}), 400

            try:
                txn_id = int(txn_ref_raw.upper().replace("TXN-", ""))
            except ValueError:
                return jsonify({"error": f'"{txn_ref_raw}" is not a valid transaction reference.'}), 400

            sale = Sale.query.get(txn_id)
            if not sale:
                return jsonify({"error": f'Transaction TXN-{txn_id:05d} not found.'}), 404

            sold_map = {}
            for sd in sale.sale_details:
                already = (
                    db.session.query(db.func.sum(DefectDetail.quantity))
                    .filter(
                        DefectDetail.transaction_id == txn_id,
                        DefectDetail.product_id     == sd.product_id,
                        DefectDetail.is_archived     == False,
                        DefectDetail.status.in_(["submitted", "active"]),
                    )
                    .scalar() or 0
                )
                sold_map[sd.product_id] = max(0, sd.quantity - already)

            for item in needs_txn:
                pid = item.get("product_id")
                qty = int(item.get("qty", 0))
                if pid not in sold_map:
                    p = Product.query.get(pid)
                    return jsonify({"error": f'"{p.product_name.capitalize() if p else pid}" was not in TXN-{txn_id:05d}.'}), 400
                if qty > sold_map[pid]:
                    p = Product.query.get(pid)
                    return jsonify({"error": f'"{p.product_name.capitalize() if p else pid}": only {sold_map[pid]} unit(s) eligible.'}), 400

            normalised = f"TXN-{txn_id:05d}"
            for item in customer_items:
                item["txn_ref"] = normalised

    # ── Per-item validation and resolution ────────────────────────────────────
    for item in items:
        product = Product.query.get(item.get("product_id"))
        if not product or product.status == "archived":
            return jsonify({"error": f'Product "{item.get("product_id")}" not found or archived.'}), 400

        qty      = int(item.get("qty", 0))
        reason   = item.get("reason", "")
        log_type = item.get("log_type", "instore")

        if qty <= 0:
            return jsonify({"error": f'Invalid quantity for "{product.product_name}".'}), 400
        if reason not in REASONS:
            return jsonify({"error": f'Invalid reason "{reason}".'}), 400
        if log_type == "customer" and reason not in CUSTOMER_REASONS:
            return jsonify({"error": f'Reason "{reason}" is invalid for a customer return.'}), 400
        if log_type == "instore" and reason not in INSTORE_REASONS:
            return jsonify({"error": f'Reason "{reason}" is invalid for an in-store log.'}), 400

        # ── Resolve workflow status ───────────────────────────────────────────
        role = current_user.role
        if role in ("superadmin", "admin"):
            status = "active"
        elif role == "stocking":
            status = "submitted"
        else:  # cashier
            # change_of_mind is auto-approved; damaged/expired needs admin review
            status = "active" if (log_type == "customer" and reason == "change_of_mind") else "submitted"

        # ── Resolve customer compensation ─────────────────────────────────────
        if log_type == "customer":
            cust_comp = item.get("customer_compensation", "")
            if reason == "change_of_mind":
                cust_comp = cust_comp if cust_comp in ("exchange_same", "exchange_different") else "exchange_same"
            else:
                cust_comp = cust_comp if cust_comp in VALID_CUSTOMER_COMPS else "full_refund"
        else:
            cust_comp = "none"

        # ── Resolve supplier compensation ─────────────────────────────────────
        sup_comp = "none" if reason == "change_of_mind" else "pending"

        # ── Stock check — only in-store items going active deduct from available
        if log_type == "instore" and status == "active":
            stock = product.inventory.quantity_available if product.inventory else 0
            already_queued = sum(
                int(other.get("qty", 0))
                for other in items
                if other is not item
                and other.get("product_id") == product.product_id
                and other.get("log_type") == "instore"
                and other.get("_status") == "active"
            )
            if qty + already_queued > stock:
                return jsonify({"error": f'"{product.product_name.capitalize()}": only {stock} in stock.'}), 400

        item["_status"]    = status
        item["_cust_comp"] = cust_comp
        item["_sup_comp"]  = sup_comp

    # ── Build header ──────────────────────────────────────────────────────────
    total_cost    = sum(float(Product.query.get(i["product_id"]).cost_price)    * int(i["qty"]) for i in items)
    total_revenue = sum(float(Product.query.get(i["product_id"]).revenue_price) * int(i["qty"]) for i in items)
    total_amount  = sum(float(Product.query.get(i["product_id"]).total_price)   * int(i["qty"]) for i in items)

    defect = Defect(
        defect_datetime     = datetime.utcnow(),
        user_id             = current_user.user_id,
        total_cost_price    = round(total_cost,    2),
        total_revenue_price = round(total_revenue, 2),
        total_amount        = round(total_amount,  2),
    )
    db.session.add(defect)
    db.session.flush()

    logged = []
    for item in items:
        product   = Product.query.get(item["product_id"])
        qty       = int(item["qty"])
        reason    = item["reason"]
        log_type  = item["log_type"]
        status    = item["_status"]
        cust_comp = item["_cust_comp"]
        sup_comp  = item["_sup_comp"]
        origin    = "in_store" if log_type == "instore" else "customer"

        txn_ref_raw = item.get("txn_ref") if log_type == "customer" else None
        txn_ref = None
        if txn_ref_raw:
            try:
                txn_ref = int(str(txn_ref_raw).upper().replace("TXN-", ""))
            except (ValueError, TypeError):
                txn_ref = None

        detail = DefectDetail(
            defect_id               = defect.defect_id,
            product_id              = product.product_id,
            quantity                = qty,
            origin                  = origin,
            reason                  = reason,
            status                  = status,
            customer_compensation   = cust_comp,
            supplier_compensation   = sup_comp,
            cost_price_at_defect    = float(product.cost_price),
            revenue_price_at_defect = float(product.revenue_price),
            price_at_defect         = float(product.total_price),
            subtotal_unit           = round(float(product.cost_price)    * qty, 2),
            subtotal_revenue        = round(float(product.revenue_price) * qty, 2),
            subtotal_amount         = round(float(product.total_price)   * qty, 2),
            transaction_id          = txn_ref,
        )
        db.session.add(detail)

        if status == "active":
            _apply_inventory_on_activate(detail)

        logged.append({
            "product_name": product.product_name.capitalize(),
            "qty":          qty,
            "log_type":     "Customer Return" if log_type == "customer" else "In-Store",
            "reason":       REASON_LABELS[reason],
            "status":       STATUS_LABELS[status],
            "cust_comp":    CUSTOMER_COMP_LABELS[cust_comp],
            "sup_comp":     SUPPLIER_COMP_LABELS[sup_comp],
            "txn_ref":      f"TXN-{txn_ref:05d}" if txn_ref else None,
            "new_stock":    max(0, product.inventory.quantity_available if product.inventory else 0),
        })

    try:
        audit(
            "INSERT",
            "Defects",
            f"Created defect log #{defect.defect_id} with {len(items)} item(s)",
            reference_id=defect.defect_id,
            reference_table="Defect",
            user_id=current_user.user_id
        )
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


@defects_bp.route("/api/refresh-token", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def refresh_token():
    session["defect_token"] = generate_charge_token()
    return jsonify({"defect_token": session["defect_token"]})

@defects_bp.route("/detail/<int:detail_id>/propose", methods=["POST"])
@login_required
@role_required("stocking")
def propose(detail_id):
    detail = DefectDetail.query.get_or_404(detail_id)

    if detail.is_archived:
        flash("Record has been deleted.", "warning")
        return redirect(url_for("defects.index"))

    if detail.status != "active" or detail.supplier_compensation != "pending":
        flash("Only active items with pending supplier compensation can be proposed.", "warning")
        return redirect(url_for("defects.index"))

    proposed = request.form.get("supplier_compensation", "").strip()
    if proposed not in RESOLVABLE_SUP_COMPS:
        flash("Invalid supplier compensation.", "danger")
        return redirect(url_for("defects.index"))

    detail.proposed_supplier_compensation = proposed
    audit(
        "UPDATE",
        "Defects",
        f"Proposed supplier compensation '{proposed}' for '{detail.product.product_name.capitalize()}'",
        reference_id=detail.defect_detail_id,
        reference_table="DefectDetail",
        user_id=current_user.user_id
    )
    db.session.commit()

    name = detail.product.product_name.capitalize()
    flash(f'"{name}" supplier comp proposal submitted — awaiting admin approval.', "success")
    return redirect(request.referrer or url_for("defects.index"))

@defects_bp.route("/detail/<int:detail_id>/clear-proposal", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def clear_proposal(detail_id):
    detail = DefectDetail.query.get_or_404(detail_id)
    detail.proposed_supplier_compensation = None
    audit(
        "UPDATE",
        "Defects",
        f"Cleared supplier compensation proposal for '{detail.product.product_name.capitalize()}'",
        reference_id=detail.defect_detail_id,
        reference_table="DefectDetail",
        user_id=current_user.user_id
    )
    db.session.commit()

    name = detail.product.product_name.capitalize()
    flash(f'Proposal for "{name}" rejected — back to pending.', "warning")
    return redirect(request.referrer or url_for("defects.index"))