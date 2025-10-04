"""allow null cursor position

Revision ID: 009_allow_null_cursor
Revises: 008_add_boolean_operator_and_secondary_pattern
Create Date: 2025-10-04

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '009_allow_null_cursor'
down_revision = '008_add_boolean_operator_and_secondary_pattern'
branch_labels = None
depends_on = None


def upgrade():
    # Allow NULL values in cursors.position
    # This allows cursors to start from the beginning when position is NULL
    op.alter_column('cursors', 'position',
               existing_type=sa.Text(),
               nullable=True)


def downgrade():
    # Revert to NOT NULL (will fail if NULL values exist)
    op.alter_column('cursors', 'position',
               existing_type=sa.Text(),
               nullable=False)
