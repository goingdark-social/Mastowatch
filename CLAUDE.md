# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Essential Workflow: Use MCP Tools First

**CRITICAL: Always use Serena MCP tools for code navigation, search, and editing. Use Context7 for library documentation.**

### Start Every Session

```bash
# 1. Check onboarding status
mcp__serena__check_onboarding_performed

# 2. List and read relevant memories
mcp__serena__list_memories
mcp__serena__read_memory <memory_name>
```

### Code Navigation (Always Use Serena)

```bash
# Get file/directory structure
mcp__serena__list_dir <path>

# Get symbol overview before reading files
mcp__serena__get_symbols_overview <file_path>

# Find symbols by name
mcp__serena__find_symbol <symbol_name> --include_body=True

# Find all references to a symbol
mcp__serena__find_referencing_symbols <symbol_name> <file_path>

# Search for patterns in code
mcp__serena__search_for_pattern <pattern>
```

### Code Editing (Always Use Serena)

```bash
# Replace entire symbol body (functions, classes, methods)
mcp__serena__replace_symbol_body <symbol_name> <file_path> <new_body>

# Insert code after a symbol
mcp__serena__insert_after_symbol <symbol_name> <file_path> <new_code>

# Insert code before a symbol
mcp__serena__insert_before_symbol <symbol_name> <file_path> <new_code>
```

### Library Documentation (Always Use Context7)

```bash
# 1. Resolve library name to Context7 ID
mcp__context7__resolve-library-id <library_name>

# 2. Fetch documentation
mcp__context7__get-library-docs <context7_id> --topic <specific_topic>

# Common libraries in this project:
# - Mastodon.py: /halcy/mastodon.py
# - FastAPI: resolve first
# - Celery: resolve first
# - SQLAlchemy: resolve first
```

### Knowledge Management (Critical - Always Use)

```bash
# After discovering something valuable, write it to memory
mcp__serena__write_memory <memory_name> "<1-3 line summary>"

# Before editing unfamiliar code, check memories
mcp__serena__read_memory <relevant_memory>

# Delete outdated information
mcp__serena__delete_memory <memory_name>
```

### Standard Workflow for Any Code Task

1. **Check memories** for existing knowledge about the area
2. **Use get_symbols_overview** to understand file structure
3. **Use find_symbol** to locate specific code
4. **Use find_referencing_symbols** before modifying anything
5. **Use Context7** if you need library API documentation
6. **Make edits** using Serena symbol editing tools
7. **Write to memory** any discoveries or patterns you found
8. **Test** changes with pytest

**Only use traditional file operations (Read/Edit/Write) when:**
- Editing non-code files (configs, docs, requirements.txt)
- Serena tools are unavailable or fail
- Working with generated code or binary files

## Project Overview

MastoWatch is a **Mastodon moderation sidecar** that analyzes accounts and statuses, then files reports via the Mastodon API for human moderators to review. It's a **watch-and-report system** with optional enforcement actions, built on FastAPI, Celery, PostgreSQL, and Redis.

**Core Purpose**: Automated content moderation for Mastodon instances using a pluggable rule engine.

## Architecture

### Service Stack
- **API** (`backend/app/main.py`): FastAPI web server exposing REST endpoints
- **Worker** (`backend/app/tasks/jobs.py`): Celery workers for background processing
- **Beat**: Celery scheduler for periodic polling tasks
- **Database**: PostgreSQL with Alembic migrations
- **Redis**: Celery broker + result backend
- **Frontend**: React SPA with Mantine UI, served from `/dashboard`

### Key Services

#### MastodonService (`backend/app/services/mastodon_service.py`)
**Primary interface to Mastodon API** - wraps `Mastodon.py` library.
- All Mastodon API calls MUST go through this service
- Provides both async (for FastAPI) and sync (for Celery) methods
- Handles rate limiting, authentication, and error handling
- Never use `requests`, `httpx`, or `urllib` directly for Mastodon API calls

#### RuleService (`backend/app/services/rule_service.py`)
**Database-driven rule engine** - evaluates accounts against configured rules.
- Rules stored in PostgreSQL (old `rules.yml` is deprecated)
- Uses pluggable detector system for different pattern types
- Caches active rules with configurable TTL
- Returns violation scores and evidence for enforcement decisions

#### EnforcementService (`backend/app/services/enforcement_service.py`)
**Action executor** - handles automated moderation actions.
- Creates reports, warnings, silences, or suspensions
- Respects `DRY_RUN` mode (default: true)
- Records all actions in audit logs
- Integrates with Slack notifications

### Detector System (`backend/app/services/detectors/`)
Pluggable pattern matching for different rule types:
- `keyword_detector.py`: Text-based keyword matching
- `regex_detector.py`: Regular expression patterns
- `behavioral_detector.py`: Account behavior analysis (post frequency, follower ratios)
- `media_detector.py`: Attachment and media analysis
- `base.py`: Abstract detector interface

All detectors implement a common interface and return evidence with scores.

### Data Flow

1. **Account Discovery**:
   - Celery Beat triggers `poll_admin_accounts` every 30s (configurable)
   - Fetches accounts from Mastodon admin API
   - Persists to PostgreSQL with upsert pattern

2. **Rule Evaluation**:
   - Account + recent statuses → `RuleService.evaluate_account()`
   - Each active rule runs through its detector
   - Returns aggregated score and violation evidence

3. **Enforcement**:
   - If score exceeds threshold → `EnforcementService`
   - Creates Mastodon report or takes action (based on rule config)
   - Records action in audit log

4. **Webhook Processing**:
   - Real-time events → `/webhooks/status` endpoint
   - Validates HMAC signature
   - Queues `process_new_status` Celery task
   - Triggers immediate analysis for new content

## Development Commands

### Setup & Testing

**Finding test files**: Use Serena tools
```bash
# Find test files
mcp__serena__find_file "test_*.py" tests/

# Understand test structure
mcp__serena__get_symbols_overview tests/test_api.py
```

**Running tests**: Use traditional bash
```bash
# Install dependencies
pip install -r backend/requirements.txt
pip install -r tests/requirements-test.txt

# Run all tests
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest

# Run specific test file
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest tests/test_api.py -v

# Run single test
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest tests/test_api.py::test_healthz -v
```

### Code Quality

```bash
# Format code (120 char line length)
make format

# Check formatting
make format-check

# Lint with Ruff
make lint

# Type check with MyPy
make typecheck

# Run all checks
make check
```

### Docker Stack

```bash
# Development mode (hot reload)
make dev

# Production mode
make prod

# Backend only (for frontend development)
make backend-only

# View logs
make logs           # All services
make logs-api       # API only
make logs-worker    # Worker only

# Service management
make stop
make clean
make status
```

### Database Operations

```bash
# Create migration
make migration name="description_here"

# Database shell
make shell-db

# Migrations run automatically on container startup via migrate service
```

### Frontend Development

```bash
cd frontend
npm install
npm run dev      # Development server on :5173
npm run build    # Production build
```

## Critical Configuration

### Environment Variables

See `docs/ENVIRONMENT.md` for complete documentation. Key variables:

**Required**:
- `INSTANCE_BASE`: Mastodon instance URL
- `BOT_TOKEN`: Token with `read` + `write:reports` scopes
- `ADMIN_TOKEN`: Token with `admin:read` + `admin:write` scopes
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `API_KEY`: Secure random string for API authentication
- `WEBHOOK_SECRET`: Secure random string for webhook validation

**Safety Controls**:
- `DRY_RUN=true`: Prevents actual enforcement (default in dev)
- `PANIC_STOP=false`: Emergency stop for all processing
- `SKIP_STARTUP_VALIDATION=false`: Skip config validation (tests only)

**OAuth (Admin UI)**:
- `OAUTH_CLIENT_ID`: From Mastodon OAuth app
- `OAUTH_CLIENT_SECRET`: From Mastodon OAuth app
- `OAUTH_REDIRECT_URI`: Callback URL (e.g., `https://domain/admin/callback`)

### Authentication Patterns

**API Endpoints**:
- Webhook: HMAC SHA256 signature in `X-Hub-Signature-256` header
- Admin UI: OAuth2 + HttpOnly session cookie
- Programmatic: Static API key in `X-API-Key` header

**Test Authentication**:
Tests mock Mastodon API calls - see `tests/conftest.py` for fixtures.

## Code Conventions

### Database Patterns
- **Foreign keys**: Enforce referential integrity
- **UPSERT**: Use `ON CONFLICT DO UPDATE` for idempotent operations
- **Deduplication**: `dedupe_key` fields prevent duplicate reports
- **Timestamps**: All models have `created_at` and `updated_at` (timezone-aware)

### HTTP Client Policy
- **REQUIRED**: Use `MastodonService` wrapper for all Mastodon API calls
- **BANNED**: Direct use of `requests`, `httpx`, `urllib` for Mastodon
- Ruff enforces this via `flake8-tidy-imports` rules in `pyproject.toml`
- Exceptions only in `app/integrations/http_adapter.py` and `app/services/slack_service.py`

### Error Handling
- **Structured logging**: JSON format with request IDs
- **Health checks**: `/healthz` returns 503 on service unavailability
- **Graceful degradation**: `PANIC_STOP` halts processing, `DRY_RUN` logs without executing
- **Retry logic**: Celery tasks use exponential backoff with jitter

### Testing Strategy
- **Isolation**: In-memory SQLite + separate Redis for tests
- **Mocking**: All Mastodon API calls mocked with `unittest.mock.patch`
- **Structure**: Tests organized by feature area (`tests/api/`, `tests/services/`, `tests/tasks/`)
- **Environment**: Uses `tests/.env.test` for test-specific config

## File Structure

```
backend/app/
├── api/              # FastAPI routers
│   ├── analytics.py  # Metrics and overview
│   ├── auth.py       # OAuth and session management
│   ├── config.py     # Runtime config endpoints
│   ├── logs.py       # Audit log access
│   ├── rules.py      # Rule CRUD operations
│   └── scanning.py   # Manual scan triggers
├── services/         # Business logic
│   ├── detectors/    # Pattern matching plugins
│   ├── enforcement_service.py
│   ├── mastodon_service.py
│   ├── rule_service.py
│   └── slack_service.py
├── tasks/           # Celery jobs
│   ├── celery_app.py
│   └── jobs.py
├── models.py        # SQLAlchemy models
├── schemas.py       # Pydantic schemas
├── config.py        # Settings (pydantic-settings)
├── db.py            # Database session management
└── main.py          # FastAPI app initialization

frontend/
├── src/
│   ├── components/  # React components
│   └── App.tsx      # Main application
└── vite.config.ts   # Build configuration

tests/
├── conftest.py      # Pytest fixtures
├── services/        # Service tests
├── tasks/           # Celery task tests
└── test_*.py        # API and integration tests
```

## Common Tasks

### Adding a New Rule Type

**Use Serena tools throughout:**

1. **Understand existing detectors**:
   ```bash
   mcp__serena__list_dir backend/app/services/detectors/
   mcp__serena__get_symbols_overview backend/app/services/detectors/base.py
   mcp__serena__find_symbol BaseDetector backend/app/services/detectors/base.py --include_body=True
   ```

2. **Check how detectors are registered**:
   ```bash
   mcp__serena__find_symbol RuleService/__init__ backend/app/services/rule_service.py --include_body=True
   ```

3. **Create new detector** using `mcp__serena__insert_after_symbol` or Write tool for new files

4. **Find all references to detector registration**:
   ```bash
   mcp__serena__find_referencing_symbols detectors backend/app/services/rule_service.py
   ```

5. **Write discovery to memory**:
   ```bash
   mcp__serena__write_memory detector_patterns "Detectors inherit BaseDetector, registered in RuleService.__init__, pattern in create_rule validates detector type"
   ```

### Adding an API Endpoint

**Use Serena tools throughout:**

1. **Explore existing routers**:
   ```bash
   mcp__serena__list_dir backend/app/api/
   mcp__serena__get_symbols_overview backend/app/api/rules.py
   ```

2. **Check authentication patterns**:
   ```bash
   mcp__serena__find_symbol get_current_user_hybrid backend/app/main.py --include_body=True
   mcp__serena__search_for_pattern "Depends\(get_current_user"
   ```

3. **Add new endpoint** using `mcp__serena__insert_after_symbol`

4. **Document the pattern**:
   ```bash
   mcp__serena__write_memory api_auth_patterns "Admin endpoints use Depends(get_current_user_hybrid), webhooks use validate_webhook_signature, public endpoints have no auth"
   ```

### Modifying Database Schema

1. Update models in `backend/app/models.py`
2. Create migration: `make migration name="description"`
3. Review generated migration in `backend/migrations/versions/`
4. Test migration up/down
5. Update relevant services and tests

### Working with Mastodon API

**Use Context7 for Mastodon.py documentation, Serena for code:**

1. **Check existing MastodonService methods**:
   ```bash
   mcp__serena__find_symbol MastodonService backend/app/services/mastodon_service.py --depth=1
   ```

2. **Get Mastodon.py library docs**:
   ```bash
   mcp__context7__get-library-docs /halcy/mastodon.py --topic "account endpoints"
   ```

3. **Find usage examples**:
   ```bash
   mcp__serena__find_referencing_symbols MastodonService backend/app/services/mastodon_service.py
   ```

4. **Add new method** using `mcp__serena__insert_after_symbol`

5. **Document in memory**:
   ```bash
   mcp__serena__write_memory mastodon_service_patterns "Async methods for FastAPI, sync wrappers with _sync suffix for Celery, all use Mastodon.py client from get_client()"
   ```

**Never** use `requests`, `httpx`, or `urllib` directly - Ruff enforces this

## Debugging Tips

- **Health checks**: `curl http://localhost:8080/healthz` shows service status
- **Metrics**: Prometheus endpoint at `/metrics`
- **Queue inspection**: Use Flower or `celery inspect` commands
- **Database**: `make shell-db` for PostgreSQL console
- **Logs**: Structured JSON logs with request IDs for tracing
- **DRY_RUN mode**: Set `DRY_RUN=true` to preview actions without execution

## Important Notes

- **Moderation context**: This system handles sensitive content - reliability and auditability are critical
- **Legal footer**: Every page must show footer linking to goingdark.social (license requirement)
- **Rule priority**: Database rules take precedence over any file-based config
- **Cursor-based pagination**: Account polling uses PostgreSQL cursors for efficient pagination
- **Version compatibility**: Requires Mastodon 4.0.0+ (configurable via `MIN_MASTODON_VERSION`)

## MCP Tools Best Practices

### Always Use Serena For:
- 🔍 **Code navigation**: `list_dir`, `get_symbols_overview`, `find_symbol`
- 🔎 **Code search**: `search_for_pattern`, `find_referencing_symbols`
- ✏️ **Code editing**: `replace_symbol_body`, `insert_after_symbol`, `insert_before_symbol`
- 🧠 **Knowledge**: `read_memory`, `write_memory`, `list_memories`
- 📁 **File discovery**: `find_file`

### Always Use Context7 For:
- 📚 **Library docs**: `resolve-library-id` → `get-library-docs`
- 🔧 **API references**: Mastodon.py, FastAPI, Celery, SQLAlchemy, Pydantic
- 💡 **Usage examples**: Get up-to-date code patterns from official docs

### Memory Guidelines:
- **Read memories at session start** - avoid rediscovering known patterns
- **Write discoveries immediately** - 1-3 lines about architecture, patterns, gotchas
- **Update stale memories** - delete and recreate with current information
- **Good memory names**: `detector_system_overview`, `mastodon_service_patterns`, `test_fixtures_guide`
- **Bad memory names**: `temp`, `notes`, `stuff`

### When NOT to Use MCP:
- Running tests, builds, Docker commands
- Editing config files (.env, docker-compose.yml)
- Installing dependencies
- Reading binary files or generated code
- Git operations
