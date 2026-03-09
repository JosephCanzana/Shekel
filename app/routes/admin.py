from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func
from werkzeug.security import check_password_hash
from app.models.user import User
from app.utils.helpers import message

admin_bp = Blueprint("admin", __name__, url_prefix='/admin')

@admin_bp.route("/")
def dashboard():
    return render_template("admin/dashboard.html")

