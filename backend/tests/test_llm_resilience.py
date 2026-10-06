"""Tests for bounded, privacy-safe LLM execution."""

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import httpx
from openai import BadRequestError, RateLimitError

from app.agent.callbacks import ThinkingCallbackHandler
from app.agent.trace import reset_execution_context, set_execution_context
from app.services.llm_service import (
    LLMService,
    build_llm_error,
    is_retryable_llm_error,
    settings,
)
from app.services.memory import reset_agent_context, set_agent_context


def completion(content: str | None = "ok", finish_reason: str = "stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ]
    )


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            return await outcome()
        return outcome


def fake_client(*outcomes):
    completions = FakeCompletions(outcomes)
    return SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
        completions_fixture=completions,
    )


class LLMServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sleeps = []

        async def no_sleep(delay):
            self.sleeps.append(delay)

        self.no_sleep = no_sleep

    async def test_transient_timeout_retries_then_succeeds(self):
        client = fake_client(TimeoutError("temporary"), completion("done"))
        service = LLMService(client, trace_persist=None, sleep=self.no_sleep)

        with patch.object(settings, "LLM_MAX_ATTEMPTS", 2), patch.object(
            settings, "LLM_RETRY_BACKOFF_SECONDS", 0.25
        ):
            result = await service.chat([{"role": "user", "content": "hello"}])

        self.assertEqual(result, "done")
        self.assertEqual(len(client.completions_fixture.calls), 2)
        self.assertEqual(self.sleeps, [0.25])

    def test_provider_rate_limit_is_retryable_but_bad_request_is_not(self):
        request = httpx.Request("POST", "https://provider.invalid/chat")
        rate_limit = RateLimitError(
            "limited",
            response=httpx.Response(429, request=request),
            body=None,
        )
        bad_request = BadRequestError(
            "invalid",
            response=httpx.Response(400, request=request),
            body=None,
        )

        self.assertTrue(is_retryable_llm_error(rate_limit))
        self.assertFalse(is_retryable_llm_error(bad_request))

    async def test_permanent_error_is_not_retried(self):
        client = fake_client(ValueError("invalid request"), completion())
        service = LLMService(client, trace_persist=None, sleep=self.no_sleep)

        with patch.object(settings, "LLM_MAX_ATTEMPTS", 3):
            with self.assertRaisesRegex(ValueError, "invalid request"):
                await service.chat([{"role": "user", "content": "hello"}])

        self.assertEqual(len(client.completions_fixture.calls), 1)
        self.assertEqual(self.sleeps, [])

    async def test_each_attempt_has_a_request_timeout(self):
        async def hangs():
            await asyncio.sleep(1)

        client = fake_client(hangs, hangs)
        service = LLMService(client, trace_persist=None, sleep=self.no_sleep)

        with patch.object(settings, "LLM_MAX_ATTEMPTS", 2), patch.object(
            settings, "LLM_REQUEST_TIMEOUT_SECONDS", 0.001
        ), patch.object(settings, "LLM_RETRY_BACKOFF_SECONDS", 0):
            with self.assertRaises(TimeoutError):
                await service.chat([{"role": "user", "content": "hello"}])

        self.assertEqual(len(client.completions_fixture.calls), 2)

    async def test_truncated_empty_response_gets_one_larger_request(self):
        client = fake_client(
            completion("", "length"),
            completion("recovered", "stop"),
        )
        service = LLMService(client, trace_persist=None, sleep=self.no_sleep)

        result = await service.chat(
            [{"role": "user", "content": "hello"}],
            max_tokens=100,
        )

        self.assertEqual(result, "recovered")
        self.assertEqual(
            [call["max_tokens"] for call in client.completions_fixture.calls],
            [100, 2000],
        )

    async def test_trace_contains_shape_but_never_prompt_memory_or_response(self):
        secret_prompt = "private prompt sk-promptsecret123"
        secret_memory = "password=my-private-memory"
        secret_response = "confidential model output"
        client = fake_client(completion(secret_response))
        events = []
        service = LLMService(
            client,
            trace_persist=lambda task_id, event: events.append((task_id, event)),
            sleep=self.no_sleep,
        )
        execution_token = set_execution_context("task-1", "planning")
        memory_token = set_agent_context(secret_memory)
        try:
            result = await service.chat(
                [{"role": "user", "content": secret_prompt}],
                model="test-model",
            )
        finally:
            reset_agent_context(memory_token)
            reset_execution_context(execution_token)

        serialized = json.dumps(events)
        self.assertEqual(result, secret_response)
        self.assertEqual(
            [item[1]["status"] for item in events], ["running", "succeeded"]
        )
        self.assertNotIn(secret_prompt, serialized)
        self.assertNotIn(secret_memory, serialized)
        self.assertNotIn(secret_response, serialized)
        self.assertIn('"message_count": 2', serialized)
        self.assertIn('"response_chars": 25', serialized)

    async def test_failed_trace_uses_generic_message(self):
        provider_error = ValueError("prompt=private password=hunter2")
        client = fake_client(provider_error)
        events = []
        service = LLMService(
            client,
            trace_persist=lambda task_id, event: events.append(event),
            sleep=self.no_sleep,
        )
        token = set_execution_context("task-2", "analysis")
        try:
            with self.assertRaises(ValueError):
                await service.chat([{"role": "user", "content": "private"}])
        finally:
            reset_execution_context(token)

        serialized = json.dumps(events)
        self.assertNotIn("hunter2", serialized)
        self.assertNotIn("prompt=private", serialized)
        self.assertEqual(events[-1]["error"]["message"], "LLM request failed")

    def test_lazy_initialization_does_not_require_key(self):
        service = LLMService(trace_persist=None)
        self.assertIsNone(service.client)

    def test_unknown_error_normalization_never_copies_exception_text(self):
        normalized = build_llm_error(RuntimeError("token=super-secret"))
        self.assertEqual(normalized["code"], "LLM_REQUEST_FAILED")
        self.assertNotIn("super-secret", json.dumps(normalized))


class LangChainCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_callback_records_structure_without_prompt_or_response(self):
        events = []
        thoughts = []
        handler = ThinkingCallbackHandler("task-3", "arrange")
        run_id = uuid4()
        response = SimpleNamespace(
            generations=[
                [SimpleNamespace(message=SimpleNamespace(content="secret response"))]
            ]
        )

        with patch(
            "app.agent.callbacks.persist_trace_event",
            side_effect=lambda task_id, event: events.append(event),
        ), patch(
            "app.agent.callbacks.record_thought",
            side_effect=lambda *args, **kwargs: thoughts.append((args, kwargs)),
        ):
            await handler.on_chat_model_start(
                {},
                [[SimpleNamespace(content="secret prompt")]],
                run_id=run_id,
            )
            await handler.on_llm_end(response, run_id=run_id)

        serialized = json.dumps(events)
        self.assertNotIn("secret prompt", serialized)
        self.assertNotIn("secret response", serialized)
        self.assertEqual(
            [event["status"] for event in events], ["running", "succeeded"]
        )
        self.assertEqual(events[-1]["details"]["generation_count"], 1)
        self.assertIn("正文已从诊断日志省略", thoughts[-1][0][2])

    async def test_callback_error_never_copies_provider_text(self):
        events = []
        handler = ThinkingCallbackHandler("task-4", "analysis")
        run_id = uuid4()

        with patch(
            "app.agent.callbacks.persist_trace_event",
            side_effect=lambda task_id, event: events.append(event),
        ):
            await handler.on_llm_start({}, ["private prompt"], run_id=run_id)
            await handler.on_llm_error(
                ValueError("password=private-provider-body"),
                run_id=run_id,
            )

        serialized = json.dumps(events)
        self.assertNotIn("private prompt", serialized)
        self.assertNotIn("private-provider-body", serialized)
        self.assertEqual(events[-1]["error"]["code"], "LLM_REQUEST_FAILED")


if __name__ == "__main__":
    unittest.main()
