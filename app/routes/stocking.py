from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_required, current_user
from app.utils.decorator import role_required

stocking_bp = Blueprint("stocking", __name__, url_prefix='/stocking')

@stocking_bp.route("/")
@login_required
@role_required("stocking")
def dashboard():
    return render_template("stocking/dashboard.html")

