from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_required, current_user
from app.utils.decorator import role_required
from app.models.user import User

admin_bp = Blueprint("admin", __name__, url_prefix='/admin')

@admin_bp.route("/")
@login_required
@role_required("admin")
def dashboard():
    return render_template("admin/dashboard.html")


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
