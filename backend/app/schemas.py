"""Pydantic schemas for API request/response validation."""

from typing import Any

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """Evidence collected during rule evaluation."""

    matched_terms: list[str]
    matched_status_ids: list[str]
    metrics: dict
    matched_pattern: str | None = None  # For regex detector compatibility
    matched_keywords: list[str] | None = None  # For keyword detector compatibility

    def __getitem__(self, key):
        """Allow dictionary-style access for test compatibility."""
        return getattr(self, key)

    def get(self, key, default=None):
        """Allow dictionary-style .get() access for compatibility."""
        try:
            return getattr(self, key)
        except AttributeError:
            return default

    def __contains__(self, key):
        """Allow 'in' operator for test compatibility."""
        return hasattr(self, key)


class Violation(BaseModel):
    """A rule violation detected during scanning."""

    rule_name: str
    rule_type: str = "unknown"  # Default value for backward compatibility
    score: float
    evidence: Evidence
    actions: list[dict[str, Any]] = Field(default_factory=list)


class AccountsPage(BaseModel):
    """Paginated accounts response from admin API."""

    accounts: list[dict[str, Any]]
    next_cursor: str | None = None
