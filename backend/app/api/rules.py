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
                # Enhanced configuration fields
                "target_fields": rule.target_fields,
                "match_options": rule.match_options,
                "behavioral_params": rule.behavioral_params,
                "media_params": rule.media_params,
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
            target_fields=rule_data.get("target_fields"),
            match_options=rule_data.get("match_options"),
            behavioral_params=rule_data.get("behavioral_params"),
            media_params=rule_data.get("media_params"),
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
        "overview": {
            "description": "MastoWatch supports multiple detector types. Choose the right tool for each moderation task.",
            "detector_types": {
                "keyword": "Simple, fast text matching - best for known spam terms, blocked phrases, or specific words",
                "behavioral": "Account activity patterns - best for detecting bots, spam behavior, or abuse patterns",
                "media": "Media content policies - best for attachment requirements, MIME type filtering, or image hashing",
                "regex": "Advanced pattern matching - use when keyword matching isn't flexible enough (requires regex expertise)",
            },
            "choosing_detector": [
                "Start with keyword rules for simple text matches - they're faster and easier to maintain",
                "Use behavioral rules for account activity patterns like rapid posting or link spam",
                "Use media rules for attachment policies like required alt-text or MIME type filtering",
                "Only use regex when you need complex pattern matching that keywords can't handle",
            ],
        },
        "rule_types": {
            "keyword": {
                "description": "Fast, simple text matching for known terms and phrases. Best for most moderation needs.",
                "priority": 1,
                "fields": [
                    "pattern (comma-separated keywords)",
                    "target_fields (which fields to check: username, display_name, bio, content)",
                    "match_options (case_sensitive, word_boundaries, etc.)",
                    "weight",
                    "action_type",
                    "trigger_threshold",
                    "description",
                ],
                "examples": [
                    {
                        "name": "Spam Keywords in Bio",
                        "detector_type": "keyword",
                        "pattern": "casino,pills,viagra,crypto",
                        "target_fields": ["bio"],
                        "match_options": {"case_sensitive": False, "word_boundaries": True},
                        "weight": 1.2,
                        "action_type": "report",
                        "trigger_threshold": 1.0,
                        "description": "Detects common spam keywords in user bios only.",
                    },
                    {
                        "name": "Promotional Terms in Username",
                        "detector_type": "keyword",
                        "pattern": "buy,discount,sale,promo",
                        "target_fields": ["username", "display_name"],
                        "match_options": {"case_sensitive": False, "word_boundaries": False},
                        "weight": 0.8,
                        "action_type": "report",
                        "trigger_threshold": 1.0,
                        "description": "Flags promotional language in usernames and display names.",
                    },
                    {
                        "name": "Blocked Domains",
                        "detector_type": "keyword",
                        "pattern": "spam-site.com,scam-site.net,bad-domain.tk",
                        "target_fields": ["content", "bio"],
                        "match_options": {"case_sensitive": False, "word_boundaries": False},
                        "weight": 2.0,
                        "action_type": "suspend",
                        "trigger_threshold": 1.0,
                        "description": "Blocks specific known spam/scam domains.",
                    },
                ],
            },
            "behavioral": {
                "description": "Detect suspicious account activity patterns and bot-like behavior.",
                "priority": 2,
                "fields": [
                    "pattern (behavior type: rapid_posting, link_spam, automation_disclosure)",
                    "behavioral_params (time_window_hours, post_threshold, link_threshold)",
                    "weight",
                    "action_type",
                    "trigger_threshold",
                    "description",
                ],
                "examples": [
                    {
                        "name": "Rapid Posting Detection",
                        "detector_type": "behavioral",
                        "pattern": "rapid_posting",
                        "behavioral_params": {"time_window_hours": 1, "post_threshold": 10},
                        "weight": 1.5,
                        "action_type": "silence",
                        "trigger_threshold": 1.0,
                        "description": "Flags accounts posting more than 10 times per hour (typical bot behavior).",
                    },
                    {
                        "name": "Link Spam Detector",
                        "detector_type": "behavioral",
                        "pattern": "link_spam",
                        "behavioral_params": {"min_links_per_post": 3, "post_sample_size": 5},
                        "weight": 1.8,
                        "action_type": "report",
                        "trigger_threshold": 1.0,
                        "description": "Detects accounts posting excessive links (3+ links in most posts).",
                    },
                    {
                        "name": "Suspicious New Account",
                        "detector_type": "behavioral",
                        "pattern": "new_account_activity",
                        "behavioral_params": {"account_age_days": 1, "min_posts": 20},
                        "weight": 1.0,
                        "action_type": "report",
                        "trigger_threshold": 1.0,
                        "description": "Flags brand new accounts with immediate high posting activity.",
                    },
                ],
            },
            "media": {
                "description": "Media attachment policies for accessibility, content type filtering, and known image detection.",
                "priority": 3,
                "fields": [
                    "pattern (MIME type, alt-text pattern, or image hash)",
                    "media_params (require_alt_text, allowed_mime_types, blocked_hashes)",
                    "weight",
                    "action_type",
                    "trigger_threshold",
                    "description",
                ],
                "examples": [
                    {
                        "name": "Missing Alt Text",
                        "detector_type": "media",
                        "pattern": "missing_alt_text",
                        "media_params": {"require_alt_text": True},
                        "weight": 0.3,
                        "action_type": "report",
                        "trigger_threshold": 1.0,
                        "description": "Flags posts with images missing alt text (accessibility requirement).",
                    },
                    {
                        "name": "Blocked Image Types",
                        "detector_type": "media",
                        "pattern": "image/gif",
                        "media_params": {"allowed_mime_types": ["image/jpeg", "image/png", "image/webp"]},
                        "weight": 1.0,
                        "action_type": "sensitive",
                        "trigger_threshold": 1.0,
                        "description": "Blocks or marks GIF attachments as sensitive.",
                    },
                    {
                        "name": "Known Spam Image",
                        "detector_type": "media",
                        "pattern": "a1b2c3d4e5f6...",  # SHA256 hash
                        "media_params": {"detection_type": "hash"},
                        "weight": 2.5,
                        "action_type": "suspend",
                        "trigger_threshold": 1.0,
                        "description": "Detects known spam/scam image by content hash.",
                    },
                ],
            },
            "regex": {
                "description": "Advanced pattern matching using regular expressions. Use sparingly - regex can be slow and error-prone.",
                "priority": 4,
                "warning": "Regex patterns can cause performance issues and false positives. Consider using keyword rules first.",
                "fields": [
                    "pattern (regex pattern)",
                    "target_fields (which fields to check: username, display_name, bio, content)",
                    "boolean_operator",
                    "secondary_pattern",
                    "weight",
                    "action_type",
                    "trigger_threshold",
                    "description",
                ],
                "safety_tips": [
                    "Avoid catastrophic backtracking - test patterns at regex101.com",
                    "Keep patterns simple - complex regex can timeout or slow down scanning",
                    "Use keyword rules instead when possible - they're faster and safer",
                    "Always test with sample data before enabling",
                ],
                "examples": [
                    {
                        "name": "Spam URL Pattern",
                        "detector_type": "regex",
                        "pattern": r"https?://[a-zA-Z0-9.-]+\.(tk|ml|ga|cf|gq)/",
                        "target_fields": ["content", "bio"],
                        "weight": 1.5,
                        "action_type": "report",
                        "trigger_threshold": 1.0,
                        "description": "Detects URLs with free/disposable domain TLDs often used for spam.",
                    },
                    {
                        "name": "Suspicious Username Pattern",
                        "detector_type": "regex",
                        "pattern": r"^[a-z]+\d{4,}$",
                        "target_fields": ["username"],
                        "weight": 0.5,
                        "action_type": "report",
                        "trigger_threshold": 1.0,
                        "description": "Flags usernames like 'user12345' (common bot pattern).",
                    },
                ],
            },
        },
        "field_scoping": {
            "description": "Target specific fields to reduce false positives and improve precision",
            "available_fields": {
                "username": "The user's account name (e.g., '@alice')",
                "display_name": "The user's display name shown on their profile",
                "bio": "The user's profile bio/note text",
                "content": "Post content (status text)",
            },
            "examples": [
                "username-only rules catch spammy account names without false positives from legitimate post content",
                "bio-only rules target profile spam without affecting normal posting",
                "content-only rules focus on what users post, not their identity",
            ],
        },
        "match_options": {
            "description": "Fine-tune keyword matching behavior",
            "options": {
                "case_sensitive": "Whether to match case exactly (default: false)",
                "word_boundaries": "Only match whole words, not substrings (default: true)",
                "phrase_match": "Treat entire pattern as single phrase (default: false)",
            },
            "examples": [
                {"case_sensitive": False, "word_boundaries": True, "description": "Match 'spam' but not 'Spam' or 'spammer'"},
                {"case_sensitive": False, "word_boundaries": False, "description": "Match 'spam' in 'spammer', 'SPAM', etc."},
                {"case_sensitive": True, "word_boundaries": True, "description": "Exact word match, case-sensitive"},
            ],
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
        "testing_guidance": {
            "description": "How to test and validate your rules",
            "steps": [
                "1. Start with keyword rules when possible - they're easier to test and debug",
                "2. Test regex patterns with online tools first (only if keyword rules aren't sufficient)",
                "3. Start with a low weight (0.1-0.3) for new rules",
                "4. Monitor rule performance after creation",
                "5. Adjust weights based on false positive/negative rates",
                "6. Review triggered rules regularly for accuracy",
            ],
        },
        "best_practices": {
            "description": "Best practices for effective moderation rules",
            "practices": [
                "Prefer keyword rules over regex - they're faster, safer, and easier to maintain",
                "Use field scoping to target specific areas (e.g., username-only or bio-only)",
                "Configure match_options appropriately (word boundaries prevent false matches)",
                "Use behavioral rules for patterns that simple text matching can't catch",
                "Use media rules to enforce accessibility and content policies",
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
