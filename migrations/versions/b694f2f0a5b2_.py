"""empty message

Revision ID: b694f2f0a5b2
Revises: 03861e8301e2
Create Date: 2026-04-11 23:06:58.542732

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b694f2f0a5b2'
down_revision = '03861e8301e2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('Stock_In', schema=None) as batch_op:
        batch_op.add_column(sa.Column('batch_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_Stock_In_batch_id', ['batch_id'], unique=False)


def downgrade():
    with op.batch_alter_table('Stock_In', schema=None) as batch_op:
        batch_op.drop_index('ix_Stock_In_batch_id')
        batch_op.drop_column('batch_id')