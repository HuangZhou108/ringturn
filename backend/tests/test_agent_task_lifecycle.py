"""Regression tests for Agent task claiming and cancellation races."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.agent_executor import AgentExecutor
from app.api.v1.endpoints import tasks as task_endpoints
from app.models import Base, Task, TaskStatus


class AgentTaskLifecycleTests(unittest.IsolatedAsyncioTestCase):
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

    def tearDown(self):
        task_endpoints._running_tasks.clear()
        task_endpoints._background_tasks.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def add_task(self, task_id: str, status: TaskStatus) -> None:
        with self.Session() as db:
            db.add(
                Task(
                    id=task_id,
                    user_request="make a ringtone",
                    source_type="upload",
                    status=status,
                )
            )
            db.commit()

    def get_status(self, task_id: str) -> TaskStatus:
        with self.Session() as db:
            return db.query(Task).filter(Task.id == task_id).one().status

    def test_claim_is_atomic_and_never_resurrects_cancelled_task(self):
        self.add_task("pending", TaskStatus.pending)
        self.add_task("cancelled", TaskStatus.cancelled)

        with self.Session() as db:
            claimed = task_endpoints._claim_pending_task(db, "pending")
            claimed_again = task_endpoints._claim_pending_task(db, "pending")
            cancelled = task_endpoints._claim_pending_task(db, "cancelled")

        self.assertEqual(claimed.status, TaskStatus.planning)
        self.assertIsNone(claimed_again)
        self.assertIsNone(cancelled)
        self.assertEqual(self.get_status("cancelled"), TaskStatus.cancelled)

    async def test_pending_cancellation_is_immediate_and_idempotent(self):
        self.add_task("task-1", TaskStatus.pending)
        events = []

        with self.Session() as db, patch.object(
            task_endpoints,
            "persist_trace_event",
            side_effect=lambda task_id, event: events.append(event),
        ):
            first = await task_endpoints.cancel_task("task-1", db=db)
            second = await task_endpoints.cancel_task("task-1", db=db)

        self.assertEqual(first["data"]["previous_status"], "pending")
        self.assertEqual(first["data"]["current_status"], "cancelled")
        self.assertEqual(second["code"], 200)
        self.assertEqual(second["data"]["previous_status"], "cancelled")
        self.assertEqual(self.get_status("task-1"), TaskStatus.cancelled)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["kind"], "control")
        self.assertEqual(events[0]["details"]["previous_status"], "pending")

    async def test_running_cancellation_targets_registered_executor(self):
        self.add_task("task-2", TaskStatus.executing)

        class FakeExecutor:
            def __init__(self):
                self.cancel_calls = 0

            async def cancel(self):
                self.cancel_calls += 1

        executor = FakeExecutor()
        task_endpoints._running_tasks["task-2"] = executor

        with self.Session() as db, patch.object(
            task_endpoints,
            "persist_trace_event",
        ):
            result = await task_endpoints.cancel_task("task-2", db=db)

        self.assertEqual(executor.cancel_calls, 1)
        self.assertEqual(result["data"]["previous_status"], "executing")
        self.assertEqual(self.get_status("task-2"), TaskStatus.cancelled)

    async def test_background_runner_skips_already_cancelled_task(self):
        self.add_task("task-3", TaskStatus.cancelled)

        with patch.object(task_endpoints, "SessionLocal", self.Session), patch.object(
            task_endpoints, "AgentExecutor"
        ) as executor_class:
            await task_endpoints.run_agent_task("task-3")

        executor_class.assert_not_called()
        self.assertEqual(self.get_status("task-3"), TaskStatus.cancelled)

    async def test_executor_cancel_interrupts_outer_planning_task(self):
        self.add_task("planning", TaskStatus.planning)
        executor = object.__new__(AgentExecutor)
        executor._cancel_event = asyncio.Event()
        executor._subprocesses = []
        executor._active_task = None
        executor.assistant_message = SimpleNamespace(content="working")
        executor.task_id = "planning"
        executor.db = self.Session()
        executor.task = executor.db.query(Task).filter(Task.id == "planning").one()
        blocker = asyncio.Event()
        execution_task = asyncio.create_task(blocker.wait())
        executor.bind_execution_task(execution_task)

        try:
            await executor.cancel()
        finally:
            executor.db.close()

        self.assertTrue(executor._cancel_event.is_set())
        self.assertTrue(execution_task.done())
        self.assertTrue(execution_task.cancelled())
        self.assertEqual(executor.task.status, TaskStatus.cancelled)
        self.assertEqual(executor.assistant_message.content, "任务已取消")
        self.assertEqual(self.get_status("planning"), TaskStatus.cancelled)

    async def test_persisted_cancellation_wins_over_late_completion(self):
        self.add_task("late-completion", TaskStatus.executing)
        executor = object.__new__(AgentExecutor)
        executor._cancel_event = asyncio.Event()
        executor.task_id = "late-completion"
        executor.db = self.Session()
        executor.task = (
            executor.db.query(Task).filter(Task.id == "late-completion").one()
        )

        with self.Session() as cancellation_db:
            cancellation_db.query(Task).filter(
                Task.id == "late-completion"
            ).update({Task.status: TaskStatus.cancelled})
            cancellation_db.commit()

        try:
            updated = await executor._update_task_status(TaskStatus.completed)
        finally:
            executor.db.close()

        self.assertFalse(updated)
        self.assertEqual(executor.task.status, TaskStatus.cancelled)
        self.assertEqual(self.get_status("late-completion"), TaskStatus.cancelled)

    async def test_terminal_task_cannot_be_cancelled(self):
        self.add_task("completed", TaskStatus.completed)

        with self.Session() as db, patch.object(
            task_endpoints,
            "persist_trace_event",
        ) as persist_trace:
            result = await task_endpoints.cancel_task("completed", db=db)

        self.assertEqual(result["code"], 400)
        self.assertEqual(result["message"], "任务已结束，无法取消。")
        self.assertEqual(self.get_status("completed"), TaskStatus.completed)
        persist_trace.assert_not_called()

    async def test_background_runner_registers_binds_and_cleans_up(self):
        self.add_task("task-4", TaskStatus.pending)
        instances = []

        class FakeExecutor:
            def __init__(self, task_id, db):
                self.task_id = task_id
                self.bound_task = None
                self.closed = False
                instances.append(self)

            def bind_execution_task(self, task):
                self.bound_task = task

            async def execute(self):
                await asyncio.sleep(0)
                return {"success": False, "reason": "test"}

            def close(self):
                self.closed = True

        with patch.object(task_endpoints, "SessionLocal", self.Session), patch.object(
            task_endpoints, "AgentExecutor", FakeExecutor
        ):
            await task_endpoints.run_agent_task("task-4")

        self.assertEqual(len(instances), 1)
        self.assertIsNotNone(instances[0].bound_task)
        self.assertTrue(instances[0].closed)
        self.assertNotIn("task-4", task_endpoints._running_tasks)
        self.assertEqual(task_endpoints._background_tasks, set())
        self.assertEqual(self.get_status("task-4"), TaskStatus.planning)


if __name__ == "__main__":
    unittest.main()
