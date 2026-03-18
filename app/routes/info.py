from flask import render_template, Blueprint
from flask_login import login_required

info_bp = Blueprint("info", __name__, url_prefix="/info")


@info_bp.route("/")
@login_required
def index():
    return render_template("about.html")