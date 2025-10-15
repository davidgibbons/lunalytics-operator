"""
Retry utilities with exponential backoff.
"""

import asyncio
import logging
from typing import Callable, Any, Optional, TypeVar
from functools import wraps
import random

from ..config import config
from ..lunalytics.exceptions import LunalyticsRetryExhaustedError

logger = logging.getLogger(__name__)
T = TypeVar('T')


def async_retry(
    max_attempts: Optional[int] = None,
    backoff_factor: Optional[float] = None,
    max_delay: Optional[int] = None,
    exceptions: tuple = (Exception,)
):
    """
    Decorator for async functions with exponential backoff retry logic.
    
    Args:
        max_attempts: Maximum number of retry attempts (-1 for infinite)
        backoff_factor: Multiplier for delay between retries
        max_delay: Maximum delay between retries in seconds
        exceptions: Tuple of exceptions to catch and retry on
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Use config defaults if not provided
            attempts = max_attempts if max_attempts is not None else config.max_retry_attempts
            factor = backoff_factor if backoff_factor is not None else config.retry_backoff_factor
            delay = max_delay if max_delay is not None else config.retry_max_delay
            
            last_exception = None
            attempt = 0
            
            while True:
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    attempt += 1
                    
                    # Check if we should stop retrying
                    if attempts != -1 and attempt >= attempts:
                        logger.error(
                            f"Retry exhausted after {attempt} attempts for {func.__name__}: {e}"
                        )
                        raise LunalyticsRetryExhaustedError(
                            f"Retry exhausted after {attempt} attempts: {str(e)}"
                        ) from e
                    
                    # Calculate delay with jitter
                    if attempt == 1:
                        wait_time = 1.0
                    else:
                        wait_time = min(factor ** (attempt - 1), delay)
                        # Add jitter to prevent thundering herd
                        wait_time *= (0.5 + random.random() * 0.5)
                    
                    logger.warning(
                        f"Attempt {attempt} failed for {func.__name__}: {e}. "
                        f"Retrying in {wait_time:.2f} seconds..."
                    )
                    
                    await asyncio.sleep(wait_time)
            
        return wrapper
    return decorator


def sync_retry(
    max_attempts: Optional[int] = None,
    backoff_factor: Optional[float] = None,
    max_delay: Optional[int] = None,
    exceptions: tuple = (Exception,)
):
    """
    Decorator for sync functions with exponential backoff retry logic.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Use config defaults if not provided
            attempts = max_attempts if max_attempts is not None else config.max_retry_attempts
            factor = backoff_factor if backoff_factor is not None else config.retry_backoff_factor
            delay = max_delay if max_delay is not None else config.retry_max_delay
            
            last_exception = None
            attempt = 0
            
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    attempt += 1
                    
                    # Check if we should stop retrying
                    if attempts != -1 and attempt >= attempts:
                        logger.error(
                            f"Retry exhausted after {attempt} attempts for {func.__name__}: {e}"
                        )
                        raise LunalyticsRetryExhaustedError(
                            f"Retry exhausted after {attempt} attempts: {str(e)}"
                        ) from e
                    
                    # Calculate delay with jitter
                    if attempt == 1:
                        wait_time = 1.0
                    else:
                        wait_time = min(factor ** (attempt - 1), delay)
                        # Add jitter to prevent thundering herd
                        wait_time *= (0.5 + random.random() * 0.5)
                    
                    logger.warning(
                        f"Attempt {attempt} failed for {func.__name__}: {e}. "
                        f"Retrying in {wait_time:.2f} seconds..."
                    )
                    
                    import time
                    time.sleep(wait_time)
            
        return wrapper
    return decorator
