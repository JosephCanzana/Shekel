from flask import Blueprint, render_template, jsonify
from flask_login import current_user
from app.utils.maintenance_helpers import get_maintenance_state

maintenance_bp = Blueprint("maintenance", __name__)

@maintenance_bp.route("/maintenance")
def page():
    state = get_maintenance_state()
    # If somehow maintenance ended, send them back home
    if not state["is_active"]:
        from flask import redirect, url_for
        if current_user.role == "superadmin":
            return redirect(url_for("superadmin.dashboard"))
        elif current_user.role == "admin":
            return redirect(url_for("admin.dashboard"))
        elif current_user.role == "cashier":
            return redirect(url_for("cashier.transaction"))
        elif current_user.role == "stocking":
            return redirect(url_for("stocking.dashboard"))
    return render_template("maintenance.html", state=state)

@maintenance_bp.route("/api/maintenance-status")
def status_api():
    """Polled by the pre-maintenance banner to keep countdown in sync."""
    return jsonify(get_maintenance_state())