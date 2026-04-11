"""Add batch id to stock-in

Revision ID: 03861e8301e2
Revises: cbb096346baf
Create Date: 2026-04-11 15:11:49.158420

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '03861e8301e2'
down_revision = 'cbb096346baf'
branch_labels = None
depends_on = None


def upgrade():
    # REMOVED the Defect_Exchange_Items block entirely — those indexes
    # can't be dropped while foreign key constraints reference them,
    # and they're unrelated to this migration.

    with op.batch_alter_table('Sales_Details', schema=None) as batch_op:
        batch_op.alter_column('override_used',
            existing_type=mysql.SMALLINT(),
            type_=sa.Boolean(),
            comment=None,
            existing_comment='1 when this specific line item quantity exceeded quantity_available at charge time. Does not block the sale.',
            existing_nullable=False,
            existing_server_default=sa.text("'0'"))

    with op.batch_alter_table('Stock_In', schema=None) as batch_op:
        batch_op.add_column(sa.Column('batch_id', sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f('ix_Stock_In_batch_id'), ['batch_id'], unique=False)


def downgrade():
    with op.batch_alter_table('Stock_In', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_Stock_In_batch_id'))
        batch_op.drop_column('batch_id')

    with op.batch_alter_table('Sales_Details', schema=None) as batch_op:
        batch_op.alter_column('override_used',
            existing_type=sa.Boolean(),
            type_=mysql.SMALLINT(),
            comment='1 when this specific line item quantity exceeded quantity_available at charge time. Does not block the sale.',
            existing_nullable=False,
            existing_server_default=sa.text("'0'"))

    # REMOVED the Defect_Exchange_Items index recreation too