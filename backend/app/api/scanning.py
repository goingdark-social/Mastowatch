"""API router for content scanning operations."""

from typing import Any

from app.auth import require_api_key
from app.db import get_db
from app.models import ContentScan
from app.oauth import User, require_admin_hybrid
from app.scanning import ScanningSystem
from app.schemas import AccountsPage
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

router = APIRouter()


@router.post("/scan/start")
def start_scan_session(session_type: str, user: User = Depends(require_admin_hybrid)):
    """Start a new scan session."""
    if session_type not in ["remote", "local", "federated"]:
        raise HTTPException(status_code=400, detail="Invalid session type")
    scanner = ScanningSystem()
    session_id = scanner.start_scan_session(session_type)
    return {"session_id": session_id, "session_type": session_type, "status": "started"}


@router.post("/scan/{session_id}/complete")
def complete_scan_session(session_id: str, user: User = Depends(require_api_key)):
    """Complete a scan session."""
    scanner = ScanningSystem()
    scanner.complete_scan_session(session_id)
    return {"message": f"Session {session_id} completed"}


@router.get("/scan/accounts", response_model=AccountsPage)
def get_next_accounts_to_scan(
    session_type: str, limit: int = 50, cursor: str | None = None, user: User = Depends(require_api_key)
):
    """Get the next batch of accounts to scan."""
    scanner = ScanningSystem()
    accounts, next_cursor = scanner.get_next_accounts_to_scan(session_type, limit, cursor)
    return {"accounts": accounts, "next_cursor": next_cursor}


@router.post("/scan/account", response_model=dict[str, Any])
def scan_account_efficiently(
    account_data: dict[str, Any], session_id: str, user: User = Depends(require_api_key)
):
    """Scan a single account efficiently."""
    scanner = ScanningSystem()
    result = scanner.scan_account_efficiently(account_data, session_id)
    return result


@router.get("/scan/federated", response_model=list[dict[str, Any]])
def scan_federated_content(target_domains: list[str] | None = None, user: User = Depends(require_api_key)):
    """Scan federated content."""
    scanner = ScanningSystem()
    results = scanner.scan_federated_content(target_domains)
    return results


@router.get("/domains/alerts")
def get_domain_alerts(limit: int = 100, user: User = Depends(require_api_key)):
    """Get domain alerts."""
    scanner = ScanningSystem()
    alerts = scanner.get_domain_alerts(limit)
    return alerts


@router.post("/scanning/federated", tags=["scanning"])
def trigger_federated_scan(target_domains: list[str] | None = None, user: User = Depends(require_api_key)):
    """Trigger federated content scanning."""
    try:
        from app.tasks.jobs import scan_federated_content

        # Start the task
        task = scan_federated_content.delay(target_domains)

        return {"message": "Federated scan initiated", "task_id": task.id, "target_domains": target_domains or "all"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start federated scan: {str(e)}") from e


@router.post("/scanning/domain-check", tags=["scanning"])
def trigger_domain_check(user: User = Depends(require_admin_hybrid)):
    """Trigger domain violation checking."""
    try:
        from app.tasks.jobs import check_domain_violations

        # Start the task
        task = check_domain_violations.delay()

        return {"message": "Domain check initiated", "task_id": task.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start domain check: {str(e)}") from e


@router.post("/scanning/invalidate-cache", tags=["scanning"])
def invalidate_content_cache(rule_changes: bool = False, user: User = Depends(require_admin_hybrid)):
    """Invalidate content scan cache."""
    try:
        scanner = ScanningSystem()

        # Invalidate cache based on parameters
        scanner.invalidate_content_scans(rule_changes=rule_changes)

        return {"message": "Content cache invalidated", "rule_changes": rule_changes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to invalidate cache: {str(e)}") from e


@router.get("/scanning/cache-status", tags=["scanning"])
def get_cache_status(db: Session = Depends(get_db), user: User = Depends(require_admin_hybrid)):
    """Get content cache status and statistics."""
    try:
        total_scans = db.query(func.count(ContentScan.id)).scalar() or 0
        needs_rescan = db.query(func.count(ContentScan.id)).filter(ContentScan.needs_rescan.is_(True)).scalar() or 0
        last_scan = db.query(func.max(ContentScan.last_scanned_at)).scalar()

        return {
            "total_cached_scans": total_scans,
            "needs_rescan": needs_rescan,
            "cache_hit_rate": (total_scans - needs_rescan) / total_scans if total_scans > 0 else 0,
            "last_scan": last_scan.isoformat() if last_scan else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cache status: {str(e)}") from e
