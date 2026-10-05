"""Structured, persistence-backed observability for Agent executions.

The trace is deliberately separate from ``thinking_process``.  It records
engineering events (nodes, tools, routing and lifecycle), never model prompts
or hidden reasoning.  Events are stored inside ``Task.intermediate_data`` so
existing SQLite databases do not require a schema migration.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4

from app.db.session import SessionLocal
from app.models import Task as TaskModel


TRACE_KEY = "execution_trace"
TRACE_VERSION = 1
MAX_SUMMARY_LENGTH = 500
MAX_TRACE_EVENTS = 500

_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
)
_BEARER_PATTERN = re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]+")
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|password|secret|token)\s*[:=]\s*[^\s,;]+"
)
_trace_lock = threading.Lock()
logger = logging.getLogger(__name__)


def _redact_text(value: str) -> str:
    value = _BEARER_PATTERN.sub("Bearer <redacted>", value)
    return _SECRET_ASSIGNMENT_PATTERN.sub(r"\1=<redacted>", value)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds")


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _safe_value(value: Any, depth: int = 0) -> Any:
    """Return a JSON-safe, size-bounded value with common secrets removed."""
    if depth >= 4:
        return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (Path, UUID)):
        return str(value)
    if isinstance(value, str):
        return _redact_text(value)[:MAX_SUMMARY_LENGTH]
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in list(value.items())[:30]:
            safe[str(key)] = (
                "<redacted>" if _is_sensitive_key(key) else _safe_value(item, depth + 1)
            )
        return safe
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(item, depth + 1) for item in list(value)[:30]]
    return str(value)[:MAX_SUMMARY_LENGTH]


def summarize(value: Any, max_length: int = MAX_SUMMARY_LENGTH) -> str:
    """Create a deterministic, redacted summary suitable for a public API."""
    safe = _safe_value(value)
    try:
        text = json.dumps(safe, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        text = str(safe)
    return text if len(text) <= max_length else f"{text[: max_length - 3]}..."


def classify_error(error: BaseException, component: str) -> dict[str, Any]:
    """Normalize exceptions without exposing tracebacks or arbitrary inputs."""
    if isinstance(error, (TimeoutError,)):
        category = "TIMEOUT"
        retryable = True
    elif isinstance(error, FileNotFoundError):
        category = "FILE_NOT_FOUND"
        retryable = False
    elif isinstance(error, (ValueError, TypeError)):
        category = "INVALID_INPUT"
        retryable = False
    else:
        category = "EXECUTION_FAILED"
        retryable = False

    normalized_component = re.sub(r"[^A-Za-z0-9]+", "_", component).strip("_").upper()
    message = _redact_text(str(error))[:MAX_SUMMARY_LENGTH]
    return {
        "code": f"{normalized_component}_{category}",
        "type": type(error).__name__,
        "message": message,
        "retryable": retryable,
    }


def new_trace_event(
    *,
    kind: str,
    name: str,
    status: str = "running",
    parent_name: str | None = None,
    metadata: dict[str, Any] | None = None,
    event_id: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started = started_at or utc_now()
    event: dict[str, Any] = {
        "version": TRACE_VERSION,
        "event_id": event_id or str(uuid4()),
        "kind": kind,
        "name": name,
        "status": status,
        "started_at": _iso(started),
    }
    if parent_name:
        event["parent_name"] = parent_name
    if metadata:
        event["metadata"] = _safe_value(metadata)
    if finished_at:
        event["finished_at"] = _iso(finished_at)
        event["duration_ms"] = max(
            0, round((finished_at - started).total_seconds() * 1000)
        )
    if error:
        event["error"] = _safe_value(error)
    return event


def finish_trace_event(
    event: dict[str, Any],
    *,
    status: str,
    metadata: dict[str, Any] | None = None,
    error: BaseException | None = None,
) -> dict[str, Any]:
    finished = utc_now()
    started_raw = event.get("started_at")
    try:
        started = datetime.fromisoformat(started_raw) if started_raw else finished
    except (TypeError, ValueError):
        started = finished
    merged_metadata = dict(event.get("metadata") or {})
    if metadata:
        merged_metadata.update(_safe_value(metadata))
    return new_trace_event(
        kind=event["kind"],
        name=event["name"],
        status=status,
        parent_name=event.get("parent_name"),
        metadata=merged_metadata or None,
        event_id=event["event_id"],
        started_at=started,
        finished_at=finished,
        error=classify_error(error, event["name"]) if error else None,
    )


def record_trace_event(
    task_id: str,
    event: dict[str, Any],
    *,
    current_subtask: str | None = None,
    subtask_progress: int | None = None,
) -> None:
    """Insert or update one event in the task's JSON trace.

    A process-local lock prevents lost JSON updates when parallel async nodes or
    callbacks complete close together.  The database is always queried again
    inside the lock, so callers never reuse stale ORM state.
    """
    if not task_id:
        return
    with _trace_lock:
        db = SessionLocal()
        try:
            task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
            if not task:
                return
            intermediate = dict(task.intermediate_data or {})
            trace = list(intermediate.get(TRACE_KEY) or [])
            event_id = event.get("event_id")
            for index, existing in enumerate(trace):
                if existing.get("event_id") == event_id:
                    trace[index] = event
                    break
            else:
                trace.append(event)
            if len(trace) > MAX_TRACE_EVENTS:
                trace = trace[-MAX_TRACE_EVENTS:]
            intermediate[TRACE_KEY] = trace
            task.intermediate_data = intermediate
            if current_subtask is not None:
                task.current_subtask = current_subtask
            if subtask_progress is not None:
                task.subtask_progress = max(0, min(100, int(subtask_progress)))
            db.commit()
        except Exception:
            db.rollback()
            # Observability must never make the audio workflow fail.
            logger.warning(
                "Failed to persist Agent trace event for task %s",
                task_id,
                exc_info=True,
            )
        finally:
            db.close()


def get_execution_trace(task: TaskModel | None) -> list[dict[str, Any]]:
    if not task or not isinstance(task.intermediate_data, dict):
        return []
    trace = task.intermediate_data.get(TRACE_KEY)
    return list(trace) if isinstance(trace, list) else []


def traced_node(
    name: str,
    node: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]],
    *,
    progress_start: int,
    progress_end: int,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Wrap a LangGraph node with a persisted, checkpoint-safe trace event."""

    async def wrapper(state: dict[str, Any]) -> dict[str, Any]:
        task_id = str(state.get("task_id") or "")
        event = new_trace_event(
            kind="node",
            name=name,
            metadata={"attempt": int(state.get("retry_count", 0)) + 1},
        )
        record_trace_event(
            task_id,
            event,
            current_subtask=name,
            subtask_progress=progress_start,
        )
        started_clock = time.perf_counter()
        try:
            result = await node(state)
            result = dict(result or {})
            completed = finish_trace_event(
                event,
                status="success",
                metadata={
                    "updates": sorted(key for key in result if key != TRACE_KEY),
                    "elapsed_clock_ms": round(
                        (time.perf_counter() - started_clock) * 1000
                    ),
                },
            )
            record_trace_event(
                task_id,
                completed,
                current_subtask=name,
                subtask_progress=progress_end,
            )
            result[TRACE_KEY] = list(result.get(TRACE_KEY) or []) + [completed]
            return result
        except BaseException as exc:
            was_cancelled = isinstance(exc, asyncio.CancelledError)
            failed = finish_trace_event(
                event,
                status="cancelled" if was_cancelled else "failed",
                metadata={
                    "elapsed_clock_ms": round(
                        (time.perf_counter() - started_clock) * 1000
                    )
                },
                error=None if was_cancelled else exc,
            )
            record_trace_event(task_id, failed, current_subtask=name)
            raise

    wrapper.__name__ = f"traced_{name}"
    return wrapper
