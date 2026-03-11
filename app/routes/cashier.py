from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_required, current_user
from app.utils.decorator import role_required

cashier_bp = Blueprint("cashier", __name__, url_prefix='/cashier')


@cashier_bp.route("/")
@login_required
@role_required("cashier")
def dashboard():
    return redirect(url_for("cashier.transaction"))

@cashier_bp.route("/transaction")
@login_required
@role_required("cashier")
def transaction():
    return render_template("cashier/transaction.html")

