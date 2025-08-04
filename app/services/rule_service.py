import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

from app.db import SessionLocal
from app.models import Rule
from app.schemas import Violation
from app.services.detectors.behavioral_detector import BehavioralDetector
from app.services.detectors.keyword_detector import KeywordDetector
from app.services.detectors.regex_detector import RegexDetector

logger = logging.getLogger(__name__)


@dataclass
class RuleCache:
    """In-memory cache for rules to avoid frequent database hits"""

    rules: list[Rule]
    config: dict[str, Any]
    ruleset_sha256: str
    cached_at: datetime
    ttl_seconds: int = 60  # Cache for 60 seconds

    def is_expired(self) -> bool:
        """Check if the cache has expired"""
        return datetime.utcnow() - self.cached_at > timedelta(seconds=self.ttl_seconds)


class RuleService:
    """Centralized service for rule management and database operations.

    This service provides:
    - Database-only rule loading (no file dependencies)
    - Caching to reduce database load during scanning
    - CRUD operations for rule management
    - Rule statistics and metadata tracking
    """

    def __init__(self, cache_ttl_seconds: int = 60):
        self._cache: RuleCache | None = None
        self._cache_ttl = cache_ttl_seconds
        self.detectors = {
            "regex": RegexDetector(),
            "keyword": KeywordDetector(),
            "behavioral": BehavioralDetector(),
        }

    def get_active_rules(self, force_refresh: bool = False) -> tuple[list[Rule], dict[str, Any], str]:
        """Get active rules from database with caching.

        Args:
            force_refresh: If True, bypass cache and reload from database

        Returns:
            Tuple of (rules_list, config_dict, ruleset_sha256)

        """
        if not force_refresh and self._cache and not self._cache.is_expired():
            return self._cache.rules, self._cache.config, self._cache.ruleset_sha256

        return self._load_rules_from_database()

    def _load_rules_from_database(self) -> tuple[list[Rule], dict[str, Any], str]:
        """Load rules from database and update cache"""
        with SessionLocal() as session:
            # Get all enabled rules
            db_rules = session.query(Rule).filter(Rule.enabled.is_(True)).all()

            # Create a hash from all the rule data for versioning
            rule_data = []
            for rule in db_rules:
                rule_data.append(
                    f"{rule.id}:{rule.pattern}:{rule.weight}:{rule.enabled}:"
                    f"{rule.detector_type}:{rule.action_type}:{rule.trigger_threshold}"
                )

            ruleset_content = "|".join(sorted(rule_data))
            ruleset_sha256 = hashlib.sha256(ruleset_content.encode()).hexdigest()

            # Get report threshold from database config or use default
            config_row = session.execute(text("SELECT value FROM config WHERE key='report_threshold'")).scalar()

            if config_row and isinstance(config_row, dict):
                report_threshold = config_row.get("threshold", 1.0)
            else:
                report_threshold = 1.0

            config = {"report_threshold": report_threshold}

            # Update cache
            self._cache = RuleCache(
                rules=db_rules,
                config=config,
                ruleset_sha256=ruleset_sha256,
                cached_at=datetime.utcnow(),
                ttl_seconds=self._cache_ttl,
            )

            logger.debug(f"Loaded {len(db_rules)} rules from database, SHA: {ruleset_sha256[:8]}")

            return db_rules, config, ruleset_sha256

    def create_rule(
        self,
        name: str,
        detector_type: str,
        pattern: str,
        weight: float,
        action_type: str,
        trigger_threshold: float,
        action_duration_seconds: int | None = None,
        action_warning_text: str | None = None,
        warning_preset_id: str | None = None,
        enabled: bool = True,
        description: str | None = None,
        created_by: str = "system",
    ) -> Rule:
        """Create a new rule in the database.

        Args:
            name: Human-readable name for the rule
            detector_type: Type of detector (regex, keyword, behavioral)
            pattern: Pattern for the rule
            weight: Weight/score assigned when rule matches
            action_type: Type of action to take (report, silence, suspend, etc.)
            trigger_threshold: Score threshold to trigger the rule
            action_duration_seconds: Duration for timed actions
            action_warning_text: Warning text for the action
            warning_preset_id: Preset ID for warnings
            enabled: Whether the rule is active
            description: Optional description of the rule
            created_by: User/system that created the rule

        Returns:
            The created Rule object

        """
        with SessionLocal() as session:
            rule = Rule(
                name=name,
                detector_type=detector_type,
                pattern=pattern,
                weight=weight,
                action_type=action_type,
                trigger_threshold=trigger_threshold,
                action_duration_seconds=action_duration_seconds,
                action_warning_text=action_warning_text,
                warning_preset_id=warning_preset_id,
                enabled=enabled,
                description=description,
                created_by=created_by,
                created_at=datetime.utcnow(),
            )

            session.add(rule)
            session.commit()
            session.refresh(rule)

            # Invalidate cache since rules changed
            self._invalidate_cache()

            logger.info(f"Created new rule: {name} (type: {detector_type}, weight: {weight})")
            return rule

    def update_rule(self, rule_id: int, **updates) -> Rule | None:
        """Update an existing rule.

        Args:
            rule_id: ID of the rule to update
            **updates: Dictionary of fields to update

        Returns:
            Updated Rule object or None if not found

        """
        with SessionLocal() as session:
            rule = session.query(Rule).filter(Rule.id == rule_id).first()
            if not rule:
                return None

            # Update provided fields
            for field, value in updates.items():
                if hasattr(rule, field):
                    setattr(rule, field, value)

            rule.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(rule)

            # Invalidate cache since rules changed
            self._invalidate_cache()

            logger.info(f"Updated rule {rule_id}: {list(updates.keys())}")
            return rule

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a rule from the database.

        Args:
            rule_id: ID of the rule to delete

        Returns:
            True if rule was deleted, False if not found

        """
        with SessionLocal() as session:
            rule = session.query(Rule).filter(Rule.id == rule_id).first()
            if not rule:
                return False

            session.delete(rule)
            session.commit()

            # Invalidate cache since rules changed
            self._invalidate_cache()

            logger.info(f"Deleted rule {rule_id}: {rule.name}")
            return True

    def toggle_rule(self, rule_id: int, enabled: bool) -> Rule | None:
        """Enable or disable a rule.

        Args:
            rule_id: ID of the rule to toggle
            enabled: New enabled state

        Returns:
            Updated Rule object or None if not found

        """
        return self.update_rule(rule_id, enabled=enabled)

    def bulk_toggle_rules(self, rule_ids: list[int], enabled: bool) -> list[Rule]:
        """Enable or disable multiple rules at once.

        Args:
            rule_ids: List of rule IDs to toggle
            enabled: New enabled state for all rules

        Returns:
            List of updated Rule objects

        """
        updated_rules = []
        with SessionLocal() as session:
            rules = session.query(Rule).filter(Rule.id.in_(rule_ids)).all()

            for rule in rules:
                rule.enabled = enabled
                rule.updated_at = datetime.utcnow()
                updated_rules.append(rule)

            session.commit()

            # Invalidate cache since rules changed
            self._invalidate_cache()

            logger.info(f"Bulk toggled {len(updated_rules)} rules to enabled={enabled}")
            return updated_rules

    def get_rule_by_id(self, rule_id: int) -> Rule | None:
        """Get a rule by its ID.

        Args:
            rule_id: ID of the rule to retrieve

        Returns:
            Rule object or None if not found

        """
        with SessionLocal() as session:
            return session.query(Rule).filter(Rule.id == rule_id).first()

    def get_rule_statistics(self) -> dict[str, Any]:
        """Get statistics about rules usage and performance.

        Returns:
            Dictionary containing rule statistics

        """
        with SessionLocal() as session:
            total_rules = session.query(Rule).count()
            enabled_rules = session.query(Rule).filter(Rule.enabled.is_(True)).count()

            return {
                "total_rules": total_rules,
                "enabled_rules": enabled_rules,
                "disabled_rules": total_rules - enabled_rules,
                "cache_status": self.get_cache_status(),
            }

    def evaluate_account(self, account_data: dict[str, Any], statuses: list[dict[str, Any]]) -> list[Violation]:
        """Evaluates an account and its statuses against all active rules."""

        all_violations: list[Violation] = []
        active_rules, _, _ = self.get_active_rules()

        for rule in active_rules:
            detector = self.detectors.get(rule.detector_type)
            if not detector:
                logger.warning(f"No detector found for type: {rule.detector_type}")
                continue

            violations_from_detector = detector.evaluate(rule, account_data, statuses)
            for violation in violations_from_detector:
                if violation.score >= rule.trigger_threshold:
                    all_violations.append(violation)

        return all_violations

    def get_config_value(self, key: str, default: Any | None = None) -> Any:
        _, config, _ = self.get_active_rules()
        return config.get(key, default)

    @property
    def ruleset_sha256(self) -> str | None:
        if self._cache:
            return self._cache.ruleset_sha256
        return None

    def invalidate_cache(self):
        """Force cache invalidation to refresh rules on next access"""
        self._invalidate_cache()

    def _invalidate_cache(self):
        """Internal method to invalidate the cache"""
        self._cache = None
        logger.debug("Rule cache invalidated")

    def get_cache_status(self) -> dict[str, Any]:
        """Get current cache status information.

        Returns:
            Dictionary with cache status details

        """
        if not self._cache:
            return {
                "cached": False,
                "expired": True,
                "cached_at": None,
                "ttl_seconds": self._cache_ttl,
                "rules_count": 0,
            }

        return {
            "cached": True,
            "expired": self._cache.is_expired(),
            "cached_at": self._cache.cached_at.isoformat(),
            "ttl_seconds": self._cache_ttl,
            "rules_count": len(self._cache.rules),
            "ruleset_sha256": self._cache.ruleset_sha256[:8],
        }


# Global instance for use throughout the application
rule_service = RuleService()
