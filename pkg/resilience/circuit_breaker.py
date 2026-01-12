"""
Circuit Breaker implementation.

Provides resilience pattern for external service calls.
"""
import asyncio
import time
from enum import Enum
from typing import Callable, TypeVar, Any, Optional
from functools import wraps

from pkg.logger.logger import get_logger


logger = get_logger(__name__)


T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""
    
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, rejecting calls
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open."""
    
    def __init__(self, message: str = "Circuit breaker is open") -> None:
        """
        Initialize circuit breaker error.
        
        Args:
            message: Error message.
        """
        self.message = message
        super().__init__(self.message)


class CircuitBreaker:
    """
    Circuit Breaker implementation.
    
    Prevents cascading failures by failing fast when a service is unavailable.
    
    States:
    - CLOSED: Normal operation, calls pass through.
    - OPEN: Service is failing, calls are rejected immediately.
    - HALF_OPEN: Testing if service has recovered.
    
    Attributes:
        failure_threshold: Number of failures before opening circuit.
        recovery_timeout: Seconds to wait before testing recovery.
        half_open_max_calls: Max calls allowed in half-open state.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 1,
        name: str = "default",
    ) -> None:
        """
        Initialize the circuit breaker.
        
        Args:
            failure_threshold: Number of failures to open circuit.
            recovery_timeout: Seconds before attempting recovery.
            half_open_max_calls: Max test calls in half-open state.
            name: Circuit breaker name for logging.
        """
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._name = name
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state
    
    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count
    
    async def call(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Execute a function through the circuit breaker.
        
        Args:
            func: Async function to execute.
            *args: Function arguments.
            **kwargs: Function keyword arguments.
            
        Returns:
            Function result.
            
        Raises:
            CircuitBreakerError: If circuit is open.
        """
        async with self._lock:
            await self._check_state()
            
            if self._state == CircuitState.OPEN:
                logger.warning(
                    "Circuit breaker is open, rejecting call",
                    circuit=self._name,
                )
                raise CircuitBreakerError(
                    f"Circuit breaker '{self._name}' is open"
                )
            
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self._half_open_max_calls:
                    raise CircuitBreakerError(
                        f"Circuit breaker '{self._name}' is half-open, max calls reached"
                    )
                self._half_open_calls += 1
        
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise
    
    async def _check_state(self) -> None:
        """Check and update circuit state based on timeout."""
        if self._state == CircuitState.OPEN:
            if self._last_failure_time is not None:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self._recovery_timeout:
                    logger.info(
                        "Circuit breaker transitioning to half-open",
                        circuit=self._name,
                        elapsed=elapsed,
                    )
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
    
    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(
                    "Circuit breaker closing after successful recovery",
                    circuit=self._name,
                )
                self._state = CircuitState.CLOSED
            
            self._failure_count = 0
            self._half_open_calls = 0
    
    async def _on_failure(self) -> None:
        """Handle failed call."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                logger.warning(
                    "Circuit breaker opening after failed recovery attempt",
                    circuit=self._name,
                )
                self._state = CircuitState.OPEN
            elif self._failure_count >= self._failure_threshold:
                logger.warning(
                    "Circuit breaker opening after threshold exceeded",
                    circuit=self._name,
                    failures=self._failure_count,
                    threshold=self._failure_threshold,
                )
                self._state = CircuitState.OPEN
    
    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self._half_open_calls = 0
        logger.info("Circuit breaker reset", circuit=self._name)


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    name: Optional[str] = None,
) -> Callable:
    """
    Decorator to apply circuit breaker to an async function.
    
    Args:
        failure_threshold: Number of failures to open circuit.
        recovery_timeout: Seconds before attempting recovery.
        name: Circuit breaker name.
        
    Returns:
        Decorator function.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        cb_name = name or func.__name__
        cb = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            name=cb_name,
        )
        
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await cb.call(func, *args, **kwargs)
        
        # Attach circuit breaker for inspection
        wrapper.circuit_breaker = cb  # type: ignore
        
        return wrapper
    
    return decorator
