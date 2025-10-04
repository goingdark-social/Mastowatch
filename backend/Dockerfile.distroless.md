# Distroless Dockerfile for MastoWatch Backend

This Dockerfile creates a much smaller image (~50MB target) using Google's distroless base image.

## Benefits
- Smaller attack surface (no shell, package managers, etc.)
- Smaller image size (removes OS packages)
- security (runs as nonroot by default)

## Trade-offs  
- No shell access for debugging (use `docker exec` won't work)
- Healthchecks need to be external or use Python directly
- Harder to troubleshoot issues inside the container

## Usage
Build with: `docker build -f Dockerfile.distroless -t mastowatch-backend:distroless .`

For production Kubernetes, update healthchecks to use HTTP probes instead of exec probes.

For docker-compose, you can replace the healthcheck with:
```yaml
healthcheck:
test: ["CMD", "/usr/bin/python3", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/livez').getcode()==200 else 1)"]
```
