from flask import redirect, url_for, request
from flask_login import current_user
from app.utils.maintenance_helpers import get_maintenance_state

EXEMPT_ROUTES = {
    "maintenance.page",
    "maintenance.status_api",
    "superadmin.maintenance_update",
    "superadmin.maintenance_end",
    "auth.login",
    "auth.logout",
    "auth.forgot_password",
    "auth.reset_password", 
    "static",
}

def register_maintenance_middleware(app):
    @app.before_request
    def check_maintenance():
        # Let superadmins through always
        if current_user.is_authenticated and current_user.role == "superadmin":
            return

        # Skip exempt routes
        if request.endpoint in EXEMPT_ROUTES:
            return

        state = get_maintenance_state()
        if state["is_active"]:
            return redirect(url_for("maintenance.page"))