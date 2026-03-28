from flask import Blueprint, render_template
from flask_login import login_required
from app.utils.decorator import role_required
from app.utils.index_helpers import *

admin_bp = Blueprint("superadmin", __name__, url_prefix='/admin')

@admin_bp.route("/")
@login_required
@role_required("superadmin", "admin")
def dashboard():
    stats = get_admin_stats()
    return render_template(
        "admin/dashboard.html",
        time_of_day         = get_time_of_day(),
        stats               = stats,
        recent_transactions = stats["recent_transactions"],
        low_stock_items     = get_low_stock_items(),
        defects             = get_defects(),
    )


@admin_bp.route("/reports")
@login_required
@role_required("superadmin")
def reports():
    return "repor"


@admin_bp.route("/audit_logs")
@login_required
@role_required("superadmin")
def audit_logs():
    return "logs"
