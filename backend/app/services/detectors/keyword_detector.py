"""Keyword detector for content analysis."""

import re
from app.models import Rule
from app.schemas import Evidence, Violation
from app.services.detectors.base import BaseDetector


class KeywordDetector(BaseDetector):
    """Detector for keyword patterns in account and status text."""

    def evaluate(self, rule: Rule, account_data: dict[str, any], statuses: list[dict[str, any]]) -> list[Violation]:
        """Evaluate account and statuses for keyword matches."""
        violations: list[Violation] = []

        terms = [term.strip() for term in rule.pattern.split(",")]
        
        # Get match options with defaults
        match_options = rule.match_options or {}
        case_sensitive = match_options.get("case_sensitive", False)
        word_boundaries = match_options.get("word_boundaries", True)
        
        # Get target fields (default to all if not specified)
        target_fields = rule.target_fields or ["username", "display_name", "bio", "content"]
        
        # Extract field values
        u = account_data.get("username") or (account_data.get("acct", "").split("@")[0]) or ""
        dn = account_data.get("display_name") or ""
        note = account_data.get("note") or ""

        # Check username for keywords if targeted
        if "username" in target_fields:
            matched_terms_username = self._find_matches(u, terms, case_sensitive, word_boundaries)
            if matched_terms_username:
                violations.append(
                    Violation(
                        rule_name=rule.name,
                        score=rule.weight,
                        evidence=Evidence(
                            matched_terms=matched_terms_username,
                            matched_status_ids=[],
                            metrics={"username": u, "field": "username"},
                            matched_keywords=matched_terms_username,
                        ),
                    )
                )

        # Check display name for keywords if targeted
        if "display_name" in target_fields:
            matched_terms_display = self._find_matches(dn, terms, case_sensitive, word_boundaries)
            if matched_terms_display:
                violations.append(
                    Violation(
                        rule_name=rule.name,
                        score=rule.weight,
                        evidence=Evidence(
                            matched_terms=matched_terms_display,
                            matched_status_ids=[],
                            metrics={"display_name": dn, "field": "display_name"},
                            matched_keywords=matched_terms_display,
                        ),
                    )
                )

        # Check bio/note for keywords if targeted
        if "bio" in target_fields:
            matched_terms_note = self._find_matches(note, terms, case_sensitive, word_boundaries)
            if matched_terms_note:
                violations.append(
                    Violation(
                        rule_name=rule.name,
                        score=rule.weight,
                        evidence=Evidence(
                            matched_terms=matched_terms_note,
                            matched_status_ids=[],
                            metrics={"note": note, "field": "bio"},
                            matched_keywords=matched_terms_note,
                        ),
                    )
                )

        # Check content for keywords if targeted
        if "content" in target_fields:
            for s in statuses or []:
                content = s.get("content", "")
                matched_terms_content = self._find_matches(content, terms, case_sensitive, word_boundaries)
                if matched_terms_content:
                    violations.append(
                        Violation(
                            rule_name=rule.name,
                            score=rule.weight,
                            evidence=Evidence(
                                matched_terms=matched_terms_content,
                                matched_status_ids=[s.get("id")],
                                metrics={"content": content, "field": "content"},
                                matched_keywords=matched_terms_content,
                            ),
                        )
                    )

        return violations

    def _find_matches(
        self, text: str, terms: list[str], case_sensitive: bool, word_boundaries: bool
    ) -> list[str]:
        """Find matching terms in text with specified options.
        
        Args:
            text: Text to search in
            terms: Terms to search for
            case_sensitive: Whether to match case exactly
            word_boundaries: Whether to require word boundaries
            
        Returns:
            List of matched terms
        """
        matched = []
        search_text = text if case_sensitive else text.lower()
        
        for term in terms:
            search_term = term if case_sensitive else term.lower()
            
            if word_boundaries:
                # Use word boundary regex for whole-word matching
                pattern = r'\b' + re.escape(search_term) + r'\b'
                if re.search(pattern, search_text, re.IGNORECASE if not case_sensitive else 0):
                    matched.append(term)
            else:
                # Simple substring matching
                if search_term in search_text:
                    matched.append(term)
                    
        return matched
