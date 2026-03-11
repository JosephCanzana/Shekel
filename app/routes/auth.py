from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func
from werkzeug.security import check_password_hash
from app.models.user import User
from app.utils.helpers import message

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
        try:
            if user.role == "admin":
                return redirect(url_for("admin.dashboard"))
            elif user.role == "co-admin":
                return redirect(url_for("admin.dashboard"))
            elif user.role == "cashier":
                return redirect(url_for("cashier.transaction"))
            elif user.role == "stocking":
                return redirect(url_for("stocking.dashboard"))
        except Exception as e:
            return message(404, "An error occur while validating your role")

    return render_template("auth/login.html")


@auth_bp.route("/login/<int:user_id>/account_activation", methods=["GET", "POST"])
def account_activation(user_id):
    user = User.get_by_id(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("auth.login"))

    # if already activated, just send to login
    if user.status != "not_activated":
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        password        = request.form.get("password", "").strip()
        password_confirm = request.form.get("password_confirm", "").strip()

        if not password or not password_confirm:
            flash("Please fill in all fields.", "danger")
            return redirect(url_for("auth.account_activation", user_id=user_id))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("auth.account_activation", user_id=user_id))

        if password != password_confirm:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("auth.account_activation", user_id=user_id))

        user.set_password(password)
        user.status = "activated"
        user.save()

        login_user(user)
        flash("Welcome! Your account has been activated.", "success")

        if user.role == "admin":
            return redirect(url_for("admin.dashboard"))
        elif user.role == "co-admin":
            return redirect(url_for("admin.dashboard"))
        elif user.role == "cashier":
            return redirect(url_for("cashier.transaction"))
        elif user.role == "stocking":
            return redirect(url_for("stocking.dashboard"))

    return render_template("auth/account_activation.html", user=user)


@auth_bp.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))