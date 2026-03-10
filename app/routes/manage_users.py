from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_required, current_user
from app.utils.decorator import role_required
from app.extensions import db
from app.models.user import User

manage_users_bp = Blueprint("manage_users", __name__, url_prefix="/admin/users")


# ── List all users ─────────────────────────────────────────
@manage_users_bp.route("/")
@login_required
@role_required("admin", "co-admin")
def index():
    users = User.get_all()
    return render_template("admin/users/index.html", users=users)

