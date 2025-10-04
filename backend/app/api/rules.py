"""Rules API router for managing moderation rules."""

import logging
import re
from typing import Any

from app.db import get_db
from app.models import Analysis, Rule
from app.oauth import User, require_admin_hybrid
from app.scanning import ScanningSystem
from app.services.rule_service import rule_service
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter()

# Constants
MAX_RULE_WEIGHT = 5.0


@router.get("/rules/current", tags=["rules"])
def get_current_rules(user: User = Depends(require_admin_hybrid)):
    """Get current rule configuration including database rules."""
    rules_list, config, _ = rule_service.get_active_rules()

    # Convert rules list to dictionary format for backwards compatibility
    rules_dict = {}
    for rule in rules_list:
        rules_dict[rule.name] = {
            "id": rule.id,
            "detector_type": rule.detector_type,
            "pattern": rule.pattern,
            "weight": rule.weight,
            "enabled": rule.enabled,
            "action_type": rule.action_type,
            "trigger_threshold": rule.trigger_threshold,
        }

    return {
        "rules": {**rules_dict, "report_threshold": config.get("report_threshold", 1.0)},
        "report_threshold": config.get("report_threshold", 1.0),
    }


@router.get("/rules", tags=["rules"])
def list_rules(user: User = Depends(require_admin_hybrid), session: Session = Depends(get_db)):
    """List all rules (both enabled and disabled)."""
    # Get ALL rules for the admin interface, not just active ones
    all_rules = session.query(Rule).order_by(Rule.created_at.desc()).all()
    response = []

    # Convert rules to flat list for easier frontend consumption
    for rule in all_rules:
        response.append(
            {
                "id": rule.id,
                "name": rule.name,
                "detector_type": rule.detector_type,
                "pattern": rule.pattern,
                "boolean_operator": rule.boolean_operator,
                "secondary_pattern": rule.secondary_pattern,
                "weight": rule.weight,
                "enabled": rule.enabled,
                "action_type": rule.action_type,
                "action_duration_seconds": rule.action_duration_seconds,
                "action_warning_text": rule.action_warning_text,
                "warning_preset_id": rule.warning_preset_id,
                "trigger_threshold": rule.trigger_threshold,
                "trigger_count": rule.trigger_count,
                "last_triggered_at": rule.last_triggered_at.isoformat() if rule.last_triggered_at else None,
                "last_triggered_content": rule.last_triggered_content,
                "created_by": rule.created_by,
                "updated_by": rule.updated_by,
                "description": rule.description,
                "created_at": rule.created_at.isoformat() if rule.created_at else None,
                "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
                "rule_type": rule.detector_type,  # For backwards compatibility
            }
        )

    return {"rules": response}


@router.post("/rules", tags=["rules"])
def create_rule(
    rule_data: dict[str, Any], user: User = Depends(require_admin_hybrid), session: Session = Depends(get_db)
):
    """Create a new rule."""
    try:
        # Validate required fields
        required_fields = ["name", "detector_type", "pattern", "weight", "action_type", "trigger_threshold"]
        for field in required_fields:
            if field not in rule_data:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": f"Missing required field: {field}",
                        "required_fields": required_fields,
                        "help": "Use GET /rules/help for examples and guidance",
                    },
                )

        valid_detector_types = ["regex", "keyword", "behavioral", "media"]
        if rule_data["detector_type"] not in valid_detector_types:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": f"Invalid detector_type: {rule_data['detector_type']}",
                    "valid_types": valid_detector_types,
                    "help": "Use GET /rules/help to see examples for each rule type",
                },
            )

        boolean_operator = rule_data.get("boolean_operator")
        secondary_pattern = rule_data.get("secondary_pattern")
        if boolean_operator and boolean_operator not in ["AND", "OR"]:
            raise HTTPException(status_code=400, detail="boolean_operator must be AND or OR")
        if (boolean_operator and not secondary_pattern) or (secondary_pattern and not boolean_operator):
            raise HTTPException(
                status_code=400, detail="boolean_operator and secondary_pattern must be provided together"
            )

        # Validate weight
        try:
            weight = float(rule_data["weight"])
            if weight < 0 or weight > MAX_RULE_WEIGHT:
                raise ValueError("Weight must be between 0 and 5.0")
        except (ValueError, TypeError) as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": f"Invalid weight: {str(e)}",
                    "guidelines": (
                        "Weight should be 0.1-0.3 (mild), 0.4-0.6 (moderate), 0.7-0.9 (strong), 1.0+ (very strong)"
                    ),
                    "help": "Use GET /rules/help for weight guidelines and examples",
                },
            ) from e

        # Test regex pattern if detector_type is regex
        if rule_data["detector_type"] == "regex":
            try:
                re.compile(rule_data["pattern"])
                if secondary_pattern:
                    re.compile(secondary_pattern)
            except re.error as e:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": f"Invalid regex pattern: {str(e)}",
                        "pattern": rule_data["pattern"],
                        "detector_type": rule_data["detector_type"],
                        "suggestions": [
                            "Check for unescaped special characters",
                            "Ensure balanced parentheses and brackets",
                            "Test on regex101.com first",
                        ],
                    },
                ) from e

        # Create rule
        new_rule = rule_service.create_rule(
            name=rule_data["name"],
            detector_type=rule_data["detector_type"],
            pattern=rule_data["pattern"],
            boolean_operator=boolean_operator,
            secondary_pattern=secondary_pattern,
            weight=rule_data["weight"],
            action_type=rule_data["action_type"],
            trigger_threshold=rule_data["trigger_threshold"],
            action_duration_seconds=rule_data.get("action_duration_seconds"),
            action_warning_text=rule_data.get("action_warning_text"),
            warning_preset_id=rule_data.get("warning_preset_id"),
            enabled=rule_data.get("enabled", True),
            description=rule_data.get("description"),
            created_by=user.username if user else "system",
        )

        return new_rule

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error("Failed to create rule", extra={"error": str(e), "rule_data": rule_data})
        raise HTTPException(status_code=500, detail="Failed to create rule") from e


@router.get("/rules/help", tags=["rules"])
def get_rule_creation_help():
    """Get comprehensive help text and examples for creating rules."""
    return {
        "rule_types": {
            "regex": {
                "description": "Matches against text content using regular expressions.",
                "fields": [
                    "pattern",
                    "boolean_operator",
                    "secondary_pattern",
                    "weight",
                    "action_type",
                    "trigger_threshold",
                    "description",
                ],
                "examples": [
                    {
                        "name": "Spam URL Regex",
                        "detector_type": "regex",
                        "pattern": r"https?://[a-zA-Z0-9.-]+\\.(tk|ml|ga|cf|gq)/",
                        "weight": 1.5,
                        "action_type": "report",
                        "trigger_threshold": 1.0,
                        "description": "Detects common spam URLs using free domains.",
                    }
                ],
            },
            "keyword": {
                "description": "Matches against text content for specific keywords.",
                "fields": [
                    "pattern (comma-separated keywords)",
                    "boolean_operator",
                    "secondary_pattern",
                    "weight",
                    "action_type",
                    "trigger_threshold",
                    "target_field (username, display_name, content)",
                    "description",
                ],
                "examples": [
                    {
                        "name": "Crypto Keywords",
                        "detector_type": "keyword",
                        "pattern": "bitcoin, crypto, nft, blockchain",
                        "weight": 0.8,
                        "action_type": "silence",
                        "trigger_threshold": 1.0,
                        "target_field": "content",
                        "description": "Detects cryptocurrency related keywords in posts.",
                    }
                ],
            },
            "behavioral": {
                "description": "Matches against account behavior metrics.",
                "fields": [
                    "pattern (behavior type, e.g., 'rapid_posting')",
                    "boolean_operator",
                    "secondary_pattern",
                    "weight",
                    "action_type",
                    "trigger_threshold",
                    "description",
                ],
                "examples": [
                    {
                        "name": "Rapid Posting Behavior",
                        "detector_type": "behavioral",
                        "pattern": "rapid_posting",
                        "weight": 1.2,
                        "action_type": "suspend",
                        "trigger_threshold": 5.0,
                        "description": "Detects accounts posting more than 5 times in an hour.",
                    }
                ],
            },
            "media": {
                "description": "Examines media attachments for alt text, MIME types, or URL hashes.",
                "fields": [
                    "pattern",
                    "weight",
                    "action_type",
                    "trigger_threshold",
                    "description",
                ],
                "examples": [
                    {
                        "name": "Disallowed Image Type",
                        "detector_type": "media",
                        "pattern": "image/gif",
                        "weight": 1.0,
                        "action_type": "report",
                        "trigger_threshold": 1.0,
                        "description": "Flags GIF attachments.",
                    }
                ],
            },
        },
        "action_types": ["report", "silence", "suspend", "disable", "sensitive", "domain_block"],
        "weight_guidelines": {
            "description": "Rule weight determines how much each match contributes to the final score",
            "guidelines": [
                "0.1 - 0.3: Very mild indicators (suspicious but not conclusive)",
                "0.4 - 0.6: Moderate indicators (worth noting but not alarming)",
                "0.7 - 0.9: Strong indicators (likely problematic content)",
                "1.0 - 1.5: Very strong indicators (almost certainly spam/abuse)",
                "1.6+: Extreme indicators (immediate action warranted)",
            ],
        },
        "trigger_threshold_guidelines": {
            "description": "The score an account must reach to trigger the rule's action.",
            "guidelines": [
                "For simple rules, often 1.0 (a single match triggers the action).",
                "For behavioral rules, this might be a count (e.g., 5 posts in an hour).",
                "Can be used to combine multiple weaker rules to trigger a stronger action.",
            ],
        },
        "regex_tips": {
            "description": "Tips for creating effective regex patterns",
            "tips": [
                "Use ^ and $ to match the entire string (^pattern$)",
                "Use .* to match any characters before/after your pattern",
                r"Use \d for digits, \w for word characters, \s for spaces",
                r"Use + for one or more, * for zero or more, {3,} for 3 or more",
                r"Use (option1|option2) for alternatives",
                r"Escape special characters with backslash: \. \? \+ \*",
                "Test your patterns carefully - they affect real moderation decisions",
            ],
        },
        "testing_guidance": {
            "description": "How to test and validate your rules",
            "steps": [
                "1. Test your regex pattern with online tools first",
                "2. Start with a low weight (0.1-0.3) for new rules",
                "3. Monitor rule performance after creation",
                "4. Adjust weights based on false positive/negative rates",
                "5. Use the dry-run mode to test before applying",
                "6. Review triggered rules regularly for accuracy",
            ],
        },
        "best_practices": {
            "description": "Best practices for effective moderation rules",
            "practices": [
                "Create specific rules rather than overly broad ones",
                "Use descriptive names that explain what the rule catches",
                "Start conservative and adjust based on results",
                "Combine multiple weak indicators rather than one strong one",
                "Regularly review and update rules as spam evolves",
                "Document the reasoning behind each rule",
                "Consider cultural and language differences",
            ],
        },
    }


@router.put("/rules/{rule_id}", tags=["rules"])
def update_rule(
    rule_id: int, rule_data: dict, user: User = Depends(require_admin_hybrid), session: Session = Depends(get_db)
):
    """Update an existing rule."""
    try:
        updated_rule = rule_service.update_rule(rule_id, **rule_data)
        if not updated_rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        return updated_rule

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error("Failed to update rule", extra={"error": str(e), "rule_id": rule_id, "rule_data": rule_data})
        raise HTTPException(status_code=500, detail="Failed to update rule") from e


@router.delete("/rules/{rule_id}", tags=["rules"])
def delete_rule(rule_id: int, user: User = Depends(require_admin_hybrid), session: Session = Depends(get_db)):
    """Delete a rule."""
    try:
        if not rule_service.delete_rule(rule_id):
            raise HTTPException(status_code=404, detail="Rule not found")

        return {"message": "Rule deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error("Failed to delete rule", extra={"error": str(e), "rule_id": rule_id})
        raise HTTPException(status_code=500, detail="Failed to delete rule") from e


@router.post("/rules/{rule_id}/toggle", tags=["rules"])
def toggle_rule(rule_id: int, user: User = Depends(require_admin_hybrid), session: Session = Depends(get_db)):
    """Toggle rule enabled/disabled status."""
    try:
        # First get the current rule to determine the new state
        current_rule = rule_service.get_rule_by_id(rule_id)
        if not current_rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        toggled_rule = rule_service.toggle_rule(rule_id, not current_rule.enabled)
        if not toggled_rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        # Invalidate content scans due to rule changes
        scanner = ScanningSystem()
        scanner.invalidate_content_scans(rule_changes=True)

        return {
            "id": toggled_rule.id,
            "name": toggled_rule.name,
            "enabled": toggled_rule.enabled,
            "message": f"Rule {'enabled' if toggled_rule.enabled else 'disabled'}",
        }

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error("Failed to toggle rule", extra={"error": str(e), "rule_id": rule_id})
        raise HTTPException(status_code=500, detail="Failed to toggle rule") from e


@router.post("/rules/bulk-toggle", tags=["rules"])
def bulk_toggle_rules(
    rule_ids: list[int],
    enabled: bool,
    user: User = Depends(require_admin_hybrid),
    session: Session = Depends(get_db),
):
    """Toggle multiple rules at once."""
    try:
        updated_rules = rule_service.bulk_toggle_rules(rule_ids, enabled)

        # Invalidate content scans due to rule changes
        scanner = ScanningSystem()
        scanner.invalidate_content_scans(rule_changes=True)

        return {
            "updated_rules": [r.name for r in updated_rules],
            "enabled": enabled,
            "message": f"{len(updated_rules)} rules {'enabled' if enabled else 'disabled'}",
        }

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error("Failed to bulk toggle rules", extra={"error": str(e), "rule_ids": rule_ids})
        raise HTTPException(status_code=500, detail="Failed to bulk toggle rules") from e


@router.get("/rules/{rule_id}/details", tags=["rules"])
def get_rule_details(rule_id: int, user: User = Depends(require_admin_hybrid), session: Session = Depends(get_db)):
    """Get detailed information about a specific rule."""
    try:
        rule = session.query(Rule).filter(Rule.id == rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        # Get recent analyses using this rule
        recent_analyses = (
            session.query(Analysis)
            .filter(Analysis.rule_key == rule.name)
            .order_by(desc(Analysis.created_at))
            .limit(10)
            .all()
        )

        return {
            "id": rule.id,
            "name": rule.name,
            "detector_type": rule.detector_type,
            "pattern": rule.pattern,
            "weight": float(rule.weight),
            "action_type": rule.action_type,
            "trigger_threshold": float(rule.trigger_threshold),
            "action_duration_seconds": rule.action_duration_seconds,
            "action_warning_text": rule.action_warning_text,
            "warning_preset_id": rule.warning_preset_id,
            "enabled": rule.enabled,
            "description": rule.description,
            "created_by": rule.created_by,
            "updated_by": rule.updated_by,
            "created_at": rule.created_at.isoformat() if rule.created_at else None,
            "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
            "recent_analyses": [
                {
                    "id": analysis.id,
                    "mastodon_account_id": analysis.mastodon_account_id,
                    "score": float(analysis.score),
                    "created_at": analysis.created_at.isoformat(),
                    "evidence": analysis.evidence,
                }
                for analysis in recent_analyses
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get rule details", extra={"error": str(e), "rule_id": rule_id})
        raise HTTPException(status_code=500, detail="Failed to get rule details") from e


@router.post("/rules/reload", tags=["ops"])
def reload_rules(user: User = Depends(require_admin_hybrid)):
    """Reload rules from database."""
    try:
        old_sha = rule_service.ruleset_sha256 if rule_service.ruleset_sha256 else "unknown"

        try:
            rule_service.get_active_rules(force_refresh=True)
        except Exception as e:
            logger.error(
                "Failed to load rules from database",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            raise HTTPException(
                status_code=500,
                detail={"error": "rules_load_failed", "message": f"Failed to load rules from database: {str(e)}"},
            ) from e

        new_sha = rule_service.ruleset_sha256

        logger.info(
            "Rules configuration reloaded from database",
            extra={
                "old_sha": old_sha[:8] if old_sha != "unknown" else old_sha,
                "new_sha": new_sha[:8],
                "sha_changed": old_sha != new_sha,
            },
        )

        return {"reloaded": True, "ruleset_sha256": new_sha, "previous_sha256": old_sha, "changed": old_sha != new_sha}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to reload rules", extra={"error": str(e), "error_type": type(e).__name__})
        raise HTTPException(
            status_code=500, detail={"error": "rules_reload_failed", "message": f"Failed to reload rules: {str(e)}"}
        ) from e
