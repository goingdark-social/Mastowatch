# Mastodon API Client Integration

**⚠️ DEPRECATED**: This document describes the old MastoClient wrapper that has been removed.

**Please refer to [mastodon-py-integration.md](mastodon-py-integration.md) for current Mastodon API usage.**

## Migration Complete

As of this version, MastoWatch has fully migrated to using the official `mastodon.py` library through the `MastodonService` wrapper. The old OpenAPI-generated `MastoClient` and `app/clients/mastodon/` have been removed.

All Mastodon API operations now go through `MastodonService` in `backend/app/services/mastodon_service.py`.

See [mastodon-py-integration.md](mastodon-py-integration.md) for complete documentation on the current implementation.
)
for status in statuses:
    print(f"Status {status['id']}: {len(status['content'])} characters")
```

### Report Creation
```python
report = client.create_report(
    account_id="123456",
    comment="Automated report based on rule violations",
    status_ids=["789", "101112"],
    category="violation",
    forward=True,
    rule_ids=["rule_1", "rule_2"],
)
print(f"Report created with ID: {report['id']}")
```

### Admin Operations
```python
accounts, next_max_id = client.get_admin_accounts(origin="remote", limit=100)
```

## Management Commands

### Script Commands
```bash
# Show current status
./scripts/mastodon_api.sh status

# Update submodule and copy latest schema
./scripts/mastodon_api.sh update-schema

# Regenerate Python client from current schema
./scripts/mastodon_api.sh regenerate

# Full update: submodule + schema + client
./scripts/mastodon_api.sh update
```

### Makefile Targets
```bash
# Show API client status
make api-client-status

# Update schema from submodule
make update-api-spec

# Regenerate client
make regenerate-client

# Full update
make update-mastodon-client
```

## Client Usage

### Basic Usage

```python
from app.mastodon_client import MastoClient

admin = MastoClient(settings.ADMIN_TOKEN)
bot = MastoClient(settings.BOT_TOKEN)
```

### Common Operations

```python
account = admin.get_account(account_id)
statuses = admin.get_account_statuses(account_id, limit=40)
report = bot.create_report(
    account_id=account_id,
    comment="Automated moderation report",
    status_ids=status_ids,
)
print(account["username"], report["id"])
```

### Benefits

- ✅ **Generated Models**: Uses typed OpenAPI client internally
- ✅ **Fewer Errors**: No more `.json()` typos or missing fields
- ✅ **Better Documentation**: Types serve as documentation
- ✅ **Easier Refactoring**: Type-aware code transformations
- ✅ **Admin Coverage**: Helper methods handle endpoints outside the OpenAPI spec

## Automation

### Submodule Updates

The abraham/mastodon-openapi repository is automatically updated weekly via GitHub Actions. To get these updates:

1. **Manual update:**
   ```bash
   make update-api-spec
   ```

2. **CI/CD automation** (see `.github/workflows/` for examples)

### Version Tracking

- **Submodule commit** tracks exact API specification version
- **Generated client** reflects the capabilities at generation time
- **Schema backup** created automatically before updates

## Troubleshooting

### Common Issues

1. **Missing admin endpoints:**
   - Admin endpoints may not be in the community OpenAPI spec
   - Add a helper method to `MastoClient`
   - Contribute missing endpoints to abraham/mastodon-openapi

2. **Generation warnings:**
   - Some endpoints may have parsing issues in the generator
   - Check `/tmp/openapi-generate.log` for details
   - Usually safe to ignore, client still works

3. **Submodule issues:**
   ```bash
   # Re-initialize submodule
   git submodule update --init --recursive
   
   # Force update to latest
   git submodule update --remote --force
   ```

### Debugging

1. **Check status:**
   ```bash
   make api-client-status
   ```

2. **Verbose generation:**
   ```bash
   openapi-python-client generate --path specs/openapi.json --meta none --verbose
   ```

3. **Validate schema:**
   ```bash
   python -m json.tool specs/openapi.json > /dev/null
   ```

## Contributing

### Adding New Endpoints

1. **Check if endpoint exists** in generated client
2. **Add to MastoClient** if available in OpenAPI spec
3. **Add a helper method** if admin-only or missing from spec
4. **Consider contributing** missing endpoints to abraham/mastodon-openapi

### Schema Updates

1. **Test with latest schema:**
   ```bash
   make update-mastodon-client
   python -m pytest tests/
   ```

2. **Update type annotations** if API changes
3. **Add backward compatibility** for breaking changes
4. **Document migration steps** for major changes

## Future Improvements

- [ ] Complete admin endpoint coverage in community OpenAPI spec
- [ ] Automated weekly submodule updates via CI/CD
- [ ] Integration testing against live Mastodon instances
- [ ] Further refine the consolidated `MastoClient` as the single API interface
- [ ] Generated client caching and optimization
