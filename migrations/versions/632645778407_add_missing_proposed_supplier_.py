"""add missing proposed_supplier_compensation column

Revision ID: 632645778407
Revises: redesign_defect_detail
Create Date: 2026-04-06 05:03:34.056078

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '632645778407'
down_revision = 'redesign_defect_detail'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'Defect_Details',
        sa.Column('proposed_supplier_compensation', sa.String(length=50), nullable=True)
    )

def downgrade():
    op.drop_column('Defect_Details', 'proposed_supplier_compensation')
