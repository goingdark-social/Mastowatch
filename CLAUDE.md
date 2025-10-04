# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MastoWatch is a Mastodon **auto-moderation** tool that analyzes accounts/statuses for violations. While the long-term goal is automated enforcement, the system currently operates in **report-only mode** until stable enough to trust with direct moderation actions. Reports are filed for human moderator review in Mastodon's admin UI.

**Tech Stack:**
- Backend: FastAPI (Python) with Celery workers
- Database: PostgreSQL with Alembic migrations
- Cache/Queue: Redis
- Frontend: React (Vite)
- Mastodon Integration: OpenAPI-generated client + mastodon.py for OAuth

**Development Tools:**
- **Serena MCP**: Use Serena tools for all codebase exploration, symbol search, and code editing. Always read/write memories for collaboration context.
- **Context7 MCP**: Query Context7 for up-to-date library documentation when coding (e.g., FastAPI, Celery patterns).

## Essential Commands

### Testing
```bash
# Run all tests (always set PYTHONPATH and SKIP_STARTUP_VALIDATION)
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest

# Run specific test
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest tests/test_file.py::TestClass::test_method -v

# Run with minimal output
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest -x -q
```

### Code Quality
```bash
make lint          # Ruff linting with auto-fix
make format        # Black formatting (120 char line length)
make format-check  # Check formatting without changes
make typecheck     # MyPy type checking
make check         # Run all checks (lint + format-check + typecheck + test)
```

### Development
```bash
make dev           # Start full stack with hot reload
make dev-d         # Start in detached mode
make backend-only  # Start only backend services (for frontend dev)
make clean         # Clean containers and volumes
```

### Database
```bash
make shell-db      # Open PostgreSQL shell
make migration name="description"  # Create new Alembic migration
```

### Logs & Debugging
```bash
make logs          # All services
make logs-api      # API only
make logs-worker   # Celery worker only
make status        # Show service status
```

### Mastodon API Client
```bash
make update-mastodon-client  # Update OpenAPI spec and regenerate client
make api-client-status       # Show current client version
```

## Architecture

### Core Components

**Entry Points:**
- `backend/app/main.py` - FastAPI application with health checks, webhooks, and API routes
- `backend/app/tasks/celery_app.py` - Celery worker configuration with Beat schedule
- `backend/app/tasks/jobs.py` - Background job implementations

**Key Services (`backend/app/services/`):**
- `mastodon_service.py` - **ALL Mastodon API calls must go through MastodonService**
- `enforcement_service.py` - Handles report filing and enforcement actions
- `rule_service.py` - Rule evaluation and pattern matching
- `config_service.py` - Runtime configuration management

**API Routes (`backend/app/api/`):**
- `auth.py` - OAuth login/logout/session management
- `rules.py` - CRUD operations for moderation rules
- `analytics.py` - System metrics and scanning progress
- `scanning.py` - Manual scan triggers and status
- `logs.py` - Enforcement audit logs

**Authentication:**
- Admin access uses OAuth (via mastodon.py library)
- API access uses X-API-Key header
- Testing: Override `get_current_user_hybrid` dependency per test (see `tests/test_authentication_authorization.py`)

### Job System & Background Processing

**Celery Architecture:**
- **Beat Scheduler**: Schedules recurring jobs (uses `celery-sqlalchemy-scheduler` with database backend)
- **Worker Processes**: Execute queued tasks asynchronously
- **Redis**: Message broker and result backend
- **Job Definition**: All background tasks in `backend/app/tasks/jobs.py`

**Scheduled Jobs** (configured in `backend/app/tasks/celery_app.py`):
- `poll-admin-accounts`: Every 30s - scan remote accounts for violations
- `poll-admin-accounts-local`: Every 30s - scan local accounts for violations
- `queue-stats`: Every 15s - update queue metrics

**Job Flow:**
1. Beat scheduler triggers job or webhook queues job
2. Celery worker picks up task from Redis queue
3. Worker calls MastodonService to fetch data
4. Scanner evaluates against active rules
5. EnforcementService files reports (or takes action when auto-enforcement flag enabled)
6. Results logged to database with request IDs

### Data Flow

1. **Automated Scanning (Celery Beat)**:
   - `poll-admin-accounts` task runs every 30s for remote accounts
   - `poll-admin-accounts-local` task runs every 30s for local accounts
   - Tasks call `MastodonService.admin_accounts_v2()` to fetch admin account data
   - **Critical**: Admin API returns objects with nested `account` field, NOT plain account objects
   - Scanner in `scanning.py` evaluates accounts against rules
   - Violations trigger report creation via `EnforcementService`

2. **Real-time Webhook Processing**:
   - Mastodon instance sends webhooks to `/webhooks/mastodon_events`
   - `status.created` events queue `process_new_status` task
   - Worker analyzes status and associated account
   - Reports filed if violations detected

3. **Rule Evaluation**:
   - Rules can combine two patterns with boolean operators (AND/OR)
   - Each pattern matches against account metadata, status content, or media
   - Rules reference admin fields (email, IP, confirmed, created_at) - requires admin API data

4. **Future: Auto-Enforcement Mode**:
   - System designed for automated moderation actions (warnings, limits, suspensions)
   - Currently disabled until thoroughly tested and stable
   - When enabled: EnforcementService will execute actions instead of just filing reports

### Database Architecture

- **Foreign keys enforce referential integrity**
- **Performance indexes on common query patterns**
- **UPSERT pattern** (`ON CONFLICT DO UPDATE`) for idempotent writes
- **Timestamps**: Include `created_at`/`updated_at` on all tables
- **Alembic migrations**: Run via `migrate` service, `DATABASE_URL` env var overrides `alembic.ini`

### Critical Patterns

**Mastodon API Access:**
- NEVER call Mastodon APIs directly with `requests`/`httpx`
- ALWAYS use `MastodonService` wrapper
- Prefer OpenAPI-generated client methods
- Fall back to raw HTTP only for admin endpoints not in OpenAPI spec

**Admin vs Public Data:**
- Public account API: username, display_name, followers_count, etc.
- Admin account API: **email, IP, confirmed, approved, role, created_at** (essential for spam detection)
- Scanner needs full admin objects, not just nested `account` field

**Testing FastAPI Dependencies:**
- Store reference to dependency function in test setUp
- Override via `app.dependency_overrides[dependency_func] = mock_function`
- Clear in tearDown: `app.dependency_overrides.clear()`
- See `tests/test_authentication_authorization.py` for examples

**Logging:**
- Structured JSON logs with request IDs
- Use `logger.info()` with structured fields, not string concatenation
- Request ID tracking for distributed tracing

### Known Issues & Gotchas

1. **Admin Account Data Structure**: Code expects admin objects with nested `account` field. Don't pass just `account_data.get("account", {})` to scanner - pass full admin object.

2. **Scan Progress Tracking**: `ScanSession.total_accounts` and `current_cursor` are never set (always NULL), so progress percentage shows 0% even during active scans.

3. **Webhook Configuration**: Webhooks are implemented but require Mastodon instance to be configured to send events to MastoWatch endpoint.

4. **Startup Validation**: Always set `SKIP_STARTUP_VALIDATION=1` during tests to avoid version/API checks.

## Frontend Development

```bash
cd frontend
npm ci              # Install dependencies
npm run dev         # Development server
npm run build       # Production build
```

Frontend connects to backend API via `VITE_API_URL` environment variable.

## Legal Notice

Every page includes footer link to goingdark.social. The application refuses to run without this credit - it's part of the license. Do not remove or rename.
