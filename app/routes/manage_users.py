from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_required, current_user
from app.utils.decorator import role_required
from app.extensions import db
from app.models.user import User
from app.utils.helpers import validate_name, validate_password
from sqlalchemy.exc import IntegrityError
from app.utils.audit import audit

manage_users_bp = Blueprint("manage_users", __name__, url_prefix="/admin/users")
VALID_ROLES = {"superadmin", "admin", "cashier", "stocking"}

@manage_users_bp.route("/")
@login_required
@role_required("superadmin", "admin")
def index():
    users = User.get_all()
    users_data = [u.to_dict() for u in users if u.user_id != current_user.user_id]
    return render_template("admin/users/index.html",
                           users=users,
                           users_data=users_data)


@manage_users_bp.route("/add", methods=["GET", "POST"])
@login_required
@role_required("superadmin", "admin")
def add():
    global VALID_ROLES
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip().lower()
        last_name  = request.form.get("last_name",  "").strip().lower()
        role       = request.form.get("role",       "").strip().lower()
        password   = request.form.get("password",   "").strip()

        # required fields
        if not all([first_name, last_name, role]):
            flash("First name, last name and role are required.", "danger")
            return redirect(url_for("manage_users.add"))

        # name validation
        ok, err = validate_name(first_name, "First name")
        if not ok:
            flash(err, "danger")
            return redirect(url_for("manage_users.add"))

        ok, err = validate_name(last_name, "Last name")
        if not ok:
            flash(err, "danger")
            return redirect(url_for("manage_users.add"))
        
        if role not in VALID_ROLES:
            flash("Invalid role selected.", "danger")
            return redirect(url_for("manage_users.add"))

        # password: validate if provided, otherwise use default
        if password:
            ok, err = validate_password(password)
            if not ok:
                flash(err, "danger")
                return redirect(url_for("manage_users.add"))
        else:
            password = User.get_default_password()


        # duplicate check
        existing_user = User.query.filter_by(
            first_name=first_name,
            last_name=last_name,
            # role=role <- uncomment later
        ).first()
        if existing_user:
            # flash("A user with this name and role already exists.", "danger") <- uncomment later
            flash("A user with this name already exists.", "danger")
            return redirect(url_for("manage_users.add"))

        user = User(
            user_id    = User.generate_id(),
            first_name = first_name,
            last_name  = last_name,
            role       = role,
            status     = "not_activated"
        )
        user.set_password(password)
        audit("INSERT", "Users",
      f"User '{first_name} {last_name}' ({role}) created",
      reference_id=user.user_id, reference_table="Users")
        user.save()

        flash(f"{first_name} {last_name} has been created.", "success")
        return redirect(url_for("manage_users.index"))

    return render_template("admin/users/form.html",
                           default_pass=User.get_default_password())


@manage_users_bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("superadmin", "admin")
def edit(user_id):
    global VALID_ROLES

    user = User.get_by_id(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("manage_users.index"))
    if user.role == 'superadmin':
        flash("Can't edit admin!", "danger")
        return redirect(url_for("manage_users.index"))

    if request.method == "POST":
        first_name = request.form.get("first_name", user.first_name).strip().lower()
        last_name  = request.form.get("last_name",  user.last_name).strip().lower()
        role       = request.form.get("role",       user.role).strip()
        status     = request.form.get("status",     user.status).strip()
        password   = request.form.get("password",   "").strip()

        # ── name validation
        ok, err = validate_name(first_name, "First name")
        if not ok:
            flash(err, "danger")
            return redirect(url_for("manage_users.edit", user_id=user_id))

        ok, err = validate_name(last_name, "Last name")
        if not ok:
            flash(err, "danger")
            return redirect(url_for("manage_users.edit", user_id=user_id))

        # ── password validation (only if provided)
        if password:
            ok, err = validate_password(password)
            if not ok:
                flash(err, "danger")
                return redirect(url_for("manage_users.edit", user_id=user_id))
            user.set_password(password)

        # duplicate check
        existing_user = User.query.filter(
            User.first_name == first_name,
            User.last_name == last_name,
            User.user_id != user_id
        ).first()
        if existing_user:
            # flash("A user with this name and role already exists.", "danger") <- uncomment later
            flash("A user with this name already exists.", "danger")
            return redirect(url_for("manage_users.add"))


        if role not in VALID_ROLES:
            flash("Invalid role selected.", "danger")
            return redirect(url_for("manage_users.edit", user_id=user_id))

        user.first_name = first_name
        user.last_name  = last_name
        user.role       = role
        user.status     = status
        audit("UPDATE", "Users",
      f"User '{user.first_name} {user.last_name}' updated",
      reference_id=user_id, reference_table="Users")
        user.save()

        flash(f"{user.first_name} {user.last_name} has been updated.", "success")
        return redirect(url_for("manage_users.index"))

    return render_template("admin/users/form.html",
                           user=user,
                           default_pass=User.get_default_password())


@manage_users_bp.route("/<int:user_id>/status_update", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def status(user_id):
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
    audit("UPDATE", "Users",
      f"User '{user.first_name} {user.last_name}' status changed to '{new_status}'",
      reference_id=user_id, reference_table="Users")
    user.save()
    flash(f"{user.first_name} {user.last_name} is now {new_status.replace('_', ' ')}.", "success")
    return redirect(request.referrer or url_for("manage_users.index"))


@manage_users_bp.route("/<int:user_id>/reset_password", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def reset_password(user_id):
    user = User.get_by_id(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("manage_users.index"))

    default = User.get_default_password()
    user.set_password(default)
    user.status = "not_activated"
    audit("UPDATE", "Users",
      f"Password reset for '{user.first_name} {user.last_name}'",
      reference_id=user_id, reference_table="Users")
    user.save()
    flash(f"Password for {user.first_name} {user.last_name} has been reset to default.", "success")
    return redirect(request.referrer or url_for("manage_users.index"))


@manage_users_bp.route("/<int:user_id>/delete", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def delete(user_id):
    user = User.get_by_id(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("manage_users.index"))

    if user.status != "archived":
        flash("Only archived users can be deleted.", "danger")
        return redirect(url_for("manage_users.index"))

    name = f"{user.first_name} {user.last_name}"
    try:
        audit("DELETE", "Users",
      f"User '{name}' permanently deleted",
      reference_id=user_id, reference_table="Users")
        user.delete()
        flash(f"{name} has been permanently deleted.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Cannot delete user because it is referenced by other records", "danger")
        return redirect(url_for("manage_users.index"))
    
    return redirect(url_for("manage_users.index"))