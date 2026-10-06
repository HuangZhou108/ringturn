"""Database-backed task leases and restart recovery helpers."""

from __future__ import annotations

import asyncio
import os
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import Task, TaskExecutionLease, TaskStatus

settings = get_settings()
INSTANCE_ID = settings.AGENT_INSTANCE_ID or (
    f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
)
RUNNABLE_STATUSES = (
    TaskStatus.pending,
    TaskStatus.planning,
    TaskStatus.executing,
)


@dataclass(frozen=True)
class TaskClaim:
    task_id: str
    previous_status: TaskStatus
    recovered: bool
    attempt_count: int


def _ensure_lease_row(task_id: str) -> None:
    now = datetime.utcnow()
    db = SessionLocal()
    try:
        if db.query(TaskExecutionLease).filter_by(task_id=task_id).first():
            return
        db.add(
            TaskExecutionLease(
                task_id=task_id,
                owner_id="unclaimed",
                attempt_count=0,
                acquired_at=now,
                heartbeat_at=now,
                expires_at=now - timedelta(seconds=1),
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
    finally:
        db.close()


def claim_task(task_id: str, owner_id: str = INSTANCE_ID) -> TaskClaim | None:
    """Atomically acquire a lease and claim a pending or orphaned active task."""
    _ensure_lease_row(task_id)
    db = SessionLocal(expire_on_commit=False)
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=max(1.0, settings.AGENT_LEASE_SECONDS))
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task or task.status not in RUNNABLE_STATUSES:
            return None
        previous_status = task.status
        updated = (
            db.query(TaskExecutionLease)
            .filter(
                TaskExecutionLease.task_id == task_id,
                TaskExecutionLease.expires_at <= now,
            )
            .update(
                {
                    TaskExecutionLease.owner_id: owner_id,
                    TaskExecutionLease.attempt_count: TaskExecutionLease.attempt_count + 1,
                    TaskExecutionLease.acquired_at: now,
                    TaskExecutionLease.heartbeat_at: now,
                    TaskExecutionLease.expires_at: expires_at,
                },
                synchronize_session=False,
            )
        )
        if updated != 1:
            db.rollback()
            return None

        if previous_status == TaskStatus.pending:
            transitioned = (
                db.query(Task)
                .filter(Task.id == task_id, Task.status == TaskStatus.pending)
                .update(
                    {Task.status: TaskStatus.planning, Task.updated_at: now},
                    synchronize_session=False,
                )
            )
            if transitioned != 1:
                db.rollback()
                return None
        db.commit()
        lease = db.query(TaskExecutionLease).filter_by(task_id=task_id).one()
        return TaskClaim(
            task_id=task_id,
            previous_status=previous_status,
            recovered=previous_status in {TaskStatus.planning, TaskStatus.executing},
            attempt_count=lease.attempt_count,
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def heartbeat_task(task_id: str, owner_id: str = INSTANCE_ID) -> bool:
    db = SessionLocal()
    now = datetime.utcnow()
    try:
        updated = (
            db.query(TaskExecutionLease)
            .filter(
                TaskExecutionLease.task_id == task_id,
                TaskExecutionLease.owner_id == owner_id,
            )
            .update(
                {
                    TaskExecutionLease.heartbeat_at: now,
                    TaskExecutionLease.expires_at: now
                    + timedelta(seconds=max(1.0, settings.AGENT_LEASE_SECONDS)),
                },
                synchronize_session=False,
            )
        )
        db.commit()
        return updated == 1
    finally:
        db.close()


def release_task(task_id: str, owner_id: str = INSTANCE_ID) -> None:
    db = SessionLocal()
    try:
        db.query(TaskExecutionLease).filter(
            TaskExecutionLease.task_id == task_id,
            TaskExecutionLease.owner_id == owner_id,
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def recoverable_task_ids() -> list[str]:
    """Return pending tasks and active tasks whose lease is absent or expired."""
    db = SessionLocal()
    now = datetime.utcnow()
    try:
        leases = {
            lease.task_id: lease
            for lease in db.query(TaskExecutionLease).all()
        }
        tasks = db.query(Task).filter(Task.status.in_(RUNNABLE_STATUSES)).all()
        return [
            task.id
            for task in tasks
            if task.status == TaskStatus.pending
            or task.id not in leases
            or leases[task.id].expires_at <= now
        ]
    finally:
        db.close()


async def maintain_lease(
    task_id: str,
    stop_event: asyncio.Event,
    owner_id: str = INSTANCE_ID,
) -> None:
    interval = max(0.1, settings.AGENT_HEARTBEAT_SECONDS)
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            if not await asyncio.to_thread(heartbeat_task, task_id, owner_id):
                return
