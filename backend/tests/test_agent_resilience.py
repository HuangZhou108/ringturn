"""Unit tests for bounded Agent retry and timeout policies."""

import asyncio
import importlib.util
import sys
import unittest
from pathlib import Path

_MODULE_PATH = Path(__file__).parent.parent / "app" / "agent" / "resilience.py"
_SPEC = importlib.util.spec_from_file_location("agent_resilience", _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"无法加载 Agent resilience 模块: {_MODULE_PATH}")
_RESILIENCE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _RESILIENCE
_SPEC.loader.exec_module(_RESILIENCE)


class RetryPolicyTests(unittest.TestCase):
    def test_invalid_policy_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "max_attempts"):
            _RESILIENCE.RetryPolicy(max_attempts=0)
        with self.assertRaisesRegex(ValueError, "timeout_seconds"):
            _RESILIENCE.RetryPolicy(timeout_seconds=0)

    def test_allowlist_only_activates_named_tools(self):
        enabled = _RESILIENCE.policy_for_name(
            "get_metadata",
            allowlist="get_metadata, detect_tempo_beats",
            max_attempts=3,
            timeout_seconds=5,
            backoff_seconds=0.25,
            max_backoff_seconds=2,
        )
        disabled = _RESILIENCE.policy_for_name(
            "render_midi_with_fluidsynth",
            allowlist="get_metadata, detect_tempo_beats",
            max_attempts=3,
            timeout_seconds=5,
            backoff_seconds=0.25,
            max_backoff_seconds=2,
        )

        self.assertEqual(enabled.max_attempts, 3)
        self.assertEqual(enabled.timeout_seconds, 5)
        self.assertEqual(disabled, _RESILIENCE.RetryPolicy())

    def test_backoff_is_exponential_and_capped(self):
        policy = _RESILIENCE.RetryPolicy(
            max_attempts=5,
            backoff_seconds=2,
            max_backoff_seconds=5,
        )

        self.assertEqual(_RESILIENCE.retry_delay_seconds(policy, 1), 2)
        self.assertEqual(_RESILIENCE.retry_delay_seconds(policy, 2), 4)
        self.assertEqual(_RESILIENCE.retry_delay_seconds(policy, 3), 5)


class RunWithRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_failure_retries_then_succeeds(self):
        calls = []
        retries = []
        sleeps = []

        async def operation(attempt):
            calls.append(attempt)
            if attempt == 1:
                raise ConnectionError("temporary dependency failure")
            return "ok"

        async def fake_sleep(delay):
            sleeps.append(delay)

        result, attempts = await _RESILIENCE.run_with_retry(
            operation,
            policy=_RESILIENCE.RetryPolicy(
                max_attempts=2,
                backoff_seconds=0.5,
            ),
            on_retry=lambda attempt, error, delay: retries.append(
                (attempt, type(error).__name__, delay)
            ),
            sleep=fake_sleep,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(attempts, 2)
        self.assertEqual(calls, [1, 2])
        self.assertEqual(retries, [(1, "ConnectionError", 0.5)])
        self.assertEqual(sleeps, [0.5])

    async def test_non_transient_failure_is_not_retried(self):
        calls = []

        async def operation(attempt):
            calls.append(attempt)
            raise ValueError("invalid audio data")

        with self.assertRaisesRegex(ValueError, "invalid audio data"):
            await _RESILIENCE.run_with_retry(
                operation,
                policy=_RESILIENCE.RetryPolicy(max_attempts=3),
            )

        self.assertEqual(calls, [1])

    async def test_custom_retry_classifier_can_extend_policy(self):
        calls = []

        async def operation(attempt):
            calls.append(attempt)
            if attempt == 1:
                raise LookupError("provider-specific transient failure")
            return "ok"

        result, attempts = await _RESILIENCE.run_with_retry(
            operation,
            policy=_RESILIENCE.RetryPolicy(max_attempts=2),
            retry_if=lambda error: isinstance(error, LookupError),
        )

        self.assertEqual((result, attempts), ("ok", 2))
        self.assertEqual(calls, [1, 2])

    async def test_timeout_is_bounded_and_retried(self):
        calls = []
        retries = []

        async def operation(attempt):
            calls.append(attempt)
            await asyncio.sleep(1)

        with self.assertRaises(TimeoutError):
            await _RESILIENCE.run_with_retry(
                operation,
                policy=_RESILIENCE.RetryPolicy(
                    max_attempts=2,
                    timeout_seconds=0.001,
                ),
                on_retry=lambda attempt, error, delay: retries.append(attempt),
            )

        self.assertEqual(calls, [1, 2])
        self.assertEqual(retries, [1])

    async def test_cancellation_is_never_retried(self):
        calls = []

        async def operation(attempt):
            calls.append(attempt)
            raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            await _RESILIENCE.run_with_retry(
                operation,
                policy=_RESILIENCE.RetryPolicy(max_attempts=3),
            )

        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
