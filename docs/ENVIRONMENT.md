# MastoWatch Environment Configuration

This document describes all environment variables used by MastoWatch for configuration.

## Required Environment Variables

These variables must be set for MastoWatch to function properly:

### Mastodon Instance Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `INSTANCE_BASE` | Base URL of your Mastodon instance | `https://mastodon.social` |
| `BOT_TOKEN` | Mastodon bot token with required API permissions | `your_bot_token_here` |
| `ADMIN_TOKEN` | Mastodon admin token for accessing admin endpoints | `your_admin_token_here` |

### Database Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+psycopg://user:pass@host:port/db` |

### Redis Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `REDIS_URL` | Redis connection string for Celery broker/backend | `redis://host:port/db` |

### Security Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `API_KEY` | Secure API key for programmatic access | Generate with: `openssl rand -base64 32` |
| `WEBHOOK_SECRET` | Secret for validating incoming webhooks | Generate with: `openssl rand -base64 32` |

## Optional Environment Variables

### Safety Controls

| Variable | Default | Description |
|----------|---------|-------------|
| `DRY_RUN` | `true` (dev) / `false` (prod) | When true, prevents actual enforcement actions |
| `PANIC_STOP` | `false` | Emergency stop switch to halt all processing |
| `SKIP_STARTUP_VALIDATION` | `false` | Skip configuration validation on startup |

### Database Connection (PostgreSQL)

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_DB` | `mastowatch` | PostgreSQL database name |
| `POSTGRES_USER` | `mastowatch` | PostgreSQL username |
| `POSTGRES_PASSWORD` | *(required)* | PostgreSQL password |

### Frontend Integration

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ORIGINS` | `["http://localhost:3000"]` | JSON array of allowed CORS origins |

### OAuth Configuration (Admin Dashboard)

| Variable | Default | Description |
|----------|---------|-------------|
| `OAUTH_CLIENT_ID` | *(empty)* | OAuth client ID for admin authentication |
| `OAUTH_CLIENT_SECRET` | *(empty)* | OAuth client secret |
| `OAUTH_REDIRECT_URI` | *(empty)* | OAuth redirect URI |

### Performance Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `POLL_ADMIN_ACCOUNTS_INTERVAL` | `30` | Interval for polling remote admin accounts (seconds) |
| `POLL_ADMIN_ACCOUNTS_LOCAL_INTERVAL` | `30` | Interval for polling local admin accounts (seconds) |
| `QUEUE_STATS_INTERVAL` | `60` | Interval for recording queue statistics (seconds) |
| `BATCH_SIZE` | `100` | Number of accounts to process per batch |
| `MAX_PAGES_PER_POLL` | `10` | Maximum pages to process per polling cycle |

## Environment Configuration by Deployment Type

### Production Deployment

For production, set these variables through your deployment platform (Kubernetes secrets, Docker Compose environment, etc.):

```bash
# Required - Replace with actual values
INSTANCE_BASE=https://your-mastodon-instance.com
BOT_TOKEN=your_actual_bot_token
ADMIN_TOKEN=your_actual_admin_token
DATABASE_URL=postgresql+psycopg://user:password@db-host:5432/mastowatch
REDIS_URL=redis://redis-host:6379/0
API_KEY=your_secure_api_key_32_chars_minimum
WEBHOOK_SECRET=your_secure_webhook_secret_32_chars

# Database
POSTGRES_PASSWORD=your_secure_db_password

# Production settings
DRY_RUN=false
CORS_ORIGINS=["https://your-domain.com"]
```

### Development Deployment

The `docker-compose.override.yml` provides safe defaults for development:

```bash
# Optional - Override defaults if needed
INSTANCE_BASE=https://your-test-instance.example.com
BOT_TOKEN=your_dev_bot_token
ADMIN_TOKEN=your_dev_admin_token
API_KEY=dev_api_key_change_in_production
WEBHOOK_SECRET=dev_webhook_secret_change_in_production

# Development automatically sets:
# - DRY_RUN=true (safe mode)
# - Local database credentials
# - Permissive CORS for local development
```

## Security Considerations

### Token Security

- **Bot Token**: Should have minimum required permissions for your use case
- **Admin Token**: Requires admin-level access to your Mastodon instance
- **API Key**: Use a cryptographically secure random string (minimum 32 characters)
- **Webhook Secret**: Use a cryptographically secure random string

### Production Hardening

1. **Never commit secrets** to version control
2. **Use environment-specific configuration** (separate dev/staging/prod)
3. **Rotate tokens regularly** as part of security maintenance
4. **Monitor token usage** through Mastodon's admin interface
5. **Set DRY_RUN=false** only after thorough testing

### Generating Secure Secrets

```bash
# Generate API key
openssl rand -base64 32

# Generate webhook secret
openssl rand -base64 32

# Generate random password
openssl rand -base64 16
```

## Validation

MastoWatch performs startup validation to ensure required configuration is present and valid. If validation fails, the application will refuse to start and display specific error messages.

To temporarily bypass validation (not recommended for production):

```bash
SKIP_STARTUP_VALIDATION=true
```

## Troubleshooting

### Common Configuration Issues

1. **"BOT_TOKEN is missing"**: Ensure the token is set and not a placeholder value
2. **"Database connection failed"**: Verify DATABASE_URL format and credentials
3. **"Redis connection failed"**: Verify REDIS_URL and Redis server availability
4. **"Invalid CORS origins"**: Ensure CORS_ORIGINS is valid JSON array format

### Debug Configuration

To see what configuration values are being used (with secrets masked):

```bash
# Check application logs during startup
docker-compose logs api | grep -i config
```
