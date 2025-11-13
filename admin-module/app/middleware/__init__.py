"""
Middleware для Admin Module.
"""

from .rate_limit import RateLimitMiddleware

__all__ = [
    "RateLimitMiddleware",
]
