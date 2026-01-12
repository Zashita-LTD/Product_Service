"""
HTTP Middleware for Product Service.

Provides middleware components for request processing.
"""

from .metrics import MetricsMiddleware

__all__ = [
    "MetricsMiddleware",
]
