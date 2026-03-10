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
    users_data = [u.to_dict() for u in users if u.user_id != current_user.user_id]
    return render_template("admin/users/index.html",
                           users=users,
                           users_data=users_data)


@manage_users_bp.route("/add", methods=["GET", "POST"])
@login_required
@role_required("admin", "co-admin")
def add():
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip().lower()
        last_name  = request.form.get("last_name",  "").strip().lower()
        role       = request.form.get("role",       "").strip().lower()
        password   = request.form.get("password",   "").strip()

        if not password:
            password = User.get_default_password()

        if not all([first_name, last_name, role, password]):
            flash(f"All fields are required.{password}!", "danger")
            return redirect(url_for("manage_users.add"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("manage_users.add"))
        
        existing_user = User.query.filter_by(
            first_name=first_name,
            last_name=last_name,
            role=role
        ).first()

        if existing_user:
            flash("A user with this name and role already exists.", "danger")
            return redirect(url_for("manage_users.add"))

        user = User(
            user_id    = User.generate_id(),
            first_name = first_name,
            last_name  = last_name,
            role=role,
            status="not_activated"
        )
        user.set_password(password)
        user.save()

        flash(f"{first_name} {last_name} has been created.", "success")
        return redirect(url_for("manage_users.index"))

    return render_template("admin/users/form.html", default_pass=User.get_default_password())


@manage_users_bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin", "co-admin")
def edit(user_id):
    user = User.get_by_id(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("manage_users.index"))

    if request.method == "POST":
        user.first_name = request.form.get("first_name", user.first_name).strip()
        user.last_name  = request.form.get("last_name",  user.last_name).strip()
        user.role       = request.form.get("role",       user.role).strip()
        user.status     = request.form.get("status",     user.status).strip()

        password = request.form.get("password", "").strip()
        if password:
            if len(password) < 6:
                flash("Password must be at least 6 characters.", "danger")
                return redirect(url_for("manage_users.edit", user_id=user_id))
            user.set_password(password)

        user.save()
        flash(f"{user.first_name} {user.last_name} has been updated.", "success")
        return redirect(url_for("manage_users.index"))

    return render_template("admin/users/form.html", user=user)


@manage_users_bp.route("/<int:user_id>/status_update", methods=["POST"])
@login_required
@role_required("admin", "co-admin")
def status(user_id):
    """
    Status hierarchy:
    - archived      → fully deactivated
    - suspended     → temporary loss of access
    - not_activated → account exists but not yet active
    - activated     → normal access
    """
    if current_user.user_id == user_id:
        flash("You cannot change your own account status.", "danger")
        return redirect(request.referrer or url_for("manage_users.index"))

    user = User.get_by_id(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("manage_users.index"))

    new_status = request.form.get("status", "").strip()
    if new_status not in {"activated", "not_activated", "suspended", "archived"}:
        flash("Invalid status.", "danger")
        return redirect(request.referrer or url_for("manage_users.index"))

    user.status = new_status
    user.save()
    flash(f"{user.first_name} {user.last_name} is now {new_status.replace('_', ' ')}.", "success")
    return redirect(request.referrer or url_for("manage_users.index"))


@manage_users_bp.route("/<int:user_id>/reset_password", methods=["POST"])
@login_required
@role_required("admin", "co-admin")
def reset_password(user_id):
    user = User.get_by_id(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("manage_users.index"))

    user.set_password(User.get_default_password())
    user.save()
    flash(f"Password for {user.first_name} {user.last_name} has been reset to default ({User.get_default_password()}).", "success")
    return redirect(request.referrer or url_for("manage_users.index"))


@manage_users_bp.route("/<int:user_id>/delete", methods=["POST"])
@login_required
@role_required("admin")  # admin only — too destructive for co-admin
def delete(user_id):
    user = User.get_by_id(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("manage_users.index"))

    if user.status != "archived":
        flash("Only archived users can be deleted.", "danger")
        return redirect(url_for("manage_users.index"))

    name = f"{user.first_name} {user.last_name}"
    user.delete()
    flash(f"{name} has been permanently deleted.", "success")
    return redirect(url_for("manage_users.index"))