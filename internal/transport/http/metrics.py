"""
Metrics collection middleware for HTTP requests.

Collects metrics for all HTTP requests using Prometheus.
"""

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from internal.infrastructure.metrics import (
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION,
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to collect HTTP request metrics.
    
    Tracks request count and duration for all endpoints.
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request and collect metrics.
        
        Args:
            request: Incoming HTTP request.
            call_next: Next middleware/handler in chain.
            
        Returns:
            HTTP response.
        """
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Extract request details
        endpoint = request.url.path
        method = request.method
        status = response.status_code
        
        # Record metrics
        HTTP_REQUESTS_TOTAL.labels(
            method=method,
            endpoint=endpoint,
            status_code=status
        ).inc()
        
        HTTP_REQUEST_DURATION.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)
        
        return response
