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

        login_user(user)
        try:
            if user.role == "admin":
                return redirect(url_for("admin.dashboard"))
            elif user.role == "co-admin":
                return redirect(url_for("admin.dashboard"))
            elif user.role == "cashier":
                return redirect(url_for("cashier.transaction"))
            elif user.role == "inventory":
                return redirect(url_for("stocking.dashboard"))
        except Exception as e:
            return message(404, "An error occur while validating your role")

    return render_template("auth/login.html")

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))