import json
from flask import request, redirect, url_for, flash, Blueprint, render_template
from flask_login import login_required
from app.utils.decorator import role_required
from app.utils.index_helpers import get_time_of_day 
from app.models.user import User
from datetime import datetime, timedelta
from app.models.maintenance import MaintenanceSettings
from app.extensions import db
from app.utils.maintenance_helpers import get_maintenance_state


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

@superadmin_bp.route("/maintenance", methods=["GET"])
@login_required
@role_required("superadmin")
def maintenance_control():
    state = get_maintenance_state()
    return render_template(
        "superadmin/maintenance_control.html",
        state=state,
        time_of_day=get_time_of_day(),
    )


@superadmin_bp.route("/maintenance/update", methods=["POST"])
@login_required
@role_required("superadmin")
def maintenance_update():
    m = MaintenanceSettings.get()

    minutes_until        = int(request.form.get("minutes_until") or 0)
    duration_minutes_raw = request.form.get("duration_minutes", "").strip()
    duration_minutes     = int(duration_minutes_raw) if duration_minutes_raw else None
    show_countdown       = request.form.get("show_countdown") == "on"
    auto_end             = request.form.get("auto_end") == "on"
    message              = request.form.get("message", m.message)

    now = datetime.utcnow()
    m.scheduled_start = now + timedelta(minutes=minutes_until) if minutes_until > 0 else now
    m.estimated_end   = (
        now + timedelta(minutes=minutes_until + duration_minutes)
        if duration_minutes else None
    )
    m.show_countdown  = show_countdown
    m.auto_end        = auto_end
    m.message         = message
    m.is_active       = (minutes_until == 0)

    db.session.commit()

    flash(
        "Maintenance scheduled." if minutes_until > 0 else "Maintenance activated.",
        "success",
    )
    return redirect(url_for("superadmin.maintenance_control"))


@superadmin_bp.route("/maintenance/cancel", methods=["POST"])
@login_required
@role_required("superadmin")
def maintenance_cancel():
    """Cancel a scheduled (not yet active) maintenance window."""
    m = MaintenanceSettings.get()

    if m.is_active:
        flash("Cannot cancel: maintenance is already active. Use 'End Maintenance' instead.", "error")
        return redirect(url_for("superadmin.maintenance_control"))

    m.scheduled_start = None
    m.estimated_end   = None
    m.show_countdown  = False
    m.auto_end        = False

    db.session.commit()

    flash("Scheduled maintenance has been cancelled.", "success")
    return redirect(url_for("superadmin.maintenance_control"))


@superadmin_bp.route("/maintenance/end", methods=["POST"])
@login_required
@role_required("superadmin")
def maintenance_end():
    m = MaintenanceSettings.get()

    m.is_active       = False
    m.scheduled_start = None
    m.estimated_end   = None

    db.session.commit()

    flash("Maintenance ended. System is back online.", "success")
    return redirect(url_for("superadmin.maintenance_control"))