"""add tendered and change amount to sales

Revision ID: 05666bc78729
Revises: 55c4f7c818b1
Create Date: 2026-04-20 01:06:16.647544

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '05666bc78729'
down_revision = '55c4f7c818b1'
branch_labels = None
depends_on = None



def upgrade():
    # Only add columns if they don't already exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("Sales")]

    if "tendered_amount" not in existing_columns:
        op.add_column("Sales", sa.Column("tendered_amount", sa.Numeric(10, 2), nullable=True))

    if "change_amount" not in existing_columns:
        op.add_column("Sales", sa.Column("change_amount", sa.Numeric(10, 2), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("Sales")]

    if "change_amount" in existing_columns:
        op.drop_column("Sales", "change_amount")

    if "tendered_amount" in existing_columns:
        op.drop_column("Sales", "tendered_amount")
