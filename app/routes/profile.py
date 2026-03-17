from flask               import render_template, request, flash, redirect, url_for, Blueprint
from flask_login         import login_required, current_user
from sqlalchemy.exc      import DataError
from app.extensions      import db
from app.models.user     import User
from app.models.recovery_detail import RecoveryDetail
from app.utils.helpers   import _is_admin, _can_change_password

profile_bp = Blueprint("profile", __name__, url_prefix="/profile")


@profile_bp.route("/", methods=["GET"])
@login_required
def index():
    return render_template(
        "profile/index.html",
        user            = current_user,
        can_change_pw   = _can_change_password(),
        is_admin        = _is_admin(),
    )


@profile_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    """Admin and co-admin only."""
    if not _can_change_password():
        flash("You do not have permission to change your password.", "danger")
        return redirect(url_for("profile.index"))

    current_pw  = request.form.get("current_password",  "").strip()
    new_pw      = request.form.get("new_password",       "").strip()
    confirm_pw  = request.form.get("confirm_password",   "").strip()

    if not all([current_pw, new_pw, confirm_pw]):
        flash("All password fields are required.", "danger")
        return redirect(url_for("profile.index"))

    if not current_user.check_password(current_pw):
        flash("Current password is incorrect.", "danger")
        return redirect(url_for("profile.index"))

    if new_pw != confirm_pw:
        flash("New passwords do not match.", "danger")
        return redirect(url_for("profile.index"))

    if len(new_pw) < 8:
        flash("New password must be at least 8 characters.", "danger")
        return redirect(url_for("profile.index"))

    if new_pw == current_pw:
        flash("New password must be different from the current one.", "danger")
        return redirect(url_for("profile.index"))

    try:
        current_user.set_password(new_pw)
        db.session.commit()
        flash("Password updated successfully.", "success")
    except Exception:
        db.session.rollback()
        flash("Something went wrong. Please try again.", "danger")

    return redirect(url_for("profile.index"))


@profile_bp.route("/recovery", methods=["POST"])
@login_required
def update_recovery():
    """Admin only — add or update recovery email / phone."""
    if not _is_admin():
        flash("Only the admin can manage recovery details.", "danger")
        return redirect(url_for("profile.index"))

    email  = request.form.get("email",        "").strip()
    phone  = request.form.get("phone_number", "").strip()

    if not email:
        flash("Recovery email is required.", "danger")
        return redirect(url_for("profile.index"))

    # basic email sanity check (no heavy dependency)
    if "@" not in email or "." not in email.split("@")[-1]:
        flash("Please enter a valid email address.", "danger")
        return redirect(url_for("profile.index"))

    try:
        if current_user.recovery_detail:
            current_user.recovery_detail.email        = email
            current_user.recovery_detail.phone_number = phone or None
        else:
            db.session.add(RecoveryDetail(
                user_id      = current_user.user_id,
                email        = email,
                phone_number = phone or None,
            ))
        db.session.commit()
        flash("Recovery details saved.", "success")
    except DataError:
        db.session.rollback()
        flash("One or more values are out of range.", "danger")
    except Exception:
        db.session.rollback()
        flash("Something went wrong. Please try again.", "danger")

    return redirect(url_for("profile.index"))