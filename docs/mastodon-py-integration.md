# Mastodon.py Library Integration

This document describes the integration of the official [mastodon.py](https://github.com/halcy/mastodon.py) library into MastoWatch.

## Overview

MastoWatch uses the official `mastodon.py` library for all Mastodon API operations, providing better reliability, community support, and built-in features like rate limiting and OAuth handling.

## Architecture

```
┌─────────────────────────────────────────────┐
│         Application Code                     │
│  (auth.py, oauth.py, scanning.py, etc.)    │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌──────────────────────┐
│  MastodonService     │
│  (mastodon.py)       │
└──────────┬───────────┘
           │
           ▼
    ┌──────────────┐
    │ mastodon.py  │
    │   Library    │
    └──────────────┘
```

## MastodonService Wrapper

The `MastodonService` class in `backend/app/services/mastodon_service.py` provides a centralized interface to mastodon.py with the following features:

### Key Features

- **Client Caching**: Reuses clients with the same access token to avoid unnecessary instantiation
- **Synchronous Architecture**: Direct synchronous calls to mastodon.py (no async overhead)
- **Rate Limiting**: Uses mastodon.py's built-in rate limiting (`ratelimit_method="wait"`)
- **Error Handling**: Catches and logs `MastodonAPIError` and `MastodonNetworkError`
- **Singleton Pattern**: Global `mastodon_service` instance for easy access

### Usage Example

```python
from app.services.mastodon_service import mastodon_service

# OAuth token exchange
token_info = mastodon_service.exchange_oauth_code(
    code="authorization_code",
    redirect_uri="https://example.com/callback"
)

# Verify credentials
account = mastodon_service.verify_credentials(access_token)

# Get account information
account = mastodon_service.get_account(account_id="12345")

# Create a report
report = mastodon_service.create_report(
    account_id="12345",
    status_ids=["67890"],
    comment="Automated moderation report",
    forward=False
)
```

## Available Methods

### Authentication

- `exchange_oauth_code(code, redirect_uri)` - Exchange OAuth code for access token using official `log_in()` method
- `verify_credentials(access_token)` - Verify and get account info

### Account Operations

- `get_account(account_id)` - Get account information
- `get_account_statuses(account_id, limit=20, ...)` - Get account statuses
- `get_admin_accounts(origin=None, status=None, ...)` - List admin accounts (uses v2 API)

### Moderation

- `create_report(account_id, status_ids=None, ...)` - Create moderation report
- `admin_suspend_account(account_id)` - Suspend an account (admin)
- `admin_create_domain_block(domain, severity="suspend", ...)` - Block a domain (admin)

### Instance Info

- `get_instance_info()` - Get instance information (auto-selects latest API version)
- `get_instance_rules()` - Get instance rules

### Sync Wrappers for Background Workers

These methods run synchronously for use in RQ background jobs:

- `admin_account_action_sync(account_id, action_type, text=None, warning_preset_id=None)` - Moderate account (warn, silence, suspend)
- `admin_unsilence_account_sync(account_id)` - Remove silence from account
- `admin_unsuspend_account_sync(account_id)` - Remove suspension from account
- `create_report_sync(account_id, status_ids=None, ...)` - Create report synchronously

### Client Access

- `get_client(access_token=None)` - Get a configured Mastodon client
- `get_admin_client()` - Get client with admin credentials
- `get_bot_client()` - Get client with bot credentials

## Migration Status

### ✅ Complete Migration to mastodon.py

All Mastodon API operations have been migrated to use the official mastodon.py library with correct method names:

- [x] OAuth token exchange (using `log_in()` method)
- [x] Credential verification
- [x] User authentication
- [x] Account fetching
- [x] Report creation
- [x] Admin operations (using `admin_account_moderate()` for moderation actions)
- [x] All moderation actions
- [x] Instance info (using non-versioned methods that auto-select latest API)

The old `MastoClient` (OpenAPI-generated wrapper) and `app/clients/mastodon/` directory have been removed. All code now uses `MastodonService` exclusively.

### Recent Updates (2025-01)

The following improvements have been made to the mastodon.py integration:

1. **OAuth Code Exchange**: Now uses public `log_in()` method instead of private `_Mastodon__api_request`
2. **Admin Moderation**: Changed from non-existent `admin_account_action_v2` to correct `admin_account_moderate`
3. **Domain Blocking**: Changed from non-existent `admin_create_domain_block_v2` to correct `admin_create_domain_block`
4. **Instance Methods**: Use non-versioned `instance()` and `instance_rules()` instead of explicit `_v2` variants, allowing automatic API version selection
5. **Fully Synchronous Architecture**: Removed all async/await wrappers and `asyncio` usage - all methods now directly call mastodon.py synchronously, eliminating overhead while FastAPI automatically handles concurrency via threadpool
6. **RQ Job System**: Replaced Celery with RQ (Redis Queue) for simpler, more observable background job processing with built-in dashboard and API management

## Configuration

No special configuration is needed. The service reads from the existing settings:

```python
# Settings used by MastodonService
INSTANCE_BASE = "https://mastodon.social"
OAUTH_CLIENT_ID = "your_client_id"
OAUTH_CLIENT_SECRET = "your_client_secret"
MASTODON_CLIENT_SECRET = "admin_access_token"
MASTODON_CLIENT_SECRET = "bot_access_token"
USER_AGENT = "MastoWatch/1.0"
HTTP_TIMEOUT = 30.0
```

## Error Handling

The service catches and re-raises mastodon.py exceptions:

```python
from mastodon import MastodonAPIError, MastodonNetworkError

try:
    account = mastodon_service.verify_credentials(token)
except MastodonAPIError as e:
    # API returned an error (4xx, 5xx)
    logger.error(f"API error: {e}")
except MastodonNetworkError as e:
    # Network issue
    logger.error(f"Network error: {e}")
```

## Testing

The mastodon.py integration is tested through existing test suites:

```bash
# Run OAuth/auth tests
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest tests/test_authentication_authorization.py

# Run all tests
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest
```

All tests pass with the mastodon.py integration.

## Performance Considerations

### Client Caching

The service caches Mastodon client instances to avoid repeated instantiation:

```python
# Cached internally - only created once per unique token
client1 = mastodon_service.get_client("token_abc")
client2 = mastodon_service.get_client("token_abc")  # Returns cached instance
```

### Rate Limiting

mastodon.py handles rate limiting automatically:

- Waits when rate limit is hit
- Retries failed requests
- Respects `X-RateLimit-*` headers

This means you don't need manual throttling when using MastodonService.

## FastAPI Integration

MastodonService methods are synchronous and can be called directly from FastAPI endpoints. FastAPI automatically runs synchronous route handlers in a threadpool, providing proper concurrency:

```python
@router.get("/account/{account_id}")
def get_account(account_id: str):
    """Get account information - FastAPI handles threading automatically."""
    return mastodon_service.get_account(account_id)
```

For long-running operations, queue them to RQ workers instead:

```python
@router.post("/scan/account")
def scan_account(account_id: str):
    """Queue account scan - returns immediately."""
    from app.jobs.tasks import analyze_and_maybe_report
    from app.jobs.worker import get_queue
    
    queue = get_queue()
    job = queue.enqueue(analyze_and_maybe_report, {"account_id": account_id})
    return {"status": "queued", "job_id": job.id}
```

## References

- [mastodon.py GitHub](https://github.com/halcy/mastodon.py)
- [mastodon.py Documentation](https://mastodonpy.readthedocs.io/)
- [Mastodon API Documentation](https://docs.joinmastodon.org/api/)

## Troubleshooting

### OAuth Errors

If you see OAuth-related errors, check:

1. `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET` are set correctly
2. Redirect URI matches exactly (including trailing slashes)
3. Scopes are appropriate for the operation

### Rate Limiting

mastodon.py waits automatically when rate limited. If you see delays:

1. This is expected behavior
2. The library respects server rate limits
3. Consider caching results when possible

### Import Errors

If `from mastodon import Mastodon` fails:

```bash
pip install Mastodon.py
```

The library should be installed automatically via `requirements.txt`.
