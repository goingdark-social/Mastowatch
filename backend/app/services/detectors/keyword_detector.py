"""Keyword detector for content analysis."""

from app.models import Rule
from app.schemas import Evidence, Violation
from app.services.detectors.base import BaseDetector


class KeywordDetector(BaseDetector):
    """Detector for keyword patterns in account and status text."""

    def evaluate(self, rule: Rule, account_data: dict[str, any], statuses: list[dict[str, any]]) -> list[Violation]:
        """Evaluate account and statuses for keyword matches."""
        violations: list[Violation] = []

        terms = [term.strip() for term in rule.pattern.split(",")]
        u = account_data.get("username") or (account_data.get("acct", "").split("@")[0]) or ""
        dn = account_data.get("display_name") or ""
        note = account_data.get("note") or ""

        # Check username for keywords
        matched_terms_username = []
        for term in terms:
            if term.lower() in u.lower():
                matched_terms_username.append(term)

        if matched_terms_username:
            violations.append(
                Violation(
                    rule_name=rule.name,
                    score=rule.weight,
                    evidence=Evidence(
                        matched_terms=matched_terms_username, 
                        matched_status_ids=[], 
                        metrics={"username": u},
                        matched_keywords=matched_terms_username
                    ),
                )
            )

        # Check display name for keywords
        matched_terms_display = []
        for term in terms:
            if term.lower() in dn.lower():
                matched_terms_display.append(term)

        if matched_terms_display:
            violations.append(
                Violation(
                    rule_name=rule.name,
                    score=rule.weight,
                    evidence=Evidence(
                        matched_terms=matched_terms_display, 
                        matched_status_ids=[], 
                        metrics={"display_name": dn},
                        matched_keywords=matched_terms_display
                    ),
                )
            )

        # Check bio/note for keywords
        matched_terms_note = []
        for term in terms:
            if term.lower() in note.lower():
                matched_terms_note.append(term)

        if matched_terms_note:
            violations.append(
                Violation(
                    rule_name=rule.name,
                    score=rule.weight,
                    evidence=Evidence(
                        matched_terms=matched_terms_note, 
                        matched_status_ids=[], 
                        metrics={"note": note},
                        matched_keywords=matched_terms_note
                    ),
                )
            )

        # Check content for keywords
        for s in statuses or []:
            content = s.get("content", "")
            matched_terms_content = []
            for term in terms:
                if term.lower() in content.lower():
                    matched_terms_content.append(term)

            if matched_terms_content:
                violations.append(
                    Violation(
                        rule_name=rule.name,
                        score=rule.weight,
                        evidence=Evidence(
                            matched_terms=matched_terms_content,
                            matched_status_ids=[s.get("id")],
                            metrics={"content": content},
                            matched_keywords=matched_terms_content
                        ),
                    )
                )

        return violations
