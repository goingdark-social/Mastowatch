"""Scanning API router for content scanning operations."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func

from app.auth import get_api_key
from app.db import SessionLocal
from app.enhanced_scanning import EnhancedScanningSystem
from app.models import ContentScan
from app.schemas import DomainAlert, ScanSession

router = APIRouter()


@router.post("/scan/start", response_model=ScanSession)
async def start_scan_session(session_type: str, api_key: str = Depends(get_api_key)):
    """Start a new scan session."""
    if session_type not in ["remote", "local", "federated"]:
        raise HTTPException(status_code=400, detail="Invalid session type")
    scanner = EnhancedScanningSystem()
    session_id = scanner.start_scan_session(session_type)
    return {"session_id": session_id, "session_type": session_type, "status": "started"}


@router.post("/scan/{session_id}/complete")
async def complete_scan_session(session_id: str, api_key: str = Depends(get_api_key)):
    """Complete a scan session."""
    scanner = EnhancedScanningSystem()
    scanner.complete_scan_session(session_id)
    return {"message": f"Session {session_id} completed"}


@router.get("/scan/accounts", response_model=list[dict[str, Any]])
async def get_next_accounts_to_scan(
    session_type: str, limit: int = 50, cursor: str | None = None, api_key: str = Depends(get_api_key)
):
    """Get the next batch of accounts to scan."""
    scanner = EnhancedScanningSystem()
    accounts, next_cursor = scanner.get_next_accounts_to_scan(session_type, limit, cursor)
    return accounts


@router.post("/scan/account", response_model=dict[str, Any])
async def scan_account_efficiently(account_data: dict[str, Any], session_id: str, api_key: str = Depends(get_api_key)):
    """Scan a single account efficiently."""
    scanner = EnhancedScanningSystem()
    result = scanner.scan_account_efficiently(account_data, session_id)
    return result


@router.get("/scan/federated", response_model=list[dict[str, Any]])
async def scan_federated_content(target_domains: list[str] | None = None, api_key: str = Depends(get_api_key)):
    """Scan federated content."""
    scanner = EnhancedScanningSystem()
    results = scanner.scan_federated_content(target_domains)
    return results


@router.get("/domains/alerts", response_model=list[DomainAlert])
async def get_domain_alerts(limit: int = 100, api_key: str = Depends(get_api_key)):
    """Get domain alerts."""
    scanner = EnhancedScanningSystem()
    alerts = scanner.get_domain_alerts(limit)
    return alerts


@router.post("/scanning/federated", tags=["scanning"])
def trigger_federated_scan(target_domains: list[str] | None = None, api_key: str = Depends(get_api_key)):
    """Trigger federated content scanning."""
    try:
        from app.tasks.jobs import scan_federated_content

        # Start the task
        task = scan_federated_content.delay(target_domains)

        return {"message": "Federated scan initiated", "task_id": task.id, "target_domains": target_domains or "all"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start federated scan: {str(e)}") from e


@router.post("/scanning/domain-check", tags=["scanning"])
def trigger_domain_check(api_key: str = Depends(get_api_key)):
    """Trigger domain violation checking."""
    try:
        from app.tasks.jobs import check_domain_violations

        # Start the task
        task = check_domain_violations.delay()

        return {"message": "Domain check initiated", "task_id": task.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start domain check: {str(e)}") from e


@router.post("/scanning/invalidate-cache", tags=["scanning"])
def invalidate_content_cache(rule_changes: bool = False, time_based: bool = False, api_key: str = Depends(get_api_key)):
    """Invalidate content scan cache."""
    try:
        scanner = EnhancedScanningSystem()

        # Invalidate cache based on parameters
        scanner.invalidate_content_scans(rule_changes=rule_changes, time_based=time_based)

        return {"message": "Content cache invalidated", "rule_changes": rule_changes, "time_based": time_based}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to invalidate cache: {str(e)}") from e


@router.get("/scanning/cache-status", tags=["scanning"])
def get_cache_status(api_key: str = Depends(get_api_key)):
    """Get content cache status and statistics."""
    try:
        with SessionLocal() as db:
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
