import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# The current app.agent package eagerly imports the LLM service.  These tests do
# not call an LLM, but a placeholder prevents import-time configuration failure.
os.environ.setdefault("LLM_API_KEY", "test-key")

from app.agent import observability
from app.agent.observability import (
    TRACE_KEY,
    classify_error,
    finish_trace_event,
    get_execution_trace,
    new_trace_event,
    record_trace_event,
    summarize,
    traced_node,
)
from app.agent.state import append_trace_events
from app.models import Base, Task


@pytest.fixture
def trace_database(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(observability, "SessionLocal", testing_session)

    with testing_session() as db:
        db.add(
            Task(
                id="task-1",
                user_request="test",
                intermediate_data={"audio_path": "/tmp/input.wav"},
            )
        )
        db.commit()
    yield testing_session
    engine.dispose()


def test_summarize_redacts_secret_fields_and_bearer_tokens():
    summary = summarize(
        {
            "api_key": "should-not-leak",
            "nested": {"password": "also-secret"},
            "header": "Bearer abc.def-123",
            "error": "request failed api_key=plain-text-secret",
            "safe": "visible",
        }
    )

    assert "should-not-leak" not in summary
    assert "also-secret" not in summary
    assert "abc.def-123" not in summary
    assert "plain-text-secret" not in summary
    assert "<redacted>" in summary
    assert "visible" in summary


def test_record_trace_event_upserts_and_preserves_intermediate_data(trace_database):
    running = new_trace_event(kind="node", name="fetch_source")
    record_trace_event(
        "task-1", running, current_subtask="fetch_source", subtask_progress=5
    )
    completed = finish_trace_event(
        running, status="success", metadata={"updates": ["audio_path"]}
    )
    record_trace_event("task-1", completed, subtask_progress=10)

    with trace_database() as db:
        task = db.query(Task).filter(Task.id == "task-1").one()
        trace = get_execution_trace(task)
        assert task.intermediate_data["audio_path"] == "/tmp/input.wav"
        assert task.current_subtask == "fetch_source"
        assert task.subtask_progress == 10
        assert len(trace) == 1
        assert trace[0]["event_id"] == running["event_id"]
        assert trace[0]["status"] == "success"
        assert trace[0]["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_traced_node_returns_checkpoint_safe_terminal_event(monkeypatch):
    persisted = []
    monkeypatch.setattr(
        observability,
        "record_trace_event",
        lambda task_id, event, **kwargs: persisted.append((task_id, event, kwargs)),
    )

    async def node(state):
        return {"result": 42}

    wrapped = traced_node("example", node, progress_start=20, progress_end=30)
    result = await wrapped({"task_id": "task-1", "retry_count": 1})

    assert result["result"] == 42
    assert len(result[TRACE_KEY]) == 1
    assert result[TRACE_KEY][0]["status"] == "success"
    assert result[TRACE_KEY][0]["metadata"]["attempt"] == 2
    assert result[TRACE_KEY][0]["metadata"]["updates"] == ["result"]
    assert [entry[1]["status"] for entry in persisted] == ["running", "success"]


@pytest.mark.asyncio
async def test_traced_node_persists_normalized_failure(monkeypatch):
    persisted = []
    monkeypatch.setattr(
        observability,
        "record_trace_event",
        lambda task_id, event, **kwargs: persisted.append(event),
    )

    async def node(state):
        raise FileNotFoundError("missing.mid")

    wrapped = traced_node("render", node, progress_start=75, progress_end=90)
    with pytest.raises(FileNotFoundError):
        await wrapped({"task_id": "task-1"})

    assert persisted[-1]["status"] == "failed"
    assert persisted[-1]["error"] == {
        "code": "RENDER_FILE_NOT_FOUND",
        "type": "FileNotFoundError",
        "message": "missing.mid",
        "retryable": False,
    }


def test_trace_reducer_is_append_only():
    assert append_trace_events([{"event_id": "a"}], [{"event_id": "b"}]) == [
        {"event_id": "a"},
        {"event_id": "b"},
    ]


def test_timeout_error_is_marked_retryable():
    normalized = classify_error(TimeoutError("slow"), "llm")
    assert normalized["code"] == "LLM_TIMEOUT"
    assert normalized["retryable"] is True
