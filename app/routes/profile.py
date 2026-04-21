from datetime import datetime
from flask               import render_template, request, flash, redirect, url_for, Blueprint, current_app
from flask_login         import login_required, current_user
from flask_mail import Message
from sqlalchemy.exc      import DataError
from app.extensions      import db, mail
from app.utils.decorator import role_required
from app.models.recovery_detail import RecoveryDetail
from app.utils.helpers import validate_password,validate_email, validate_phone, generate_verification_token, get_token_expiry, message

profile_bp = Blueprint("profile", __name__, url_prefix="/profile")


@profile_bp.route("/", methods=["GET"])
@login_required
def index():
    return render_template(
        "profile/index.html",
        user                = current_user,
        can_change_pw       = current_user.role in ("superadmin", "admin"),
        is_admin            = current_user.role == "superadmin",
        can_manage_recovery = current_user.role in ("superadmin", "admin"),
    )


@profile_bp.route("/change-password", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def change_password():

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

    ok, err = validate_password(new_pw)
    if not ok:
        flash(err, "danger")
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
@role_required("superadmin", "admin")
def update_recovery():
    email = request.form.get("email",        "").strip()
    phone = request.form.get("phone_number", "").strip()

    if not email:
        flash("Email is required for account recovery.", "danger")
        return redirect(url_for("profile.index"))

    ok, err = validate_email(email)
    if not ok:
        flash(err, "danger")
        return redirect(url_for("profile.index"))

    existing = RecoveryDetail.query.filter_by(email=email).first()
    if existing and existing.user_id != current_user.user_id:
        flash("That email is already used by another account.", "danger")
        return redirect(url_for("profile.index"))

    ok, err = validate_phone(phone)
    if not ok:
        flash(err, "danger")
        return redirect(url_for("profile.index"))

    try:
        token  = generate_verification_token()
        expiry = get_token_expiry(minutes=60)

        if current_user.recovery_detail:
            current_user.recovery_detail.email               = email
            current_user.recovery_detail.phone_number        = phone or None
            current_user.recovery_detail.is_verified         = False  # reset on email change
            current_user.recovery_detail.verify_token        = token
            current_user.recovery_detail.verify_token_expiry = expiry
        else:
            db.session.add(RecoveryDetail(
                user_id             = current_user.user_id,
                email               = email,
                phone_number        = phone or None,
                is_verified         = False,
                verify_token        = token,
                verify_token_expiry = expiry,
            ))
        db.session.commit()

        base_url   = current_app.config["APP_BASE_URL"]
        verify_url = f"{base_url}/profile/recovery/verify/{token}"
        msg        = Message("Verify your recovery email — Shekel", recipients=[email])
        msg.body   = (
            f"Hello,\n\nClick the link to verify your recovery email "
            f"(expires in 1 hour).\n\n{verify_url}\n\n"
            f"If you did not request this, ignore this email."
        )
        mail.send(msg)
        flash("Verification email sent. Please check your inbox to confirm.", "success")

    except DataError:
        db.session.rollback()
        flash("One or more values are out of range.", "danger")
    except Exception:
        db.session.rollback()
        flash("Something went wrong. Please try again.", "danger")

    return redirect(url_for("profile.index"))


@profile_bp.route("/update-identity", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def update_identity():
    first_name = request.form.get("first_name", "").strip().lower()
    last_name  = request.form.get("last_name",  "").strip().lower()

    if not all([first_name, last_name]):
        flash("All fields are required.", "danger")
        return redirect(url_for("profile.index"))

    try:
        current_user.first_name = first_name
        current_user.last_name  = last_name
        db.session.commit()
        flash("Profile updated successfully.", "success")
    except DataError:
        db.session.rollback()
        flash("One or more values are out of range.", "danger")
    except Exception:
        db.session.rollback()
        flash("Something went wrong. Please try again.", "danger")

    return redirect(url_for("profile.index"))


@profile_bp.route("/recovery/verify/<token>")
@login_required
@role_required("superadmin", "admin")
def verify_recovery_email(token):
    recovery = RecoveryDetail.query.filter_by(
        verify_token=token,
        user_id=current_user.user_id
    ).first()

    if not recovery or recovery.verify_token_expiry < datetime.utcnow():
        flash("Verification link is invalid or has expired.", "danger")
        return redirect(url_for("profile.index"))

    recovery.is_verified         = True
    recovery.verify_token        = None   # consume token
    recovery.verify_token_expiry = None
    db.session.commit()

    flash("Recovery email verified successfully.", "success")
    return redirect(url_for("profile.index"))

@profile_bp.route("/recovery/resend-verification", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def resend_verification():
    recovery = current_user.recovery_detail

    if not recovery:
        flash("No recovery email set yet.", "danger")
        return redirect(url_for("profile.index"))

    if recovery.is_verified:
        flash("Your recovery email is already verified.", "info")
        return redirect(url_for("profile.index"))

    try:
        token  = generate_verification_token()
        expiry = get_token_expiry(minutes=60)

        recovery.verify_token        = token
        recovery.verify_token_expiry = expiry
        db.session.commit()

        base_url  = current_app.config["APP_BASE_URL"]
        reset_url = f"{base_url}/reset-password/{token}"
        msg        = Message(
            "Verify your recovery email — Shekel",
            sender=os.getenv("MAIL_USERNAME"),
            recipients=[recovery.email]
        )
        msg.body = (
            f"Hello,\n\nClick the link to verify your recovery email "
            f"(expires in 1 hour).\n\n{verify_url}\n\n"
            f"If you did not request this, ignore this email."
        )
        mail.send(msg)
        flash("Verification email resent. Please check your inbox.", "success")

    except Exception as e:
        db.session.rollback()
        print(f"Resend verification error: {e}")
        flash("Something went wrong. Please try again.", "danger")

    return redirect(url_for("profile.index"))