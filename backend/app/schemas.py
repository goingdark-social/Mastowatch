from typing import Any, Dict, List
from pydantic import BaseModel, Field


class Evidence(BaseModel):
    matched_terms: List[str]
    matched_status_ids: List[str]
    metrics: Dict
    matched_pattern: str | None = None  # For regex detector compatibility
    matched_keywords: List[str] | None = None  # For keyword detector compatibility

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
    rule_name: str
    rule_type: str = "unknown"  # Default value for backward compatibility
    score: float
    evidence: Evidence
    actions: List[Dict[str, Any]] = Field(default_factory=list)


class AccountsPage(BaseModel):
    accounts: List[Dict[str, Any]]
    next_cursor: str | None = None
