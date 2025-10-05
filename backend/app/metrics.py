from prometheus_client import Counter, Gauge, Histogram

accounts_scanned = Counter("sidecar_accounts_scanned_total", "Admin accounts analyzed")
analyses_flagged = Counter("sidecar_analyses_flagged_total", "Analyses flagged", ["rule"])
reports_submitted = Counter("sidecar_reports_submitted_total", "Reports submitted", ["domain"])
http_errors = Counter("sidecar_http_errors_total", "HTTP errors", ["endpoint", "code"])
queue_backlog = Gauge("sidecar_queue_backlog", "Length of RQ queue", ["queue"])
report_latency = Histogram("sidecar_report_latency_seconds", "Latency from analysis to report")
api_call_seconds = Histogram("sidecar_api_call_seconds", "API call duration seconds", ["endpoint"])
redis_degraded = Counter("sidecar_redis_degraded_total", "Redis unavailable fallbacks")
rate_limit_sleeps = Counter("sidecar_rate_limit_sleeps_total", "Times the rate limiter caused a sleep")
cursor_lag_pages = Gauge("sidecar_cursor_lag_pages", "Admin accounts pagination pages remaining", ["cursor"])
analysis_latency = Histogram("sidecar_analysis_latency_seconds", "Latency from account fetch to analysis")
