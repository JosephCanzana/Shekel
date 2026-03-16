import re
import pytz
from datetime import datetime
from flask import render_template
from flask_login import current_user
from app.models.category import Category
from app.models.product import Product
from app.models.product_bundle import ProductBundle

PHT = pytz.timezone("Asia/Manila")

def message(num=400, message="Error occur"):
    return render_template("message.html", message=message, error_code=num)

def to_pht(utc_dt):
    """Convert a naive UTC datetime to PHT."""
    return utc_dt.replace(tzinfo=pytz.utc).astimezone(PHT)

def pht_now():
    """Get current datetime in PHT."""
    return datetime.now(PHT)

def pht_today():
    """Get today's date in PHT."""
    return datetime.now(PHT).date()

def get_time_of_day():
    hour = pht_now().hour
    if hour < 12:
        return "morning"
    elif hour < 18:
        return "afternoon"
    return "evening"

# User
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


# Category
def validate_category_name(name):
    if not re.match(r"^[a-zA-Z0-9\s\-&/]+$", name):
        return False, "Category name can only contain letters, numbers, spaces, hyphens, ampersands, and slashes."
    return True, None


# Inventory
def validate_product_name(name):
    if not re.match(r"^[a-zA-Z0-9\s\-&/().]+$", name):
        return False, "Product name contains invalid characters."
    return True, None

def validate_price(value, label):
    try:
        price = float(value)
        if price < 0:
            return False, f"{label} cannot be negative."
        return True, None
    except (ValueError, TypeError):
        return False, f"{label} must be a valid number."

def get_active_categories():
    return Category.query.filter_by(status="active").order_by(Category.category_name).all()

def get_product(product_id):
    return Product.query.get(product_id)

def is_admin_or_coadmin():
    return current_user.role in ("admin", "co-admin")


def barcode_in_use(barcode, exclude_product_id=None, exclude_bundle_id=None):
    """
    Returns a string describing where the barcode is already used,
    or None if it's free.
    Checks Products and ProductBundles so the same barcode
    can't appear in both tables.
    """
    product = Product.query.get(barcode)
    if product and barcode != exclude_product_id:
        return f'"{barcode}" is already used as a Product ID ({product.product_name})'

    bundle = ProductBundle.query.get(barcode)
    if bundle and barcode != exclude_bundle_id:
        return f'"{barcode}" is already used as a Bundle ID ({bundle.bundle_name})'

    return None