"""scanning system

Revision ID: 006_scanning_system
Revises: 005_add_rule_model
Create Date: 2025-01-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "006_scanning_system"
down_revision = "005_add_rule_model"
branch_labels = None
depends_on = None


def upgrade():
    # Enhance accounts table
    op.add_column("accounts", sa.Column("scan_cursor_position", sa.Text(), nullable=True))
    op.add_column("accounts", sa.Column("last_full_scan_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("accounts", sa.Column("content_hash", sa.Text(), nullable=True))

    # Enhance rules table
    op.add_column("rules", sa.Column("trigger_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("rules", sa.Column("last_triggered_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("rules", sa.Column("last_triggered_content", sa.JSON(), nullable=True))
    op.add_column("rules", sa.Column("created_by", sa.Text(), nullable=True, server_default="system"))
    op.add_column("rules", sa.Column("updated_by", sa.Text(), nullable=True))
    op.add_column("rules", sa.Column("description", sa.Text(), nullable=True))

    # Create domain_alerts table
    op.create_table(
        "domain_alerts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("violation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_violation_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("defederation_threshold", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("is_defederated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("defederated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("defederated_by", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain"),
    )

    # Create scan_sessions table
    op.create_table(
        "scan_sessions",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("session_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("accounts_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_accounts", sa.Integer(), nullable=True),
        sa.Column("current_cursor", sa.Text(), nullable=True),
        sa.Column("last_account_id", sa.Text(), nullable=True),
        sa.Column("rules_applied", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("session_metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create content_scans table
    op.create_table(
        "content_scans",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("mastodon_account_id", sa.Text(), nullable=False),
        sa.Column("status_id", sa.Text(), nullable=True),
        sa.Column("scan_type", sa.Text(), nullable=False),
        sa.Column("last_scanned_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("scan_result", sa.JSON(), nullable=True),
        sa.Column("rules_version", sa.Text(), nullable=True),
        sa.Column("needs_rescan", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_hash"),
    )

    # Create indexes for performance
    op.create_index("ix_accounts_content_hash", "accounts", ["content_hash"])
    # ix_accounts_domain already exists, skip it
    op.create_index("ix_accounts_last_full_scan_at", "accounts", ["last_full_scan_at"])

    op.create_index("ix_rules_trigger_count", "rules", ["trigger_count"])
    op.create_index("ix_rules_last_triggered_at", "rules", ["last_triggered_at"])

    op.create_index("ix_domain_alerts_domain", "domain_alerts", ["domain"])
    op.create_index("ix_domain_alerts_is_defederated", "domain_alerts", ["is_defederated"])
    op.create_index("ix_domain_alerts_violation_count", "domain_alerts", ["violation_count"])

    op.create_index("ix_scan_sessions_session_type", "scan_sessions", ["session_type"])
    op.create_index("ix_scan_sessions_status", "scan_sessions", ["status"])
    op.create_index("ix_scan_sessions_started_at", "scan_sessions", ["started_at"])

    op.create_index("ix_content_scans_mastodon_account_id", "content_scans", ["mastodon_account_id"])
    op.create_index("ix_content_scans_scan_type", "content_scans", ["scan_type"])
    op.create_index("ix_content_scans_last_scanned_at", "content_scans", ["last_scanned_at"])
    op.create_index("ix_content_scans_needs_rescan", "content_scans", ["needs_rescan"])


def downgrade():
    # Drop indexes
    op.drop_index("ix_content_scans_needs_rescan", "content_scans")
    op.drop_index("ix_content_scans_last_scanned_at", "content_scans")
    op.drop_index("ix_content_scans_scan_type", "content_scans")
    op.drop_index("ix_content_scans_mastodon_account_id", "content_scans")

    op.drop_index("ix_scan_sessions_started_at", "scan_sessions")
    op.drop_index("ix_scan_sessions_status", "scan_sessions")
    op.drop_index("ix_scan_sessions_session_type", "scan_sessions")

    op.drop_index("ix_domain_alerts_violation_count", "domain_alerts")
    op.drop_index("ix_domain_alerts_is_defederated", "domain_alerts")
    op.drop_index("ix_domain_alerts_domain", "domain_alerts")

    op.drop_index("ix_rules_last_triggered_at", "rules")
    op.drop_index("ix_rules_trigger_count", "rules")

    op.drop_index("ix_accounts_last_full_scan_at", "accounts")
    # ix_accounts_domain was pre-existing, don't drop it
    op.drop_index("ix_accounts_content_hash", "accounts")

    # Drop tables
    op.drop_table("content_scans")
    op.drop_table("scan_sessions")
    op.drop_table("domain_alerts")

    # Remove columns from rules table
    op.drop_column("rules", "description")
    op.drop_column("rules", "updated_by")
    op.drop_column("rules", "created_by")
    op.drop_column("rules", "last_triggered_content")
    op.drop_column("rules", "last_triggered_at")
    op.drop_column("rules", "trigger_count")

    # Remove columns from accounts table
    op.drop_column("accounts", "content_hash")
    op.drop_column("accounts", "last_full_scan_at")
    op.drop_column("accounts", "scan_cursor_position")
