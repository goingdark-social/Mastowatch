"""Regex detector for pattern matching in content."""

import re

from app.models import Rule
from app.schemas import Evidence, Violation
from app.services.detectors.base import BaseDetector


class RegexDetector(BaseDetector):
    """Detector for regex patterns in account and status text."""

    def evaluate(self, rule: Rule, account_data: dict[str, any], statuses: list[dict[str, any]]) -> list[Violation]:
        """Evaluate account and statuses for regex pattern matches."""
        violations: list[Violation] = []

        u = account_data.get("username") or (account_data.get("acct", "").split("@")[0]) or ""
        dn = account_data.get("display_name") or ""
        note = account_data.get("note") or ""

        # Apply regex to username
        if match := re.search(rule.pattern, u, re.I):
            violations.append(
                Violation(
                    rule_name=rule.name,
                    rule_type=rule.detector_type,
                    score=rule.weight,
                    evidence=Evidence(
                        matched_terms=[u], 
                        matched_status_ids=[], 
                        metrics={"username": u},
                        matched_pattern=match.group(0)
                    ),
                )
            )

        # Apply regex to display name
        if match := re.search(rule.pattern, dn, re.I):
            violations.append(
                Violation(
                    rule_name=rule.name,
                    rule_type=rule.detector_type,
                    score=rule.weight,
                    evidence=Evidence(
                        matched_terms=[dn], 
                        matched_status_ids=[], 
                        metrics={"display_name": dn},
                        matched_pattern=match.group(0)
                    ),
                )
            )

        # Apply regex to bio/note
        if match := re.search(rule.pattern, note, re.I):
            violations.append(
                Violation(
                    rule_name=rule.name,
                    rule_type=rule.detector_type,
                    score=rule.weight,
                    evidence=Evidence(
                        matched_terms=[note], 
                        matched_status_ids=[], 
                        metrics={"note": note},
                        matched_pattern=match.group(0)
                    ),
                )
            )

        # Apply regex to status content
        for s in statuses or []:
            content = s.get("content", "")
            if match := re.search(rule.pattern, content, re.I):
                violations.append(
                    Violation(
                        rule_name=rule.name,
                        rule_type=rule.detector_type,
                        score=rule.weight,
                        evidence=Evidence(
                            matched_terms=[content], 
                            matched_status_ids=[s.get("id")], 
                            metrics={"content": content},
                            matched_pattern=match.group(0)
                        ),
                    )
                )

        return violations
