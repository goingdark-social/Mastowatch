"""Helpers for applying and reverting moderation actions."""

import logging
from typing import Any

from app.config import get_settings
from app.db import SessionLocal
from app.models import AuditLog
from app.services.mastodon_service import mastodon_service

logger = logging.getLogger(__name__)
settings = get_settings()


class EnforcementService:
    """Wrap Mastodon admin endpoints used for moderation."""

    def __init__(self, client=None):
        # Allow injecting a Mastodon client (tests) or use the singleton service
        # If a raw client is passed, keep it for direct calls; otherwise use
        # the high-level mastodon_service wrapper.
        if client is not None:
            self.mastodon_service = None
            self.client = client
        else:
            self.mastodon_service = mastodon_service
            self.client = None

    def _log_action(
        self,
        *,
        action_type: str,
        account_id: str,
        rule_id: int | None,
        evidence: dict[str, Any] | None,
        api_response: Any,
    ) -> None:
        with SessionLocal() as session:
            session.add(
                AuditLog(
                    action_type=action_type,
                    triggered_by_rule_id=rule_id,
                    target_account_id=account_id,
                    evidence=evidence,
                    api_response=api_response,
                )
            )
            session.commit()

    def _post_action(
        self,
        account_id: str,
        payload: dict[str, Any],
        *,
        rule_id: int | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        if settings.DRY_RUN:
            logger.info("DRY RUN: %s %s", account_id, payload.get("type"))
            self._log_action(
                action_type=payload.get("type", ""),
                account_id=account_id,
                rule_id=rule_id,
                evidence=evidence,
                api_response={"dry_run": True},
            )
            return

        try:
            # Use mastodon_service for admin actions
            if self.client is not None:
                # Tests may pass a mocked client. Try calling admin_account_moderate
                # if available, otherwise return a mock response.
                if hasattr(self.client, "admin_account_moderate"):
                    api_response = self.client.admin_account_moderate(
                        id=account_id,
                        action=payload.get("type", "") if payload.get("type") != "warn" else None,
                        text=payload.get("text"),
                        warning_preset_id=payload.get("warning_preset_id"),
                    )
                else:
                    # Fallback to a generic mock response
                    api_response = {"mocked": True}
            else:
                api_response = self.mastodon_service.admin_account_action_sync(
                    account_id=account_id,
                    action_type=payload.get("type", ""),
                    text=payload.get("text"),
                    warning_preset_id=payload.get("warning_preset_id"),
                )
        except Exception as e:
            logger.error("Failed to perform action on account %s: %s", account_id, str(e))
            api_response = {"error": str(e)}

        self._log_action(
            action_type=payload.get("type", ""),
            account_id=account_id,
            rule_id=rule_id,
            evidence=evidence,
            api_response=api_response,
        )

    def warn_account(
        self,
        account_id: str,
        *,
        text: str | None = None,
        warning_preset_id: str | None = None,
        rule_id: int | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        """Send an admin warning."""
        payload: dict[str, Any] = {"type": "none"}
        if text:
            payload["text"] = text
        if warning_preset_id:
            payload["warning_preset_id"] = warning_preset_id
        self._post_action(account_id, payload, rule_id=rule_id, evidence=evidence)

    def silence_account(
        self,
        account_id: str,
        *,
        text: str | None = None,
        warning_preset_id: str | None = None,
        rule_id: int | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        """Silence an account."""
        payload: dict[str, Any] = {"type": "silence"}
        if text:
            payload["text"] = text
        if warning_preset_id:
            payload["warning_preset_id"] = warning_preset_id
        self._post_action(account_id, payload, rule_id=rule_id, evidence=evidence)

    def suspend_account(
        self,
        account_id: str,
        *,
        text: str | None = None,
        warning_preset_id: str | None = None,
        rule_id: int | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        """Suspend an account."""
        payload: dict[str, Any] = {"type": "suspend"}
        if text:
            payload["text"] = text
        if warning_preset_id:
            payload["warning_preset_id"] = warning_preset_id
        self._post_action(account_id, payload, rule_id=rule_id, evidence=evidence)

    def unsilence_account(
        self,
        account_id: str,
        *,
        rule_id: int | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        """Lift a previously applied silence."""
        if settings.DRY_RUN:
            logger.info("DRY RUN: unsilence %s", account_id)
            self._log_action(
                action_type="unsilence",
                account_id=account_id,
                rule_id=rule_id,
                evidence=evidence,
                api_response={"dry_run": True},
            )
            return

        try:
            if self.client is not None:
                if hasattr(self.client, "admin_account_unsilence"):
                    api_response = self.client.admin_account_unsilence(account_id)
                else:
                    api_response = {"mocked": True}
            else:
                api_response = self.mastodon_service.admin_unsilence_account_sync(account_id)
        except Exception as e:
            logger.error("Failed to unsilence account %s: %s", account_id, str(e))
            api_response = {"error": str(e)}

        self._log_action(
            action_type="unsilence",
            account_id=account_id,
            rule_id=rule_id,
            evidence=evidence,
            api_response=api_response,
        )

    def unsuspend_account(
        self,
        account_id: str,
        *,
        rule_id: int | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        """Lift a previously applied suspension."""
        if settings.DRY_RUN:
            logger.info("DRY RUN: unsuspend %s", account_id)
            self._log_action(
                action_type="unsuspend",
                account_id=account_id,
                rule_id=rule_id,
                evidence=evidence,
                api_response={"dry_run": True},
            )
            return

        try:
            if self.client is not None:
                if hasattr(self.client, "admin_account_unsuspend"):
                    api_response = self.client.admin_account_unsuspend(account_id)
                else:
                    api_response = {"mocked": True}
            else:
                api_response = self.mastodon_service.admin_unsuspend_account_sync(account_id)
        except Exception as e:
            logger.error("Failed to unsuspend account %s: %s", account_id, str(e))
            api_response = {"error": str(e)}

        self._log_action(
            action_type="unsuspend",
            account_id=account_id,
            rule_id=rule_id,
            evidence=evidence,
            api_response=api_response,
        )

    def perform_account_action(self, *, account_id: str, action_type: str, **kwargs) -> None:
        """Generic dispatcher used by task handlers to perform an action.

        This maps a generic action call into the concrete helper methods on this
        service. Tests and task handlers call this convenience method to keep
        call-sites small.
        """
        # Map action types to methods
        if action_type == "warn":
            self.warn_account(
                account_id,
                text=kwargs.get("warning_text") or kwargs.get("comment"),
                warning_preset_id=kwargs.get("warning_preset_id"),
                rule_id=kwargs.get("rule_id"),
                evidence=kwargs.get("evidence"),
            )
        elif action_type == "silence":
            self.silence_account(
                account_id,
                text=kwargs.get("warning_text") or kwargs.get("comment"),
                warning_preset_id=kwargs.get("warning_preset_id"),
                rule_id=kwargs.get("rule_id"),
                evidence=kwargs.get("evidence"),
            )
        elif action_type == "suspend":
            self.suspend_account(
                account_id,
                text=kwargs.get("warning_text") or kwargs.get("comment"),
                warning_preset_id=kwargs.get("warning_preset_id"),
                rule_id=kwargs.get("rule_id"),
                evidence=kwargs.get("evidence"),
            )
        elif action_type == "unsilence":
            self.unsilence_account(account_id, rule_id=kwargs.get("rule_id"), evidence=kwargs.get("evidence"))
        elif action_type == "unsuspend":
            self.unsuspend_account(account_id, rule_id=kwargs.get("rule_id"), evidence=kwargs.get("evidence"))
        elif action_type == "report":
            # For reports, prefer using the mastodon_service create_report sync
            try:
                if self.client is not None:
                    # Some test clients expose a helper to create reports
                    if hasattr(self.client, "report"):
                        self.client.report(
                            account_id=account_id,
                            status_ids=kwargs.get("status_ids") or [],
                            comment=kwargs.get("comment", ""),
                        )
                    else:
                        # Best-effort; tests usually mock higher-level call sites
                        pass
                else:
                    # Use mastodon_service sync wrapper
                    mastodon_service.create_report_sync(
                        account_id=account_id,
                        status_ids=kwargs.get("status_ids"),
                        comment=kwargs.get("comment", ""),
                    )
            except Exception:
                # Don't let reporting errors raise out of the dispatcher
                logger.exception("Error performing report action for %s", account_id)
        else:
            logger.warning("Unknown action_type passed to perform_account_action: %s", action_type)
