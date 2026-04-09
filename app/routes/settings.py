import json
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from app.utils.decorator import role_required
from app.models.role_column_setting import RoleColumnSetting
from app.models.app_settings import AppSettings
from app.extensions import db
from app.utils.helpers import validate_password
from app.utils.audit import audit

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")

ALL_COLUMNS = [
    {"key": "sku",                 "label": "Barcode / SKU",       "group": "Product"},
    {"key": "bundle_barcode",      "label": "Bundle Barcode",       "group": "Product"},
    {"key": "bundle_name",         "label": "Bundle Name",          "group": "Product"},
    {"key": "units_per_bundle",    "label": "Units per Bundle",     "group": "Product"},
    {"key": "category",            "label": "Category",             "group": "Product"},
    {"key": "status",              "label": "Status",               "group": "Product"},
    {"key": "stock",               "label": "Stock (Units)",        "group": "Inventory"},
    {"key": "low_stock_threshold", "label": "Low Stock Threshold",  "group": "Inventory"},
    {"key": "last_updated",        "label": "Last Updated",         "group": "Inventory"},
    {"key": "unit_cost",           "label": "Unit Cost",            "group": "Pricing"},
    {"key": "unit_revenue",        "label": "Unit Revenue",         "group": "Pricing"},
    {"key": "unit_price",          "label": "Unit Price",           "group": "Pricing"},
    {"key": "bundle_cost",         "label": "Bundle Cost",          "group": "Pricing"},
    {"key": "bundle_revenue",      "label": "Bundle Revenue",       "group": "Pricing"},
    {"key": "bundle_price",        "label": "Bundle Price",         "group": "Pricing"},
    {"key": "stock_cost_value",    "label": "Stock Cost Value",     "group": "Value"},
    {"key": "stock_revenue_value", "label": "Stock Revenue Value",  "group": "Value"},
    {"key": "stock_total_value",   "label": "Stock Total Value",    "group": "Value"},
]

LOCKED_COLUMNS = ["name", "actions"]

ROLE_COLUMN_DEFAULTS = {
    "admin": {
        "available": [c["key"] for c in ALL_COLUMNS],
        "defaults":  ["stock", "unit_price", "stock_total_value", "low_stock_threshold"]
    },
    "stocking": {
        "available": ["sku", "bundle_name", "stock", "unit_price",
                      "bundle_price", "stock_total_value",
                      "category", "low_stock_threshold", "status", "last_updated"],
        "defaults":  ["stock", "unit_price", "low_stock_threshold"]
    }
}


def get_role_setting(role, page="inventory"):
    setting = RoleColumnSetting.query.filter_by(role=role, page=page).first()
    if setting:
        return {
            "available": json.loads(setting.available),
            "defaults":  json.loads(setting.defaults)
        }
    return ROLE_COLUMN_DEFAULTS.get(role, {"available": [], "defaults": []})


# ── Index ─────────────────────────────────────────────────────────────────────
@settings_bp.route("/")
@login_required
@role_required("superadmin")
def index():
    app_settings = AppSettings.get()
    return render_template("settings/index.html",
                           default_password=app_settings.default_password)


# ── Columns page ──────────────────────────────────────────────────────────────
@settings_bp.route("/columns")
@login_required
@role_required("superadmin")
def columns():
    admin_cols    = get_role_setting("admin")
    stocking_cols = get_role_setting("stocking")
    return render_template("settings/columns.html",
                           all_columns=ALL_COLUMNS,
                           locked_columns=LOCKED_COLUMNS,
                           admin_available=admin_cols["available"],
                           admin_defaults=admin_cols["defaults"],
                           stocking_available=stocking_cols["available"],
                           stocking_defaults=stocking_cols["defaults"])


# ── POST default password ─────────────────────────────────────────────────────
@settings_bp.route("/api/default-password", methods=["POST"])
@login_required
@role_required("superadmin")
def update_default_password():
    data     = request.json or {}
    password = data.get("password", "").strip()

    if not password:
        return jsonify({"error": "Password is required."}), 400

    ok, err = validate_password(password)
    if not ok:
        return jsonify({"error": err}), 400

    AppSettings.set_default_password(password)
    audit("UPDATE", "Settings", f"{current_user.first_name} updated the password", user_id=current_user.user_id)
    db.session.commit()
    return jsonify({"ok": True})


# ── GET role column settings ──────────────────────────────────────────────────
@settings_bp.route("/api/role-columns/<role>", methods=["GET"])
@login_required
@role_required("superadmin")
def get_role_columns(role):
    if role not in ("admin", "stocking"):
        return jsonify({"error": "Invalid role."}), 400
    return jsonify(get_role_setting(role))


# ── POST save role column settings ───────────────────────────────────────────
@settings_bp.route("/api/role-columns/<role>", methods=["POST"])
@login_required
@role_required("superadmin")
def save_role_columns(role):
    if role not in ("admin", "stocking"):
        return jsonify({"error": "Invalid role."}), 400

    data      = request.json or {}
    page      = data.get("page", "inventory")
    available = data.get("available", [])
    defaults  = data.get("defaults",  [])

    # defaults must be subset of available
    defaults = [c for c in defaults if c in available]

    setting = RoleColumnSetting.query.filter_by(role=role, page=page).first()
    if setting:
        setting.available = json.dumps(available)
        setting.defaults  = json.dumps(defaults)
        action = "UPDATE"
    else:
        db.session.add(RoleColumnSetting(
            role=role, page=page,
            available=json.dumps(available),
            defaults=json.dumps(defaults)
        ))
        action = "INSERT"

    audit(action, "Settings",
          f"Role column settings {action.lower()}d for '{role}' on '{page}' page")

    db.session.commit()
    return jsonify({"ok": True})