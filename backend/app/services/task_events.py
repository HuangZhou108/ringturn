"""Durable task events with low-latency in-process fan-out."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.db.session import SessionLocal
from app.models import TaskEvent


def _iso(value: datetime | None = None) -> str:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class _Subscriber:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue


class TaskEventBroker:
    """Thread-safe process-local fan-out; the DB log covers other workers."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[_Subscriber]] = {}
        self._lock = threading.Lock()

    def subscribe(self, task_id: str) -> _Subscriber:
        subscriber = _Subscriber(asyncio.get_running_loop(), asyncio.Queue())
        with self._lock:
            self._subscribers.setdefault(task_id, set()).add(subscriber)
        return subscriber

    def unsubscribe(self, task_id: str, subscriber: _Subscriber) -> None:
        with self._lock:
            subscribers = self._subscribers.get(task_id)
            if not subscribers:
                return
            subscribers.discard(subscriber)
            if not subscribers:
                self._subscribers.pop(task_id, None)

    def publish(self, task_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers.get(task_id, ()))
        for subscriber in subscribers:
            def put(sub: _Subscriber = subscriber) -> None:
                sub.queue.put_nowait(event)

            try:
                subscriber.loop.call_soon_threadsafe(put)
            except RuntimeError:
                self.unsubscribe(task_id, subscriber)


broker = TaskEventBroker()


def serialize_task_event(event: TaskEvent) -> dict[str, Any]:
    payload = dict(event.payload or {})
    return {
        **payload,
        "event_id": event.id,
        "type": event.event_type,
        "task_id": event.task_id,
        "timestamp": _iso(event.created_at),
    }


def emit_task_event(
    task_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Append one event and immediately publish it to local subscribers."""
    db = SessionLocal(expire_on_commit=False)
    try:
        event = TaskEvent(
            task_id=task_id,
            event_type=event_type,
            payload=dict(payload or {}),
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        serialized = serialize_task_event(event)
        broker.publish(task_id, serialized)
        return serialized
    except Exception as error:
        db.rollback()
        print(f"[TASK_EVENT] persistence failed: {type(error).__name__}")
        return None
    finally:
        db.close()


def get_task_events(
    task_id: str,
    *,
    after_event_id: int = 0,
    limit: int = 500,
) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        events = (
            db.query(TaskEvent)
            .filter(TaskEvent.task_id == task_id, TaskEvent.id > after_event_id)
            .order_by(TaskEvent.id.asc())
            .limit(max(1, min(limit, 2000)))
            .all()
        )
        return [serialize_task_event(event) for event in events]
    finally:
        db.close()


def emit_task_status(task_id: str, status: str, **details: Any) -> None:
    event_type = {
        "completed": "completed",
        "failed": "failed",
        "cancelled": "cancelled",
        "waiting_input": "waiting_input",
    }.get(status, "status_update")
    emit_task_event(task_id, event_type, {"status": status, **details})
