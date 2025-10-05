import logging
from datetime import UTC, datetime, timedelta

from app.db import SessionLocal
from app.models import Account, Analysis, ContentScan, Report
from app.oauth import User, require_admin_hybrid
from app.services.rule_service import rule_service
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/analytics/overview", tags=["analytics"])
def get_analytics_overview(_: User = Depends(require_admin_hybrid)):
    """Get overview metrics for the dashboard"""
    try:
        with SessionLocal() as db:
            # Time ranges
            now = datetime.now(UTC)
            last_24h = now - timedelta(hours=24)
            now - timedelta(days=7)
            now - timedelta(days=30)

            # Total counts
            total_accounts = db.query(func.count(Account.id)).scalar() or 0
            total_analyses = db.query(func.count(Analysis.id)).scalar() or 0
            total_reports = db.query(func.count(Report.id)).scalar() or 0

            # Recent activity (last 24h)
            recent_analyses = db.query(func.count(Analysis.id)).filter(Analysis.created_at >= last_24h).scalar() or 0
            recent_reports = db.query(func.count(Report.id)).filter(Report.created_at >= last_24h).scalar() or 0

            # Rule effectiveness (analyses by rule)
            rule_stats = (
                db.query(
                    Analysis.rule_key,
                    func.count(Analysis.id).label("count"),
                    func.avg(Analysis.score).label("avg_score"),
                )
                .group_by(Analysis.rule_key)
                .all()
            )

            # Top domains with most activity
            domain_stats = (
                db.query(Account.domain, func.count(Analysis.id).label("analysis_count"))
                .join(Analysis, Account.mastodon_account_id == Analysis.mastodon_account_id)
                .group_by(Account.domain)
                .order_by(desc("analysis_count"))
                .limit(10)
                .all()
            )

            return {
                "totals": {"accounts": total_accounts, "analyses": total_analyses, "reports": total_reports},
                "recent_24h": {"analyses": recent_analyses, "reports": recent_reports},
                "rules": [
                    {
                        "rule_key": rule.rule_key,
                        "count": rule.count,
                        "avg_score": float(rule.avg_score) if rule.avg_score else 0,
                    }
                    for rule in rule_stats
                ],
                "top_domains": [
                    {"domain": domain.domain, "analysis_count": domain.analysis_count} for domain in domain_stats
                ],
            }
    except Exception as e:
        logger.error("Failed to fetch analytics overview", extra={"error": str(e), "error_type": type(e).__name__})
        raise HTTPException(
            status_code=500, detail={"error": "analytics_fetch_failed", "message": "Failed to fetch analytics overview"}
        )


@router.get("/analytics/timeline", tags=["analytics"])
def get_analytics_timeline(days: int = 7, _: User = Depends(require_admin_hybrid)):
    """Get timeline data for analyses and reports"""
    try:
        if days < 1 or days > 365:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_days_parameter", "message": "Days parameter must be between 1 and 365"},
            )

        with SessionLocal() as db:
            end_date = datetime.now(UTC)
            start_date = end_date - timedelta(days=days)

            # Daily analysis counts
            daily_analyses = (
                db.query(func.date(Analysis.created_at).label("date"), func.count(Analysis.id).label("count"))
                .filter(Analysis.created_at >= start_date)
                .group_by(func.date(Analysis.created_at))
                .order_by("date")
                .all()
            )

            # Daily report counts
            daily_reports = (
                db.query(func.date(Report.created_at).label("date"), func.count(Report.id).label("count"))
                .filter(Report.created_at >= start_date)
                .group_by(func.date(Report.created_at))
                .order_by("date")
                .all()
            )

            return {
                "analyses": [{"date": str(item.date), "count": item.count} for item in daily_analyses],
                "reports": [{"date": str(item.date), "count": item.count} for item in daily_reports],
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to fetch analytics timeline", extra={"error": str(e), "error_type": type(e).__name__, "days": days}
        )
        raise HTTPException(
            status_code=500, detail={"error": "timeline_fetch_failed", "message": "Failed to fetch analytics timeline"}
        )


@router.get("/analytics/accounts", tags=["analytics"])
def get_account_details(limit: int = 50, offset: int = 0, _: User = Depends(require_admin_hybrid)):
    """Get detailed account information with analysis counts"""
    with SessionLocal() as db:
        accounts = (
            db.query(
                Account,
                func.count(Analysis.id).label("analysis_count"),
                func.count(Report.id).label("report_count"),
                func.max(Analysis.created_at).label("last_analysis"),
            )
            .outerjoin(Analysis, Account.mastodon_account_id == Analysis.mastodon_account_id)
            .outerjoin(Report, Account.mastodon_account_id == Report.mastodon_account_id)
            .group_by(Account.id)
            .order_by(desc("analysis_count"))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "accounts": [
                {
                    "id": acc.Account.id,
                    "mastodon_account_id": acc.Account.mastodon_account_id,
                    "acct": acc.Account.acct,
                    "domain": acc.Account.domain,
                    "last_checked_at": acc.Account.last_checked_at.isoformat() if acc.Account.last_checked_at else None,
                    "analysis_count": acc.analysis_count or 0,
                    "report_count": acc.report_count or 0,
                    "last_analysis": acc.last_analysis.isoformat() if acc.last_analysis else None,
                }
                for acc in accounts
            ]
        }


@router.get("/analytics/reports", tags=["analytics"])
def get_report_details(limit: int = 50, offset: int = 0, _: User = Depends(require_admin_hybrid)):
    """Get detailed report information"""
    with SessionLocal() as db:
        reports = (
            db.query(Report, Account.acct, Account.domain)
            .join(Account, Report.mastodon_account_id == Account.mastodon_account_id)
            .order_by(desc(Report.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "reports": [
                {
                    "id": report.Report.id,
                    "mastodon_account_id": report.Report.mastodon_account_id,
                    "account": f"{report.acct}@{report.domain}",
                    "status_id": report.Report.status_id,
                    "mastodon_report_id": report.Report.mastodon_report_id,
                    "comment": report.Report.comment,
                    "created_at": report.Report.created_at.isoformat(),
                }
                for report in reports
            ]
        }


@router.get("/analytics/analyses/{account_id}", tags=["analytics"])
def get_account_analyses(account_id: str, limit: int = 50, offset: int = 0, _: User = Depends(require_admin_hybrid)):
    """Get detailed analysis information for a specific account including scan data"""
    with SessionLocal() as db:
        # Get traditional analyses
        analyses = (
            db.query(Analysis)
            .filter(Analysis.mastodon_account_id == account_id)
            .order_by(desc(Analysis.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        # Get content scans
        content_scans = (
            db.query(ContentScan)
            .filter(ContentScan.mastodon_account_id == account_id)
            .order_by(desc(ContentScan.last_scanned_at))
            .limit(limit // 2)  # Get fewer of these to avoid overwhelming
            .all()
        )

        # Convert traditional analyses
        traditional_analyses = [
            {
                "id": analysis.id,
                "status_id": analysis.status_id,
                "rule_key": analysis.rule_key,
                "score": float(analysis.score),
                "evidence": analysis.evidence,
                "created_at": analysis.created_at.isoformat(),
                "scan_type": "traditional",
            }
            for analysis in analyses
        ]

        # Convert content scans
        scans = [
            {
                "id": scan.id,
                "status_id": scan.status_id,
                "content_hash": scan.content_hash,
                "scan_type": scan.scan_type,
                "scan_result": scan.scan_result,
                "rules_version": scan.rules_version,
                "last_scanned_at": scan.last_scanned_at.isoformat() if scan.last_scanned_at else None,
                "needs_rescan": scan.needs_rescan,
                "rule_key": "scan",
                "score": scan.scan_result.get("total_score", 0.0) if scan.scan_result else 0.0,
                "evidence": scan.scan_result,
                "created_at": scan.last_scanned_at.isoformat() if scan.last_scanned_at else None,
            }
            for scan in content_scans
        ]

        # Combine and sort by date
        all_analyses = traditional_analyses + scans
        all_analyses.sort(key=lambda x: x["created_at"] or "", reverse=True)

        return {"analyses": all_analyses[:limit]}


@router.get("/analytics/scanning", tags=["analytics"])
def get_scanning_analytics(_: User = Depends(require_admin_hybrid)):
    """Get real-time scanning analytics and job tracking"""
    try:
        import redis
        from app.config import get_settings
        from app.models import ScanSession
        from app.scanning import ScanningSystem

        ScanningSystem()
        settings = get_settings()

        # Get active jobs from Redis/RQ
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)

        # Get RQ queue length (RQ uses different queue naming than Celery)
        # Note: RQ jobs are tracked differently - see /jobs/* endpoints for details
        r.llen("default")

        with SessionLocal() as db:
            # Get active scan sessions
            active_sessions = db.query(ScanSession).filter(ScanSession.status == "active").all()

            # Get recent completed sessions
            recent_sessions = (
                db.query(ScanSession)
                .filter(ScanSession.completed_at.isnot(None))
                .order_by(desc(ScanSession.completed_at))
                .limit(5)
                .all()
            )

            # Get last federated scan and domain check times
            (
                db.query(ScanSession.completed_at)
                .filter(ScanSession.session_type == "federated", ScanSession.status == "completed")
                .order_by(desc(ScanSession.completed_at))
                .first()
            )

            (
                db.query(ScanSession.completed_at)
                .filter(ScanSession.session_type == "domain_check", ScanSession.status == "completed")
                .order_by(desc(ScanSession.completed_at))
                .first()
            )

            # Get content scan statistics
            content_scan_stats = db.query(
                func.count(ContentScan.id).label("total_scans"),
                func.count(ContentScan.id).filter(ContentScan.needs_rescan).label("needs_rescan"),
                func.max(ContentScan.last_scanned_at).label("last_scan"),
            ).first()

            return {
                "active_sessions": [
                    {
                        "id": session.id,
                        "session_type": session.session_type,
                        "accounts_processed": session.accounts_processed,
                        "total_accounts": session.total_accounts,
                        "started_at": session.started_at.isoformat(),
                        "current_cursor": getattr(session, "current_cursor", None),
                    }
                    for session in active_sessions
                ],
                "recent_sessions": [
                    {
                        "id": session.id,
                        "session_type": session.session_type,
                        "accounts_processed": session.accounts_processed,
                        "started_at": session.started_at.isoformat() if session.started_at else None,
                        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
                        "status": "completed",  # These are all completed sessions
                    }
                    for session in recent_sessions
                ],
                "content_scan_stats": {
                    "total_scans": content_scan_stats.total_scans or 0,
                    "needs_rescan": content_scan_stats.needs_rescan or 0,
                    "last_scan": content_scan_stats.last_scan.isoformat() if content_scan_stats.last_scan else None,
                },
            }

    except Exception as e:
        logger.error("Failed to fetch scanning analytics", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to fetch scanning analytics")


@router.get("/analytics/domains", tags=["analytics"])
def get_domain_analytics(_: User = Depends(require_admin_hybrid)):
    """Get domain analytics and federated scanning results"""
    try:
        from app.models import DomainAlert

        with SessionLocal() as db:
            # Get domain alerts
            domain_alerts = db.query(DomainAlert).order_by(desc(DomainAlert.violation_count)).limit(50).all()

            # Get domain statistics from accounts
            domain_stats = (
                db.query(
                    Account.domain,
                    func.count(Account.id).label("account_count"),
                    func.count(Analysis.id).label("analysis_count"),
                )
                .outerjoin(Analysis, Account.mastodon_account_id == Analysis.mastodon_account_id)
                .group_by(Account.domain)
                .order_by(desc("analysis_count"))
                .limit(20)
                .all()
            )

            # Calculate summary statistics
            total_domains = len(domain_stats)
            defederated_domains = sum(1 for alert in domain_alerts if alert.is_defederated)
            high_risk_domains = len(
                [alert for alert in domain_alerts if not alert.is_defederated and alert.violation_count > 0]
            )
            monitored_domains = total_domains

            return {
                "summary": {
                    "total_domains": total_domains,
                    "defederated_domains": defederated_domains,
                    "high_risk_domains": high_risk_domains,
                    "monitored_domains": monitored_domains,
                },
                "domain_alerts": [
                    {
                        "domain": alert.domain,
                        "violation_count": alert.violation_count,
                        "last_violation_at": alert.last_violation_at.isoformat() if alert.last_violation_at else None,
                        "defederation_threshold": 10,  # Default threshold, could be configurable
                        "is_defederated": alert.is_defederated,
                        "defederated_at": alert.defederated_at.isoformat() if alert.defederated_at else None,
                    }
                    for alert in domain_alerts
                ],
                "domain_stats": [
                    {
                        "domain": stat.domain,
                        "account_count": stat.account_count,
                        "analysis_count": stat.analysis_count or 0,
                    }
                    for stat in domain_stats
                ],
            }
    except Exception as e:
        logger.error("Failed to fetch domain analytics", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to fetch domain analytics") from e


@router.get("/analytics/rules/statistics", tags=["analytics"])
def get_rule_statistics(user: User = Depends(require_admin_hybrid)):
    """Get comprehensive rule statistics and performance metrics."""
    try:
        rule_stats = rule_service.get_rule_statistics()
        return rule_stats
    except Exception as e:
        logger.error("Failed to fetch rule statistics", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to fetch rule statistics") from e
