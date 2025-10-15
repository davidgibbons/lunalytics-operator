"""Retry utilities with exponential backoff."""

import asyncio
import logging
import random
import time
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from ..config import config
from ..lunalytics.exceptions import LunalyticsRetryExhaustedError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def async_retry(
    max_attempts: Optional[int] = None,
    backoff_factor: Optional[float] = None,
    max_delay: Optional[int] = None,
    exceptions: tuple = (Exception,),
):
    """Decorator for async functions with exponential backoff retry logic."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            attempts = (
                max_attempts if max_attempts is not None else config.max_retry_attempts
            )
            factor = (
                backoff_factor
                if backoff_factor is not None
                else config.retry_backoff_factor
            )
            delay = max_delay if max_delay is not None else config.retry_max_delay

            attempt = 0

            while True:
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    attempt += 1

                    if attempts != -1 and attempt >= attempts:
                        logger.error(
                            "Retry exhausted after %s attempts for %s: %s",
                            attempt,
                            func.__name__,
                            e,
                        )
                        raise LunalyticsRetryExhaustedError(
                            f"Retry exhausted after {attempt} attempts: {e}"
                        ) from e

                    if attempt == 1:
                        wait_time = 1.0
                    else:
                        wait_time = min(factor ** (attempt - 1), delay)
                        wait_time *= 0.5 + random.random() * 0.5

                    logger.warning(
                        "Attempt %s failed for %s: %s. Retrying in %.2f seconds...",
                        attempt,
                        func.__name__,
                        e,
                        wait_time,
                    )

                    await asyncio.sleep(wait_time)

        return wrapper

    return decorator


def sync_retry(
    max_attempts: Optional[int] = None,
    backoff_factor: Optional[float] = None,
    max_delay: Optional[int] = None,
    exceptions: tuple = (Exception,),
):
    """Decorator for sync functions with exponential backoff retry logic."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            attempts = (
                max_attempts if max_attempts is not None else config.max_retry_attempts
            )
            factor = (
                backoff_factor
                if backoff_factor is not None
                else config.retry_backoff_factor
            )
            delay = max_delay if max_delay is not None else config.retry_max_delay

            attempt = 0

            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    attempt += 1

                    if attempts != -1 and attempt >= attempts:
                        logger.error(
                            "Retry exhausted after %s attempts for %s: %s",
                            attempt,
                            func.__name__,
                            e,
                        )
                        raise LunalyticsRetryExhaustedError(
                            f"Retry exhausted after {attempt} attempts: {e}"
                        ) from e

                    if attempt == 1:
                        wait_time = 1.0
                    else:
                        wait_time = min(factor ** (attempt - 1), delay)
                        wait_time *= 0.5 + random.random() * 0.5

                    logger.warning(
                        "Attempt %s failed for %s: %s. Retrying in %.2f seconds...",
                        attempt,
                        func.__name__,
                        e,
                        wait_time,
                    )

                    time.sleep(wait_time)

        return wrapper

    return decorator
