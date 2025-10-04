import time

import redis
from app.config import get_settings
from app.metrics import rate_limit_sleeps, redis_degraded

settings = get_settings()
rcli = redis.from_url(settings.REDIS_URL, decode_responses=True)


def _keys(key):
    return f"rl:{key}:limit", f"rl:{key}:remaining", f"rl:{key}:reset"


def update_from_headers(key, headers):
    lim = headers.get("X-RateLimit-Limit")
    rem = headers.get("X-RateLimit-Remaining")
    rst = headers.get("X-RateLimit-Reset")
    if lim and rem and rst:
        k1, k2, k3 = _keys(key)
        pipe = rcli.pipeline()
        pipe.setex(k1, 3600, lim)
        pipe.setex(k2, 3600, rem)
        pipe.setex(k3, 3600, rst)
        pipe.execute()


def throttle_if_needed(key):
    """If Redis is missing, fail-open slowly at ~1 rps per worker."""
    try:
        k1, k2, k3 = _keys(key)
        rem = rcli.get(k2)
        rst = rcli.get(k3)
        now = int(time.time())
        if rem is not None and rst is not None:
            if int(rem) <= 1 and now < int(rst):
                sleep_for = max(0, int(rst) - now) + 1
                time.sleep(min(sleep_for, 60))
                rate_limit_sleeps.inc()
                return
    except Exception:
        redis_degraded.inc()
        time.sleep(1.0)
