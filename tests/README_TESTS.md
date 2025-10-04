# MastoWatch Test Suite

## Overview

This test suite verifies the correct handling of Mastodon admin API responses and the scanning flow. The tests are designed to catch the critical bugs identified in the scanning system, particularly around admin account data structure handling.

## Critical Test Files

### 1. `test_admin_account_structure.py`

Tests the **critical bug** where the system was incorrectly extracting account data from admin API responses.

**Problem**: Code expected `{"account": {...}}` wrapper, but Mastodon API v2 returns admin objects with a NESTED `account` field:

```python
{
    "id": "123",
    "username": "user",
    "email": "user@example.com",      # ← Admin metadata
    "ip": "1.2.3.4",                  # ← Admin metadata (STRING in v2, not object)
    "ips": [{"ip": "1.2.3.4", "used_at": "..."}],  # ← IP history
    "confirmed": true,                 # ← Admin metadata
    "account": {                       # ← Nested PUBLIC account
        "id": "123",
        "username": "user",
        "acct": "user@domain",
        ...
    }
}
```

**Key Tests**:
- `test_persist_account_handles_admin_structure` - Verifies account persistence with admin fields
- `test_scanner_receives_full_admin_object` - Ensures scanner gets full admin object, not just nested account
- `test_scanner_can_access_admin_fields` - Verifies admin fields (email, IP, confirmed) are accessible
- `test_poll_accounts_passes_full_admin_object` - Tests the actual polling flow

### 2. `test_scanning_integration.py`

Integration tests for the complete scanning flow from Celery Beat → Polling → Scanning → Reporting.

**Key Tests**:
- `test_poll_scan_detect_flow` - End-to-end flow with violation detection
- `test_analyze_and_report_flow` - Analysis and reporting logic
- `test_session_lifecycle` - Scan session creation, update, completion
- `test_admin_accounts_structure` - Validates fixtures match actual Mastodon API
- `test_cursor_saved_between_polls` - Pagination cursor persistence
- `test_behavioral_rule_uses_admin_fields` - Rule evaluation with admin metadata

## Mastodon API Compliance

All test fixtures are based on **official Mastodon API documentation**:

### Admin Accounts v2 API
- **Endpoint**: `GET /api/v2/admin/accounts`
- **Docs**: https://docs.joinmastodon.org/methods/admin/accounts/#v2
- **Structure**: See `sample_admin_account_data` fixture in `conftest.py`

### Pagination
- **Method**: `client.get_pagination_info(response)`
- **Returns**: `{"max_id": str, "since_id": str, "min_id": str}`

### Status Objects
- **Structure**: Matches Mastodon API status entity
- **Fields**: id, created_at, account, content, visibility, etc.

## Running Tests

### Run All Tests
```bash
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest
```

### Run Specific Test File
```bash
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest tests/test_admin_account_structure.py -v
```

### Run Single Test
```bash
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest tests/test_admin_account_structure.py::TestAdminAccountDataStructure::test_scanner_receives_full_admin_object -v
```

### Run Integration Tests Only
```bash
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest tests/test_scanning_integration.py -v
```

## Database Schema Changes

### Cursor Table - NULL Position Allowed

**Change**: The `cursors.position` column now allows NULL values (previously NOT NULL).

**Why**: NULL position indicates "start from beginning" - this is the natural initial state for cursors. The previous NOT NULL constraint required tests to provide a dummy value, which was incorrect.

**Migration**: `009_allow_null_cursor_position.py`

```sql
-- Before:
CREATE TABLE cursors (
    name TEXT PRIMARY KEY,
    position TEXT NOT NULL,  -- ❌ Forced dummy values
    updated_at TIMESTAMP
);

-- After:
CREATE TABLE cursors (
    name TEXT PRIMARY KEY,
    position TEXT NULL,       -- ✅ NULL = start from beginning
    updated_at TIMESTAMP
);
```

**Test Impact**: Tests can now properly initialize cursors:
```python
# Correct initialization
test_db_session.execute(
    text("INSERT INTO cursors (name, position) VALUES (:n, :p)"),
    {"n": "admin_accounts_remote", "p": None}  # ✅ NULL is valid!
)
```

## Expected Failures (Before Fixes)

The following tests **WILL FAIL** until the bugs are fixed:

1. **`test_poll_accounts_passes_full_admin_object`**
   - **Why**: `jobs.py` currently does `account_data.get("account", {})` which strips admin metadata
   - **Fix**: Change to `account_data` (pass full admin object)

2. **`test_scanner_can_access_admin_fields`**
   - **Why**: Scanner receives only nested account, not full admin object
   - **Fix**: Pass full admin object to scanner

3. **`test_accounts_processed_increments`**
   - **Why**: Session progress fields (`total_accounts`, `current_cursor`) never updated
   - **Fix**: Update session progress in polling loop

4. **`test_cursor_saved_between_polls`**
   - **Why**: Pagination cursor extraction has bugs in fallback paths
   - **Fix**: Use `get_pagination_info()` consistently

## Test Fixtures

### Updated `conftest.py` Fixtures

#### `sample_admin_account_data`
Full admin account structure matching Mastodon API v2. **Use this for all admin API tests**.

#### `sample_admin_accounts_list`
List of admin accounts (what `admin_accounts()` returns).

#### `sample_account_data`
Regular public account data (what `account()` returns). **NOT for admin API tests**.

#### `mock_mastodon_client`
Now properly mocks:
- `admin_accounts()` → Returns admin account list
- `get_pagination_info()` → Returns pagination cursors

## Writing New Tests

### Testing Admin API Responses

```python
def test_my_admin_feature(sample_admin_account_data):
    # Use sample_admin_account_data for admin API tests
    account = sample_admin_account_data

    # Admin fields are accessible
    assert account["email"] is not None
    assert account["ip"]["ip"] is not None
    assert account["confirmed"] is not None

    # Nested account is accessible
    assert account["account"]["acct"] is not None
```

### Testing Scanner Flow

```python
@patch('app.tasks.jobs.mastodon_service')
def test_scanner_with_admin_data(mock_mastodon, sample_admin_accounts_list):
    # Mock API to return admin accounts
    mock_mastodon.get_admin_accounts_sync.return_value = (
        sample_admin_accounts_list,
        "next_cursor_123"
    )

    # Test your feature
    # ...
```

### Testing Rule Evaluation

```python
def test_rule_needs_admin_fields(sample_admin_account_data):
    # Create rule that checks admin fields
    rule = Rule(
        name="new_unconfirmed_check",
        detector_type="behavioral",
        pattern="check_new_unconfirmed",
        # ...
    )

    # Rule should be able to access:
    # - sample_admin_account_data["confirmed"]
    # - sample_admin_account_data["created_at"]
    # - sample_admin_account_data["email"]
```

## Debugging Failed Tests

### Check Admin Object Structure
```python
# Print admin object to verify structure
print(json.dumps(sample_admin_account_data, indent=2))
```

### Verify Mock Calls
```python
# Check what was passed to scanner
mock_scanner.scan_account_efficiently.assert_called_once()
call_args = mock_scanner.scan_account_efficiently.call_args[0]
account_data = call_args[0]

print("Account data received:", account_data.keys())
assert "email" in account_data  # Should have admin fields!
```

### Check Database State
```python
# Verify account was persisted correctly
account = test_db_session.query(Account).filter_by(
    mastodon_account_id="123"
).first()

print(f"Email: {account.email}")
print(f"IP: {account.ip}")
```

## Memory References

The following Serena memories document the issues these tests address:

- `scanning-system-issues-2025-10-04` - Original issue analysis
- `mastowatch-architecture-issues-2025-10-04` - Architecture documentation
- `scanning-improvement-plan-2025-10-04` - Improvement roadmap

## Test Coverage Goals

- [x] Admin account data structure handling
- [x] Pagination cursor persistence
- [x] Scan session progress tracking
- [x] Rule evaluation with admin fields
- [x] End-to-end scanning flow
- [x] Webhook payload handling
- [x] Error handling and edge cases
- [x] Mastodon API compliance

## CI/CD Integration

These tests should run in CI/CD pipeline with:

```yaml
test:
  script:
    - pip install -r backend/requirements.txt
    - pip install -r tests/requirements-test.txt
    - PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest --cov=app --cov-report=html
```

## Next Steps

1. **Run tests** to verify they capture the bugs
2. **Fix the bugs** in `backend/app/tasks/jobs.py`
3. **Re-run tests** to verify fixes work
4. **Expand test coverage** for other edge cases

## Questions?

Check the Mastodon API docs:
- Admin Accounts: https://docs.joinmastodon.org/methods/admin/accounts/
- Mastodon.py: https://mastodonpy.readthedocs.io/
