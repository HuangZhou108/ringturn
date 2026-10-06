"""Regression tests for durable scheduling, events and human intervention."""

import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from fastapi import BackgroundTasks
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.endpoints import feedback as feedback_endpoints
from app.api.v1.endpoints import tasks as task_endpoints
from app.api.v1.websocket.chat import ConnectionManager
from app.agent.agent_executor import AgentExecutor
from app.models import (Base, Feedback, HumanIntervention,
                        HumanInterventionStatus, Task, TaskExecutionLease,
                        TaskStatus)
from app.schemas import (FeedbackCreate, HumanInterventionAnswer,
                         HumanInterventionCreate)
from app.services import task_events, task_scheduler
from app.services.feedback_analysis import FeedbackDecision


class AgentRuntimeContinuityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        task_endpoints._running_tasks.clear()
        task_endpoints._background_tasks.clear()
        task_endpoints._scheduled_tasks.clear()

    def tearDown(self):
        task_endpoints._running_tasks.clear()
        task_endpoints._background_tasks.clear()
        task_endpoints._scheduled_tasks.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def add_task(self, task_id: str, status: TaskStatus) -> None:
        with self.Session() as db:
            db.add(
                Task(
                    id=task_id,
                    user_request="make a ringtone",
                    source_type="upload",
                    source_value="song.wav",
                    ringtone_params={"tempo": 120},
                    status=status,
                )
            )
            db.commit()

    def status(self, task_id: str) -> TaskStatus:
        with self.Session() as db:
            return db.query(Task).filter(Task.id == task_id).one().status

    async def test_lease_prevents_duplicates_and_allows_expired_recovery(self):
        self.add_task("lease-task", TaskStatus.pending)
        with patch.object(task_scheduler, "SessionLocal", self.Session):
            first = task_scheduler.claim_task("lease-task", "worker-a")
            duplicate = task_scheduler.claim_task("lease-task", "worker-b")
            with self.Session() as db:
                db.query(TaskExecutionLease).filter_by(task_id="lease-task").update(
                    {TaskExecutionLease.expires_at: datetime.utcnow() - timedelta(seconds=1)}
                )
                db.commit()
            recoverable = task_scheduler.recoverable_task_ids()
            recovered = task_scheduler.claim_task("lease-task", "worker-b")
            task_scheduler.release_task("lease-task", "worker-b")

        self.assertIsNotNone(first)
        self.assertFalse(first.recovered)
        self.assertIsNone(duplicate)
        self.assertIn("lease-task", recoverable)
        self.assertIsNotNone(recovered)
        self.assertTrue(recovered.recovered)
        self.assertEqual(recovered.attempt_count, 2)
        self.assertEqual(self.status("lease-task"), TaskStatus.planning)

    async def test_durable_event_is_replayed_and_fanned_out(self):
        self.add_task("event-task", TaskStatus.executing)
        subscriber = task_events.broker.subscribe("event-task")
        try:
            with patch.object(task_events, "SessionLocal", self.Session):
                emitted = task_events.emit_task_event(
                    "event-task",
                    "status_update",
                    {"status": "executing"},
                )
                replay = task_events.get_task_events("event-task", after_event_id=0)
            queued = await asyncio.wait_for(subscriber.queue.get(), timeout=1)
        finally:
            task_events.broker.unsubscribe("event-task", subscriber)

        self.assertEqual(emitted["event_id"], replay[0]["event_id"])
        self.assertEqual(queued["type"], "status_update")
        self.assertEqual(queued["status"], "executing")

    async def test_runtime_suspend_interrupts_work_without_cancelling_task(self):
        self.add_task("suspend-task", TaskStatus.executing)
        executor = object.__new__(AgentExecutor)
        executor.task_id = "suspend-task"
        executor.db = self.Session()
        executor.task = executor.db.query(Task).filter_by(id="suspend-task").one()
        executor._subprocesses = []
        executor._active_task = None
        executor._suspend_reason = None
        blocker = asyncio.Event()
        execution_task = asyncio.create_task(blocker.wait())
        executor._execution_task = execution_task
        try:
            await executor.suspend("runtime_shutdown")
        finally:
            executor.db.close()

        self.assertTrue(execution_task.cancelled())
        self.assertEqual(self.status("suspend-task"), TaskStatus.executing)

    async def test_feedback_is_persisted_and_child_is_scheduled(self):
        self.add_task("parent", TaskStatus.completed)
        decision = FeedbackDecision(
            resume_from_node="arrange",
            params={"instrument": "Violin"},
        )
        with self.Session() as db, patch.object(
            feedback_endpoints,
            "analyze_feedback",
            AsyncMock(return_value=decision),
        ), patch.object(feedback_endpoints, "emit_task_event"), patch.object(
            task_endpoints, "schedule_agent_task"
        ) as schedule, patch(
            "app.agent.thinking_utils.record_thought"
        ):
            result = await feedback_endpoints.submit_feedback(
                "parent",
                FeedbackCreate(feedback="换成小提琴", parent_task_id="parent"),
                BackgroundTasks(),
                db,
            )

        child_id = result["data"]["task_id"]
        with self.Session() as db:
            child = db.query(Task).filter(Task.id == child_id).one()
            feedback = db.query(Feedback).filter(Feedback.task_id == "parent").one()
        self.assertEqual(feedback.content, "换成小提琴")
        self.assertEqual(child.resume_from_node, "arrange")
        self.assertEqual(child.ringtone_params["instrument"], "Violin")
        schedule.assert_called_once_with(child_id)

    async def test_human_intervention_pauses_and_resumes_same_task(self):
        self.add_task("human-task", TaskStatus.executing)
        decision = FeedbackDecision(
            resume_from_node="arrange",
            params={"tempo": 140},
        )
        with self.Session() as db, patch.object(
            feedback_endpoints, "emit_task_status"
        ), patch.object(feedback_endpoints, "emit_task_event"):
            requested = await feedback_endpoints.request_human_intervention(
                "human-task",
                HumanInterventionCreate(
                    question="需要更快还是更慢？",
                    resume_from_node="arrange",
                ),
                db,
            )

        intervention_id = requested["data"]["intervention_id"]
        self.assertEqual(self.status("human-task"), TaskStatus.waiting_input)

        with self.Session() as db, patch.object(
            feedback_endpoints,
            "analyze_feedback",
            AsyncMock(return_value=decision),
        ), patch.object(feedback_endpoints, "emit_task_status"), patch.object(
            feedback_endpoints, "emit_task_event"
        ), patch.object(task_endpoints, "schedule_agent_task") as schedule:
            answered = await feedback_endpoints.answer_human_intervention(
                "human-task",
                intervention_id,
                HumanInterventionAnswer(response="更快一些"),
                db,
            )

        with self.Session() as db:
            task = db.query(Task).filter(Task.id == "human-task").one()
            intervention = db.query(HumanIntervention).filter_by(id=intervention_id).one()
        self.assertEqual(answered["data"]["status"], "responded")
        self.assertEqual(task.status, TaskStatus.pending)
        self.assertEqual(task.ringtone_params["tempo"], 140)
        self.assertEqual(intervention.status, HumanInterventionStatus.responded)
        schedule.assert_called_once_with("human-task")

    async def test_connection_manager_keeps_multiple_clients_per_task(self):
        class FakeWebSocket:
            def __init__(self):
                self.messages = []
                self.accepted = False

            async def accept(self):
                self.accepted = True

            async def send_json(self, message):
                self.messages.append(message)

        manager = ConnectionManager()
        first = FakeWebSocket()
        second = FakeWebSocket()
        await manager.connect("task", first)
        await manager.connect("task", second)
        await manager.send_message("task", {"type": "heartbeat"})

        self.assertTrue(first.accepted and second.accepted)
        self.assertEqual(first.messages, [{"type": "heartbeat"}])
        self.assertEqual(second.messages, [{"type": "heartbeat"}])
        manager.disconnect("task", first)
        self.assertEqual(len(manager.active_connections["task"]), 1)


if __name__ == "__main__":
    unittest.main()
