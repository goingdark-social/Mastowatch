# MastoWatch (Watch-and-Report Sidecar)

**⚠️ Work in Progress**: This project is under active development. Features and documentation may change.

Analyze accounts/statuses and **file reports via API** so human moderators act in Mastodon's admin UI. **No auto-enforcement.**

## Production-Ready Features

- ✅ **Error Handling**: Comprehensive API error responses with structured logging and request IDs
- ✅ **Health Checks**: Robust health monitoring with proper HTTP status codes (503 for service unavailability)
- ✅ **Security**: Webhook signature validation, API key authentication, and security scanning
- ✅ **Database**: Foreign keys, performance indexes, reliable migrations
- ✅ **Monitoring**: Prometheus metrics, structured JSON logging, and detailed analytics
- ✅ **Frontend**: settings interface with error states and real-time configuration
- ✅ **Testing**: Comprehensive edge case test coverage (22 test scenarios)
- ✅ **CI/CD**: Automated testing, static analysis, and code formatting
- ✅ **API Compliance**: Automated validation against mastodon.py library (see [docs/api-compliance-checker.md](docs/api-compliance-checker.md))
- ✅ **Audit Logs**: Enforcement actions recorded with rule context and API responses
- ✅ **User Notifications**: Warnings and suspensions include messages sent through Mastodon
- ✅ **Media-aware Scanning**: Analyzes attachments for alt text, MIME types, and URL hashes
- ✅ **Context-aware Status Analysis**: Each new status is checked alongside the account's latest public posts. Unlisted posts don't affect rate rules but are still scanned for shady links.

## Quick start

To get a working stack, run:

```bash
docker compose up
```

For local development use the setup script. It launches a mock Mastodon server unless `.env.local` is present.

```bash
./scripts/setup-dev.sh
```

## Configuration

**📖 For complete environment variable documentation, see: [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)**

### Quick Setup

1. Copy the environment template: `cp .env.example .env`
2. Edit `.env` with your actual values
3. For production: Set required tokens and secrets
4. For development: The override file provides safe defaults

### Minimum Required Settings

* `INSTANCE_BASE`: your Mastodon instance base URL
* `MASTODON_CLIENT_SECRET`: token with `write:reports` scope
* `MASTODON_CLIENT_SECRET`: token with admin read scopes
* `API_KEY`: secure random string for API authentication
* `WEBHOOK_SECRET`: secure random string for webhook signature validation
* `DATABASE_URL`: PostgreSQL connection string
* `REDIS_URL`: Redis connection string
* `USER_AGENT`: user agent for Mastodon requests (default: `MastoWatch/<VERSION> (+moderation-sidecar)`)
* `HTTP_TIMEOUT`: seconds before Mastodon requests time out (default: `30`)
* `VERSION`: application version (default: `0.1.0`)
* `SKIP_STARTUP_VALIDATION`: `true` to skip startup checks (for testing only)
* `UI_ORIGIN`: origin for the dashboard UI
* `MIN_MASTODON_VERSION`: minimum supported Mastodon version (default: `4.0.0`)
* `POLL_ADMIN_ACCOUNTS_INTERVAL`: seconds between remote admin polls (default: `30`)
* `POLL_ADMIN_ACCOUNTS_LOCAL_INTERVAL`: seconds between local admin polls (default: `30`)
* `QUEUE_STATS_INTERVAL`: seconds between queue metrics snapshots (default: `15`)
* `VITE_API_URL`: API base URL for the frontend

To send notifications to Slack, set `SLACK_WEBHOOKS` to a JSON object mapping event names to webhook URLs.

### Getting Mastodon Access Tokens

This application uses **direct access tokens** rather than OAuth2 client credentials. You need to create two applications in your Mastodon instance:

#### 1. Admin Token (for moderation operations)
1. Go to your Mastodon instance → **Settings → Development**
2. Click **"New Application"**
3. Configure:
   - **Application name**: `MastoWatch Admin`
   - **Scopes**: Select `admin:read` and `admin:write`
4. Click **"Submit"**
5. Copy the **"Your access token"** → use as `MASTODON_CLIENT_SECRET` in `.env`

#### 2. Bot Token (for reading and reporting)
1. Create another new application
2. Configure:
   - **Application name**: `MastoWatch Bot`  
   - **Scopes**: Select `read` and `write:reports`
3. Click **"Submit"**
4. Copy the **"Your access token"** → use as `MASTODON_CLIENT_SECRET` in `.env`

**Note**: You only need the access tokens, not the client key/secret shown in the application details.

#### 3. OAuth Application (for admin web interface)
1. Create a third application for OAuth login
2. Configure:
   - **Application name**: `MastoWatch OAuth`
   - **Scopes**: Select `read:accounts` (for user verification)
   - **Redirect URI**: Your callback URL (e.g., `https://your.domain/admin/callback`)
3. Click **"Submit"**
4. Copy the **"Client key"** → use as `OAUTH_CLIENT_ID` in `.env`
5. Copy the **"Client secret"** → use as `OAUTH_CLIENT_SECRET` in `.env`

## Mastodon API Integration

MastoWatch uses the official [mastodon.py](https://github.com/halcy/mastodon.py) library for all Mastodon API operations:

- **Official library**: Community-maintained with full Mastodon API support
- **Built-in features**: Rate limiting, pagination, error handling
- **Synchronous architecture**: Direct synchronous calls, FastAPI handles concurrency via threadpool
- **Centralized access**: All API calls go through `MastodonService` wrapper

See [docs/mastodon-py-integration.md](docs/mastodon-py-integration.md) for complete integration details.

### API Endpoints

#### Health & Monitoring
* `GET /healthz` - Health check with service status (returns 503 if services unavailable)
* `GET /metrics` - Prometheus metrics for monitoring

#### Configuration Management (requires admin login)
* `GET /config` - Return non-sensitive configuration details
* `POST /config/dry_run?enable=true|false` - Toggle dry run mode
* `POST /config/panic_stop?enable=true|false` - Emergency stop all processing

#### Rule Management (requires admin login)
* `GET /rules` - List all rules
* `POST /rules` - Create a rule
* `PUT /rules/{id}` - Update a rule
* `DELETE /rules/{id}` - Delete a rule
* `POST /rules/{id}/toggle` - Enable or disable a rule

Rules may combine two patterns using `boolean_operator` (`AND` or `OR`) with a `secondary_pattern`.

#### Analytics & Data (requires admin login)
* `GET /analytics/overview` - System analytics overview with account/report metrics
* `GET /analytics/timeline?days=N` - Timeline analytics for the past N days (1-365)
* `GET /logs` - Enforcement audit log entries

#### Authentication
* `GET /admin/login` - Initiate OAuth login flow for admin access
* `GET /admin/callback` - OAuth callback handler
* `POST /admin/logout` - Clear admin session
* `GET /api/v1/me` - Get current user information

#### Testing & Validation  
* `POST /dryrun/evaluate` - Test rule evaluation (body: `{"account": {...}, "statuses": [...]}`) returns `{"score": float, "hits": [[rule, weight, evidence], ...]}`

#### Webhooks
* `POST /webhooks/status` - Webhook endpoint for Mastodon status updates (requires signature validation)

### Error Handling
All API endpoints return structured error responses with:
- **Request IDs** for tracing and debugging
- **Detailed error messages** with context
- **Proper HTTP status codes** (400/401/404/422/500/503)
- **Structured logging** with JSON format for monitoring

## Background Jobs

MastoWatch uses RQ (Redis Queue) for background job processing:

- **Simple**: Jobs are plain Python functions - no decorators needed
- **Observable**: Built-in web dashboard and REST API for monitoring
- **Synchronous**: Matches the synchronous nature of mastodon.py
- **Recurring jobs**: RQ Scheduler handles cron-like scheduling
- **Dashboard**: Access at `http://localhost:9181` in development

See [docs/rq-migration.md](docs/rq-migration.md) for complete job system documentation.

## Notes

* RQ Scheduler manages recurring jobs (poll_admin_accounts, queue_stats, etc.) with configurable intervals via environment variables.
* All endpoints use structured JSON logging with request IDs for troubleshooting.
* Alembic migrations run via the `migrate` service. Note that `alembic.ini` leaves `sqlalchemy.url` empty; the `DATABASE_URL` environment variable is used instead.
* Add Prometheus to scrape `/metrics` as desired.
* Foreign keys ensure data integrity; performance indexes optimize common queries.
* RQ Dashboard provides real-time monitoring of job queues, status, and history.

## Legal Notice

Every page shows a footer linking to [goingdark.social](https://goingdark.social). The app refuses to run without it. Don't remove or rename this credit; it's part of the license.
