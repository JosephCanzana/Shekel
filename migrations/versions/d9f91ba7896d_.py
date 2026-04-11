"""empty message

Revision ID: d9f91ba7896d
Revises: 03861e8301e2
Create Date: 2026-04-11 23:14:56.880480

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd9f91ba7896d'
down_revision = '03861e8301e2'
branch_labels = None
depends_on = None




def upgrade():
    with op.batch_alter_table('Stock_In', schema=None) as batch_op:
        batch_op.drop_index('ix_Stock_In_batch_id')  # drop old one
        batch_op.alter_column(
            'batch_id',
            existing_type=sa.String(length=36),
            type_=sa.Integer(),
            nullable=True
        )
        batch_op.create_index('ix_Stock_In_batch_id', ['batch_id'], unique=False)


def downgrade():
    with op.batch_alter_table('Stock_In', schema=None) as batch_op:
        batch_op.alter_column(
            'batch_id',
            existing_type=sa.Integer(),
            type_=sa.String(length=36),
            nullable=True
        )