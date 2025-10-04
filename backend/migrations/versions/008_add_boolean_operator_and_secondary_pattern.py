"""add_boolean_operator_and_secondary_pattern

Revision ID: 008_add_boolean_operator
Revises: d8163352b057
Create Date: 2025-10-04 17:33:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008_add_boolean_operator"
down_revision: str | None = "d8163352b057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create enum type if it doesn't exist
    op.execute("CREATE TYPE boolean_operator_enum AS ENUM ('AND', 'OR')")

    # Add boolean_operator column
    op.add_column("rules", sa.Column("boolean_operator", sa.Enum("AND", "OR", name="boolean_operator_enum", create_type=False), nullable=True))

    # Add secondary_pattern column
    op.add_column("rules", sa.Column("secondary_pattern", sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove columns
    op.drop_column("rules", "secondary_pattern")
    op.drop_column("rules", "boolean_operator")

    # Drop enum type
    op.execute("DROP TYPE boolean_operator_enum")
