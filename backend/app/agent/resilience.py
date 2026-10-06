"""Bounded retry and timeout primitives for Agent execution.

The helpers in this module are deliberately independent from FastAPI,
SQLAlchemy and the audio stack so that policy decisions stay deterministic and
can be unit-tested without loading production dependencies.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, TypeVar

T = TypeVar("T")


class ExecutionDeadlineExceeded(TimeoutError):
    """Raised when the bounded Agent pipeline exhausts its execution budget."""


@dataclass(frozen=True)
class RetryPolicy:
    """Policy for retrying one explicitly allow-listed operation."""

    max_attempts: int = 1
    timeout_seconds: float | None = None
    backoff_seconds: float = 0.0
    max_backoff_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds must not be negative")
        if self.max_backoff_seconds < 0:
            raise ValueError("max_backoff_seconds must not be negative")


def parse_name_allowlist(value: str | Iterable[str] | None) -> frozenset[str]:
    """Normalize a comma-separated or iterable allow-list."""

    if value is None:
        return frozenset()
    values = value.split(",") if isinstance(value, str) else value
    return frozenset(str(item).strip() for item in values if str(item).strip())


def retry_delay_seconds(policy: RetryPolicy, failed_attempt: int) -> float:
    """Return capped exponential backoff after a one-based failed attempt."""

    if failed_attempt < 1 or policy.backoff_seconds == 0:
        return 0.0
    delay = policy.backoff_seconds * (2 ** (failed_attempt - 1))
    return min(delay, policy.max_backoff_seconds)


def is_retryable_error(error: BaseException) -> bool:
    """Classify only transient failures as retryable.

    Broad runtime or validation errors are intentionally excluded: replaying
    audio transformations after an unknown failure can duplicate side effects.
    """

    return isinstance(error, (TimeoutError, ConnectionError))


def policy_for_name(
    name: str,
    *,
    allowlist: str | Iterable[str] | None,
    max_attempts: int,
    timeout_seconds: float,
    backoff_seconds: float,
    max_backoff_seconds: float,
) -> RetryPolicy:
    """Return an active policy only for an explicitly allow-listed name."""

    if name not in parse_name_allowlist(allowlist):
        return RetryPolicy()
    return RetryPolicy(
        max_attempts=max_attempts,
        timeout_seconds=timeout_seconds,
        backoff_seconds=backoff_seconds,
        max_backoff_seconds=max_backoff_seconds,
    )


async def run_with_retry(
    operation: Callable[[int], Awaitable[T]],
    *,
    policy: RetryPolicy,
    on_retry: Callable[[int, BaseException, float], Any] | None = None,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> tuple[T, int]:
    """Run an operation with bounded attempts and per-attempt timeouts.

    ``operation`` receives a one-based attempt number.  The return value pairs
    the result with the number of attempts used.  ``on_retry`` is invoked only
    when another attempt will actually happen.
    """

    for attempt in range(1, policy.max_attempts + 1):
        try:
            pending = operation(attempt)
            if policy.timeout_seconds is None:
                result = await pending
            else:
                result = await asyncio.wait_for(
                    pending,
                    timeout=policy.timeout_seconds,
                )
            return result, attempt
        except asyncio.CancelledError:
            raise
        except Exception as error:
            should_retry = attempt < policy.max_attempts and is_retryable_error(error)
            if not should_retry:
                raise
            delay = retry_delay_seconds(policy, attempt)
            if on_retry is not None:
                callback_result = on_retry(attempt, error, delay)
                if asyncio.iscoroutine(callback_result):
                    await callback_result
            if delay:
                await sleep(delay)

    raise AssertionError("retry loop exited without a result or exception")
