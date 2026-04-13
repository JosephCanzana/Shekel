import re
from datetime import datetime
from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from flask_mail import Message
from sqlalchemy import func
from werkzeug.security import check_password_hash
from app.extensions import mail, db
from app.models.user import User
from app.models.recovery_detail import RecoveryDetail
from app.utils.helpers import generate_reset_token, get_token_expiry, validate_password, message
from app.utils.audit import audit

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name  = request.form.get("full_name", "").strip()
        password = request.form.get("password", "").strip()

        if not name or not password:
            flash("Please fill in all fields.", "error")
            return redirect(url_for("auth.login"))

        # normalize input — lowercase, collapse extra spaces
        normalized = " ".join(name.lower().split())
        parts = normalized.split()

        if len(parts) < 2:
            flash("Please enter your full name.", "error")
            return redirect(url_for("auth.login"))

        # build all possible first/last name splits
        # e.g. "juan miguel dela cruz" →
        #   first="juan"            last="miguel dela cruz"
        #   first="juan miguel"     last="dela cruz"
        #   first="juan miguel dela" last="cruz"
        candidates = [
            (" ".join(parts[:i]), " ".join(parts[i:]))
            for i in range(1, len(parts))
        ]

        # find user matching any split combination
        user = None
        for first, last in candidates:
            user = User.query.filter(
                func.lower(User.first_name) == first,
                func.lower(User.last_name)  == last
            ).first()
            if user:
                break


        if not user:
            flash("Invalid name or password.", "error")
            return redirect(url_for("auth.login"))

        if not check_password_hash(user.password, password):
            flash("Invalid name or password.", "error")
            return redirect(url_for("auth.login"))
        
        if user.status == "archived":
            flash("Your account is archived! Please contact the admin")
            return redirect(url_for("auth.login"))
        elif user.status == "suspended":
            flash("Your account is suspended! Please contact the admin")
            return redirect(url_for("auth.login"))
        elif user.status == "not_activated":
            return redirect(url_for("auth.account_activation", user_id=user.user_id))

        login_user(user)
        if current_user.role != "superadmin":
            audit("LOGIN", "Auth", f"{user.first_name} logged in", user_id=user.user_id)
            db.session.commit()
        try:
            if user.role == "superadmin":
                return redirect(url_for("superadmin.dashboard"))
            elif user.role == "admin":
                return redirect(url_for("admin.dashboard"))
            elif user.role == "cashier":
                return redirect(url_for("cashier.transaction"))
            elif user.role == "stocking":
                return redirect(url_for("stocking.dashboard"))
        except Exception as e:
            return message(404, f"An error occur while validating your role{e}")

    return render_template("auth/login.html")


@auth_bp.route("/login/<int:user_id>/account_activation", methods=["GET", "POST"])
def account_activation(user_id):
    user = User.get_by_id(user_id)
    
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("auth.login"))

    if user.status != "not_activated":
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        password         = request.form.get("password", "").strip()
        password_confirm = request.form.get("password_confirm", "").strip()

        if not password or not password_confirm:
            flash("Please fill in all fields.", "danger")
            return redirect(url_for("auth.account_activation", user_id=user_id))

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return redirect(url_for("auth.account_activation", user_id=user_id))

        if not re.search(r"[A-Z]", password):
            flash("Password must contain at least one uppercase letter.", "danger")
            return redirect(url_for("auth.account_activation", user_id=user_id))

        if not re.search(r"[a-z]", password):
            flash("Password must contain at least one lowercase letter.", "danger")
            return redirect(url_for("auth.account_activation", user_id=user_id))

        if not re.search(r"\d", password):
            flash("Password must contain at least one number.", "danger")
            return redirect(url_for("auth.account_activation", user_id=user_id))

        if not re.search(r"[@$!%*?&_#\-]", password):
            flash("Password must contain at least one special character (@$!%*?&_#-).", "danger")
            return redirect(url_for("auth.account_activation", user_id=user_id))

        if password != password_confirm:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("auth.account_activation", user_id=user_id))
        
        if password == User.get_default_password():
            flash("Default password is not allowed.", "danger")
            return redirect(url_for("auth.account_activation", user_id=user_id))

        user.set_password(password)
        user.status = "activated"
        user.save()

        login_user(user)
        flash("Welcome! Your account has been activated.", "success")

        audit("UPDATE", "Auth", f"{user.first_name} activated the account", user_id=user.user_id)
        db.session.commit()

        if user.role == "superadmin":
            return redirect(url_for("superadmin.dashboard"))
        elif user.role == "admin":
            return redirect(url_for("admin.dashboard"))
        elif user.role == "cashier":
            return redirect(url_for("cashier.transaction"))
        elif user.role == "stocking":
            return redirect(url_for("stocking.dashboard"))

    return render_template("auth/account_activation.html", user=user)


@auth_bp.route("/logout", methods=["GET", "POST"])
@login_required
def logout():        
    if current_user.role != "superadmin":
        audit("LOGOUT", "Auth", f"{current_user.first_name} logged out", user_id=current_user.user_id)
        db.session.commit()
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))



# ── Forgot Password ───────────────────────────────────────
@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        recovery = RecoveryDetail.query.filter_by(email=email).first()

        if (recovery
                and recovery.user.role == "superadmin"
                and recovery.is_verified):          # ← only send if verified
            token                 = generate_reset_token()
            recovery.reset_token  = token
            recovery.token_expiry = get_token_expiry()
            db.session.commit()

            reset_url = url_for('auth.reset_password', token=token, _external=True)
            msg       = Message("Password Reset — Shekel", recipients=[email])
            msg.body  = (
                f"Hello,\n\nClick the link to reset your password "
                f"(expires in 30 minutes).\n\n{reset_url}\n\n"
                f"If you did not request this, ignore this email."
            )
            mail.send(msg)

        flash("If that email belongs to a superadmin account, a reset link has been sent.", "info")
        return redirect(url_for('auth.forgot_password'))

    return render_template("auth/forgot_password.html")


# ── Reset Password ────────────────────────────────────────
@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    recovery = RecoveryDetail.query.filter_by(reset_token=token).first()

    if not recovery or recovery.token_expiry < datetime.utcnow():
        flash("Reset link is invalid or has expired.", "error")
        return redirect(url_for('auth.forgot_password'))

    if recovery.user.role != "superadmin":
        flash("Reset link is invalid or has expired.", "error")
        return redirect(url_for('auth.forgot_password'))

    if request.method == "POST":
        password = request.form.get("password", "").strip()
        confirm  = request.form.get("confirm_password", "").strip()

        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for('auth.reset_password', token=token))

        valid, err = validate_password(password)
        if not valid:
            flash(err, "error")
            return redirect(url_for('auth.reset_password', token=token))

        recovery.user.set_password(password)
        recovery.reset_token  = None
        recovery.token_expiry = None
        db.session.commit()

        flash("Password reset successful. You can now log in.", "success")
        return redirect(url_for('auth.login'))

    return render_template("auth/reset_password.html", token=token)
