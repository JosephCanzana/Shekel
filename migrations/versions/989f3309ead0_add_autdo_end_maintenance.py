"""add autdo end maintenance

Revision ID: 989f3309ead0
Revises: 1b3045f8bc08
Create Date: 2026-04-21 02:40:16.521475

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '989f3309ead0'
down_revision = '1b3045f8bc08'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('maintenance_settings',
        sa.Column('auto_end', sa.Boolean(), nullable=False, server_default=sa.text('1'))
    )

def downgrade():
    op.drop_column('maintenance_settings', 'auto_end')

    # ### end Alembic commands ###
