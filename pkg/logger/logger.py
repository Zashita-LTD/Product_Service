"""
Structured logging module.

Provides JSON-formatted structured logging with context support.
"""
import logging
import json
import sys
from datetime import datetime
from typing import Any, Optional
from contextvars import ContextVar


# Context variable for request ID
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.
    
    Outputs log records as JSON for easy parsing by log aggregators.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record as JSON.
        
        Args:
            record: Log record to format.
            
        Returns:
            JSON-formatted log string.
        """
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add request ID from context if available
        request_id = request_id_var.get()
        if request_id:
            log_data["request_id"] = request_id
        
        # Add extra fields from record
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in (
                    "name", "msg", "args", "levelname", "levelno",
                    "pathname", "filename", "module", "exc_info",
                    "exc_text", "stack_info", "lineno", "funcName",
                    "created", "msecs", "relativeCreated", "thread",
                    "threadName", "processName", "process", "message",
                    "taskName",
                ):
                    log_data[key] = self._serialize_value(value)
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False, default=str)
    
    def _serialize_value(self, value: Any) -> Any:
        """
        Serialize a value for JSON output.
        
        Args:
            value: Value to serialize.
            
        Returns:
            JSON-serializable value.
        """
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        if isinstance(value, (list, tuple)):
            return [self._serialize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        return str(value)


class StructuredLogger(logging.Logger):
    """
    Logger with structured logging support.
    
    Allows passing extra fields as keyword arguments.
    """
    
    def _log_with_extras(
        self,
        level: int,
        msg: str,
        args: tuple,
        **kwargs: Any,
    ) -> None:
        """
        Log with extra fields.
        
        Args:
            level: Log level.
            msg: Log message.
            args: Message arguments.
            **kwargs: Extra fields to include in log.
        """
        extra = kwargs.pop("extra", {})
        extra.update(kwargs)
        super()._log(level, msg, args, extra=extra)
    
    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log debug message with extra fields."""
        self._log_with_extras(logging.DEBUG, msg, args, **kwargs)
    
    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log info message with extra fields."""
        self._log_with_extras(logging.INFO, msg, args, **kwargs)
    
    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log warning message with extra fields."""
        self._log_with_extras(logging.WARNING, msg, args, **kwargs)
    
    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log error message with extra fields."""
        self._log_with_extras(logging.ERROR, msg, args, **kwargs)
    
    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log critical message with extra fields."""
        self._log_with_extras(logging.CRITICAL, msg, args, **kwargs)


# Set custom logger class
logging.setLoggerClass(StructuredLogger)


def setup_logging(
    level: str = "INFO",
    json_format: bool = True,
) -> None:
    """
    Set up logging configuration.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_format: Whether to use JSON format.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))
    
    if json_format:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
        )
    
    root_logger.addHandler(handler)


def get_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (typically __name__).
        
    Returns:
        StructuredLogger instance.
    """
    return logging.getLogger(name)  # type: ignore


def set_request_id(request_id: str) -> None:
    """
    Set the request ID in context.
    
    Args:
        request_id: Request identifier.
    """
    request_id_var.set(request_id)


def get_request_id() -> Optional[str]:
    """
    Get the current request ID from context.
    
    Returns:
        Request ID or None.
    """
    return request_id_var.get()
