"""Create maintenance model

Revision ID: 1b3045f8bc08
Revises: 05666bc78729
Create Date: 2026-04-21 01:45:54.102847

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1b3045f8bc08'
down_revision = '05666bc78729'
branch_labels = None
depends_on = None



def upgrade():
    op.create_table(
        'maintenance_settings',
        sa.Column('id',               sa.Integer(),   nullable=False, autoincrement=True),
        sa.Column('is_active',        sa.Boolean(),   nullable=False, server_default=sa.text('0')),
        sa.Column('scheduled_start',  sa.DateTime(),  nullable=True),
        sa.Column('estimated_end',    sa.DateTime(),  nullable=True),
        sa.Column('show_countdown',   sa.Boolean(),   nullable=False, server_default=sa.text('1')),
        sa.Column('message',          sa.Text(),      nullable=True),
        sa.Column('updated_at',       sa.DateTime(),  nullable=True,
                  server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )

    # Seed one default row so MaintenanceSettings.get() always finds a record
    op.execute("""
        INSERT INTO maintenance_settings
            (is_active, scheduled_start, estimated_end, show_countdown, message, updated_at)
        VALUES
            (0, NULL, NULL, 1, 'We are performing scheduled maintenance. Be right back!', NOW())
    """)


def downgrade():
    op.drop_table('maintenance_settings')
