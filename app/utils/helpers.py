from flask import render_template
import re

def message(num=400, message="Error occur"):
    return render_template("message.html", message=message, error_code=num)

def validate_password(password):
    """
    Returns (True, None) if valid.
    Returns (False, error_message) if invalid.
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number."
    if not re.search(r"[@$!%*?&_#\-]", password):
        return False, "Password must contain at least one special character (@$!%*?&_#-)."
    return True, None


def validate_name(value, field_label):
    """
    Returns (True, None) if valid.
    Returns (False, error_message) if invalid.
    """
    if not re.match(r"^[a-zA-Z\s\-]+$", value):
        return False, f"{field_label} can only contain letters, spaces, and hyphens."
    return True, None


def validate_category_name(name):
    if not re.match(r"^[a-zA-Z0-9\s\-&/]+$", name):
        return False, "Category name can only contain letters, numbers, spaces, hyphens, ampersands, and slashes."
    return True, None
