import os

from app.db import Base
from sqlalchemy import JSON, TIMESTAMP, BigInteger, Boolean, Column, ForeignKey, Integer, Numeric, Text
from sqlalchemy import Enum as sa_Enum
from sqlalchemy.sql import func


def get_id_column():
    """Get appropriate ID column type based on database URL."""
    database_url = os.environ.get("DATABASE_URL", "")
    if "sqlite" in database_url:
        return Column(Integer, primary_key=True, autoincrement=True)
    else:
        return Column(BigInteger, primary_key=True, autoincrement=True)


def get_id_fk_column(table_name):
    """Get appropriate foreign key column type based on database URL."""
    database_url = os.environ.get("DATABASE_URL", "")
    if "sqlite" in database_url:
        return Column(Integer, ForeignKey(f"{table_name}.id"), nullable=True)
    else:
        return Column(BigInteger, ForeignKey(f"{table_name}.id"), nullable=True)


class Account(Base):
    __tablename__ = "accounts"
    id = get_id_column()
    mastodon_account_id = Column(Text, unique=True, nullable=False)
    acct = Column(Text, nullable=False)
    domain = Column(Text, nullable=False)
    last_checked_at = Column(TIMESTAMP(timezone=True))
    last_status_seen_id = Column(Text)
    # fields for better scanning management
    scan_cursor_position = Column(Text)  # Tracks position in status scanning
    last_full_scan_at = Column(TIMESTAMP(timezone=True))  # When we last did a complete scan
    content_hash = Column(Text)  # Hash of account metadata to detect changes


class Analysis(Base):
    __tablename__ = "analyses"
    id = get_id_column()
    mastodon_account_id = Column(Text, nullable=False)
    status_id = Column(Text)
    rule_key = Column(Text, nullable=False)
    score = Column(Numeric, nullable=False)
    evidence = Column(JSON, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class Report(Base):
    __tablename__ = "reports"
    id = get_id_column()
    mastodon_account_id = Column(Text, nullable=False)
    status_id = Column(Text)
    mastodon_report_id = Column(Text)
    dedupe_key = Column(Text, unique=True, nullable=False)
    comment = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class Config(Base):
    __tablename__ = "config"
    key = Column(Text, primary_key=True)
    value = Column(JSON, nullable=False)
    updated_by = Column(Text)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())


class Cursor(Base):
    __tablename__ = "cursors"
    name = Column(Text, primary_key=True)
    position = Column(Text, nullable=True)  # NULL position means start from beginning
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())


class Rule(Base):
    __tablename__ = "rules"
    id = get_id_column()
    name = Column(Text, nullable=False)
    # Change rule_type to detector_type
    detector_type = Column(Text, nullable=False)  # e.g., 'regex', 'keyword', 'behavioral'
    pattern = Column(Text, nullable=False)
    boolean_operator = Column(
        sa_Enum("AND", "OR", name="boolean_operator_enum", create_type=False),
        nullable=True,
    )
    secondary_pattern = Column(Text, nullable=True)
    weight = Column(Numeric, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    # New columns for action types and duration
    action_type = Column(
        sa_Enum(
            "report",
            "silence",
            "suspend",
            "disable",
            "sensitive",
            "domain_block",
            name="action_type_enum",
            create_type=False,
        ),
        nullable=False,
    )
    action_duration_seconds = Column(Integer, nullable=True)
    action_warning_text = Column(Text, nullable=True)
    warning_preset_id = Column(Text, nullable=True)
    trigger_threshold = Column(Numeric, nullable=False, default=1.0)
    # Enhanced detector configuration fields
    target_fields = Column(JSON, nullable=True)  # ['username', 'display_name', 'bio', 'content'] for scoping
    match_options = Column(JSON, nullable=True)  # {'case_sensitive': bool, 'word_boundaries': bool, etc}
    behavioral_params = Column(JSON, nullable=True)  # {'time_window_hours': int, 'threshold': int, etc}
    media_params = Column(JSON, nullable=True)  # {'require_alt_text': bool, 'allowed_mime_types': [], etc}
    # metadata fields
    trigger_count = Column(Integer, nullable=False, default=0)  # Number of times rule has been triggered
    last_triggered_at = Column(TIMESTAMP(timezone=True))  # When rule was last triggered
    last_triggered_content = Column(JSON)  # Content that last triggered the rule
    created_by = Column(Text, default="system")  # User who created the rule
    updated_by = Column(Text)  # User who last updated the rule
    description = Column(Text)  # Description/notes about the rule
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())


class DomainAlert(Base):
    """Track domain-level violations and defederation thresholds"""

    __tablename__ = "domain_alerts"
    id = get_id_column()
    domain = Column(Text, nullable=False, unique=True)
    violation_count = Column(Integer, nullable=False, default=0)
    last_violation_at = Column(TIMESTAMP(timezone=True))
    defederation_threshold = Column(Integer, nullable=False, default=10)  # Configurable threshold
    is_defederated = Column(Boolean, nullable=False, default=False)
    defederated_at = Column(TIMESTAMP(timezone=True))
    defederated_by = Column(Text)
    notes = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())


class ScanSession(Base):
    """Track scanning sessions and progress across multiple users/accounts"""

    __tablename__ = "scan_sessions"
    id = get_id_column()
    session_type = Column(Text, nullable=False)  # 'local', 'remote', 'federated'
    status = Column(Text, nullable=False, default="active")  # 'active', 'completed', 'paused', 'failed'
    accounts_processed = Column(Integer, nullable=False, default=0)
    total_accounts = Column(Integer)  # Estimated total if known
    current_cursor = Column(Text)  # Current position in the scan
    last_account_id = Column(Text)  # Last processed account ID
    rules_applied = Column(JSON)  # Rules that were active during this session
    started_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    completed_at = Column(TIMESTAMP(timezone=True))
    session_metadata = Column(JSON)  # Additional session metadata (renamed from metadata)


class ContentScan(Base):
    """Track individual content scans to prevent re-processing"""

    __tablename__ = "content_scans"
    id = get_id_column()
    content_hash = Column(Text, nullable=False, unique=True)  # Hash of content being scanned
    mastodon_account_id = Column(Text, nullable=False)
    status_id = Column(Text)  # Optional status ID if scanning specific posts
    scan_type = Column(Text, nullable=False)  # 'account', 'status', 'profile'
    last_scanned_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    scan_result = Column(JSON)  # Store scan results for caching
    rules_version = Column(Text)  # Rules version hash when scanned
    needs_rescan = Column(Boolean, nullable=False, default=False)  # Flag for content that needs re-scanning


class ScheduledAction(Base):
    __tablename__ = "scheduled_actions"
    id = get_id_column()
    mastodon_account_id = Column(Text, index=True, nullable=False)
    action_to_reverse = Column(
        sa_Enum(
            "report",
            "silence",
            "suspend",
            "disable",
            "sensitive",
            "domain_block",
            name="action_type_enum",
            create_type=False,
        ),
        nullable=False,
    )
    expires_at = Column(TIMESTAMP(timezone=True), index=True, nullable=False)


class InteractionHistory(Base):
    __tablename__ = "interaction_history"
    id = get_id_column()
    source_account_id = Column(Text, nullable=False)
    target_account_id = Column(Text, nullable=False)
    status_id = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class AccountBehaviorMetrics(Base):
    __tablename__ = "account_behavior_metrics"
    id = get_id_column()
    mastodon_account_id = Column(Text, unique=True, nullable=False)
    posts_last_1h = Column(Integer, default=0)
    posts_last_24h = Column(Integer, default=0)
    last_sampled_status_id = Column(Text)
    last_calculated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = get_id_column()
    action_type = Column(Text, nullable=False)
    triggered_by_rule_id = get_id_fk_column("rules")
    target_account_id = Column(Text, nullable=False)
    timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now())
    evidence = Column(JSON)
    api_response = Column(JSON)
