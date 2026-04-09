"""expand audit_log module enum

Revision ID: bf23f77956c0
Revises: 3041cde81369
Create Date: 2026-04-09 03:39:45.401847

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bf23f77956c0'
down_revision = '3041cde81369'
branch_labels = None
depends_on = None


# ── enum definitions ──────────────────────────────────────────────────────────
OLD_ENUM = ("products", "inventory", "sales", "defects", "users", "stock_in")
NEW_ENUM = ("Products", "Inventory", "Sales", "Defects", "Users", "Stock_In",
            "Settings", "Auth")
 
TABLE  = "Audit_Log"
COLUMN = "module"
 
 
def upgrade() -> None:
    # Step 1 – Widen the column to accept BOTH old and new values so that
    #          existing rows are never invalid mid-migration.
    transition_values = OLD_ENUM + NEW_ENUM          # full union, no duplicates
    _modify_enum(transition_values)
 
    # Step 2 – Re-case every existing row (old lowercase → PascalCase).
    #          Uses a CASE expression so a single UPDATE touches all rows once.
    op.execute(f"""
        UPDATE `{TABLE}`
        SET `{COLUMN}` = CASE `{COLUMN}`
            WHEN 'products'  THEN 'Products'
            WHEN 'inventory' THEN 'Inventory'
            WHEN 'sales'     THEN 'Sales'
            WHEN 'defects'   THEN 'Defects'
            WHEN 'users'     THEN 'Users'
            WHEN 'stock_in'  THEN 'Stock_In'
            ELSE `{COLUMN}`               -- already PascalCase, leave untouched
        END
    """)
 
    # Step 3 – Lock the column down to the final, clean enum.
    _modify_enum(NEW_ENUM)
 
 
def downgrade() -> None:
    # Step 1 – Widen to accept both directions again.
    transition_values = OLD_ENUM + NEW_ENUM
    _modify_enum(transition_values)
 
    # Step 2 – Revert PascalCase → lowercase.
    #          Rows with Settings / Auth have no lowercase equivalent,
    #          so they are coerced to 'products' as a safe fallback.
    op.execute(f"""
        UPDATE `{TABLE}`
        SET `{COLUMN}` = CASE `{COLUMN}`
            WHEN 'Products'  THEN 'products'
            WHEN 'Inventory' THEN 'inventory'
            WHEN 'Sales'     THEN 'sales'
            WHEN 'Defects'   THEN 'defects'
            WHEN 'Users'     THEN 'users'
            WHEN 'Stock_In'  THEN 'stock_in'
            ELSE 'products'               -- Settings / Auth: fallback
        END
    """)
 
    # Step 3 – Restore the original enum.
    _modify_enum(OLD_ENUM)
 
 
# ── helpers ───────────────────────────────────────────────────────────────────
 
def _modify_enum(values: tuple) -> None:
    """Issue a MySQL MODIFY COLUMN to set the ENUM to *values*."""
    enum_literals = ", ".join(f"'{v}'" for v in values)
    op.execute(
        f"ALTER TABLE `{TABLE}` "
        f"MODIFY COLUMN `{COLUMN}` ENUM({enum_literals}) NOT NULL"
    )
 