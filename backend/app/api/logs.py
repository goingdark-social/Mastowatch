"""Audit log inspection endpoints."""

from app.db import get_db
from app.models import AuditLog
from app.oauth import User, require_admin_hybrid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/logs", tags=["logs"])
def list_logs(
    account_id: str | None = Query(None),
    rule_id: int | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    user: User = Depends(require_admin_hybrid),
    session: Session = Depends(get_db),
):
    """List audit log entries."""
    query = session.query(AuditLog).order_by(AuditLog.timestamp.desc())
    if account_id:
        query = query.filter(AuditLog.target_account_id == account_id)
    if rule_id:
        query = query.filter(AuditLog.triggered_by_rule_id == rule_id)
    logs = query.limit(limit).all()
    return [
        {
            "id": log.id,
            "action_type": log.action_type,
            "triggered_by_rule_id": log.triggered_by_rule_id,
            "target_account_id": log.target_account_id,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "evidence": log.evidence,
            "api_response": log.api_response,
        }
        for log in logs
    ]
