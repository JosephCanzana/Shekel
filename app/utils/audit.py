"""
utils/audit.py
~~~~~~~~~~~~~~
Thin wrapper around ``AuditLog.log()`` for ergonomic imports.

Module constants (PascalCase — must match DB enum exactly):
    Products | Inventory | Sales | Defects | Users | Stock_In | Settings | Auth

Usage — inside any route, BEFORE ``db.session.commit()``:

    from app.utils.audit import audit

    # Login
    audit("LOGIN", "Auth", f"{user.first_name} logged in", user_id=user.user_id)

    # Sale completed
    audit("INSERT", "Sales",
          f"Sale #{sale.transaction_id} — ₱{sale.total_amount:.2f}",
          reference_id=sale.transaction_id, reference_table="Sales")

    # Product updated
    audit("UPDATE", "Products",
          f"Product '{product.product_name}' updated",
          reference_id=product.product_id, reference_table="Products")

    # User deleted
    audit("DELETE", "Users",
          f"User '{target.first_name} {target.last_name}' archived",
          reference_id=target.user_id, reference_table="Users")

    db.session.commit()   # ← one commit saves both the change AND the log entry

Action types : INSERT | UPDATE | DELETE | LOGIN | LOGOUT
"""

from app.models.audit_log import AuditLog


def audit(
    action_type: str,
    module: str,
    description: str,
    *,
    reference_id: int | None = None,
    reference_table: str | None = None,
    user_id: int | None = None,
) -> AuditLog | None:
    """
    Proxy for ``AuditLog.log()``.

    Does **not** commit — always commit in the calling route so that the audit
    log and the business change are atomic (both saved or both rolled back).
    """
    return AuditLog.log(
        action_type,
        module,
        description,
        reference_id    = reference_id,
        reference_table = reference_table,
        user_id         = user_id,
    )