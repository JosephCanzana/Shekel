"""add defect_exchange_items and sale_detail override_used

Revision ID: a1b2c3d4e5f6
Revises: 39dde2ed4132
Create Date: 2026-04-11

Changes
-------
1. Create Defect_Exchange_Items table
   - exchange_item_id  INT PK AUTO_INCREMENT
   - defect_detail_id  INT FK → Defect_Details(defect_detail_id) ON DELETE CASCADE
   - product_id        VARCHAR(100) FK → Products(product_id) ON UPDATE CASCADE ON DELETE RESTRICT
   - quantity          INT NOT NULL DEFAULT 1
   - price_at_exchange DECIMAL(10,2) NOT NULL
   - no_money_exchange TINYINT(1) NOT NULL DEFAULT 0
   - override_used     TINYINT(1) NOT NULL DEFAULT 0

2. Add override_used TINYINT(1) NOT NULL DEFAULT 0 to Sales_Details table
   (per line item — flags exactly which product exceeded available stock
   at charge time, not just the transaction as a whole)

Note: Defect_Details.exchange_product_id and .price_difference are intentionally
left in place for backward compatibility with existing rows. They are deprecated
for all new writes — new exchange_different records use Defect_Exchange_Items.
"""

from alembic import op
import sqlalchemy as sa


# ── Identifiers ───────────────────────────────────────────────────────────────
revision = "a1b2c3d4e5f6"
down_revision = "39dde2ed4132"   # ← replace with your actual head
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. Defect_Exchange_Items ──────────────────────────────────────────────
    op.create_table(
        "Defect_Exchange_Items",
        sa.Column("exchange_item_id",  sa.Integer(),       primary_key=True, autoincrement=True),
        sa.Column("defect_detail_id",  sa.Integer(),       nullable=False),
        sa.Column("product_id",        sa.String(100),     nullable=False),
        sa.Column("quantity",          sa.Integer(),       nullable=False, server_default="1"),
        sa.Column("price_at_exchange", sa.Numeric(10, 2),  nullable=False),
        sa.Column("no_money_exchange", sa.SmallInteger(),  nullable=False, server_default="0"),
        sa.Column("override_used",     sa.SmallInteger(),  nullable=False, server_default="0"),

        sa.ForeignKeyConstraint(
            ["defect_detail_id"],
            ["Defect_Details.defect_detail_id"],
            name="fk_dei_defect_detail_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["Products.product_id"],
            name="fk_dei_product_id",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),

        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )

    op.create_index(
        "ix_dei_defect_detail_id",
        "Defect_Exchange_Items",
        ["defect_detail_id"],
    )
    op.create_index(
        "ix_dei_product_id",
        "Defect_Exchange_Items",
        ["product_id"],
    )

    # ── 2. Sales_Details.override_used ────────────────────────────────────────
    op.add_column(
        "Sales_Details",
        sa.Column(
            "override_used",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
            comment=(
                "1 when this specific line item quantity exceeded "
                "quantity_available at charge time. Does not block the sale."
            ),
        ),
    )


def downgrade():
    # ── 2. Remove Sales_Details.override_used ─────────────────────────────────
    op.drop_column("Sales_Details", "override_used")

    # ── 1. Drop Defect_Exchange_Items ─────────────────────────────────────────
    op.drop_index("ix_dei_product_id",        table_name="Defect_Exchange_Items")
    op.drop_index("ix_dei_defect_detail_id",  table_name="Defect_Exchange_Items")
    op.drop_table("Defect_Exchange_Items")