"""redesign defect_detail: split compensation, merge reasons, add origin/status/soft-delete

Revision ID: redesign_defect_detail
Revises: (set this to your current head revision)
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# ── Set these to match your actual revision chain ─────────────────────────────
revision    = "redesign_defect_detail"
down_revision = "55a467207c93"   # ← replace with your current head from `flask db current`
branch_labels = None
depends_on    = None
# ─────────────────────────────────────────────────────────────────────────────


def upgrade():
    # ── Step 1: Add new nullable columns ─────────────────────────────────────
    op.add_column("Defect_Details",
        sa.Column("origin",
            mysql.ENUM("in_store", "customer"),
            nullable=True))

    op.add_column("Defect_Details",
        sa.Column("status",
            mysql.ENUM("submitted", "active", "rejected"),
            nullable=True))

    op.add_column("Defect_Details",
        sa.Column("customer_compensation",
            mysql.ENUM("full_refund", "partial_refund", "exchange_same",
                       "exchange_different", "none"),
            nullable=True))

    op.add_column("Defect_Details",
        sa.Column("supplier_compensation",
            mysql.ENUM("pending", "loss", "same_item", "different_item", "money", "none"),
            nullable=True))

    op.add_column("Defect_Details",
        sa.Column("exchange_product_id", sa.String(100), nullable=True))

    op.add_column("Defect_Details",
        sa.Column("price_difference", sa.Numeric(10, 2), nullable=True))

    op.add_column("Defect_Details",
        sa.Column("rejection_note", sa.Text, nullable=True))

    op.add_column("Defect_Details",
        sa.Column("is_deleted", sa.Boolean, nullable=True, server_default="0"))

    op.add_column("Defect_Details",
        sa.Column("deleted_by", sa.Integer, nullable=True))

    op.add_column("Defect_Details",
        sa.Column("deleted_at", sa.DateTime, nullable=True))

    # ── Step 2: Migrate existing data ─────────────────────────────────────────

    # origin: infer from transaction_id
    op.execute("""
        UPDATE Defect_Details
        SET origin = CASE
            WHEN transaction_id IS NOT NULL THEN 'customer'
            ELSE 'in_store'
        END
    """)

    # status: all existing records are considered active (already processed)
    op.execute("UPDATE Defect_Details SET status = 'active'")

    # supplier_compensation: map from old compensation column
    op.execute("""
        UPDATE Defect_Details
        SET supplier_compensation = CASE
            WHEN compensation = 'pending'  THEN 'pending'
            WHEN compensation = 'loss'     THEN 'loss'
            WHEN compensation = 'returned' THEN 'same_item'
            ELSE 'pending'
        END
    """)

    # customer_compensation: best-effort mapping from old data
    op.execute("""
        UPDATE Defect_Details
        SET customer_compensation = CASE
            WHEN transaction_id IS NOT NULL AND reason = 'change_of_mind' THEN 'exchange_same'
            WHEN transaction_id IS NOT NULL AND compensation = 'returned'  THEN 'exchange_same'
            WHEN transaction_id IS NOT NULL                                THEN 'full_refund'
            ELSE 'none'
        END
    """)

    # is_deleted: all existing = not deleted
    op.execute("UPDATE Defect_Details SET is_deleted = 0")

# ── Step 3: Widen enum to include both old AND new values ─────────────────
    op.alter_column(
        "Defect_Details", "reason",
        existing_type=mysql.ENUM("defect", "damage", "expired", "change_of_mind"),
        type_=mysql.ENUM("defect", "damage", "damaged", "expired", "change_of_mind"),
        existing_nullable=False,
        nullable=False,
    )

    # ── Step 4: Migrate data now that 'damaged' is a valid enum value ─────────
    op.execute("""
        UPDATE Defect_Details
        SET reason = 'damaged'
        WHERE reason IN ('defect', 'damage')
    """)

    # ── Step 5: Narrow enum to final values only ──────────────────────────────
    op.alter_column(
        "Defect_Details", "reason",
        existing_type=mysql.ENUM("defect", "damage", "damaged", "expired", "change_of_mind"),
        type_=mysql.ENUM("damaged", "expired", "change_of_mind"),
        existing_nullable=False,
        nullable=False,
    )

    # ── Step 6: Add foreign keys for new columns ──────────────────────────────
    op.create_foreign_key(
        "fk_defect_detail_exchange_product",
        "Defect_Details", "Products",
        ["exchange_product_id"], ["product_id"],
        onupdate="CASCADE", ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_defect_detail_deleted_by",
        "Defect_Details", "Users",
        ["deleted_by"], ["user_id"],
    )

    # ── Step 7: Drop old compensation column ──────────────────────────────────
    op.drop_column("Defect_Details", "compensation")


def downgrade():
    # Restore old compensation column
    op.add_column("Defect_Details",
        sa.Column("compensation",
            mysql.ENUM("pending", "loss", "returned"),
            nullable=True))

    op.execute("""
        UPDATE Defect_Details
        SET compensation = CASE
            WHEN supplier_compensation = 'pending'                    THEN 'pending'
            WHEN supplier_compensation = 'loss'                       THEN 'loss'
            WHEN supplier_compensation IN ('same_item','different_item','money') THEN 'returned'
            ELSE 'pending'
        END
    """)

    op.alter_column("Defect_Details", "compensation",
        existing_type=mysql.ENUM("pending", "loss", "returned"),
        nullable=False)

    # Restore reason enum
    op.execute("""
        UPDATE Defect_Details SET reason = 'defect' WHERE reason = 'damaged'
    """)
    op.alter_column(
        "Defect_Details", "reason",
        existing_type=mysql.ENUM("damaged", "expired", "change_of_mind"),
        type_=mysql.ENUM("defect", "damage", "expired", "change_of_mind"),
        existing_nullable=False,
        nullable=False,
    )

    # Drop FK constraints
    op.drop_constraint("fk_defect_detail_exchange_product", "Defect_Details", type_="foreignkey")
    op.drop_constraint("fk_defect_detail_deleted_by", "Defect_Details", type_="foreignkey")

    # Drop new columns
    for col in ["origin", "status", "customer_compensation", "supplier_compensation",
                "exchange_product_id", "price_difference", "rejection_note",
                "is_deleted", "deleted_by", "deleted_at"]:
        op.drop_column("Defect_Details", col)