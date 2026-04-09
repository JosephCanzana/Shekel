import io
import json
from collections import Counter, defaultdict
from datetime import datetime, date as _date

from flask import (
    Blueprint, render_template, request,
    jsonify, url_for, send_file,
)
from flask_login import login_required, current_user
from sqlalchemy import func

from app.utils.decorator import role_required
from app.utils.index_helpers import (
    get_admin_stats, get_time_of_day, get_low_stock_items, get_defects,
)
from app.utils.helpers import to_pht, _pht_fix

from app.models.stock_adjustment_request import StockAdjustmentRequest
from app.models.stock_adjustment_detail  import StockAdjustmentDetail
from app.models.defect_detail import DefectDetail
from app.models.defect     import Defect
from app.models.product    import Product
from app.models.user       import User
from app.models.inventory  import Inventory
from app.models.stock_in   import StockIn
from app.models.audit_log  import AuditLog
from app.extensions import db

admin_bp = Blueprint("admin", __name__, url_prefix='/admin')


# ── Dashboard ─────────────────────────────────────────────────────────────────
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

    defect_rows = (
        db.session.query(DefectDetail, Defect, Product, User)
        .join(Defect,   Defect.defect_id     == DefectDetail.defect_id)
        .join(Product,  Product.product_id   == DefectDetail.product_id)
        .join(User,     User.user_id         == Defect.user_id)
        .filter(DefectDetail.status      == "submitted")
        .filter(DefectDetail.is_archived == False)
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
            "approve_url":  url_for("defects.approve",        detail_id=detail.defect_detail_id),
            "reject_url":   url_for("defects.reject",         detail_id=detail.defect_detail_id),
            "delete_url":   url_for("defects.archive_detail", detail_id=detail.defect_detail_id),
        }
        for detail, defect, product, user in defect_rows
    ]

    proposal_rows = (
        db.session.query(DefectDetail, Defect, Product, User)
        .join(Defect,   Defect.defect_id     == DefectDetail.defect_id)
        .join(Product,  Product.product_id   == DefectDetail.product_id)
        .join(User,     User.user_id         == Defect.user_id)
        .filter(DefectDetail.status                        == "active")
        .filter(DefectDetail.supplier_compensation         == "pending")
        .filter(DefectDetail.proposed_supplier_compensation != None)
        .filter(DefectDetail.is_archived                   == False)
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
            "approve_url":  url_for("defects.review",         detail_id=detail.defect_detail_id),
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
        .filter(DefectDetail.is_archived == False)
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
        pending_data  = [_pht_fix(r.to_dict()) for r in pending],
        history_data  = [_pht_fix(r.to_dict()) for r in history],
        defect_data   = defect_data,
        proposal_data = proposal_data,
        defect_history = defect_history,
    )


# ── Review API ────────────────────────────────────────────────────────────────
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

        action  = decision.get("action")
        product = detail.product

        if action == "approve":
            raw_qty = decision.get("quantity_approved")
            try:
                qty = int(raw_qty) if raw_qty is not None else detail.quantity_requested
                if qty <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                return jsonify({"error": f"Invalid quantity for '{detail.product.product_name}'."}), 400

            detail.approve(qty)
            if detail.request.request_type == "adjustment":
                if product and product.status != "archived":
                    if product.inventory:
                        product.inventory.quantity_available = qty
                        product.inventory.last_updated        = datetime.utcnow()
            else:
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

                    db.session.add(StockIn(
                        product_id        = detail.product_id,
                        user_id           = current_user.user_id,
                        quantity_received = qty,
                        stockin_datetime  = datetime.utcnow(),
                        notes             = detail.note or None,
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


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIT LOGS
# ═══════════════════════════════════════════════════════════════════════════════

@admin_bp.route("/audit_logs")
@login_required
@role_required("superadmin")
def audit_logs():
    from sqlalchemy import distinct
 
    PER_PAGE = 50
 
    # ── query params ──────────────────────────────────────────────────────────
    page         = request.args.get("page",        1,  type=int)
    raw_uid      = request.args.get("user_id",     "").strip()
    action_type  = request.args.get("action_type", "").strip()
    module       = request.args.get("module",      "").strip()
    q            = request.args.get("q",           "").strip()
    date_from    = request.args.get("date_from",   "").strip()
    date_to      = request.args.get("date_to",     "").strip()
 
    # ── base query ────────────────────────────────────────────────────────────
    qry = (
        AuditLog.query
        .outerjoin(User, AuditLog.user_id == User.user_id)
        .order_by(AuditLog.action_datetime.desc())
    )
 
    if raw_uid:
        try:
            qry = qry.filter(AuditLog.user_id == int(raw_uid))
        except ValueError:
            pass
    if action_type:
        qry = qry.filter(AuditLog.action_type == action_type)
    if module:
        qry = qry.filter(AuditLog.module == module)
    if q:
        qry = qry.filter(AuditLog.description.ilike(f"%{q}%"))
    if date_from:
        try:
            qry = qry.filter(
                AuditLog.action_datetime >= datetime.strptime(date_from, "%Y-%m-%d")
            )
        except ValueError:
            date_from = ""
    if date_to:
        try:
            qry = qry.filter(
                AuditLog.action_datetime
                <= datetime.strptime(date_to, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                )
            )
        except ValueError:
            date_to = ""
 
    logs = qry.paginate(page=page, per_page=PER_PAGE, error_out=False)
 
    # ── today stats ───────────────────────────────────────────────────────────
    today_start = datetime.combine(_date.today(), datetime.min.time())
 
    total_today = AuditLog.query.filter(
        AuditLog.action_datetime >= today_start
    ).count()
 
    logins_today = AuditLog.query.filter(
        AuditLog.action_datetime >= today_start,
        AuditLog.action_type == "LOGIN",
    ).count()
 
    unique_users_today = (
        db.session.query(db.func.count(distinct(AuditLog.user_id)))
        .filter(AuditLog.action_datetime >= today_start)
        .scalar()
        or 0
    )
 
    all_users = User.query.order_by(User.first_name, User.last_name).all()
 
    filters = dict(
        user_id     = int(raw_uid) if raw_uid and raw_uid.isdigit() else None,
        action_type = action_type,
        module      = module,
        q           = q,
        date_from   = date_from,
        date_to     = date_to,
    )
 
    stats = dict(
        total_today         = total_today,
        logins_today        = logins_today,
        unique_users_today  = unique_users_today,
    )
 
    return render_template(
        "admin/audit_logs.html",
        logs      = logs,
        filters   = filters,
        stats     = stats,
        all_users = all_users,
    )


@admin_bp.route("/audit_logs/export")
@login_required
@role_required("superadmin")
def export_audit_logs():
    """Download filtered audit log as a formatted Excel file."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    f_user      = request.args.get("user_id",     type=int)
    f_action    = request.args.get("action_type", "").strip()
    f_module    = request.args.get("module",      "").strip()
    f_search    = request.args.get("q",           "").strip()
    f_date_from = request.args.get("date_from",   "").strip()
    f_date_to   = request.args.get("date_to",     "").strip()

    q = AuditLog.query.join(User, AuditLog.user_id == User.user_id)
    if f_user:
        q = q.filter(AuditLog.user_id == f_user)
    if f_action:
        q = q.filter(AuditLog.action_type == f_action)
    if f_module:
        q = q.filter(AuditLog.module == f_module)
    if f_search:
        q = q.filter(AuditLog.description.ilike(f"%{f_search}%"))
    if f_date_from:
        try:
            q = q.filter(AuditLog.action_datetime >= datetime.strptime(f_date_from, "%Y-%m-%d"))
        except ValueError:
            pass
    if f_date_to:
        try:
            dt_to = datetime.strptime(f_date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            q = q.filter(AuditLog.action_datetime <= dt_to)
        except ValueError:
            pass

    logs = q.order_by(AuditLog.action_datetime.desc()).all()

    wb  = openpyxl.Workbook()
    ws  = wb.active
    ws.title = "Audit Log"

    hdr_fill = PatternFill("solid", fgColor="1E293B")
    hdr_font = Font(bold=True, color="FFFFFF", size=11)
    alt_fill = PatternFill("solid", fgColor="F8FAFC")
    thin     = Border(bottom=Side(style="thin", color="E2E8F0"))

    headers    = ["#", "Date & Time (PHT)", "User", "Role", "Action", "Module", "Description", "Reference"]
    col_widths = [6,   22,                  24,     12,     10,       12,       60,             18]

    from openpyxl.utils import get_column_letter
    for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.font      = hdr_font
        cell.fill      = hdr_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.row_dimensions[1].height = 22
    ws.freeze_panes = "A2"

    for ri, log in enumerate(logs, 2):
        pht_dt = to_pht(log.action_datetime).strftime("%b %d, %Y %I:%M %p") if log.action_datetime else ""
        u      = log.user
        name   = f"{u.first_name} {u.last_name}".strip().title() if u else "—"
        role   = u.role.title() if u else "—"
        ref    = f"{log.reference_table} #{log.reference_id}" if log.reference_id else "—"

        row_data = [ri - 1, pht_dt, name, role, log.action_type, log.module, log.description, ref]
        for ci, val in enumerate(row_data, 1):
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.border    = thin
            cell.alignment = Alignment(vertical="center", wrap_text=(ci == 7))
            if ri % 2 == 0:
                cell.fill = alt_fill
        ws.row_dimensions[ri].height = 18

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"audit_log_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# REPORTS — helpers
# ═══════════════════════════════════════════════════════════════════════════════
 
def _paginate_list(lst, page, per_page=25):
    """Slice a plain Python list into a pagination dict."""
    total    = len(lst)
    pages    = max(1, (total + per_page - 1) // per_page)
    page     = max(1, min(page, pages))
    start    = (page - 1) * per_page
    return {
        "rows":     lst[start: start + per_page],
        "total":    total,
        "page":     page,
        "pages":    pages,
        "per_page": per_page,
        "has_prev": page > 1,
        "has_next": page < pages,
        "prev_num": page - 1,
        "next_num": page + 1,
    }
 
 
def _build_chart_data(data):
    """
    Produce JSON-serialisable dicts consumed by Chart.js in reports.html.
    All Decimal / date values are cast to native Python types here.
    """
    # ── Sales ─────────────────────────────────────────────────────────────────
    # Reverse so chart x-axis runs oldest → newest
    daily_asc = list(reversed(list(data["sales"]["daily"])))
    sales_chart = {
        "labels":       [str(r.date) for r in daily_asc],
        "revenue":      [float(r.total or 0) for r in daily_asc],
        "transactions": [int(r.transactions) for r in daily_asc],
    }
    top_products_chart = {
        "labels":  [r.product_name[:22].capitalize() for r in data["sales"]["top_products"]],
        "units":   [int(r.units_sold or 0)           for r in data["sales"]["top_products"]],
        "revenue": [float(r.revenue or 0)            for r in data["sales"]["top_products"]],
    }
 
    # ── Inventory ─────────────────────────────────────────────────────────────
    inv_sorted = sorted(
        data["inventory"]["rows"],
        key=lambda x: x[1].quantity_available,
        reverse=True,
    )[:12]
    inv_chart = {
        "labels":    [p.product_name[:22].capitalize() for p, inv, _ in inv_sorted],
        "in_stock":  [inv.quantity_available            for _, inv, _ in inv_sorted],
        "defective": [inv.quantity_defective or 0       for _, inv, _ in inv_sorted],
        "threshold": [p.low_reorder_threshold           for p, _, _ in inv_sorted],
    }
 
    # ── Stock In ──────────────────────────────────────────────────────────────
    stock_by_date: dict[str, int] = defaultdict(int)
    for s, _, _ in data["stock"]["rows"]:
        if s.stockin_datetime:
            d = str(to_pht(s.stockin_datetime).date())
            stock_by_date[d] += s.quantity_received
    stock_dates = sorted(stock_by_date)
    stock_chart = {
        "labels": stock_dates,
        "units":  [stock_by_date[d] for d in stock_dates],
    }
 
    # ── Defects ───────────────────────────────────────────────────────────────
    reason_counter: Counter = Counter()
    for detail, _, _, _ in data["defects"]["rows"]:
        reason_counter[detail.reason.replace("_", " ").title()] += detail.quantity
 
    defects_chart = {
        "origin_labels": ["Customer", "In-Store"],
        "origin_counts": [
            data["defects"]["customer_origin"],
            data["defects"]["store_origin"],
        ],
        "reason_labels": [k for k, _ in reason_counter.most_common(8)],
        "reason_counts": [v for _, v in reason_counter.most_common(8)],
    }
 
    return {
        "sales":        sales_chart,
        "top_products": top_products_chart,
        "inventory":    inv_chart,
        "stock":        stock_chart,
        "defects":      defects_chart,
    }
 
 
 
def _parse_date_range():
    """Return (date_from, date_to, date_from_str, date_to_str) from request args."""
    today = datetime.utcnow().date()
    dfrom_s = request.args.get("date_from", today.replace(day=1).isoformat())
    dto_s   = request.args.get("date_to",   today.isoformat())
 
    try:
        dfrom = datetime.strptime(dfrom_s, "%Y-%m-%d")
    except ValueError:
        dfrom   = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        dfrom_s = dfrom.date().isoformat()
 
    try:
        dto = datetime.strptime(dto_s, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
    except ValueError:
        dto   = datetime.utcnow().replace(hour=23, minute=59, second=59)
        dto_s = dto.date().isoformat()
 
    return dfrom, dto, dfrom_s, dto_s
 
 
def _build_report_data(date_from, date_to):
    """
    Collect data for all four report tabs.
 
    Column mapping verified against actual DB schema (shekel_db dump):
        Sales.transaction_id        ← PK  (NOT sale_id)
        Sales.total_amount          ← final selling total
        Sales.total_revenue_price   ← revenue component
        Sales.total_cost_price      ← cost component
        Sales.sale_datetime         ✓
        Sales.payment_method        ✓
 
        Sales_Details.sale_detail_id      ← PK
        Sales_Details.transaction_id      ← FK to Sales
        Sales_Details.product_id          ← FK to Products (varchar)
        Sales_Details.quantity            ✓
        Sales_Details.price_at_sale       ← unit selling price
        Sales_Details.subtotal_amount     ← line total
 
        Products.product_id               ← varchar(100) PK
        Products.low_reorder_threshold    ← per-product low stock level
        Products.total_price              ← current selling price
 
        Stock_In.stockin_id               ← PK  (NOT stock_in_id)
    """
    from app.models.sale        import Sale
    from app.models.sale_detail import SaleDetail
    from app.models.category    import Category
 
    # ── 1. Sales ─────────────────────────────────────────────────────────────
    sales_list = (
        Sale.query
        .filter(Sale.sale_datetime.between(date_from, date_to))
        .order_by(Sale.sale_datetime.desc())
        .all()
    )
 
    # Daily breakdown
    daily_sales = (
        db.session.query(
            func.date(Sale.sale_datetime).label("date"),
            func.count(Sale.transaction_id).label("transactions"),   # ← transaction_id
            func.sum(Sale.total_amount).label("total"),
        )
        .filter(Sale.sale_datetime.between(date_from, date_to))
        .group_by(func.date(Sale.sale_datetime))
        .order_by(func.date(Sale.sale_datetime).desc())
        .all()
    )
 
    total_revenue = sum(float(s.total_amount or 0) for s in sales_list)
    avg_order     = (total_revenue / len(sales_list)) if sales_list else 0
 
    # Top 10 products by units sold
    top_products = (
        db.session.query(
            Product.product_name,
            func.sum(SaleDetail.quantity).label("units_sold"),
            func.sum(SaleDetail.subtotal_amount).label("revenue"),  # ← subtotal_amount
        )
        .join(SaleDetail, SaleDetail.product_id == Product.product_id)
        .join(Sale,       Sale.transaction_id    == SaleDetail.transaction_id)  # ← transaction_id
        .filter(Sale.sale_datetime.between(date_from, date_to))
        .group_by(Product.product_id, Product.product_name)
        .order_by(func.sum(SaleDetail.quantity).desc())
        .limit(10)
        .all()
    )
 
    sales_data = {
        "total_revenue":      total_revenue,
        "total_transactions": len(sales_list),
        "avg_order":          avg_order,
        "daily":              daily_sales,    # (date, transactions, total)
        "top_products":       top_products,   # (product_name, units_sold, revenue)
    }
 
    # ── 2. Inventory ──────────────────────────────────────────────────────────
    # Shows current state — intentionally NOT date-filtered.
    inv_rows = (
        db.session.query(Product, Inventory, Category)
        .join(Inventory, Inventory.product_id == Product.product_id)
        .outerjoin(Category, Category.category_id == Product.category_id)
        .filter(Product.status != "archived")
        .order_by(Product.product_name)
        .all()
    )
 
    inventory_data = {
        "total_products": len(inv_rows),
        "total_units":    sum(inv.quantity_available for _, inv, _ in inv_rows),
        # low_stock: qty > 0 AND qty <= the product's own reorder threshold
        "low_stock":    sum(
            1 for p, inv, _ in inv_rows
            if 0 < inv.quantity_available <= p.low_reorder_threshold
        ),
        "out_of_stock": sum(1 for _, inv, _ in inv_rows if inv.quantity_available == 0),
        "rows":         inv_rows,   # (Product, Inventory, Category) — NOT "items" (conflicts with dict.items())
    }
 
    # ── 3. Stock Movement ─────────────────────────────────────────────────────
    stock_rows = (
        db.session.query(StockIn, Product, User)
        .join(Product, Product.product_id == StockIn.product_id)
        .join(User,    User.user_id        == StockIn.user_id)
        .filter(StockIn.stockin_datetime.between(date_from, date_to))
        .order_by(StockIn.stockin_datetime.desc())
        .all()
    )
 
    stock_data = {
        "total_entries": len(stock_rows),
        "total_units":   sum(s.quantity_received for s, _, _ in stock_rows),
        "rows":          stock_rows,   # (StockIn, Product, User)
    }
 
    # ── 4. Defects ────────────────────────────────────────────────────────────
    defect_rows = (
        db.session.query(DefectDetail, Defect, Product, User)
        .join(Defect,  Defect.defect_id    == DefectDetail.defect_id)
        .join(Product, Product.product_id  == DefectDetail.product_id)
        .join(User,    User.user_id        == Defect.user_id)
        .filter(Defect.defect_datetime.between(date_from, date_to))
        .filter(DefectDetail.is_archived == False)
        .order_by(Defect.defect_datetime.desc())
        .all()
    )
 
    defects_data = {
        "total":           len(defect_rows),
        "total_units":     sum(d.quantity for d, _, _, _ in defect_rows),
        "customer_origin": sum(1 for d, _, _, _ in defect_rows if d.origin == "customer"),
        "store_origin":    sum(1 for d, _, _, _ in defect_rows if d.origin == "in_store"),
        "rows":            defect_rows,   # (DefectDetail, Defect, Product, User)
    }
 
    return {
        "sales":     sales_data,
        "inventory": inventory_data,
        "stock":     stock_data,
        "defects":   defects_data,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# REPORTS — routes
# ═══════════════════════════════════════════════════════════════════════════════
 
@admin_bp.route("/reports")
@login_required
@role_required("superadmin")
def reports():
    
    date_from, date_to, date_from_str, date_to_str = _parse_date_range()
    active_tab = request.args.get("tab", "sales")
    page       = request.args.get("page", 1, type=int)
    per_page   = 25
 
    data       = _build_report_data(date_from, date_to)
    chart_json = json.dumps(_build_chart_data(data))
 
    # Paginate only the active tab's detail rows
    if active_tab == "inventory":
        detail = _paginate_list(data["inventory"]["rows"], page, per_page)
    elif active_tab == "stock":
        detail = _paginate_list(data["stock"]["rows"], page, per_page)
    elif active_tab == "defects":
        detail = _paginate_list(data["defects"]["rows"], page, per_page)
    else:  # sales — daily breakdown
        detail = _paginate_list(list(data["sales"]["daily"]), page, per_page)
 
    return render_template(
        "admin/reports.html",
        data       = data,
        detail     = detail,
        chart_json = chart_json,
        active_tab = active_tab,
        date_from  = date_from_str,
        date_to    = date_to_str,
    )
 
 
@admin_bp.route("/reports/pdf")
@login_required
@role_required("superadmin")
def export_report_pdf():
    """Render a print-ready PDF for the current tab + date range."""
    from weasyprint import HTML
 
    date_from, date_to, date_from_str, date_to_str = _parse_date_range()
    tab  = request.args.get("tab", "sales")
    data = _build_report_data(date_from, date_to)
 
    html_str = render_template(
        "admin/reports_pdf.html",
        data         = data,
        tab          = tab,
        date_from    = date_from_str,
        date_to      = date_to_str,
        generated_at = to_pht(datetime.utcnow()).strftime("%B %d, %Y  %I:%M %p PHT"),
    )
 
    pdf_bytes = HTML(string=html_str, base_url=request.host_url).write_pdf()
 
    buf = io.BytesIO(pdf_bytes)
    buf.seek(0)
    filename = f"report_{tab}_{date_from_str}_to_{date_to_str}.pdf"
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf",
    )
 
 
@admin_bp.route("/reports/export")
@login_required
@role_required("superadmin")
def export_report():
    """Download the selected report tab as a formatted Excel workbook."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
 
    date_from, date_to, date_from_str, date_to_str = _parse_date_range()
    tab  = request.args.get("tab", "sales")
    data = _build_report_data(date_from, date_to)
 
    wb = openpyxl.Workbook()
 
    # ── Shared style helpers ──────────────────────────────────────────────────
    def make_header(ws, headers, col_widths):
        fill = PatternFill("solid", fgColor="1E293B")
        font = Font(bold=True, color="FFFFFF", size=11)
        for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
            cell = ws.cell(row=1, column=ci, value=h)
            cell.font      = font
            cell.fill      = fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            ws.column_dimensions[get_column_letter(ci)].width = w
        ws.row_dimensions[1].height = 22
        ws.freeze_panes = "A2"
 
    def write_row(ws, ri, values, wrap_cols=None):
        alt_fill = PatternFill("solid", fgColor="F8FAFC")
        thin     = Border(bottom=Side(style="thin", color="E2E8F0"))
        for ci, val in enumerate(values, 1):
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.border    = thin
            cell.alignment = Alignment(vertical="center", wrap_text=(wrap_cols and ci in wrap_cols))
            if ri % 2 == 0:
                cell.fill = alt_fill
        ws.row_dimensions[ri].height = 18
 
    def add_summary(ws, row, label, value):
        ws.cell(row=row, column=1, value=label).font = Font(bold=True)
        ws.cell(row=row, column=2, value=value)
 
    # ── Sales ─────────────────────────────────────────────────────────────────
    if tab == "sales":
        ws = wb.active
        ws.title = "Sales Summary"
        s = data["sales"]
 
        add_summary(ws, 1, "Period",              f"{date_from_str}  →  {date_to_str}")
        add_summary(ws, 2, "Total Transactions",  s["total_transactions"])
        add_summary(ws, 3, "Total Revenue (₱)",   round(s["total_revenue"], 2))
        add_summary(ws, 4, "Avg Order Value (₱)", round(s["avg_order"], 2))
 
        # Blank row then daily table starting at row 6
        start = 6
        ws.cell(row=start, column=1, value="Daily Breakdown").font = Font(bold=True, size=12)
        start += 1
        for ci, (h, w) in enumerate(
            zip(["Date", "Transactions", "Revenue (₱)"], [18, 16, 18]), 1
        ):
            cell = ws.cell(row=start, column=ci, value=h)
            cell.font      = Font(bold=True, color="FFFFFF")
            cell.fill      = PatternFill("solid", fgColor="1E293B")
            cell.alignment = Alignment(horizontal="center")
            ws.column_dimensions[get_column_letter(ci)].width = w
        ws.freeze_panes = f"A{start + 1}"
 
        for ri, row in enumerate(s["daily"], start + 1):
            write_row(ws, ri, [str(row.date), row.transactions, round(float(row.total or 0), 2)])
 
        # Top products on sheet 2
        ws2 = wb.create_sheet("Top Products")
        make_header(ws2, ["Product", "Units Sold", "Revenue (₱)"], [36, 14, 16])
        for ri, row in enumerate(s["top_products"], 2):
            write_row(ws2, ri, [
                row.product_name.capitalize(),
                int(row.units_sold or 0),
                round(float(row.revenue or 0), 2),
            ])
 
    # ── Inventory ─────────────────────────────────────────────────────────────
    elif tab == "inventory":
        ws = wb.active
        ws.title = "Inventory"
        inv = data["inventory"]
 
        add_summary(ws, 1, "Total Products",  inv["total_products"])
        add_summary(ws, 2, "Total Units",     inv["total_units"])
        add_summary(ws, 3, "Low Stock",       inv["low_stock"])
        add_summary(ws, 4, "Out of Stock",    inv["out_of_stock"])
 
        start = 6
        headers    = ["Product", "Category", "In Stock", "Defective", "Reorder Threshold", "Status", "Last Updated"]
        col_widths = [36,        20,          12,         12,          18,                  12,       22]
        for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
            cell = ws.cell(row=start, column=ci, value=h)
            cell.font      = Font(bold=True, color="FFFFFF")
            cell.fill      = PatternFill("solid", fgColor="1E293B")
            cell.alignment = Alignment(horizontal="center")
            ws.column_dimensions[get_column_letter(ci)].width = w
        ws.freeze_panes = f"A{start + 1}"
 
        for ri, (product, inv_row, category) in enumerate(inv["rows"], start + 1):
            last_upd = to_pht(inv_row.last_updated).strftime("%b %d, %Y") if inv_row.last_updated else "—"
            write_row(ws, ri, [
                product.product_name.capitalize(),
                category.category_name.capitalize() if category else "—",
                inv_row.quantity_available,
                inv_row.quantity_defective or 0,
                product.low_reorder_threshold,      # ← per-product threshold from Products table
                product.status.title(),
                last_upd,
            ])
 
    # ── Stock Movement ────────────────────────────────────────────────────────
    elif tab == "stock":
        ws = wb.active
        ws.title = "Stock Movement"
        sk = data["stock"]
 
        add_summary(ws, 1, "Period",         f"{date_from_str}  →  {date_to_str}")
        add_summary(ws, 2, "Total Entries",  sk["total_entries"])
        add_summary(ws, 3, "Total Units In", sk["total_units"])
 
        start = 5
        headers    = ["Date & Time (PHT)", "Product", "Qty Received", "Received By", "Notes"]
        col_widths = [22,                  36,         14,             22,             40]
        for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
            cell = ws.cell(row=start, column=ci, value=h)
            cell.font      = Font(bold=True, color="FFFFFF")
            cell.fill      = PatternFill("solid", fgColor="1E293B")
            cell.alignment = Alignment(horizontal="center")
            ws.column_dimensions[get_column_letter(ci)].width = w
        ws.freeze_panes = f"A{start + 1}"
 
        for ri, (stock_in, product, user) in enumerate(sk["rows"], start + 1):
            pht_dt = to_pht(stock_in.stockin_datetime).strftime("%b %d, %Y %I:%M %p") if stock_in.stockin_datetime else "—"
            name   = f"{user.first_name} {user.last_name}".strip().title()
            write_row(ws, ri, [
                pht_dt,
                product.product_name.capitalize(),
                stock_in.quantity_received,
                name,
                stock_in.notes or "—",
            ], wrap_cols={5})
 
    # ── Defects ───────────────────────────────────────────────────────────────
    elif tab == "defects":
        ws = wb.active
        ws.title = "Defects"
        df = data["defects"]
 
        add_summary(ws, 1, "Period",           f"{date_from_str}  →  {date_to_str}")
        add_summary(ws, 2, "Total Records",    df["total"])
        add_summary(ws, 3, "Total Units",      df["total_units"])
        add_summary(ws, 4, "Customer Origin",  df["customer_origin"])
        add_summary(ws, 5, "In-Store Origin",  df["store_origin"])
 
        start = 7
        headers    = ["Date (PHT)", "Product", "Qty", "Origin", "Reason", "Cust. Compensation", "Status", "Logged By"]
        col_widths = [22,           30,         8,     12,       22,       22,                   12,       22]
        for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
            cell = ws.cell(row=start, column=ci, value=h)
            cell.font      = Font(bold=True, color="FFFFFF")
            cell.fill      = PatternFill("solid", fgColor="1E293B")
            cell.alignment = Alignment(horizontal="center")
            ws.column_dimensions[get_column_letter(ci)].width = w
        ws.freeze_panes = f"A{start + 1}"
 
        for ri, (detail, defect, product, user) in enumerate(df["rows"], start + 1):
            pht_dt = to_pht(defect.defect_datetime).strftime("%b %d, %Y %I:%M %p") if defect.defect_datetime else "—"
            name   = f"{user.first_name} {user.last_name}".strip().title()
            write_row(ws, ri, [
                pht_dt,
                product.product_name.capitalize(),
                detail.quantity,
                "Customer" if detail.origin == "customer" else "In-Store",
                detail.reason.replace("_", " ").title(),
                detail.customer_compensation.replace("_", " ").title(),
                detail.status.title(),
                name,
            ])
 
    else:
        wb.active.title = "No Data"
 
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
 
    filename = f"report_{tab}_{date_from_str}_to_{date_to_str}.xlsx"
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
 