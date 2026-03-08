from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User
from app.utils.helpers import message

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form.get("full_name")
        password = request.form.get("password")




        return message(404, f"{name} pass: {password}")
    else:    
        return render_template("auth/login.html")
    