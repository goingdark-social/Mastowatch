# GitHub Copilot Instructions for MastoWatch

**ALWAYS follow these instructions first. Only fallback to additional search and context gathering if the information here is incomplete or found to be in error.**

## Project Overview

MastoWatch is a **Mastodon moderation sidecar** that analyzes accounts/statuses and files reports via API for human moderators. It's a **watch-and-report system with no auto-enforcement** by default, built with FastAPI, Celery, PostgreSQL, and Redis.

## Architecture & Key Components

### Core Services Stack
- **API** (`app/api/`): FastAPI web server with routers for analytics, auth, config, rules, and scanning. `app/main.py` is the entrypoint.
- **Worker** (`app/tasks/jobs.py`): Celery workers for background account analysis and webhook event processing.
- **Beat**: Celery scheduler for periodic polling (every 30s).
- **Database**: PostgreSQL with Alembic for migrations.
- **Redis**: Celery broker and caching for deduplication and rate limiting.

### Rule Engine & Analysis
- **Rules**: **Database-driven exclusively** via the `RuleService` (`app/services/rule_service.py`). The old `rules.yml` is deprecated and no longer used.
- **Scanning**: An enhanced scanning system (`app/enhanced_scanning.py`) handles efficient, deduplicated account scanning.
- **Enforcement**: Optional automated actions are managed by the `EnforcementService` (`app/services/enforcement_service.py`).
- **Detectors**: Pluggable detection modules (`app/services/detectors/`) implement specific logic (regex, keyword, behavioral) for the rule engine.

### Mastodon API Client Wrapper
- **Primary Interface**: All application logic **must** interact with the Mastodon API through the `MastodonService` wrapper class in `app/services/mastodon_service.py`. This class handles rate-limiting, provides async wrappers, and uses the official mastodon.py library.
- **Official Library**: The `MastodonService` uses the official **mastodon.py library** which provides a complete, well-tested interface to the Mastodon API with built-in rate limiting and error handling.

## Working Effectively

### Bootstrap and Validate the Repository
**ALWAYS run these commands first to set up your development environment:**

```bash
# Install Python dependencies for quality checks and testing
cd /home/runner/work/Mastowatch/Mastowatch
python -m pip install --upgrade pip
pip install -r backend/requirements.txt -r tests/requirements-test.txt
```

**Initial validation**: Run this quick test to verify setup works:
```bash
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest tests/test_startup_validation.py::test_validate_mastodon_version_ok --no-header --tb=short
```

**Dependencies Summary**:
- **Python**: Uses Python 3.12+ (3.13 in CI)
- **Node**: Uses Node.js 22 for frontend development
- **Backend Dependencies**: FastAPI, Celery, SQLAlchemy, PostgreSQL, Redis
- **Frontend Dependencies**: React 19, Vite, Mantine UI, TypeScript

### Test Suite
```bash
# Run tests - VALIDATED: 147 tests complete in ~26 seconds
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest --no-header --tb=short
# Timeout: Set 2+ minutes. NEVER CANCEL - tests are comprehensive.
```

### Frontend Development
```bash
# Frontend setup and build - VALIDATED timing
cd frontend
npm ci                    # Takes ~13 seconds. NEVER CANCEL.
npm run build            # Takes ~8 seconds. NEVER CANCEL.
```

### Quality Checks
**Note: Current codebase has many quality issues but tools run quickly:**
```bash
make lint                # ~0.05 seconds - 160 ERRORS PRESENT
make format-check        # ~5 seconds - 36 FILES NEED FORMATTING  
make typecheck          # ~0.6 seconds - MODULE CONFLICTS PRESENT
```

### Docker Limitations in Sandboxed Environments
**CRITICAL: Docker commands fail in sandboxed environments due to SSL certificate issues.**
- `make dev`, `make prod`, `make build` will fail with SSL errors
- Use individual component testing instead (Python tests, frontend builds)
- In production environments, these commands work normally

## Development Workflows

### Make Commands (Preferred)
**ALWAYS use `make` commands when working with this project.** The project includes a comprehensive Makefile that provides convenient shortcuts for all common development tasks.

```bash
# Development with hot reload
make dev

# Backend only (for frontend development)
make backend-only

# Production environment
make prod

# Stop all services
make stop

# Clean up containers and volumes
make clean

# View service status
make status

# View logs
make logs              # All services
make logs-api          # API only
make logs-worker       # Worker only
make logs-frontend     # Frontend only
```

### Testing Strategy
- **Restructured Test Suite**: Tests are organized by feature area, mirroring the application structure (`tests/api`, `tests/services`, `tests/tasks`).
- **Isolation**: Tests use an in-memory SQLite database and a separate Redis instance to ensure isolation and prevent side effects.
- **Mocking External APIs**: All outbound calls to the Mastodon API are mocked using `unittest.mock.patch` to prevent real network requests during tests.
- **Run tests**: `PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest` 
- **TIMING**: 147 tests complete in ~26 seconds. Set timeout to 2+ minutes. NEVER CANCEL.
- **Current Status**: Many tests fail (77/147) due to codebase inconsistencies, but test infrastructure works correctly.

### Code Quality Tools
- **Formatting**: Black with a **120-character** line length (`make format`).
- **Format checking**: `make format-check` to verify formatting without making changes. **WARNING**: 36 files currently need reformatting.
- **Linting**: Ruff with custom rules in `pyproject.toml` to ban direct use of `requests` and `httpx` (`make lint`). **WARNING**: 160 errors currently present.
- **Type checking**: MyPy with selective strictness (`make typecheck`). **WARNING**: Module naming conflicts present.
- **All quality checks**: `make check` runs lint, format-check, typecheck, and test in sequence. **EXPECT FAILURES** in current codebase.
- **HTTP Library Policy**: Only the `MastodonService` wrapper is permitted to interact with the Mastodon API. The service uses mastodon.py internally. Direct use of `requests` or `httpx` for Mastodon API calls elsewhere is a linting error.
- **TIMING**: Quality checks complete very quickly - lint ~0.05s, format-check ~5s, typecheck ~0.6s. Set timeout to 2+ minutes. NEVER CANCEL.

### Database Operations
```bash
# Run migrations (automatic during startup)
make migration name="your_migration_description"

# Database shell
make shell-db
```

### Service Management
```bash
# Restart specific services
make restart-api
make restart-worker  
make restart-frontend

# Enter container shells
make shell-api       # API container shell
```

### Mastodon Client Management
```bash
# Update OpenAPI spec from submodule
make update-api-spec

# Regenerate typed client from current spec  
make regenerate-client

# Full update: submodule + spec + client
make update-mastodon-client

# Show current API client status
make api-client-status
```

## Critical Configuration Patterns

### Environment Variables Structure
- **Required**: `INSTANCE_BASE`, `BOT_TOKEN`, `ADMIN_TOKEN`, `API_KEY`, `WEBHOOK_SECRET`
- **OAuth for admin UI**: `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_REDIRECT_URI`
- **Safety controls**: `DRY_RUN=true`, `PANIC_STOP=false`, `SKIP_STARTUP_VALIDATION=false`
- **Database URL format**: `postgresql+psycopg://user:pass@host:port/db`

### API Authentication Patterns
- **Webhook Validation**: Inbound webhooks are validated using an HMAC SHA256 signature in the `X-Hub-Signature-256` header.
- **Admin UI Auth**: An OAuth2 flow provides a secure, HttpOnly session cookie for all moderator interactions with the frontend.
- **Programmatic API Auth**: A static API key is required in the `X-API-Key` header for server-to-server calls or scripts.
- **Rate Limiting**: Handled automatically by mastodon.py's built-in rate limiting (`ratelimit_method="wait"`), accessed through the `MastodonService` wrapper.

### Task Queue Architecture
- **Polling Tasks**: `poll_admin_accounts` (remote) and `poll_admin_accounts_local` for discovering accounts.
- **Event Processing**: `process_new_report` and `process_new_status` are triggered by `report.created` and `status.created` webhook events, respectively.
- **Analysis Pipeline**: The `analyze_and_maybe_report` task evaluates accounts against the database rules and triggers enforcement actions.
- **Cursor Management**: PostgreSQL-based cursors are used for paginating through accounts during polling tasks.

## Project-Specific Conventions

### Data Flow Patterns
1.  **Account Discovery**: Celery Beat → `poll_admin_accounts` → Account persistence in PostgreSQL.
2.  **Rule Evaluation**: An account and its statuses are passed to the `RuleService`, which uses various detectors to find violations.
3.  **Report Generation/Enforcement**: If a violation's score exceeds the rule's `trigger_threshold`, the `EnforcementService` is called to perform an action (e.g., file a report) via the `MastodonService`.
4.  **Webhook Processing**: A real-time event from Mastodon (e.g., `status.created`) hits the webhook endpoint, which enqueues a specific Celery task (`process_new_status`) for immediate analysis.

### Error Handling Standards
- **Structured Logging**: JSON format with request IDs for easy tracing in production.
- **Health Checks**: The `/healthz` endpoint returns a `503` status if the database or Redis is unavailable.
- **Graceful Degradation**: `PANIC_STOP` halts all background processing. `DRY_RUN` logs intended actions without executing them.
- **Retry Strategies**: Celery tasks use exponential backoff with jitter for retrying on failure.

### Database Schema Patterns
- **Foreign Keys**: Enforce referential integrity across all tables.
- **UPSERT Patterns**: Use PostgreSQL's `ON CONFLICT DO UPDATE` for idempotent operations, such as updating account data.
- **Deduplication**: `dedupe_key` fields prevent the system from filing duplicate reports for the same underlying issue.
- **Timestamps**: All tables include `created_at` and `updated_at` with timezone information.

### Frontend Integration
- **Static Assets**: Mounted at `/dashboard` (built separately).
- **OAuth Popup Flow**: Admin login uses a popup window that communicates success or failure to the parent window via `postMessage`.
- **CORS Configuration**: Controlled by the `CORS_ORIGINS` environment variable.

## File Structure Patterns

### Key Directories
- `app/api/`: FastAPI routers, organized by resource (analytics, auth, rules, etc.).
- `app/services/`: Core business logic (RuleService, EnforcementService, MastodonService, Detectors).
- `app/tasks/`: Celery job definitions.
- `tests/`: Test suite, structured to mirror the application layout.
- `specs/`: OpenAPI schemas for client generation.

### Configuration Files
- `pyproject.toml`: Black, MyPy, and Ruff configurations, including custom rules to ban direct HTTP library usage.
- `alembic.ini`: Database migration settings (uses the `DATABASE_URL` environment variable).
- `docker-compose.yml`: Production stack definition.
- `docker-compose.override.yml`: Development overrides with hot-reloading.

When working on this codebase, always consider the moderation context. This system handles sensitive content and must be reliable, auditable, and safe.

## Validation Scenarios

### After Making Code Changes, ALWAYS Test:

1. **Basic Test Suite Validation**:
   ```bash
   PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest --no-header --tb=short -x
   # TIMING: ~26 seconds for 147 tests. NEVER CANCEL - wait for completion.
   # EXPECTED: 77/147 tests fail due to codebase inconsistencies
   ```

2. **Frontend Build Validation** (if frontend changes):
   ```bash
   cd frontend
   npm ci && npm run build
   # TIMING: npm ci ~13s, build ~8s. NEVER CANCEL.
   ```

3. **Quality Check Validation**:
   ```bash
   make lint          # EXPECT: 160 errors in current codebase (~0.05s)
   make format-check  # EXPECT: 36 files needing formatting (~5s)  
   make typecheck     # EXPECT: module conflicts (~0.6s)
   # TIMING: Each check completes very quickly. NEVER CANCEL.
   ```

### Manual Testing Requirements
- **Cannot test full Docker stack** in sandboxed environments due to SSL issues
- Focus on individual component testing (Python modules, frontend builds)
- Test API endpoints using the test client from `tests/conftest.py`
- Validate rule creation/evaluation using `RuleService` tests
- Check database operations using in-memory SQLite from tests

### Current Codebase Limitations
- **Docker builds fail** in sandboxed environments with SSL certificate errors
- **Many quality check failures** - this is the current state, not a regression
- **Test failures expected** - 77/147 tests currently fail due to codebase inconsistencies
- **Module naming conflicts** - `auth.py` conflicts require careful imports

## Time Expectations and Timeouts

### Command Timing Summary
- **Python Dependencies**: pip install ~45 seconds → Set timeout: 5+ minutes
- **Tests**: 147 tests in ~26 seconds → Set timeout: 2+ minutes
- **Frontend npm ci**: ~13 seconds → Set timeout: 2+ minutes  
- **Frontend build**: ~8 seconds → Set timeout: 2+ minutes
- **Quality checks**: lint ~0.05s, format-check ~5s, typecheck ~0.6s → Set timeout: 2+ minutes
- **Docker builds**: Would be 5-15 minutes normally, but **FAIL in sandboxed environments**

### CRITICAL: NEVER CANCEL Commands
- **NEVER CANCEL** test suites - comprehensive validation takes time
- **NEVER CANCEL** npm installs - package downloads can be slow
- **NEVER CANCEL** builds - even if they appear to hang, wait for timeout
- **ALWAYS** set generous timeouts (2+ minutes minimum, 15+ minutes for builds)

## Quick Reference - Most Common Commands

### Essential Setup (Run First)
```bash
cd /home/runner/work/Mastowatch/Mastowatch
python -m pip install --upgrade pip
pip install -r backend/requirements.txt -r tests/requirements-test.txt
```

### Testing (Use Every Time)
```bash
# Single test (fast validation)
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest tests/test_startup_validation.py::test_validate_mastodon_version_ok

# Full test suite (~26 seconds, timeout: 2+ minutes)
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest --no-header --tb=short
```

### Frontend (If Modified)
```bash
cd frontend
npm ci && npm run build    # ~21 seconds total, timeout: 2+ minutes
```

### Quality Checks (Expect Issues)
```bash
make lint format-check typecheck    # All complete in <6 seconds
```
