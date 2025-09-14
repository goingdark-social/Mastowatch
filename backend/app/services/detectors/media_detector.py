"""Detector for media attachments."""

from hashlib import sha256
from typing import Any

from app.models import Rule
from app.schemas import Evidence, Violation
from app.services.detectors.base import BaseDetector


class MediaDetector(BaseDetector):
    """Evaluate alt text, MIME types, and URL hashes of attachments."""

    def evaluate(self, rule: Rule, account_data: dict[str, Any], statuses: list[dict[str, Any]]) -> list[Violation]:
        """Find violations in media attachments."""
        violations: list[Violation] = []
        pattern = rule.pattern.lower()
        
        # Determine if this is a hash pattern (long hex string, likely SHA256)
        is_hash_pattern = len(pattern) == 64 and all(c in '0123456789abcdef' for c in pattern)
        
        for status in statuses or []:
            for attachment in status.get("media_attachments", []):
                alt_text = (attachment.get("description") or "").lower()
                mime = (attachment.get("mime_type") or "").lower()
                url = attachment.get("url") or attachment.get("remote_url") or ""
                hash_value = sha256(url.encode()).hexdigest() if url else ""
                matched_terms: list[str] = []
                metrics: dict[str, Any] = {}
                if not is_hash_pattern:
                    if pattern in alt_text:
                        matched_terms.append(alt_text)
                        metrics["alt_text"] = alt_text
                    if pattern in mime:
                        matched_terms.append(mime)
                        metrics["mime_type"] = mime
                else:
                    if pattern == hash_value:
                        matched_terms.append(hash_value)
                        metrics["hash"] = hash_value
                if matched_terms:
                    violations.append(
                        Violation(
                            rule_name=rule.name,
                            score=rule.weight,
                            evidence=Evidence(
                                matched_terms=matched_terms,
                                matched_status_ids=[status.get("id")],
                                metrics=metrics,
                            ),
                        )
                    )
        return violations
