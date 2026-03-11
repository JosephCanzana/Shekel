from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_required, current_user
from app.utils.decorator import role_required
from app.models.user import User
from app.utils.tmp_functions import *

admin_bp = Blueprint("admin", __name__, url_prefix='/admin')

@admin_bp.route("/")
@login_required
@role_required("admin", "co-admin")
def dashboard():
    return render_template(
        "admin/dashboard.html",
        time_of_day         = get_time_of_day(),
        stats               = get_admin_stats(),
        recent_transactions = get_recent_transactions(),
        low_stock_items     = get_low_stock_items(),
        defects             = get_defects(),
    )


@admin_bp.route("/manage_category")
@login_required
@role_required("admin")
def manage_category():
    return "Manage Category"


@admin_bp.route("/reports")
@login_required
@role_required("admin")
def reports():
    return "Manage Category"


@admin_bp.route("/audit_logs")
@login_required
@role_required("admin")
def audit_logs():
    return "Manage Category"
