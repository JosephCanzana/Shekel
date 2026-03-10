from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_required, current_user
from app.utils.decorator import role_required
from app.extensions import db
from app.models.user import User

manage_users_bp = Blueprint("manage_users", __name__, url_prefix="/admin/users")


@manage_users_bp.route("/")
@login_required
@role_required("admin", "co-admin")
def index():
    users = User.get_all()
    users_data = [u.to_dict() for u in users]
    return render_template("admin/users/index.html",
                           users=users,
                           users_data=users_data)


@manage_users_bp.route("/add")
@login_required
@role_required("admin", "co-admin")
def add():
    return render_template("admin/users/form.html")


@manage_users_bp.route("/<int:user_id>/edit")
@login_required
@role_required("admin", "co-admin")
def edit(user_id):
    return render_template("admin/users/form.html")

@manage_users_bp.route("/<int:user_id>/status_update")
@login_required
@role_required("admin", "co-admin")
def status(user_id):
    """
    Status hierarchy
    - Archived
    - Suspend
    - Not activated
    - Activated
    """
    return redirect(request.referrer)