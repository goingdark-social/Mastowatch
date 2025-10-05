# Mastodon API Compliance Checker

## Overview

The API compliance checker (`scripts/check_api_compliance.py`) is an automated tool that validates all Mastodon API calls in the codebase against the official `mastodon.py` library specification. This ensures 100% API compatibility and helps catch issues before they reach production.

## Why This Matters

**Historical Context**: We previously experienced critical bugs due to API misuse:
- Using non-existent methods like `client.get_admin_accounts()` (test helpers leaked into production)
- Passing `None` as parameter values instead of omitting them
- Using deprecated methods (`admin_accounts` vs `admin_accounts_v2`)
- Incorrect parameter names or types

These issues caused:
- ❌ Network timeouts and retry loops
- ❌ 403 Forbidden errors
- ❌ Silent failures and confusing error logs
- ❌ Performance degradation (2-3x slower due to retries)

## What It Checks

The compliance checker validates:

1. **Method Existence**: All called methods exist in `mastodon.py`
2. **Parameter Names**: All parameters match the official signature
3. **Deprecated APIs**: Warns about deprecated methods with migration guidance
4. **Known Issues**: Catches specific API version problems

## Usage

### Local Development

```bash
# Quick check (recommended before commits)
make api-compliance

# Verbose output (shows all API calls found)
make api-compliance-verbose
python3 scripts/check_api_compliance.py --verbose

# List all available Mastodon.py methods
python3 scripts/check_api_compliance.py --list-methods
```

### CI/CD Integration

The checker runs automatically on:
- ✅ Every push to `main` branch
- ✅ Every pull request
- ✅ Manual workflow dispatch

**Workflow**: `.github/workflows/api-compliance.yml`

The CI job will **fail the build** if any compliance errors are found, preventing bad code from being merged.

## Output Examples

### ✅ Success (All Compliant)

```
🔍 Scanning /path/to/Mastowatch for Mastodon API calls...
📊 Found 23 Mastodon API calls

================================================================================
MASTODON API COMPLIANCE REPORT
================================================================================

✅ All Mastodon API calls are compliant!
   Checked 261 available methods
```

### ❌ Failure (Issues Found)

```
🔍 Scanning /path/to/Mastowatch for Mastodon API calls...
📊 Found 26 Mastodon API calls

================================================================================
MASTODON API COMPLIANCE REPORT
================================================================================

❌ 4 ERRORS FOUND:

1. ERROR: unknown_method
   File: backend/app/scanning.py:170
   Function: get_next_accounts_to_scan()
   Message: Method 'get_admin_accounts' does not exist in mastodon.py
   💡 Did you mean: admin_accounts_v2, account, accounts?

2. ERROR: invalid_parameter
   File: backend/app/services/mastodon_service.py:177
   Function: get_admin_accounts()
   Message: Parameter 'invalid_param' is not valid for admin_accounts_v2()
   Valid parameters: origin, by_domain, status, username, display_name, ...

📊 Summary:
   Errors: 4
   Warnings: 0
   Available methods in mastodon.py: 261
```

## How It Works

### 1. AST Parsing
The checker uses Python's `ast` module to parse all Python files in `backend/app/` and extract:
- Direct client calls: `client.account_statuses(...)`
- Chained calls: `self.client.report(...)`

### 2. Signature Inspection
It uses `inspect.signature()` to get the actual method signatures from the `Mastodon` class in `mastodon.py`.

### 3. Validation
For each API call found, it checks:
- Method name exists in `Mastodon` class
- All passed parameters are valid for that method
- Known deprecated methods trigger warnings

### 4. Reporting
Generates a detailed report with:
- File path and line number
- Function context
- Error type and message
- Suggestions for fixes

## Extending the Checker

### Adding Known Issues

Edit `scripts/check_api_compliance.py`:

```python
# Known API version issues
API_VERSION_ISSUES = {
    "some_method": {
        "message": "This method changed in v2.x.x",
        "fix": "Use new_method() instead with updated parameters"
    }
}
```

### Adding Deprecation Warnings

```python
DEPRECATED_METHODS = {
    "admin_accounts": "Use admin_accounts_v2() instead - v1 may return incorrect data",
    "old_method": "Use new_method() instead"
}
```

## Best Practices

### Before Committing
```bash
# Always run before committing API changes
make api-compliance
```

### When Adding New Mastodon API Calls
1. Check available methods: `python3 scripts/check_api_compliance.py --list-methods`
2. Verify parameters match mastodon.py documentation
3. Only use methods that exist in `Mastodon` class
4. Never create wrapper methods with different names (causes test/prod divergence)

### Testing
The compliance checker itself requires:
- Python 3.9+ (for modern type hints)
- `Mastodon.py` library installed

To test locally:
```bash
pip install Mastodon.py
python3 scripts/check_api_compliance.py
```

## Common Errors and Fixes

### Error: Method doesn't exist
**Problem**: Calling a method that doesn't exist in mastodon.py
```python
# ❌ BAD
client.get_admin_accounts(...)  # This method doesn't exist!

# ✅ GOOD
mastodon_service.get_admin_accounts(...)  # Use service wrapper
```

### Error: Invalid parameter
**Problem**: Passing parameters that the method doesn't accept
```python
# ❌ BAD
client.admin_accounts_v2(None=None)  # Passing None as kwarg

# ✅ GOOD
params = {"limit": 50}
if origin is not None:
    params["origin"] = origin
client.admin_accounts_v2(**params)
```

### Warning: Deprecated method
**Problem**: Using old API methods
```python
# ⚠️ DEPRECATED
client.admin_accounts()  # v1 API, may return wrong data

# ✅ RECOMMENDED
client.admin_accounts_v2()  # v2 API, correct structure
```

## Maintenance

### Updating for New mastodon.py Versions
When upgrading `mastodon.py`:

1. Check the changelog for API changes
2. Run: `python3 scripts/check_api_compliance.py --list-methods`
3. Update `DEPRECATED_METHODS` and `API_VERSION_ISSUES` if needed
4. Run full test suite: `make check`

### Monitoring
The checker is part of CI, so all PRs are automatically validated. Check the GitHub Actions tab for results.

## Related Files

- **Checker Script**: `scripts/check_api_compliance.py`
- **CI Workflow**: `.github/workflows/api-compliance.yml`
- **Makefile Targets**: `make api-compliance`, `make api-compliance-verbose`
- **Service Wrapper**: `backend/app/services/mastodon_service.py`
- **Issue History**: `API_COMPLIANCE_ISSUES.md`

## Support

If the checker reports false positives:
1. Verify you're calling mastodon.py methods correctly
2. Check if you need to update the checker for new library versions
3. File an issue with the compliance report output

The goal is **zero tolerance for API violations** - all production code must pass 100%.
