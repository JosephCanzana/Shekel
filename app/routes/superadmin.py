import json
from flask import Blueprint, render_template
from flask_login import login_required
from app.utils.decorator import role_required
from app.utils.index_helpers import get_time_of_day 
from app.models.user import User

superadmin_bp = Blueprint("superadmin", __name__, url_prefix='/superadmin')


@superadmin_bp.route("/")
@login_required
@role_required("superadmin")
def dashboard():
    users = User.query.all()
    users_json = json.dumps([{
        "user_id":    u.user_id,
        "first_name": u.first_name,
        "last_name":  u.last_name,
        "role":       u.role,
        "status":     u.status,
    } for u in users])

    return render_template(
        "superadmin/dashboard.html",
        time_of_day = get_time_of_day(),
        users_json  = users_json,
    )