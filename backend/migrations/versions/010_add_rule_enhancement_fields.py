"""add_rule_enhancement_fields

Revision ID: 010_add_rule_enhancement_fields
Revises: d8163352b057
Create Date: 2025-01-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "010_add_rule_enhancement_fields"
down_revision: str | None = "d8163352b057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add enhanced fields to rules table for better detector configuration."""
    # Add target_fields for field scoping (keyword and regex detectors)
    op.add_column("rules", sa.Column("target_fields", sa.JSON(), nullable=True))
    
    # Add match_options for keyword matching configuration
    op.add_column("rules", sa.Column("match_options", sa.JSON(), nullable=True))
    
    # Add behavioral_params for behavioral detector parameters
    op.add_column("rules", sa.Column("behavioral_params", sa.JSON(), nullable=True))
    
    # Add media_params for media detector parameters
    op.add_column("rules", sa.Column("media_params", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Remove enhanced fields from rules table."""
    op.drop_column("rules", "media_params")
    op.drop_column("rules", "behavioral_params")
    op.drop_column("rules", "match_options")
    op.drop_column("rules", "target_fields")
