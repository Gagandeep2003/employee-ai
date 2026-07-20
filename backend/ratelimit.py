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

import config

_storage_uri = config.REDIS_URL or "memory://"

limiter = Limiter(key_func=get_remote_address, storage_uri=_storage_uri)
