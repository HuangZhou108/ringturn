"""Lightweight tests for structured Agent execution diagnostics."""

import asyncio
import importlib.util
import json
import sys
import types
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

_MODULE_PATH = Path(__file__).parent.parent / "app" / "agent" / "trace.py"
_SPEC = importlib.util.spec_from_file_location("agent_trace", _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"无法加载 Agent trace 模块: {_MODULE_PATH}")
_TRACE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_TRACE)


class AgentTraceSchemaTests(unittest.TestCase):
    def test_event_is_json_serializable_and_has_checkpoint_identity(self):
        event = _TRACE.create_trace_event(
            task_id="task-1",
            kind="node",
            name="render",
            status="succeeded",
            duration_ms=12.34567,
            details={"updated_fields": ["final_audio_url"]},
        )

        json.dumps(event)
        self.assertEqual(event["task_id"], "task-1")
        self.assertEqual(event["thread_id"], "task-1")
        self.assertEqual(event["duration_ms"], 12.346)

    def test_execution_context_can_be_restored(self):
        self.assertIsNone(_TRACE.get_execution_context())
        token = _TRACE.set_execution_context("task-1", "planning")
        try:
            self.assertEqual(
                _TRACE.get_execution_context(),
                {"task_id": "task-1", "component": "planning"},
            )
        finally:
            _TRACE.reset_execution_context(token)
        self.assertIsNone(_TRACE.get_execution_context())

    def test_merge_deduplicates_orders_and_bounds_events(self):
        first = _TRACE.create_trace_event(
            task_id="task-1",
            kind="node",
            name="first",
            status="succeeded",
            timestamp="2026-01-01T00:00:00Z",
        )
        second = _TRACE.create_trace_event(
            task_id="task-1",
            kind="node",
            name="second",
            status="succeeded",
            timestamp="2026-01-01T00:00:01Z",
        )

        merged = _TRACE.merge_trace_events([second], [first, second])

        self.assertEqual([event["name"] for event in merged], ["first", "second"])

        many = [
            _TRACE.create_trace_event(
                task_id="task-1",
                kind="tool",
                name=str(index),
                status="succeeded",
                timestamp=f"2026-01-01T00:{index // 60:02d}:{index % 60:02d}Z",
            )
            for index in range(_TRACE.MAX_TRACE_EVENTS + 5)
        ]
        bounded = _TRACE.merge_trace_events([], many)
        self.assertEqual(len(bounded), _TRACE.MAX_TRACE_EVENTS)

    def test_tool_input_summary_never_contains_values(self):
        secret = "sk-this-must-not-be-recorded"
        summary = _TRACE.summarize_tool_input(
            ("/private/song.wav",),
            {"api_key": secret, "tempo": 120},
        )

        serialized = json.dumps(summary)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("/private/song.wav", serialized)
        self.assertIn("api_key", summary["keyword_names"])
        self.assertEqual(summary["keyword_types"]["tempo"], "int")

    def test_result_summary_never_contains_payload_values(self):
        summary = _TRACE.summarize_result(
            {"token": "secret-value", "audio_path": "/private/result.mp3"}
        )

        serialized = json.dumps(summary)
        self.assertNotIn("secret-value", serialized)
        self.assertNotIn("/private/result.mp3", serialized)
        self.assertEqual(summary["key_count"], 2)

    def test_error_model_redacts_credentials(self):
        error = RuntimeError(
            "api_key=sk-abcdefghijk password=hunter2 Bearer abc.def.ghi"
        )

        normalized = _TRACE.build_execution_error(
            error,
            scope="tool",
            component="render_audio",
        )
        serialized = json.dumps(normalized)

        self.assertEqual(normalized["code"], "TOOL_EXECUTION_FAILED")
        self.assertFalse(normalized["retryable"])
        self.assertNotIn("abcdefghijk", serialized)
        self.assertNotIn("hunter2", serialized)
        self.assertNotIn("abc.def.ghi", serialized)

    def test_timeout_is_marked_retryable(self):
        normalized = _TRACE.build_execution_error(
            TimeoutError("dependency timed out"),
            scope="node",
            component="extract_melody",
        )

        self.assertEqual(normalized["code"], "EXECUTION_TIMEOUT")
        self.assertTrue(normalized["retryable"])

    def test_fallback_event_has_explicit_sanitized_transition(self):
        event = _TRACE.create_fallback_event(
            task_id="task-1",
            component="melody_extraction",
            from_strategy="basic_pitch",
            to_strategy="librosa",
            reason="primary_extractor_failed",
            error=RuntimeError("token=super-secret-value"),
        )

        serialized = json.dumps(event)
        self.assertEqual(event["kind"], "resilience")
        self.assertEqual(event["status"], "fallback")
        self.assertEqual(event["details"]["to"], "librosa")
        self.assertNotIn("super-secret-value", serialized)

    def test_entry_route_explains_new_resume_and_invalid_targets(self):
        allowed = ["fetch_source", "arrange"]

        self.assertEqual(
            _TRACE.select_entry_route(
                None,
                allowed_nodes=allowed,
                default_node="fetch_source",
            ),
            ("fetch_source", "new_task"),
        )
        self.assertEqual(
            _TRACE.select_entry_route(
                "arrange",
                allowed_nodes=allowed,
                default_node="fetch_source",
            ),
            ("arrange", "feedback_resume"),
        )
        self.assertEqual(
            _TRACE.select_entry_route(
                "unknown",
                allowed_nodes=allowed,
                default_node="fetch_source",
            ),
            ("fetch_source", "invalid_resume_target_fallback"),
        )

    def test_retry_route_preserves_existing_boundary(self):
        common = {"retry_node": "arrange", "end_node": "__end__"}

        self.assertEqual(
            _TRACE.select_retry_route(
                needs_revision=False,
                retry_count=0,
                max_retries=1,
                **common,
            ),
            ("__end__", "quality_accepted"),
        )
        self.assertEqual(
            _TRACE.select_retry_route(
                needs_revision=True,
                retry_count=1,
                max_retries=1,
                **common,
            ),
            ("arrange", "quality_revision_requested"),
        )
        self.assertEqual(
            _TRACE.select_retry_route(
                needs_revision=True,
                retry_count=2,
                max_retries=1,
                **common,
            ),
            ("__end__", "retry_limit_reached"),
        )

    def test_diagnostics_are_filtered_by_task(self):
        parent_event = _TRACE.create_trace_event(
            task_id="parent",
            kind="node",
            name="render",
            status="failed",
        )
        child_event = _TRACE.create_trace_event(
            task_id="child",
            kind="node",
            name="arrange",
            status="succeeded",
        )
        intermediate = {
            "execution_trace": [parent_event, child_event],
            "execution_error": {
                "task_id": "child",
                "code": "NODE_EXECUTION_FAILED",
            },
        }

        events, error = _TRACE.get_execution_diagnostics(
            intermediate,
            task_id="child",
        )

        self.assertEqual(events, [child_event])
        self.assertEqual(
            error,
            {"task_id": "child", "code": "NODE_EXECUTION_FAILED"},
        )
        no_events, no_error = _TRACE.get_execution_diagnostics(
            intermediate,
            task_id="unknown",
        )
        self.assertEqual(no_events, [])
        self.assertIsNone(no_error)

    def test_feedback_inherits_audio_data_but_not_diagnostics(self):
        intermediate = {
            "audio_path": "/tmp/vocals.wav",
            "analysis_result": {"bpm": 120},
            "execution_trace": [{"task_id": "parent"}],
            "execution_error": {"code": "TOOL_EXECUTION_FAILED"},
        }

        inherited = _TRACE.without_execution_diagnostics(intermediate)

        self.assertEqual(inherited["audio_path"], "/tmp/vocals.wav")
        self.assertIn("analysis_result", inherited)
        self.assertNotIn("execution_trace", inherited)
        self.assertNotIn("execution_error", inherited)

    def test_persistence_reuses_intermediate_json_and_tags_error_owner(self):
        task = types.SimpleNamespace(
            id="task-1",
            intermediate_data={"audio_path": "/tmp/audio.wav"},
        )

        class Field:
            def __eq__(self, _other):
                return True

        class TaskModel:
            id = Field()

        class FakeSession:
            committed = False
            closed = False

            def query(self, _model):
                return self

            def filter(self, _condition):
                return self

            def first(self):
                return task

            def commit(self):
                self.committed = True

            def close(self):
                self.closed = True

        session = FakeSession()
        session_module = types.ModuleType("app.db.session")
        session_module.SessionLocal = lambda: session
        models_module = types.ModuleType("app.models")
        models_module.Task = TaskModel
        app_module = types.ModuleType("app")
        app_module.__path__ = []
        db_module = types.ModuleType("app.db")
        db_module.__path__ = []
        event = _TRACE.create_trace_event(
            task_id="task-1",
            kind="tool",
            name="render",
            status="failed",
            error={"code": "TOOL_EXECUTION_FAILED"},
        )

        with patch.dict(
            sys.modules,
            {
                "app": app_module,
                "app.db": db_module,
                "app.db.session": session_module,
                "app.models": models_module,
            },
        ):
            _TRACE.persist_trace_event("task-1", event)

        self.assertTrue(session.committed)
        self.assertTrue(session.closed)
        self.assertEqual(task.intermediate_data["audio_path"], "/tmp/audio.wav")
        self.assertEqual(
            task.intermediate_data["execution_error"]["task_id"],
            "task-1",
        )
        self.assertEqual(task.intermediate_data["execution_trace"], [event])


class AgentNodeInstrumentationTests(unittest.IsolatedAsyncioTestCase):
    async def test_execution_context_is_isolated_between_concurrent_tasks(self):
        ready = asyncio.Event()
        entered = 0
        lock = asyncio.Lock()

        async def worker(task_id):
            nonlocal entered
            token = _TRACE.set_execution_context(task_id, "planning")
            try:
                async with lock:
                    entered += 1
                    if entered == 2:
                        ready.set()
                await ready.wait()
                await asyncio.sleep(0)
                return _TRACE.get_execution_context()
            finally:
                _TRACE.reset_execution_context(token)

        first, second = await asyncio.gather(worker("task-1"), worker("task-2"))

        self.assertEqual(first["task_id"], "task-1")
        self.assertEqual(second["task_id"], "task-2")
        self.assertIsNone(_TRACE.get_execution_context())

    async def test_success_records_start_and_completion_without_mutating_input(self):
        persisted = []

        def persist(_task_id, event):
            persisted.append(event)

        async def node(_state):
            return {"audio_path": "/tmp/audio.wav"}

        wrapped = _TRACE.instrument_node("fetch_source", node, persist=persist)
        state = {"task_id": "task-1", "source_value": "file-1"}
        original = deepcopy(state)

        result = await wrapped(state)

        self.assertEqual(state, original)
        self.assertEqual(
            [event["status"] for event in persisted], ["running", "succeeded"]
        )
        self.assertEqual(
            persisted[-1]["details"]["updated_fields"],
            ["audio_path"],
        )
        self.assertEqual(len(result["execution_trace"]), 2)

    async def test_node_supplied_route_event_is_persisted_and_checkpointed(self):
        persisted = []

        def persist(_task_id, event):
            persisted.append(event)

        async def node(state):
            route_event = _TRACE.create_trace_event(
                task_id=state["task_id"],
                kind="route",
                name="entry_router",
                status="selected",
                details={"selected": "arrange", "reason": "feedback_resume"},
            )
            return {"execution_trace": [route_event]}

        wrapped = _TRACE.instrument_node("entry_router", node, persist=persist)
        result = await wrapped({"task_id": "task-1"})

        self.assertEqual(len(persisted), 3)
        self.assertEqual(
            [event["kind"] for event in persisted], ["node", "route", "node"]
        )
        self.assertEqual(len(result["execution_trace"]), 3)

    async def test_failure_is_recorded_and_original_exception_is_raised(self):
        persisted = []

        def persist(_task_id, event):
            persisted.append(event)

        async def node(_state):
            raise ValueError("invalid note data")

        wrapped = _TRACE.instrument_node("extract_melody", node, persist=persist)

        with self.assertRaisesRegex(ValueError, "invalid note data"):
            await wrapped({"task_id": "task-1"})

        self.assertEqual(
            [event["status"] for event in persisted], ["running", "failed"]
        )
        self.assertEqual(
            persisted[-1]["error"]["code"],
            "NODE_EXECUTION_FAILED",
        )

    async def test_cancellation_is_recorded_and_propagated(self):
        persisted = []

        def persist(_task_id, event):
            persisted.append(event)

        async def node(_state):
            raise asyncio.CancelledError()

        wrapped = _TRACE.instrument_node("render", node, persist=persist)

        with self.assertRaises(asyncio.CancelledError):
            await wrapped({"task_id": "task-1"})

        self.assertEqual(persisted[-1]["status"], "cancelled")
        self.assertEqual(
            persisted[-1]["error"]["code"],
            "EXECUTION_CANCELLED",
        )


if __name__ == "__main__":
    unittest.main()
