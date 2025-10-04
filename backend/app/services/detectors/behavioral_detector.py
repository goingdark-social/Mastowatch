"""Behavioral detector for account behavior analysis."""

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from app.db import engine
from app.models import AccountBehaviorMetrics, InteractionHistory, Rule
from app.schemas import Evidence, Violation
from app.services.detectors.base import BaseDetector
from sqlalchemy.orm import Session


class BehavioralDetector(BaseDetector):
    """Detector for behavioral patterns in account activity."""

    AUTOMATION_WINDOW = 20
    LINK_SPAM_WINDOW = 20

    def evaluate(self, rule: Rule, account_data: dict[str, Any], statuses: list[dict[str, Any]]) -> list[Violation]:
        violations: list[Violation] = []
        mastodon_account_id = account_data.get("mastodon_account_id")
        if not mastodon_account_id:
            return violations
        with Session(engine) as session:
            behavior_type = rule.pattern.lower().strip()
            if behavior_type == "rapid_posting":
                one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
                posts_last_1h = (
                    session.query(InteractionHistory)
                    .filter(
                        InteractionHistory.source_account_id == mastodon_account_id,
                        InteractionHistory.created_at >= one_hour_ago,
                    )
                    .count()
                )
                if posts_last_1h >= rule.trigger_threshold:
                    violations.append(
                        Violation(
                            rule_name=rule.name,
                            score=rule.weight,
                            evidence=Evidence(
                                matched_terms=[],
                                matched_status_ids=[],
                                metrics={"posts_last_1h": posts_last_1h, "threshold": rule.trigger_threshold},
                            ),
                        )
                    )
            elif behavior_type == "interaction_spam":
                recent_interactions = (
                    session.query(InteractionHistory)
                    .filter(InteractionHistory.source_account_id == mastodon_account_id)
                    .order_by(InteractionHistory.created_at.desc())
                    .limit(100)
                    .all()
                )
                unique_targets = {i.target_account_id for i in recent_interactions}
                if len(unique_targets) >= rule.trigger_threshold:
                    violations.append(
                        Violation(
                            rule_name=rule.name,
                            score=rule.weight,
                            evidence=Evidence(
                                matched_terms=[],
                                matched_status_ids=[],
                                metrics={
                                    "unique_targets": len(unique_targets),
                                    "recent_interactions_count": len(recent_interactions),
                                    "threshold": rule.trigger_threshold,
                                },
                            ),
                        )
                    )
            elif behavior_type == "daily_posting":
                twenty_four_hours_ago = datetime.now(UTC) - timedelta(hours=24)
                posts_last_24h = (
                    session.query(InteractionHistory)
                    .filter(
                        InteractionHistory.source_account_id == mastodon_account_id,
                        InteractionHistory.created_at >= twenty_four_hours_ago,
                    )
                    .count()
                )
                if posts_last_24h >= rule.trigger_threshold:
                    violations.append(
                        Violation(
                            rule_name=rule.name,
                            score=rule.weight,
                            evidence=Evidence(
                                matched_terms=[],
                                matched_status_ids=[],
                                metrics={"posts_last_24h": posts_last_24h, "threshold": rule.trigger_threshold},
                            ),
                        )
                    )
            elif behavior_type == "automation_disclosure":
                violations.extend(self._check_automation(rule, account_data, statuses))
            elif behavior_type == "link_spam":
                violations.extend(self._check_link_spam(rule, statuses))
            one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
            twenty_four_hours_ago = datetime.now(UTC) - timedelta(hours=24)
            posts_last_1h = (
                session.query(InteractionHistory)
                .filter(
                    InteractionHistory.source_account_id == mastodon_account_id,
                    InteractionHistory.created_at >= one_hour_ago,
                )
                .count()
            )
            posts_last_24h = (
                session.query(InteractionHistory)
                .filter(
                    InteractionHistory.source_account_id == mastodon_account_id,
                    InteractionHistory.created_at >= twenty_four_hours_ago,
                )
                .count()
            )
            metrics = (
                session.query(AccountBehaviorMetrics)
                .filter(AccountBehaviorMetrics.mastodon_account_id == mastodon_account_id)
                .first()
            )
            if not metrics:
                metrics = AccountBehaviorMetrics(
                    mastodon_account_id=mastodon_account_id,
                    posts_last_1h=posts_last_1h,
                    posts_last_24h=posts_last_24h,
                    last_calculated_at=datetime.now(UTC),
                )
                session.add(metrics)
            else:
                metrics.posts_last_1h = posts_last_1h
                metrics.posts_last_24h = posts_last_24h
                metrics.last_calculated_at = datetime.now(UTC)
            session.commit()
        return violations

    @staticmethod
    def _parse_time(value: Any) -> datetime:
        """Parse a datetime-like value and return an aware UTC datetime."""
        if isinstance(value, datetime):
            # Normalize naive datetimes to UTC and return aware datetime
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value.astimezone(UTC)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _check_automation(
        self, rule: Rule, account_data: dict[str, Any], statuses: list[dict[str, Any]]
    ) -> list[Violation]:
        items = sorted(statuses, key=lambda s: self._parse_time(s["created_at"]), reverse=True)[
            : self.AUTOMATION_WINDOW
        ]
        if not items:
            return []
        texts = [re.sub(r"\d+", "", s.get("content", "")).strip().lower() for s in items]
        counts: dict[str, list[int]] = {}
        for i, text in enumerate(texts):
            counts.setdefault(text, []).append(i)
        duplicates = {i for idxs in counts.values() for i in idxs if len(idxs) > 1}
        automation_percentage = len(duplicates) / len(items)
        times = [self._parse_time(s["created_at"]) for s in items]
        intervals = [abs((times[i] - times[i + 1]).total_seconds()) for i in range(len(times) - 1)]
        avg_interval = sum(intervals) / len(intervals) if intervals else 0
        results: list[Violation] = []
        if not account_data.get("bot") and automation_percentage > 0.5:
            matched_ids = [items[i]["id"] for i in sorted(duplicates) if items[i].get("id")]
            results.append(
                Violation(
                    rule_name=rule.name,
                    score=rule.weight,
                    evidence=Evidence(
                        matched_terms=[],
                        matched_status_ids=matched_ids,
                        metrics={"automation_percentage": automation_percentage, "average_interval": avg_interval},
                    ),
                )
            )
        if account_data.get("bot"):
            now = datetime.now(UTC)
            public_items = [s for s in items if s.get("visibility") not in ("unlisted", "private", "direct")]
            posts_last_hour = sum(
                1 for s in public_items if self._parse_time(s["created_at"]) >= now - timedelta(hours=1)
            )
            posts_last_day = sum(
                1 for s in public_items if self._parse_time(s["created_at"]) >= now - timedelta(days=1)
            )
            if posts_last_hour > 1 or posts_last_day > 24:
                matched_ids = [s["id"] for s in public_items if s.get("id")]
                results.append(
                    Violation(
                        rule_name=rule.name,
                        score=rule.weight,
                        evidence=Evidence(
                            matched_terms=[],
                            matched_status_ids=matched_ids,
                            metrics={"hourly_rate": posts_last_hour, "daily_rate": posts_last_day},
                        ),
                    )
                )
        return results

    def _check_link_spam(self, rule: Rule, statuses: list[dict[str, Any]]) -> list[Violation]:
        items = sorted(statuses, key=lambda s: self._parse_time(s["created_at"]), reverse=True)[: self.LINK_SPAM_WINDOW]
        if len(items) != self.LINK_SPAM_WINDOW:
            return []
        total = len(items)
        domain_counts: dict[str, int] = {}
        content_map: dict[str, list[int]] = {}
        links: list[tuple[int, list[str]]] = []
        for i, status in enumerate(items):
            content = status.get("content", "")
            norm = re.sub(r"\s+", " ", content).strip().lower()
            content_map.setdefault(norm, []).append(i)
            found = re.findall(r"https?://[^\s]+", content)
            if found:
                links.append((i, found))
                for link in found:
                    domain = urlparse(link).netloc
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1
        link_ratio = len(links) / total if total else 0
        repetitive = any(len(idxs) > total / 2 for idxs in content_map.values())
        single_domain = len(domain_counts) == 1
        if link_ratio == 1 and (repetitive or single_domain):
            matched_ids = [items[i]["id"] for i, _ in links if items[i].get("id")]
            return [
                Violation(
                    rule_name=rule.name,
                    score=rule.weight,
                    evidence=Evidence(
                        matched_terms=[],
                        matched_status_ids=matched_ids,
                        metrics={"link_ratio": link_ratio, "domain_distribution": domain_counts},
                    ),
                )
            ]
        return []
