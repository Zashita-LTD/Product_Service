"""
Rate Limiter implementation.

Provides rate limiting for API endpoints.
"""
import asyncio
import time
from collections import defaultdict
from typing import Optional

from pkg.logger.logger import get_logger


logger = get_logger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter.
    
    Limits the rate of operations using the token bucket algorithm.
    
    Attributes:
        rate: Number of tokens added per second.
        capacity: Maximum number of tokens in the bucket.
    """
    
    def __init__(
        self,
        rate: float = 10.0,
        capacity: int = 100,
    ) -> None:
        """
        Initialize the rate limiter.
        
        Args:
            rate: Tokens per second.
            capacity: Maximum bucket capacity.
        """
        self._rate = rate
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last_update = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens from the bucket.
        
        Args:
            tokens: Number of tokens to acquire.
            
        Returns:
            True if tokens were acquired, False otherwise.
        """
        async with self._lock:
            self._refill()
            
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            
            return False
    
    async def wait_and_acquire(
        self,
        tokens: int = 1,
        timeout: Optional[float] = None,
    ) -> bool:
        """
        Wait for tokens to become available and acquire them.
        
        Args:
            tokens: Number of tokens to acquire.
            timeout: Maximum time to wait in seconds.
            
        Returns:
            True if tokens were acquired, False if timeout.
        """
        start_time = time.time()
        
        while True:
            if await self.acquire(tokens):
                return True
            
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    return False
            
            # Calculate wait time for next token
            wait_time = (tokens - self._tokens) / self._rate
            wait_time = min(wait_time, 0.1)  # Max 100ms per iteration
            
            if timeout is not None:
                remaining = timeout - (time.time() - start_time)
                wait_time = min(wait_time, remaining)
            
            if wait_time > 0:
                await asyncio.sleep(wait_time)
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self._last_update
        self._tokens = min(
            self._capacity,
            self._tokens + elapsed * self._rate,
        )
        self._last_update = now
    
    @property
    def available_tokens(self) -> float:
        """Get current available tokens."""
        return self._tokens


class SlidingWindowRateLimiter:
    """
    Sliding window rate limiter.
    
    Provides more accurate rate limiting using sliding window algorithm.
    """
    
    def __init__(
        self,
        limit: int = 100,
        window_seconds: int = 60,
    ) -> None:
        """
        Initialize the sliding window rate limiter.
        
        Args:
            limit: Maximum requests per window.
            window_seconds: Window size in seconds.
        """
        self._limit = limit
        self._window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def is_allowed(self, key: str) -> bool:
        """
        Check if a request is allowed for the given key.
        
        Args:
            key: Identifier for rate limiting (e.g., IP address, user ID).
            
        Returns:
            True if request is allowed, False otherwise.
        """
        async with self._lock:
            now = time.time()
            window_start = now - self._window_seconds
            
            # Clean up old requests
            self._requests[key] = [
                ts for ts in self._requests[key]
                if ts > window_start
            ]
            
            # Check limit
            if len(self._requests[key]) >= self._limit:
                logger.debug(
                    "Rate limit exceeded",
                    key=key,
                    count=len(self._requests[key]),
                    limit=self._limit,
                )
                return False
            
            # Record request
            self._requests[key].append(now)
            return True
    
    async def get_remaining(self, key: str) -> int:
        """
        Get remaining requests for the given key.
        
        Args:
            key: Identifier for rate limiting.
            
        Returns:
            Number of remaining requests.
        """
        async with self._lock:
            now = time.time()
            window_start = now - self._window_seconds
            
            current_count = len([
                ts for ts in self._requests[key]
                if ts > window_start
            ])
            
            return max(0, self._limit - current_count)
    
    async def get_reset_time(self, key: str) -> Optional[float]:
        """
        Get time until rate limit resets for the given key.
        
        Args:
            key: Identifier for rate limiting.
            
        Returns:
            Seconds until reset, or None if no requests recorded.
        """
        async with self._lock:
            if not self._requests[key]:
                return None
            
            oldest_request = min(self._requests[key])
            reset_time = oldest_request + self._window_seconds - time.time()
            
            return max(0, reset_time)


class IPRateLimiter:
    """
    IP-based rate limiter for API endpoints.
    
    Provides per-IP rate limiting with configurable limits.
    """
    
    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
    ) -> None:
        """
        Initialize the IP rate limiter.
        
        Args:
            requests_per_minute: Limit per minute.
            requests_per_hour: Limit per hour.
        """
        self._minute_limiter = SlidingWindowRateLimiter(
            limit=requests_per_minute,
            window_seconds=60,
        )
        self._hour_limiter = SlidingWindowRateLimiter(
            limit=requests_per_hour,
            window_seconds=3600,
        )
    
    async def is_allowed(self, ip_address: str) -> bool:
        """
        Check if a request from an IP is allowed.
        
        Args:
            ip_address: Client IP address.
            
        Returns:
            True if request is allowed.
        """
        minute_allowed = await self._minute_limiter.is_allowed(ip_address)
        if not minute_allowed:
            return False
        
        hour_allowed = await self._hour_limiter.is_allowed(ip_address)
        return hour_allowed
    
    async def get_limits(self, ip_address: str) -> dict:
        """
        Get current rate limit status for an IP.
        
        Args:
            ip_address: Client IP address.
            
        Returns:
            Dict with limit information.
        """
        return {
            "minute": {
                "remaining": await self._minute_limiter.get_remaining(ip_address),
                "reset": await self._minute_limiter.get_reset_time(ip_address),
            },
            "hour": {
                "remaining": await self._hour_limiter.get_remaining(ip_address),
                "reset": await self._hour_limiter.get_reset_time(ip_address),
            },
        }
