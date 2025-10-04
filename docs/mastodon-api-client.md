# Mastodon API Client Integration

**⚠️ DEPRECATED**: This document describes the old MastoClient wrapper that has been removed.

**Please refer to [mastodon-py-integration.md](mastodon-py-integration.md) for current Mastodon API usage.**

## Migration Complete

As of this version, MastoWatch has fully migrated to using the official `mastodon.py` library through the `MastodonService` wrapper. The old OpenAPI-generated `MastoClient` and `app/clients/mastodon/` have been removed.

All Mastodon API operations now go through `MastodonService` in `backend/app/services/mastodon_service.py`.

See [mastodon-py-integration.md](mastodon-py-integration.md) for complete documentation on the current implementation.
