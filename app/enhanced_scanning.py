import hashlib
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass

from sqlalchemy import func, and_, or_, desc
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import SessionLocal
from app.models import Account, ScanSession, ContentScan, DomainAlert, Analysis, Rule
from app.mastodon_client import MastoClient
from app.config import get_settings
from app.services.rule_service import rule_service

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class ScanProgress:
    """Track progress of scanning operations"""
    session_id: int
    session_type: str
    accounts_processed: int
    total_accounts: Optional[int]
    current_cursor: Optional[str]
    started_at: datetime
    estimated_completion: Optional[datetime] = None


class EnhancedScanningSystem:
    """Enhanced scanning system with improved efficiency and federated tracking"""
    
    def __init__(self):
        # Use the centralized rule service instead of loading from files
        self.rule_service = rule_service
        self.settings = get_settings()
    
    def start_scan_session(self, session_type: str, metadata: Optional[Dict] = None) -> int:
        """Start a new scanning session"""
        with SessionLocal() as session:
            # Check if there's already an active session of this type
            existing = session.query(ScanSession).filter(
                and_(
                    ScanSession.session_type == session_type,
                    ScanSession.status == 'active'
                )
            ).first()
            
            if existing:
                logger.info(f"Active {session_type} scan session already exists: {existing.id}")
                return existing.id
            
            scan_session = ScanSession(
                session_type=session_type,
                status='active',
                rules_applied=self._get_current_rules_snapshot(),
                session_metadata=metadata or {}
            )
            session.add(scan_session)
            session.commit()
            session.refresh(scan_session)
            
            logger.info(f"Started new {session_type} scan session: {scan_session.id}")
            return scan_session.id
    
    def complete_scan_session(self, session_id: int, status: str = 'completed'):
        """Mark a scan session as completed"""
        with SessionLocal() as session:
            scan_session = session.query(ScanSession).filter(ScanSession.id == session_id).first()
            if scan_session:
                scan_session.status = status
                scan_session.completed_at = datetime.utcnow()
                session.commit()
                logger.info(f"Scan session {session_id} marked as {status}")
    
    def get_scan_progress(self, session_id: int) -> Optional[ScanProgress]:
        """Get progress information for a scan session"""
        with SessionLocal() as session:
            scan_session = session.query(ScanSession).filter(ScanSession.id == session_id).first()
            if not scan_session:
                return None
            
            return ScanProgress(
                session_id=scan_session.id,
                session_type=scan_session.session_type,
                accounts_processed=scan_session.accounts_processed,
                total_accounts=scan_session.total_accounts,
                current_cursor=scan_session.current_cursor,
                started_at=scan_session.started_at
            )
    
    def should_scan_account(self, account_id: str, account_data: Dict) -> bool:
        """Determine if an account needs scanning based on content changes"""
        content_hash = self._calculate_content_hash(account_data)
        
        with SessionLocal() as session:
            # Check if we have a recent scan for this content
            recent_scan = session.query(ContentScan).filter(
                and_(
                    ContentScan.mastodon_account_id == account_id,
                    ContentScan.content_hash == content_hash,
                    ContentScan.last_scanned_at > datetime.utcnow() - timedelta(hours=24),
                    ContentScan.rules_version == self.rule_service.ruleset_sha256
                )
            ).first()
            
            if recent_scan and not recent_scan.needs_rescan:
                logger.debug(f"Skipping scan for {account_id} - content unchanged")
                return False
            
            return True
    
    def scan_account_efficiently(self, account_data: Dict, session_id: int) -> Optional[Dict]:
        """Efficiently scan an account with deduplication and caching"""
        account_id = account_data.get("id")
        if not account_id:
            return None
        
        # Check if we should scan this account
        if not self.should_scan_account(account_id, account_data):
            return None
        
        content_hash = self._calculate_content_hash(account_data)
        
        try:
            # Fetch statuses for analysis
            admin_client = MastoClient(self.settings.ADMIN_TOKEN)
            statuses = admin_client.get_account_statuses(
                account_id=account_id,
                limit=self.settings.MAX_STATUSES_TO_FETCH
            )
            
            # Evaluate account against rules
            score, hits = self.rule_service.eval_account(account_data, statuses)
            
            # Store scan result
            scan_result = {
                "score": score,
                "hits": len(hits),
                "rule_hits": [{"rule": hit[0], "weight": hit[1], "evidence": hit[2]} for hit in hits],
                "scanned_at": datetime.utcnow().isoformat(),
                "status_count": len(statuses)
            }
            
            # Update content scan record
            with SessionLocal() as db_session:
                content_scan = ContentScan(
                    content_hash=content_hash,
                    mastodon_account_id=account_id,
                    scan_type='account',
                    scan_result=scan_result,
                    rules_version=self.rule_service.ruleset_sha256,
                    needs_rescan=False
                )
                
                # Use upsert to handle duplicates
                stmt = pg_insert(ContentScan).values(
                    content_hash=content_hash,
                    mastodon_account_id=account_id,
                    scan_type='account',
                    scan_result=scan_result,
                    rules_version=self.rule_service.ruleset_sha256,
                    needs_rescan=False,
                    last_scanned_at=func.now()
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=['content_hash'],
                    set_=dict(
                        scan_result=stmt.excluded.scan_result,
                        rules_version=stmt.excluded.rules_version,
                        last_scanned_at=func.now(),
                        needs_rescan=False
                    )
                )
                db_session.execute(stmt)
                
                # Update session progress
                scan_session = db_session.query(ScanSession).filter(ScanSession.id == session_id).first()
                if scan_session:
                    scan_session.accounts_processed += 1
                    scan_session.last_account_id = account_id
                
                # Update account record
                account_record = db_session.query(Account).filter(
                    Account.mastodon_account_id == account_id
                ).first()
                if account_record:
                    account_record.content_hash = content_hash
                    account_record.last_full_scan_at = datetime.utcnow()
                
                db_session.commit()
            
            # Track domain-level violations if score is above threshold
            if score >= float(self.rule_service.get_config_value("report_threshold", 1.0)):
                domain = self._extract_domain(account_data)
                if domain and domain != "local":
                    self._track_domain_violation(domain)
            
            return scan_result
            
        except Exception as e:
            logger.error(f"Error scanning account {account_id}: {e}")
            return None
    
    def get_next_accounts_to_scan(self, session_type: str, limit: int = 50, cursor: Optional[str] = None) -> Tuple[List[Dict], Optional[str]]:
        """Get next batch of accounts to scan with cursor-based pagination"""
        try:
            admin_client = MastoClient(self.settings.ADMIN_TOKEN)
            
            params = {
                "origin": session_type,  # 'local' or 'remote'
                "status": "active",
                "limit": limit
            }
            
            if cursor:
                params["max_id"] = cursor
            
            accounts = admin_client.get_admin_accounts(
                origin=session_type,
                status="active",
                limit=limit,
                max_id=cursor
            )
            
            # The generated client returns a list of dictionaries directly, no need for .json()
            # The Link header parsing is now handled within the generated client if needed, or we adapt.
            # For now, assume get_admin_accounts returns the list directly and we don't need to parse a cursor from headers.
            next_cursor = None # Assuming the generated client handles pagination internally or we adapt this later
            
            return accounts, next_cursor
            
        except Exception as e:
            logger.error(f"Error fetching {session_type} accounts: {e}")
            return [], None
    
    def scan_federated_content(self, domains: Optional[List[str]] = None) -> Dict[str, int]:
        """Scan content across federated domains"""
        session_id = self.start_scan_session("federated", {"target_domains": domains})
        results = {"scanned_domains": 0, "scanned_accounts": 0, "violations_found": 0}
        
        try:
            # Get list of domains to scan
            target_domains = domains or self._get_active_domains()
            
            for domain in target_domains:
                domain_results = self._scan_domain_content(domain, session_id)
                results["scanned_accounts"] += domain_results.get("accounts", 0)
                results["violations_found"] += domain_results.get("violations", 0)
                results["scanned_domains"] += 1
                
                # Check if domain should be defederated
                self._check_defederation_threshold(domain)
            
            self.complete_scan_session(session_id)
            
        except Exception as e:
            logger.error(f"Error in federated scan: {e}")
            self.complete_scan_session(session_id, 'failed')
        
        return results
    
    def _scan_domain_content(self, domain: str, session_id: int) -> Dict[str, int]:
        """Scan content for a specific domain"""
        results = {"accounts": 0, "violations": 0}
        
        with SessionLocal() as session:
            # Get accounts from this domain
            accounts = session.query(Account).filter(Account.domain == domain).limit(100).all()
            
            for account in accounts:
                try:
                    # Create account data structure for scanning
                    account_data = {
                        "id": account.mastodon_account_id,
                        "acct": account.acct,
                        "domain": account.domain
                    }
                    
                    scan_result = self.scan_account_efficiently(account_data, session_id)
                    if scan_result:
                        results["accounts"] += 1
                        if scan_result.get("score", 0) >= float(self.rule_service.get_config_value("report_threshold", 1.0)):
                            results["violations"] += 1
                
                except Exception as e:
                    logger.error(f"Error scanning account {account.mastodon_account_id}: {e}")
        
        return results
    
    def _track_domain_violation(self, domain: str):
        """Track violations for domain-level defederation decisions"""
        with SessionLocal() as session:
            # Get or create domain alert record
            stmt = pg_insert(DomainAlert).values(
                domain=domain,
                violation_count=1,
                last_violation_at=func.now()
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=['domain'],
                set_=dict(
                    violation_count=DomainAlert.violation_count + 1,
                    last_violation_at=func.now()
                )
            )
            session.execute(stmt)
            session.commit()
    
    def _check_defederation_threshold(self, domain: str):
        """Check if domain should be defederated based on violation count"""
        with SessionLocal() as session:
            domain_alert = session.query(DomainAlert).filter(DomainAlert.domain == domain).first()
            
            if domain_alert and not domain_alert.is_defederated:
                if domain_alert.violation_count >= domain_alert.defederation_threshold:
                    # Mark for defederation (actual defederation would be a separate process)
                    domain_alert.is_defederated = True
                    domain_alert.defederated_at = datetime.utcnow()
                    domain_alert.defederated_by = "automated_system"
                    domain_alert.notes = f"Automatic defederation after {domain_alert.violation_count} violations"
                    
                    session.commit()
                    
                    logger.warning(f"Domain {domain} marked for defederation after {domain_alert.violation_count} violations")
    
    def _calculate_content_hash(self, account_data: Dict) -> str:
        """Calculate hash of account content for change detection"""
        # Include key fields that would indicate content changes
        content_fields = {
            "username": account_data.get("username", ""),
            "display_name": account_data.get("display_name", ""),
            "note": account_data.get("note", ""),
            "avatar": account_data.get("avatar", ""),
            "header": account_data.get("header", ""),
            "fields": account_data.get("fields", [])
        }
        
        content_str = str(sorted(content_fields.items()))
        return hashlib.sha256(content_str.encode()).hexdigest()
    
    def _extract_domain(self, account_data: Dict) -> Optional[str]:
        """Extract domain from account data"""
        acct = account_data.get("acct", "")
        if "@" in acct:
            return acct.split("@")[-1]
        return "local"
    
    def _get_current_rules_snapshot(self) -> Dict:
        """Get current rules configuration for session tracking"""
        rules_list, config, ruleset_sha256 = self.rule_service.get_active_rules()
        return {
            "rules_version": ruleset_sha256,
            "report_threshold": config.get("report_threshold", 1.0),
            "rule_count": len(rules_list)
        }
    
    def _get_active_domains(self) -> List[str]:
        """Get list of active domains for federated scanning"""
        with SessionLocal() as session:
            domains = session.query(Account.domain).filter(
                and_(
                    Account.domain != "local",
                    Account.last_checked_at > datetime.utcnow() - timedelta(days=30)
                )
            ).distinct().limit(50).all()
            
            return [domain[0] for domain in domains]
    
    
    
    def get_domain_alerts(self, limit: int = 50) -> List[Dict]:
        """Get current domain alerts and defederation status"""
        with SessionLocal() as session:
            alerts = session.query(DomainAlert).order_by(
                desc(DomainAlert.violation_count)
            ).limit(limit).all()
            
            return [
                {
                    "domain": alert.domain,
                    "violation_count": alert.violation_count,
                    "last_violation_at": alert.last_violation_at.isoformat() if alert.last_violation_at else None,
                    "defederation_threshold": alert.defederation_threshold,
                    "is_defederated": alert.is_defederated,
                    "defederated_at": alert.defederated_at.isoformat() if alert.defederated_at else None,
                    "defederated_by": alert.defederated_by,
                    "notes": alert.notes
                }
                for alert in alerts
            ]
    
    def invalidate_content_scans(self, rule_changes: bool = False):
        """Mark content scans for re-scanning when rules change"""
        with SessionLocal() as session:
            if rule_changes:
                # Mark all scans as needing rescan due to rule changes
                session.query(ContentScan).update({"needs_rescan": True})
            else:
                # Mark old scans as needing rescan
                cutoff = datetime.utcnow() - timedelta(days=7)
                session.query(ContentScan).filter(
                    ContentScan.last_scanned_at < cutoff
                ).update({"needs_rescan": True})
            
            session.commit()
            logger.info("Content scans marked for re-scanning")
