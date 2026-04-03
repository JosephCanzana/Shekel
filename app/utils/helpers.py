import re
import pytz
from datetime import datetime
from flask import render_template
from flask_login import current_user
from app.models.category import Category
from app.models.product import Product
from app.models.product_bundle import ProductBundle
import uuid
import secrets
from datetime import datetime, timedelta

PHT = pytz.timezone("Asia/Manila")


def generate_charge_token():
    return str(uuid.uuid4())

def message(num=400, message="Error occur"):
    return render_template("message.html", message=message, error_code=num)

# Forgot password
def generate_reset_token():
    return secrets.token_urlsafe(32)

def get_token_expiry(minutes=30):
    return datetime.utcnow() + timedelta(minutes=minutes)

def generate_verification_token():
    return secrets.token_urlsafe(32)

# Convert utc to ph time
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
 
 
def validate_email(email):
    if not email:
        return False, "Email is required."
    pattern = r"^[\w\.\+\-]+@[\w\-]+\.[\w\.\-]+$"
    if not re.match(pattern, email):
        return False, "Please enter a valid email address."
    return True, None  
 
 
def validate_phone(phone):
    """
    Validates a Philippine mobile number.
    Accepts formats: +63XXXXXXXXXX, 09XXXXXXXXX, 9XXXXXXXXX
    Returns (True, None) if valid.
    Returns (False, error_message) if invalid.
    Phone is optional — pass empty string to skip validation.
    """
    if not phone:
        return True, None  # optional field
 
    # strip spaces and dashes for normalisation
    cleaned = re.sub(r"[\s\-]", "", phone)
 
    pattern = r"^(\+639\d{9}|09\d{9}|9\d{9})$"
    if not re.match(pattern, cleaned):
        return False, "Phone must be a valid Philippine mobile number (e.g. +63 912 345 6789 or 09123456789)."
 
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
    return current_user.role in ("superadmin", "admin")


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

# Category

def get_category_thresholds():
    """Returns {category_id: default_low_stock_threshold} for all active categories."""
    from app.models.category import Category
    return {
        c.category_id: c.default_low_stock_threshold
        for c in Category.query.filter_by(status="active").all()
    }
 