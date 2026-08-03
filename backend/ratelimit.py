"""Shared rate limiter (slowapi / limits).

Defaults to an in-memory store, which is fine for a single backend instance
(the cheapest, simplest deployment). If you run more than one backend replica
behind a load balancer, set REDIS_URL so all instances share the same counters
-- otherwise each instance enforces its own limit independently and the
effective limit becomes (limit x number of instances). A free Redis instance
(e.g. Upstash's free tier) is enough for this.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from limits import storage as limits_storage
from limits import strategies as limits_strategies

import config

_storage_uri = config.REDIS_URL or "memory://"

limiter = Limiter(key_func=get_remote_address, storage_uri=_storage_uri)

# Shared with api_keys.py, which needs a *per-key* limit value read from Mongo (set by the
# business owner when creating the key) rather than a fixed string a route decorator can
# express -- so it drives the same `limits` library directly. Reusing this storage instance
# (rather than each opening its own) keeps counts consistent under REDIS_URL in a multi-replica
# deployment, and avoids a second Redis connection pool for the same purpose.
api_key_storage = limits_storage.storage_from_string(_storage_uri)
api_key_rate_strategy = limits_strategies.MovingWindowRateLimiter(api_key_storage)
