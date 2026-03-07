# app/utils/decorators.py
from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.role not in roles:
                flash("You do not have permission.", "danger")
                return redirect(url_for("auth.dashboard"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator