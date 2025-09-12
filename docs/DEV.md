# Mastowatch Development Setup

## Production-Ready Development Environment

MastoWatch now includes comprehensive production-readiness features:

### 🔧 Enhanced Development Features
- **Comprehensive error handling** with structured logging and request IDs
- **Extensive test coverage** with 22 edge case scenarios
- **Real-time settings interface** with error states and validation
- **CI/CD integration** with automated testing and static analysis
- **Security features** including webhook signature validation and API authentication
- **Optional enforcement** to warn, silence, or suspend accounts with timed actions automatically undone

### 🧪 Testing Infrastructure
- **Edge case testing**: 22 comprehensive test scenarios covering webhooks, health checks, and configuration
- **Mocked dependencies**: Isolated testing with database, Redis, and Celery mocks
- **Environment controls**: `SKIP_STARTUP_VALIDATION=1` for test environments

### 📊 Monitoring & Observability
- **Structured JSON logging** with request IDs for tracing
- **Health endpoints** returning proper HTTP status codes (503 for service failures)
- **Prometheus metrics** with detailed application metrics
- **Analytics dashboard** with real-time system status
- **Audit logs** for enforcement actions accessible via `/logs`

## Quick Start

```bash
./scripts/setup-dev.sh
```

The script starts a stack with a mock Mastodon server using `.env.development`. Add real credentials in `.env.local` to bypass the mock. Secrets that are still missing are written to `.env.generated`.

```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml up
```

**Or use the convenient Makefile shortcuts:**

```bash
make dev           # Start development environment
make dev-build     # Start with fresh build
make backend-only  # Start only backend services
make frontend-only # Start only frontend service
make logs          # View logs
make clean         # Stop and clean up
make help          # See all available commands
```

**Note:** The `migrate` service will automatically run `alembic upgrade head` before the API starts—no manual migration step needed. The first startup may take a moment while migrations complete.

## Prerequisites

- **Docker**: Required for PostgreSQL and Redis
- **Python 3.13+**: For backend development
- **Node.js 22+**: For frontend development

## Environment Setup

1. Copy environment file: `cp .env.example .env`
2. Edit `.env` with your Mastodon instance details. The API, worker, and beat services all read from this shared file:

### Required Production Settings
   - `INSTANCE_BASE`: Your Mastodon instance URL
   - `ADMIN_TOKEN`: Admin access token from your instance
   - `BOT_TOKEN`: Bot access token from your instance
   - `API_KEY`: Random string for API authentication (production security)
   - `WEBHOOK_SECRET`: Random string for webhook validation (production security)

### OAuth Admin Login (for Web UI)
   - `OAUTH_CLIENT_ID`: OAuth application client ID
   - `OAUTH_CLIENT_SECRET`: OAuth application client secret
   - `OAUTH_REDIRECT_URI`: OAuth callback URL (e.g., `http://localhost:8000/admin/callback` for dev)
   - `OAUTH_SCOPE`: OAuth scopes for admin login (default: `read:accounts`)
   - `SESSION_SECRET_KEY`: Random secret for session cookies (generate with `openssl rand -base64 32`)

### Development Settings
   - `DRY_RUN`: Set to `true` for development to avoid sending actual reports
   - `PANIC_STOP`: Emergency stop flag (default: `false`)
   - `SKIP_STARTUP_VALIDATION`: Set to `true` when running tests (bypasses connectivity checks)
   - `UI_ORIGIN`: defaults to `http://localhost:5173`
   - `VITE_API_URL`: defaults to `http://localhost:8080`
   - `HTTP_TIMEOUT`: defaults to `30`
   - `RULE_CACHE_TTL`: defaults to `60`
   - `MIN_MASTODON_VERSION`: defaults to `4.0.0`
   - `POLL_ADMIN_ACCOUNTS_INTERVAL`: defaults to `30`
   - `POLL_ADMIN_ACCOUNTS_LOCAL_INTERVAL`: defaults to `30`
   - `QUEUE_STATS_INTERVAL`: defaults to `15`

### Database & Cache
   - `DATABASE_URL`: PostgreSQL connection (auto-configured in Docker)
   - `REDIS_URL`: Redis connection (auto-configured in Docker)

### Configuration Loading
`app/config.py` pulls values from `.env` using Pydantic's `BaseSettings`.
The settings source is defined with `model_config`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )
```

This replaces the previous `class Config` approach.

## Testing

### Running Tests
```bash
# Run all tests
pytest

# Run specific test suite
pytest tests/test_edge_cases.py -v

# Run individual test
pytest tests/test_edge_cases.py::TestEdgeCasesAndErrorHandling::test_webhook_valid_signature -v
```

### Test Environment Configuration
Tests automatically use these environment variables:
```bash
SKIP_STARTUP_VALIDATION=1  # Bypass connectivity checks
API_KEY=test_api_key_123   # For authenticated endpoint tests
WEBHOOK_SECRET=test_webhook_secret_123  # For webhook signature tests
```

### Static Analysis & Code Quality
Use the Makefile targets to keep the codebase clean and consistent:

```bash
make format       # Format code with Black
make lint         # Lint with Ruff
make typecheck    # Run MyPy
make test         # Run tests
make check        # Run all of the above
```

### Pull Request Image Builds

Add the `build_pr` label to a pull request to build the Docker image in CI. Without the label, the job is skipped.

### Getting Mastodon Access Tokens

This application requires **two access tokens** from your Mastodon instance:

#### Creating Admin Token
1. Go to your Mastodon instance → **Settings → Development**
2. Click **"New Application"**
3. Set **Application name**: `MastoWatch Admin`
4. **Important**: Set scopes to `admin:read` and `admin:write`
5. Click **"Submit"**
6. Copy **"Your access token"** and paste as `ADMIN_TOKEN` in `.env`

#### Creating Bot Token  
1. Create another new application in the same place
2. Set **Application name**: `MastoWatch Bot`
3. **Important**: Set scopes to `read` and `write:reports`
4. Click **"Submit"**
5. Copy **"Your access token"** and paste as `BOT_TOKEN` in `.env`

**Note**: This app uses direct access tokens, not OAuth2 client credentials. You only need the "Your access token" value from each application, not the client key/secret.



## Project Structure

```
app/                    # Backend Python code
├── auth.py            # API key authentication  
├── main.py            # FastAPI application with enhanced error handling
├── config.py          # Configuration management
├── models.py          # SQLAlchemy database models
├── startup_validation.py  # Environment validation with test bypass
├── clients/mastodon/  # Type-safe Mastodon API client
└── tasks/             # Celery background tasks

frontend/              # React/TypeScript frontend
├── src/App.tsx       # Enhanced settings interface with error states
└── src/api.ts        # Frontend API client

db/migrations/         # Database migrations
├── 003_add_foreign_keys.py      # Data integrity constraints
└── 004_add_performance_indexes.py  # Query optimization

tests/                 # Comprehensive test suite
├── test_edge_cases.py # 22 edge case scenarios
├── test_api.py        # API endpoint tests
└── test_config.py     # Configuration tests

.github/workflows/     # CI/CD pipeline
└── python-ci.yml      # Automated testing and static analysis

.env                   # Environment variables (copy from .env.example)
```

Remote and local account polling both use a shared helper to keep the code simple.

## Behavioral Detection

- `automation_disclosure`: checks the last twenty posts for templates and steady timing. Non-bot accounts are flagged when more than half of posts look automated and metrics report `automation_percentage` and `average_interval`. Bots are flagged if they post publicly more than once an hour or twenty-four times a day, with `hourly_rate` and `daily_rate` returned.
- `link_spam`: triggers when twenty recent posts all contain links and the content repeats or all links point to one domain. Metrics include `link_ratio` and `domain_distribution`.

## Database Features

### Production-Ready Database Schema
- **Foreign Keys**: Proper relationships between accounts, analyses, and reports with CASCADE deletion
- **Performance Indexes**: Strategic indexes on commonly queried fields:
  - `created_at` fields for time-based queries
  - `mastodon_account_id` for account lookups
  - `rule_key` for analysis filtering
  - `domain` and `acct` for account searches

### Migration Management
```bash
# Migrations run automatically in Docker, but for manual management:
alembic upgrade head    # Apply all migrations
alembic current        # Show current migration version
alembic history        # Show migration history
```

## Frontend Development

### Enhanced Settings Interface
The frontend now includes:
- **Real-time configuration** with immediate feedback
- **Error handling** with user-friendly alerts
- **System status monitoring** with service health indicators
- **Analytics dashboard** with account and report metrics
- **Persistence validation** ensuring settings are properly saved
- **AutoMod configuration** at `/config/automod` for DRY_RUN overrides, default actions, and defederation limits
- **apiFetch helper** centralizing headers and credentials for API calls

### Frontend Development Commands
```bash
cd frontend
npm install     # Install dependencies
npm run dev     # Start development server
npm run build   # Build for production
npm run preview # Preview production build
```
