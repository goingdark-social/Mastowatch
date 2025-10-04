# API Client Usage Guide

**⚠️ DEPRECATED**: This document describes the old OpenAPI-generated client that has been removed.

**Please refer to [mastodon-py-integration.md](mastodon-py-integration.md) for current Mastodon API usage.**

## Migration Complete

MastoWatch now exclusively uses the official `mastodon.py` library through the `MastodonService` wrapper. 

All Mastodon API operations should go through `MastodonService`:

```python
from app.services.mastodon_service import mastodon_service

# Get account information
account = await mastodon_service.get_account(
    account_id="123456",
    use_admin=True
)

# Create a report
report = await mastodon_service.create_report(
    account_id="12345",
    status_ids=["67890"],
    comment="Automated moderation report"
)
```

See [mastodon-py-integration.md](mastodon-py-integration.md) for complete documentation.

## Scanning

`GET /scan/accounts` returns a page of accounts to analyze.

```http
GET /scan/accounts?session_type=remote&limit=50&cursor=12345
```

Response:

```json
{
  "accounts": [{"id": "1"}],
  "next_cursor": "67890"
}
```

Send the `next_cursor` value in the query string to request the following page.
