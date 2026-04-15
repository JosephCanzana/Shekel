# app/utils/navbar_notifications.py

from __future__ import annotations
from datetime import datetime, timedelta
from app.extensions import db
from app.models.audit_log import AuditLog


_ROLE_CONFIG: dict[str, dict] = {
    "superadmin": {
        "modules": ["Auth", "Users"],
        "actions": ["LOGIN", "LOGOUT", "INSERT", "UPDATE", "DELETE"],
    },
    "admin": {
        "modules": ["Stock_In", "Defects", "Sales", "Inventory"],
        "actions": ["INSERT", "UPDATE", "DELETE"],
    },
    "stock_in": {
        "modules": ["Stock_In", "Inventory", "Defects"],
        "actions": ["INSERT", "UPDATE", "DELETE"],
    },
}

_ROLE_CONFIG["stocking"] = _ROLE_CONFIG["stock_in"]

NOTIF_ROLES = set(_ROLE_CONFIG.keys())

MODULE_META: dict[str, tuple[str, str]] = {
    "Auth":      ("login",              "--color-accent"),
    "Users":     ("manage_accounts",    "--color-accent"),
    "Stock_In":  ("add_box",            "--color-warning"),
    "Inventory": ("warehouse",          "--color-success"),
    "Defects":   ("report",             "--color-error"),
    "Sales":     ("receipt_long",       "--color-primary"),
    "Returns":   ("assignment_return",  "--color-warning"),
    "Products":  ("inventory_2",        "--color-secondary"),
    "Settings":  ("settings",           "--color-txt-muted"),
}


# ── these two were missing from your file ────────────────────

def module_meta(module: str) -> tuple[str, str]:
    """Return (material-icon-name, css-var-color) for a module string."""
    return MODULE_META.get(module, ("notifications", "--color-txt-muted"))


def relative_time(dt: datetime) -> str:
    """'just now' / '5 m ago' / '3 h ago' / 'Apr 14' helper."""
    diff = datetime.utcnow() - dt
    s = int(diff.total_seconds())
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{s // 60} m ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    return dt.strftime("%b %-d")


# ── public API ───────────────────────────────────────────────

def get_navbar_notifications(
    role: str,
    *,
    limit: int = 6,
    hours: int = 24,
    since_ts: float | None = None,
) -> tuple[list[AuditLog], int]:
    cfg = _ROLE_CONFIG.get(role)
    if not cfg:
        return [], 0

    if since_ts:
        since = datetime.utcfromtimestamp(since_ts)
    else:
        since = datetime.utcnow() - timedelta(hours=hours)

    q = AuditLog.query.filter(
        AuditLog.module.in_(cfg["modules"]),
        AuditLog.action_datetime >= since,
    )

    if cfg["actions"]:
        q = q.filter(AuditLog.action_type.in_(cfg["actions"]))

    q = q.order_by(AuditLog.action_datetime.desc())
    total = q.count()
    entries = q.limit(limit).all()
    return entries, total


# ── context-processor registration ───────────────────────────

def register_context_processor(app) -> None:
    @app.context_processor
    def _inject_navbar_notifications():
        try:
            from flask_login import current_user
            if not current_user or not current_user.is_authenticated:
                return {}
            role = current_user.role
            if role not in NOTIF_ROLES:
                return {}
            entries, count = get_navbar_notifications(role)

            newest_ts = (
                entries[0].action_datetime.timestamp() if entries else 0
            )

            return {
                "navbar_notifications": entries,
                "navbar_notif_count":   count,
                "navbar_module_meta":   module_meta,
                "navbar_rel_time":      relative_time,
                "newest_notif_time":    newest_ts,
            }
        except Exception:
            return {}