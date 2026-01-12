"""
Metrics infrastructure for Parser Service.

Provides Prometheus metrics for monitoring.
"""

from .prometheus import (
    PAGES_PARSED,
    PRODUCTS_EXTRACTED,
    PARSE_DURATION,
    PROXY_REQUESTS,
    PROXY_POOL_SIZE,
    BLOCKED_REQUESTS,
    CONTEXT_ROTATIONS,
    KAFKA_MESSAGES_PRODUCED,
)

__all__ = [
    "PAGES_PARSED",
    "PRODUCTS_EXTRACTED",
    "PARSE_DURATION",
    "PROXY_REQUESTS",
    "PROXY_POOL_SIZE",
    "BLOCKED_REQUESTS",
    "CONTEXT_ROTATIONS",
    "KAFKA_MESSAGES_PRODUCED",
]
