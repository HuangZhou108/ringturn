"""Structured, serializable diagnostics for Agent execution.

The trace is intentionally separate from ``thinking_process``.  It records
engineering events (nodes, tools, routes and failures), never model chain of
thought or raw tool arguments.
"""

from __future__ import annotations

import asyncio
import inspect
import re
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Awaitable, Callable, Iterable, Mapping
from uuid import uuid4

MAX_TRACE_EVENTS = 500
MAX_ERROR_MESSAGE_LENGTH = 500

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[-_]?key|authorization|password|secret|token)\b"
    r"(\s*[:=]\s*)([^\s,;}&]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_OPENAI_KEY = re.compile(r"\bsk-[a-zA-Z0-9_-]{8,}\b")


def utc_now_iso() -> str:
    """Return a stable UTC timestamp that sorts lexicographically."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def redact_text(value: Any, *, limit: int = MAX_ERROR_MESSAGE_LENGTH) -> str:
    """Convert a value to bounded text and remove common credential forms."""

    text = str(value)
    text = _SECRET_ASSIGNMENT.sub(r"\1\2[REDACTED]", text)
    text = _BEARER_TOKEN.sub("Bearer [REDACTED]", text)
    text = _OPENAI_KEY.sub("[REDACTED]", text)
    return text[:limit]


def summarize_tool_input(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> dict:
    """Describe a tool call without persisting argument values."""

    return {
        "positional_count": len(args),
        "positional_types": [type(value).__name__ for value in args[:10]],
        "keyword_names": sorted(str(key) for key in kwargs)[:30],
        "keyword_types": {
            str(key): type(value).__name__
            for key, value in sorted(kwargs.items(), key=lambda item: str(item[0]))[:30]
        },
    }


def summarize_result(result: Any) -> dict:
    """Return structural metadata only; never include the result payload."""

    summary: dict[str, Any] = {"type": type(result).__name__}
    if isinstance(result, Mapping):
        summary["keys"] = sorted(str(key) for key in result.keys())[:40]
        summary["key_count"] = len(result)
    elif isinstance(result, (list, tuple, set)):
        summary["item_count"] = len(result)
    elif result is None:
        summary["is_none"] = True
    return summary


def build_execution_error(
    error: BaseException,
    *,
    scope: str,
    component: str,
) -> dict:
    """Normalize exceptions into a stable public diagnostics shape."""

    if isinstance(error, asyncio.CancelledError):
        code = "EXECUTION_CANCELLED"
        retryable = False
    elif isinstance(error, (asyncio.TimeoutError, TimeoutError)):
        code = "EXECUTION_TIMEOUT"
        retryable = True
    elif isinstance(error, FileNotFoundError):
        code = "REQUIRED_FILE_NOT_FOUND"
        retryable = False
    elif isinstance(error, ConnectionError):
        code = "DEPENDENCY_CONNECTION_FAILED"
        retryable = True
    else:
        code = f"{scope.upper()}_EXECUTION_FAILED"
        retryable = False

    return {
        "code": code,
        "scope": scope,
        "component": component,
        "retryable": retryable,
        "exception_type": type(error).__name__,
        "message": redact_text(error),
    }


def create_trace_event(
    *,
    task_id: str,
    kind: str,
    name: str,
    status: str,
    duration_ms: float | None = None,
    details: Mapping[str, Any] | None = None,
    error: Mapping[str, Any] | None = None,
    timestamp: str | None = None,
) -> dict:
    """Create one JSON-safe trace event with a stable schema."""

    event = {
        "event_id": str(uuid4()),
        "task_id": task_id,
        "thread_id": task_id,
        "timestamp": timestamp or utc_now_iso(),
        "kind": kind,
        "name": name,
        "status": status,
    }
    if duration_ms is not None:
        event["duration_ms"] = round(max(0.0, duration_ms), 3)
    if details:
        event["details"] = dict(details)
    if error:
        event["error"] = dict(error)
    return event


def create_fallback_event(
    *,
    task_id: str,
    component: str,
    from_strategy: str,
    to_strategy: str,
    reason: str,
    error: BaseException | None = None,
) -> dict:
    """Create a sanitized event for an explicit, safe fallback."""

    details = {
        "from": from_strategy,
        "to": to_strategy,
        "reason": reason,
    }
    normalized_error = None
    if error is not None:
        normalized_error = build_execution_error(
            error,
            scope="fallback",
            component=component,
        )
    return create_trace_event(
        task_id=task_id,
        kind="resilience",
        name=component,
        status="fallback",
        details=details,
        error=normalized_error,
    )


def merge_trace_events(
    left: Iterable[dict] | None,
    right: Iterable[dict] | None,
) -> list[dict]:
    """LangGraph reducer that de-duplicates and bounds trace history."""

    merged: list[dict] = []
    seen: set[str] = set()
    for event in [*(left or []), *(right or [])]:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("event_id", ""))
        if event_id and event_id in seen:
            continue
        if event_id:
            seen.add(event_id)
        merged.append(event)
    merged.sort(key=lambda item: str(item.get("timestamp", "")))
    return merged[-MAX_TRACE_EVENTS:]


def get_execution_diagnostics(
    intermediate_data: Mapping[str, Any] | None,
    *,
    task_id: str,
) -> tuple[list[dict], dict | None]:
    """Return only diagnostics owned by the requested task."""

    intermediate = intermediate_data or {}
    events = [
        event
        for event in intermediate.get("execution_trace", [])
        if isinstance(event, dict) and event.get("task_id") == task_id
    ]
    error = intermediate.get("execution_error")
    if not events or not isinstance(error, dict) or error.get("task_id") != task_id:
        error = None
    return events, error


def without_execution_diagnostics(
    intermediate_data: Mapping[str, Any] | None,
) -> dict:
    """Copy reusable audio intermediates without parent-task diagnostics."""

    inherited = dict(intermediate_data or {})
    inherited.pop("execution_trace", None)
    inherited.pop("execution_error", None)
    return inherited


def select_entry_route(
    resume_from_node: str | None,
    *,
    allowed_nodes: Iterable[str],
    default_node: str,
) -> tuple[str, str]:
    """Resolve the entry target and a deterministic diagnostic reason."""

    allowed = set(allowed_nodes)
    if resume_from_node in allowed:
        return str(resume_from_node), "feedback_resume"
    if resume_from_node:
        return default_node, "invalid_resume_target_fallback"
    return default_node, "new_task"


def select_retry_route(
    *,
    needs_revision: bool,
    retry_count: int,
    max_retries: int,
    retry_node: str,
    end_node: str,
) -> tuple[str, str]:
    """Preserve the production retry condition while explaining its branch."""

    if not needs_revision:
        return end_node, "quality_accepted"
    if retry_count > max_retries:
        return end_node, "retry_limit_reached"
    return retry_node, "quality_revision_requested"


def persist_trace_event(task_id: str, event: Mapping[str, Any]) -> None:
    """Persist an event in the existing Task JSON column without a migration."""

    # Lazy imports keep the trace schema independently testable without loading
    # FastAPI, SQLAlchemy or the audio stack.
    from app.db.session import SessionLocal
    from app.models import Task as TaskModel

    db = SessionLocal()
    try:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            return
        intermediate = dict(task.intermediate_data or {})
        current = intermediate.get("execution_trace", [])
        intermediate["execution_trace"] = merge_trace_events(current, [dict(event)])
        if event.get("status") in {"failed", "cancelled"} and event.get("error"):
            execution_error = dict(event["error"])
            execution_error["task_id"] = task_id
            intermediate["execution_error"] = execution_error
        task.intermediate_data = intermediate
        db.commit()
    except Exception as persistence_error:
        # Diagnostics must never make an otherwise healthy audio task fail.
        print(
            f"[TRACE] persistence failed: {redact_text(persistence_error, limit=200)}"
        )
    finally:
        db.close()


async def _persist(
    persist: Callable[[str, Mapping[str, Any]], Any] | None,
    task_id: str,
    event: Mapping[str, Any],
) -> None:
    if persist is None or not task_id:
        return
    result = persist(task_id, event)
    if inspect.isawaitable(result):
        await result


def instrument_node(
    name: str,
    node: Callable[..., Awaitable[dict | None]],
    *,
    persist: Callable[[str, Mapping[str, Any]], Any] | None = persist_trace_event,
) -> Callable[..., Awaitable[dict]]:
    """Wrap a LangGraph node with structured start/end/failure events."""

    @wraps(node)
    async def wrapped(state: Mapping[str, Any], *args: Any, **kwargs: Any) -> dict:
        task_id = str(state.get("task_id", ""))
        started = create_trace_event(
            task_id=task_id,
            kind="node",
            name=name,
            status="running",
        )
        await _persist(persist, task_id, started)
        started_at = time.perf_counter()
        try:
            result = await node(state, *args, **kwargs)
        except asyncio.CancelledError as error:
            normalized = build_execution_error(error, scope="node", component=name)
            cancelled = create_trace_event(
                task_id=task_id,
                kind="node",
                name=name,
                status="cancelled",
                duration_ms=(time.perf_counter() - started_at) * 1000,
                error=normalized,
            )
            await _persist(persist, task_id, cancelled)
            raise
        except Exception as error:
            normalized = build_execution_error(error, scope="node", component=name)
            failed = create_trace_event(
                task_id=task_id,
                kind="node",
                name=name,
                status="failed",
                duration_ms=(time.perf_counter() - started_at) * 1000,
                error=normalized,
            )
            await _persist(persist, task_id, failed)
            raise

        updates = dict(result or {})
        returned_trace = updates.get("execution_trace", [])
        for event in returned_trace if isinstance(returned_trace, list) else []:
            if isinstance(event, dict):
                await _persist(persist, task_id, event)
        completed = create_trace_event(
            task_id=task_id,
            kind="node",
            name=name,
            status="succeeded",
            duration_ms=(time.perf_counter() - started_at) * 1000,
            details={
                "updated_fields": sorted(
                    key for key in updates.keys() if key != "execution_trace"
                )
            },
        )
        await _persist(persist, task_id, completed)
        updates["execution_trace"] = merge_trace_events(
            returned_trace if isinstance(returned_trace, list) else [],
            [started, completed],
        )
        return updates

    return wrapped
