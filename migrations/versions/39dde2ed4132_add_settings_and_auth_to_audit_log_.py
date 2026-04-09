"""add Settings and Auth to audit_log module enum

Revision ID: 39dde2ed4132
Revises: f5478b0b5e5c
Create Date: 2026-04-09 06:07:24.750774

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '39dde2ed4132'
down_revision = 'f5478b0b5e5c'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
        ALTER TABLE `Audit_Log`
        MODIFY COLUMN `module`
        ENUM('Products','Inventory','Sales','Defects','Users','Stock_In','Settings','Auth')
        NOT NULL
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE `Audit_Log`
        MODIFY COLUMN `module`
        ENUM('Products','Inventory','Sales','Defects','Users','Stock_In')
        NOT NULL
    """)