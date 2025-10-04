# GitHub Copilot Instructions for MastoWatch

**MANDATORY: ALWAYS use MCP tools (Serena + Context7) as your PRIMARY interface for this codebase. Start EVERY session by activating the Serena project. Traditional file operations are FALLBACK ONLY.**

## MCP-First Workflow (MANDATORY)

### Session Initialization (Required First Steps)

**ALWAYS run these commands at the start of EVERY work session:**

```bash
# 1. Activate Serena project (MANDATORY - DO THIS FIRST)
# Use MCP tool: activate_project
# Project config: .serena/project.yml

# 2. Verify onboarding (one-time setup)
# Use MCP tool: check_onboarding_performed
# If not performed: onboarding

# 3. Read relevant memories before ANY code work
# Use MCP tool: list_memories
# Then: read_memory for each relevant memory file
```

### All Code Operations MUST Use MCP Tools

**Navigation & Discovery:**
- `get_symbols_overview`: Inspect file structure BEFORE reading
- `find_symbol`: Locate definitions (use include_body=True for implementation)
- `find_referencing_symbols`: Find all callers before changing ANY symbol
- `search_for_pattern`: Search across codebase when symbol search insufficient
- `find_file` / `list_dir`: Locate files by name/pattern

**Code Editing (MANDATORY - NO DIRECT FILE EDITS):**
- `replace_symbol_body`: Modify function/class implementations
- `insert_before_symbol` / `insert_after_symbol`: Add new code safely
- `replace_regex`: Targeted multi-line edits when symbol tools insufficient

**Knowledge Management (MANDATORY):**
- `read_memory`: Check existing project knowledge BEFORE making changes
- `write_memory`: Document ALL discoveries (1-3 lines) AFTER gathering new info
- `list_memories`: Review available knowledge at session start
- `delete_memory`: Remove outdated knowledge

**Validation (Use Before Completing Tasks):**
- `think_about_task_adherence`: Verify you're solving the right problem
- `think_about_collected_information`: Check if you have sufficient context
- `think_about_whether_you_are_done`: Confirm task completion criteria

### Library Documentation (MANDATORY - Use Context7)

**For ANY external library questions:**

```bash
# 1. Resolve library ID first
# Use Context7 tool: resolve-library-id
# Example: "mastodon.py" → "/halcy/mastodon.py"

# 2. Fetch focused documentation
# Use Context7 tool: get-library-docs
# Specify: context7CompatibleLibraryID, topic (optional), tokens (optional)

# 3. Document findings
# Use Serena tool: write_memory
# Save key insights for future reference
```

**Common library IDs for this project:**
- Mastodon API: `/halcy/mastodon.py`
- FastAPI: Resolve as needed
- Celery: Resolve as needed
- SQLAlchemy: Resolve as needed

### Standard MCP-First Edit Workflow (MANDATORY)

**Follow this sequence for EVERY code change:**

```bash
# 1. Check memories for relevant context
list_memories
read_memory <relevant_memory_file>

# 2. Get file overview
get_symbols_overview <file_path>

# 3. Locate target symbol with implementation
find_symbol <symbol_name> --include_body=True

# 4. Find all callers (CRITICAL before changes)
find_referencing_symbols <symbol_name>

# 5. Make the edit
replace_symbol_body <symbol_name> <new_implementation>
# OR
insert_after_symbol <anchor_symbol> <new_code>

# 6. Document the change
write_memory <memory_name> "<1-3 line summary of change/discovery>"

# 7. Validate with tests
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest <test_file> --no-header --tb=short
```

### When to Use Traditional File Operations (RARE)

**ONLY use traditional bash_tool/view/str_replace when:**
- Serena project fails to activate (technical issue)
- Working with non-code files (configs, docs, requirements.txt)
- Initial repository bootstrap (dependency installation)
- Running tests and builds
- MCP tools explicitly unavailable

**Even then, return to MCP tools as soon as possible.**

## Project Overview

MastoWatch is a **Mastodon moderation sidecar** that analyzes accounts/statuses and files reports via API for human moderators. It's a **watch-and-report system with no auto-enforcement** by default, built with FastAPI, Celery, PostgreSQL, and Redis.

## Architecture & Key Components

### Core Services Stack
- **API** (`app/api/`): FastAPI web server with routers for analytics, auth, config, rules, and scanning
  - Use Serena: `get_symbols_overview app/api/` to explore
  - Entry point: `app/main.py`
- **Worker** (`app/tasks/jobs.py`): Celery workers for background account analysis and webhook event processing
  - Use Serena: `find_symbol analyze_and_maybe_report --include_body=True`
- **Beat**: Celery scheduler for periodic polling (every 30s)
- **Database**: PostgreSQL with Alembic for migrations
- **Redis**: Celery broker and caching for deduplication and rate limiting

### Rule Engine & Analysis
- **Rules**: **Database-driven exclusively** via the `RuleService` 
  - Use Serena: `find_symbol RuleService` in `app/services/rule_service.py`
  - The old `rules.yml` is deprecated and no longer used
- **Scanning**: Enhanced scanning system
  - Use Serena: `get_symbols_overview app/enhanced_scanning.py`
- **Enforcement**: Optional automated actions
  - Use Serena: `find_symbol EnforcementService` in `app/services/enforcement_service.py`
- **Detectors**: Pluggable detection modules
  - Use Serena: `list_dir app/services/detectors/`
  - Then: `get_symbols_overview` on specific detector files

### Mastodon API Client Wrapper
- **Primary Interface**: All application logic **must** interact through `MastodonService`
  - Use Serena: `find_symbol MastodonService` in `app/services/mastodon_service.py`
  - Use Context7: `resolve-library-id "mastodon.py"` → `get-library-docs /halcy/mastodon.py`
- **Official Library**: Uses **mastodon.py library** with built-in rate limiting
  - Use Context7 for authoritative documentation and examples

## Working Effectively with MCP

### Bootstrap and Validate the Repository

**ALWAYS run these commands first (uses traditional tools for setup):**

```bash
# Install Python dependencies for quality checks and testing
cd /home/runner/work/Mastowatch/Mastowatch
python -m pip install --upgrade pip
pip install -r backend/requirements.txt -r tests/requirements-test.txt
```

**After bootstrap, IMMEDIATELY switch to MCP:**

```bash
# Activate Serena project
# Use MCP tool: activate_project

# Verify onboarding
# Use MCP tool: check_onboarding_performed

# List available memories
# Use MCP tool: list_memories
```

**Initial validation (traditional testing):**
```bash
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest tests/test_startup_validation.py::test_validate_mastodon_version_ok --no-header --tb=short
```

**Dependencies Summary**:
- **Python**: Uses Python 3.12+ (3.13 in CI)
- **Node**: Uses Node.js 22 for frontend development
- **Backend Dependencies**: FastAPI, Celery, SQLAlchemy, PostgreSQL, Redis
- **Frontend Dependencies**: React 19, Vite, Mantine UI, TypeScript

### Test Suite (Traditional - No MCP)
```bash
# Run tests - VALIDATED: 147 tests complete in ~26 seconds
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest --no-header --tb=short
# Timeout: Set 2+ minutes. NEVER CANCEL - tests are comprehensive.
```

### Frontend Development (Traditional - No MCP)
```bash
# Frontend setup and build - VALIDATED timing
cd frontend
npm ci                    # Takes ~13 seconds. NEVER CANCEL.
npm run build            # Takes ~8 seconds. NEVER CANCEL.
```

### Quality Checks (Traditional - No MCP)
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

### Make Commands (Preferred for Infrastructure)
**Use `make` commands for infrastructure, but MCP tools for code work.**

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

### Testing Strategy (MCP-Enhanced)
- **Test Discovery**: Use Serena `find_file "test_*.py"` or `list_dir tests/`
- **Test Inspection**: Use Serena `get_symbols_overview tests/<test_file>.py`
- **Restructured Test Suite**: Tests organized by feature area (`tests/api`, `tests/services`, `tests/tasks`)
- **Isolation**: Tests use in-memory SQLite and separate Redis instance
- **Mocking External APIs**: All Mastodon API calls mocked using `unittest.mock.patch`
- **Run tests (traditional)**: `PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest` 
- **TIMING**: 147 tests complete in ~26 seconds. Set timeout to 2+ minutes. NEVER CANCEL.
- **Current Status**: 77/147 tests fail due to codebase inconsistencies

### Code Quality Tools (Traditional Infrastructure)
- **Formatting**: Black with **120-character** line length (`make format`)
- **Format checking**: `make format-check` (36 files currently need reformatting)
- **Linting**: Ruff with custom rules in `pyproject.toml` (`make lint`) (160 errors present)
- **Type checking**: MyPy with selective strictness (`make typecheck`) (module conflicts present)
- **All quality checks**: `make check` runs lint, format-check, typecheck, and test (EXPECT FAILURES)
- **HTTP Library Policy**: Only `MastodonService` wrapper permitted for Mastodon API
  - Use Serena: `find_referencing_symbols MastodonService` to verify compliance
- **TIMING**: Quality checks very quick - lint ~0.05s, format-check ~5s, typecheck ~0.6s

### Database Operations (Traditional Infrastructure)
```bash
# Run migrations (automatic during startup)
make migration name="your_migration_description"

# Database shell
make shell-db
```

### Service Management (Traditional Infrastructure)
```bash
# Restart specific services
make restart-api
make restart-worker  
make restart-frontend

# Enter container shells
make shell-api       # API container shell
```

### Mastodon Client Management (MCP-Enhanced)
```bash
# Update OpenAPI spec from submodule (traditional)
make update-api-spec

# Regenerate typed client from current spec (traditional)
make regenerate-client

# Full update: submodule + spec + client (traditional)
make update-mastodon-client

# Show current API client status (traditional)
make api-client-status

# Explore MastodonService implementation (MCP)
# Use Serena: get_symbols_overview app/services/mastodon_service.py
# Use Serena: find_symbol MastodonService --include_body=True

# Get mastodon.py library documentation (MCP)
# Use Context7: resolve-library-id "mastodon.py"
# Use Context7: get-library-docs /halcy/mastodon.py --topic "rate limiting"
```

## Critical Configuration Patterns

### Environment Variables Structure
- **Required**: `INSTANCE_BASE`, `BOT_TOKEN`, `ADMIN_TOKEN`, `API_KEY`, `WEBHOOK_SECRET`
- **OAuth for admin UI**: `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_REDIRECT_URI`
- **Safety controls**: `DRY_RUN=true`, `PANIC_STOP=false`, `SKIP_STARTUP_VALIDATION=false`
- **Database URL format**: `postgresql+psycopg://user:pass@host:port/db`

**To explore configuration handling (MCP):**
```bash
# Use Serena: find_symbol Settings --include_body=True
# Use Serena: search_for_pattern "INSTANCE_BASE"
```

### API Authentication Patterns
- **Webhook Validation**: HMAC SHA256 signature in `X-Hub-Signature-256` header
- **Admin UI Auth**: OAuth2 flow with HttpOnly session cookie
- **Programmatic API Auth**: Static API key in `X-API-Key` header
- **Rate Limiting**: Handled by mastodon.py via `MastodonService` wrapper

**To explore authentication implementation (MCP):**
```bash
# Use Serena: get_symbols_overview app/api/auth.py
# Use Serena: find_symbol validate_webhook --include_body=True
# Use Context7: get-library-docs /halcy/mastodon.py --topic "authentication"
```

### Task Queue Architecture
- **Polling Tasks**: `poll_admin_accounts` (remote) and `poll_admin_accounts_local`
- **Event Processing**: `process_new_report` and `process_new_status` (webhook-triggered)
- **Analysis Pipeline**: `analyze_and_maybe_report` evaluates accounts against rules
- **Cursor Management**: PostgreSQL-based cursors for pagination

**To explore task implementation (MCP):**
```bash
# Use Serena: get_symbols_overview app/tasks/jobs.py
# Use Serena: find_symbol analyze_and_maybe_report --include_body=True
# Use Serena: find_referencing_symbols process_new_status
```

## Project-Specific Conventions

### Data Flow Patterns (Explore with MCP)
1.  **Account Discovery**: Celery Beat → `poll_admin_accounts` → Account persistence
2.  **Rule Evaluation**: Account + statuses → `RuleService` → detectors → violations
3.  **Report Generation/Enforcement**: Violation score > threshold → `EnforcementService` → `MastodonService`
4.  **Webhook Processing**: Real-time event → webhook endpoint → Celery task → analysis

**To trace data flow (MCP):**
```bash
# Use Serena: find_symbol poll_admin_accounts --include_body=True
# Use Serena: find_referencing_symbols RuleService
# Use Serena: find_referencing_symbols EnforcementService
```

### Error Handling Standards
- **Structured Logging**: JSON format with request IDs
- **Health Checks**: `/healthz` endpoint (503 on DB/Redis failure)
- **Graceful Degradation**: `PANIC_STOP` halts processing, `DRY_RUN` logs without executing
- **Retry Strategies**: Celery exponential backoff with jitter

**To explore error handling (MCP):**
```bash
# Use Serena: search_for_pattern "logger.error"
# Use Serena: find_symbol healthz --include_body=True
# Use Serena: search_for_pattern "retry"
```

### Database Schema Patterns
- **Foreign Keys**: Enforce referential integrity
- **UPSERT Patterns**: PostgreSQL `ON CONFLICT DO UPDATE`
- **Deduplication**: `dedupe_key` fields prevent duplicate reports
- **Timestamps**: All tables include `created_at` and `updated_at` with timezone

**To explore database models (MCP):**
```bash
# Use Serena: list_dir app/models/
# Use Serena: get_symbols_overview app/models/<model_file>.py
# Use Serena: find_symbol Account --include_body=True
```

### Frontend Integration
- **Static Assets**: Mounted at `/dashboard`
- **OAuth Popup Flow**: Admin login with `postMessage` communication
- **CORS Configuration**: Controlled by `CORS_ORIGINS` environment variable

**To explore frontend integration (MCP):**
```bash
# Use Serena: find_symbol oauth_callback --include_body=True
# Use Serena: search_for_pattern "CORS_ORIGINS"
```

## File Structure Patterns (Explore with MCP)

### Key Directories
```bash
# Explore with Serena MCP tools:
# list_dir app/api/              # FastAPI routers
# list_dir app/services/         # Core business logic
# list_dir app/services/detectors/  # Detection modules
# list_dir app/tasks/            # Celery job definitions
# list_dir tests/                # Test suite
# list_dir specs/                # OpenAPI schemas
```

### Configuration Files (Traditional)
- `pyproject.toml`: Black, MyPy, Ruff configurations
- `alembic.ini`: Database migration settings
- `docker-compose.yml`: Production stack
- `docker-compose.override.yml`: Development overrides

## Validation Scenarios

### After Making Code Changes with MCP, ALWAYS Test:

1. **Document your changes (MCP - MANDATORY)**:
   ```bash
   # Use Serena: write_memory <change_name> "<1-3 line description>"
   ```

2. **Basic Test Suite Validation (Traditional)**:
   ```bash
   PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest --no-header --tb=short -x
   # TIMING: ~26 seconds for 147 tests. NEVER CANCEL - wait for completion.
   # EXPECTED: 77/147 tests fail due to codebase inconsistencies
   ```

3. **Frontend Build Validation (Traditional)** (if frontend changes):
   ```bash
   cd frontend
   npm ci && npm run build
   # TIMING: npm ci ~13s, build ~8s. NEVER CANCEL.
   ```

4. **Quality Check Validation (Traditional)**:
   ```bash
   make lint          # EXPECT: 160 errors in current codebase (~0.05s)
   make format-check  # EXPECT: 36 files needing formatting (~5s)  
   make typecheck     # EXPECT: module conflicts (~0.6s)
   # TIMING: Each check completes very quickly. NEVER CANCEL.
   ```

### Manual Testing Requirements
- **Cannot test full Docker stack** in sandboxed environments (SSL issues)
- Focus on individual component testing (Python modules, frontend builds)
- Test API endpoints using test client from `tests/conftest.py`
  - Use Serena: `find_symbol test_client` to understand test setup
- Validate rule creation/evaluation using `RuleService` tests
  - Use Serena: `find_file "test_rule*"` to locate tests
- Check database operations using in-memory SQLite from tests

### Current Codebase Limitations
- **Docker builds fail** in sandboxed environments (SSL certificate errors)
- **Many quality check failures** - current state, not regression
- **Test failures expected** - 77/147 tests fail due to inconsistencies
- **Module naming conflicts** - `auth.py` conflicts require careful imports
  - Use Serena: `find_symbol` with full paths to disambiguate

## Time Expectations and Timeouts

### Command Timing Summary
- **Python Dependencies**: pip install ~45 seconds → Set timeout: 5+ minutes
- **Tests**: 147 tests in ~26 seconds → Set timeout: 2+ minutes
- **Frontend npm ci**: ~13 seconds → Set timeout: 2+ minutes  
- **Frontend build**: ~8 seconds → Set timeout: 2+ minutes
- **Quality checks**: lint ~0.05s, format-check ~5s, typecheck ~0.6s → Set timeout: 2+ minutes
- **Docker builds**: Would be 5-15 minutes normally, but **FAIL in sandboxed environments**
- **MCP operations**: <1 second typically, but allow 2+ minutes for safety

### CRITICAL: NEVER CANCEL Commands
- **NEVER CANCEL** test suites - comprehensive validation takes time
- **NEVER CANCEL** npm installs - package downloads can be slow
- **NEVER CANCEL** builds - even if they appear to hang, wait for timeout
- **NEVER CANCEL** MCP tools - they may be processing large symbol graphs
- **ALWAYS** set generous timeouts (2+ minutes minimum, 15+ minutes for builds)

## Quick Reference - Most Common Commands

### Essential Setup (Run First - Traditional Then MCP)
```bash
# 1. Bootstrap dependencies (traditional)
cd /home/runner/work/Mastowatch/Mastowatch
python -m pip install --upgrade pip
pip install -r backend/requirements.txt -r tests/requirements-test.txt

# 2. Activate MCP tools (MANDATORY)
# Use MCP: activate_project
# Use MCP: check_onboarding_performed
# Use MCP: list_memories
```

### Testing (Traditional - Use Every Time)
```bash
# Single test (fast validation)
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest tests/test_startup_validation.py::test_validate_mastodon_version_ok

# Full test suite (~26 seconds, timeout: 2+ minutes)
PYTHONPATH=backend SKIP_STARTUP_VALIDATION=1 pytest --no-header --tb=short
```

### Frontend (Traditional - If Modified)
```bash
cd frontend
npm ci && npm run build    # ~21 seconds total, timeout: 2+ minutes
```

### Quality Checks (Traditional - Expect Issues)
```bash
make lint format-check typecheck    # All complete in <6 seconds
```

### Code Navigation (MCP - PRIMARY METHOD)
```bash
# Use Serena: get_symbols_overview <file_path>
# Use Serena: find_symbol <symbol_name> --include_body=True
# Use Serena: find_referencing_symbols <symbol_name>
# Use Serena: search_for_pattern "<pattern>"
```

### Code Editing (MCP - PRIMARY METHOD)
```bash
# Use Serena: replace_symbol_body <symbol_name> <new_implementation>
# Use Serena: insert_after_symbol <anchor_symbol> <new_code>
# Use Serena: replace_regex <file_path> <pattern> <replacement>
```

### Knowledge Management (MCP - MANDATORY)
```bash
# Before work: list_memories + read_memory <relevant_file>
# After work: write_memory <name> "<1-3 line summary>"
# Use Serena: list_memories
# Use Serena: read_memory <memory_file>
# Use Serena: write_memory <memory_name> "<content>"
```

### Library Documentation (Context7 - MANDATORY)
```bash
# Use Context7: resolve-library-id "<library_name>"
# Use Context7: get-library-docs <context7_library_id> --topic "<topic>"
# Example: resolve-library-id "mastodon.py" → /halcy/mastodon.py
# Example: get-library-docs /halcy/mastodon.py --topic "rate limiting"
```

## MCP Best Practices Summary

### ALWAYS (Mandatory):
1. **Start session**: `activate_project` → `check_onboarding_performed` → `list_memories`
2. **Before editing**: `read_memory` → `get_symbols_overview` → `find_symbol --include_body=True`
3. **Before changing**: `find_referencing_symbols` to find all callers
4. **Make edits**: Use `replace_symbol_body` / `insert_after_symbol` (NOT manual file edits)
5. **After editing**: `write_memory` with 1-3 line summary
6. **Library questions**: `resolve-library-id` → `get-library-docs` via Context7
7. **Validate**: Run tests, document findings in memories

### NEVER (Prohibited):
1. **Never** make direct file edits when MCP tools are available
2. **Never** skip memory checks before editing
3. **Never** skip documenting discoveries in memories
4. **Never** search the web for library docs without checking Context7 first
5. **Never** assume symbol usage without running `find_referencing_symbols`
6. **Never** complete a task without running `think_about_whether_you_are_done`

### Fallback to Traditional (Only When):
1. MCP tools fail due to technical issues
2. Working with non-code files (configs, requirements)
3. Running infrastructure commands (tests, builds, Docker)
4. Initial repository bootstrap (dependency installation)

When working on this codebase, always consider the moderation context. This system handles sensitive content and must be reliable, auditable, and safe. Use MCP tools to maintain code quality and project knowledge throughout development.