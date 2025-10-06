"""Utility functions for hashing and data processing."""

import hashlib
import json


def make_dedupe_key(account_id: str, status_ids, policy_version: str, ruleset_sha: str, evidence: dict):
    base = {
        "account_id": account_id,
        "status_ids": sorted(status_ids or []),
        "policy_version": policy_version,
        "ruleset_sha": ruleset_sha,
        "evidence": evidence,
    }
    norm = json.dumps(base, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()
