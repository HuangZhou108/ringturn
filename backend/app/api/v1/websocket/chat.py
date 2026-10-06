"""Replayable WebSocket event stream for Agent tasks."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

from app.agent.state import get_step_message
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import (HumanIntervention, HumanInterventionStatus, Task,
                        TaskStatus)
from app.services.task_events import broker, get_task_events

settings = get_settings()
TERMINAL_EVENT_TYPES = {"completed", "failed", "cancelled"}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ConnectionManager:
    """Track multiple clients per task instead of replacing older sockets."""

    def __init__(self) -> None:
        self.active_connections: dict[str, set[WebSocket]] = {}

    async def connect(self, task_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.setdefault(task_id, set()).add(websocket)

    def disconnect(self, task_id: str, websocket: WebSocket | None = None) -> None:
        connections = self.active_connections.get(task_id)
        if not connections:
            return
        if websocket is None:
            connections.clear()
        else:
            connections.discard(websocket)
        if not connections:
            self.active_connections.pop(task_id, None)

    async def send_message(self, task_id: str, message: dict) -> None:
        stale = []
        for connection in tuple(self.active_connections.get(task_id, ())):
            try:
                await connection.send_json(message)
            except Exception:
                stale.append(connection)
        for connection in stale:
            self.disconnect(task_id, connection)

    async def broadcast(self, message: dict) -> None:
        for task_id in tuple(self.active_connections):
            await self.send_message(task_id, message)


manager = ConnectionManager()


def _terminal_snapshot(task: Task) -> dict | None:
    common = {
        "task_id": task.id,
        "status": task.status.value,
        "timestamp": _timestamp(),
    }
    if task.status == TaskStatus.completed:
        return {
            "type": "completed",
            **common,
            "audio_url": task.final_audio_url,
            "duration": task.audio_duration,
        }
    if task.status == TaskStatus.failed:
        return {"type": "failed", **common, "error": task.error_message}
    if task.status == TaskStatus.cancelled:
        return {"type": "cancelled", **common, "error": task.error_message}
    return None


async def websocket_endpoint(websocket: WebSocket, task_id: str) -> None:
    """Stream durable events and resume from ``after_event_id`` on reconnect."""
    await manager.connect(task_id, websocket)
    subscriber = broker.subscribe(task_id)
    cursor_text = websocket.query_params.get("after_event_id", "0")
    try:
        cursor = max(0, int(cursor_text))
    except ValueError:
        cursor = 0

    try:
        with SessionLocal() as db:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                await websocket.send_json(
                    {"type": "error", "message": "任务不存在", "code": 404}
                )
                await websocket.close(code=4404)
                return
            initial = {
                "type": "status_update",
                "task_id": task_id,
                "status": task.status.value,
                "current_subtask": task.current_subtask,
                "subtask_progress": task.subtask_progress or 0.0,
                "message": get_step_message(task.current_subtask),
                "thinking_process": task.thinking_process or [],
                "timestamp": _timestamp(),
            }
            if task.status == TaskStatus.waiting_input:
                intervention = db.query(HumanIntervention).filter(
                    HumanIntervention.task_id == task_id,
                    HumanIntervention.status == HumanInterventionStatus.open,
                ).order_by(HumanIntervention.created_at.desc()).first()
                if intervention:
                    initial.update(
                        {
                            "intervention_id": intervention.id,
                            "intervention_question": intervention.question,
                        }
                    )
            terminal = _terminal_snapshot(task)

        await websocket.send_json(initial)

        replayed_terminal = False
        replay_limit = max(1, settings.TASK_EVENT_REPLAY_LIMIT)
        while True:
            replay = await asyncio.to_thread(
                get_task_events,
                task_id,
                after_event_id=cursor,
                limit=replay_limit,
            )
            for event in replay:
                cursor = max(cursor, int(event["event_id"]))
                await websocket.send_json(event)
                replayed_terminal = (
                    replayed_terminal or event["type"] in TERMINAL_EVENT_TYPES
                )
            if len(replay) < replay_limit or replayed_terminal:
                break

        if terminal and not replayed_terminal:
            await websocket.send_json(terminal)
            return
        if replayed_terminal:
            return

        last_heartbeat = time.monotonic()
        poll_seconds = max(0.1, settings.TASK_EVENT_POLL_SECONDS)
        heartbeat_seconds = max(poll_seconds, settings.TASK_EVENT_HEARTBEAT_SECONDS)
        while True:
            event = None
            try:
                event = await asyncio.wait_for(
                    subscriber.queue.get(),
                    timeout=poll_seconds,
                )
            except asyncio.TimeoutError:
                catch_up = await asyncio.to_thread(
                    get_task_events,
                    task_id,
                    after_event_id=cursor,
                    limit=settings.TASK_EVENT_REPLAY_LIMIT,
                )
                for persisted_event in catch_up:
                    cursor = max(cursor, int(persisted_event["event_id"]))
                    await websocket.send_json(persisted_event)
                    if persisted_event["type"] in TERMINAL_EVENT_TYPES:
                        return

            if event and int(event.get("event_id", 0)) > cursor:
                cursor = int(event["event_id"])
                await websocket.send_json(event)
                if event["type"] in TERMINAL_EVENT_TYPES:
                    return

            if time.monotonic() - last_heartbeat >= heartbeat_seconds:
                await websocket.send_json(
                    {
                        "type": "heartbeat",
                        "task_id": task_id,
                        "after_event_id": cursor,
                        "timestamp": _timestamp(),
                    }
                )
                last_heartbeat = time.monotonic()
    except WebSocketDisconnect:
        pass
    finally:
        broker.unsubscribe(task_id, subscriber)
        manager.disconnect(task_id, websocket)
