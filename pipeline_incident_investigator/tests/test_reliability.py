import json
import threading
import time
import unittest

from pipeline_incident_investigator.reliability import (
    CLOSED,
    HALF_OPEN,
    OPEN,
    CallTimeoutError,
    CircuitBreaker,
    CircuitOpenError,
    RetriesExhaustedError,
    RetryPolicy,
    TransientError,
    call_reliably,
    call_with_timeout,
)


class FakeClock:
    """A clock that only moves when told to, so backoff tests run instantly."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def _upstream(fail_times, error=None, value="ok"):
    """An fn stub that fails `fail_times` times, then returns `value`. Counts its calls."""
    state = {"calls": 0, "timeouts_seen": []}

    def fn(*, timeout):
        state["calls"] += 1
        state["timeouts_seen"].append(timeout)
        if state["calls"] <= fail_times:
            raise error or TransientError("simulated 503")
        return value

    fn.state = state
    return fn


def _reliably(fn, breaker, clock, **kwargs):
    kwargs.setdefault("policy", RetryPolicy(max_attempts=3, base_delay_seconds=1.0, max_delay_seconds=10.0))
    kwargs.setdefault("idempotent", True)
    return call_reliably(fn, breaker=breaker, sleep=clock.sleep, clock=clock, rand=lambda: 1.0, **kwargs)


class CallWithTimeoutTests(unittest.TestCase):
    def test_returns_the_value_and_passes_the_timeout_to_fn(self):
        fn = _upstream(0, value=42)
        self.assertEqual(call_with_timeout(fn, 1.5), 42)
        self.assertEqual(fn.state["timeouts_seen"], [1.5])

    def test_a_hanging_call_raises_call_timeout_error_promptly(self):
        release = threading.Event()
        self.addCleanup(release.set)  # let the abandoned thread finish

        def hangs(*, timeout):
            release.wait(5)

        started = time.monotonic()
        with self.assertRaises(CallTimeoutError):
            call_with_timeout(hangs, 0.05)
        self.assertLess(time.monotonic() - started, 1.0)

    def test_an_error_raised_by_fn_is_re_raised_unchanged(self):
        with self.assertRaises(KeyError):
            call_with_timeout(_upstream(1, error=KeyError("boom")), 1.0)

    def test_a_non_positive_timeout_is_rejected(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                call_with_timeout(_upstream(0), bad)


class RetryPolicyTests(unittest.TestCase):
    def test_delay_grows_exponentially_and_is_capped(self):
        policy = RetryPolicy(base_delay_seconds=0.5, multiplier=2.0, max_delay_seconds=3.0)
        delays = [policy.delay_for(n, rand=lambda: 1.0) for n in range(1, 6)]
        self.assertEqual(delays, [0.5, 1.0, 2.0, 3.0, 3.0])

    def test_full_jitter_picks_a_point_between_zero_and_the_ceiling(self):
        policy = RetryPolicy(base_delay_seconds=2.0)
        self.assertEqual(policy.delay_for(1, rand=lambda: 0.0), 0.0)
        self.assertEqual(policy.delay_for(1, rand=lambda: 0.25), 0.5)

    def test_retry_after_from_the_server_is_a_floor(self):
        policy = RetryPolicy(base_delay_seconds=0.5)
        self.assertEqual(policy.delay_for(1, 7.0, rand=lambda: 1.0), 7.0)

    def test_invalid_configuration_is_rejected(self):
        for kwargs in ({"max_attempts": 0}, {"base_delay_seconds": -1}, {"total_budget_seconds": 0}):
            with self.assertRaises(ValueError):
                RetryPolicy(**kwargs)


class CircuitBreakerTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.breaker = CircuitBreaker("logs", failure_threshold=3, reset_timeout_seconds=30, clock=self.clock)

    def test_opens_after_threshold_consecutive_failures(self):
        for _ in range(2):
            self.breaker.record_failure()
        self.assertEqual(self.breaker.state, CLOSED)
        self.breaker.record_failure()
        self.assertEqual(self.breaker.state, OPEN)

    def test_a_success_resets_the_consecutive_failure_count(self):
        self.breaker.record_failure()
        self.breaker.record_failure()
        self.breaker.record_success()
        self.breaker.record_failure()
        self.breaker.record_failure()
        self.assertEqual(self.breaker.state, CLOSED)

    def test_open_breaker_fails_fast_until_the_cool_down_ends(self):
        for _ in range(3):
            self.breaker.record_failure()
        with self.assertRaises(CircuitOpenError):
            self.breaker.before_call()
        self.clock.now += 29.9
        self.assertEqual(self.breaker.state, OPEN)
        self.clock.now += 0.1
        self.assertEqual(self.breaker.state, HALF_OPEN)

    def test_half_open_allows_exactly_one_trial_and_success_closes(self):
        for _ in range(3):
            self.breaker.record_failure()
        self.clock.now += 30
        self.breaker.before_call()  # the trial
        with self.assertRaises(CircuitOpenError):
            self.breaker.before_call()  # a second caller is refused while the trial runs
        self.breaker.record_success()
        self.assertEqual(self.breaker.state, CLOSED)
        self.breaker.before_call()

    def test_a_failed_trial_re_opens_for_a_full_cool_down(self):
        for _ in range(3):
            self.breaker.record_failure()
        self.clock.now += 30
        self.breaker.before_call()
        self.breaker.record_failure()
        self.assertEqual(self.breaker.state, OPEN)
        self.clock.now += 29
        self.assertEqual(self.breaker.state, OPEN)

    def test_release_frees_the_trial_slot(self):
        for _ in range(3):
            self.breaker.record_failure()
        self.clock.now += 30
        self.breaker.before_call()
        self.breaker.release()
        self.breaker.before_call()  # would raise if the slot were still held

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            CircuitBreaker("x", failure_threshold=0)
        with self.assertRaises(ValueError):
            CircuitBreaker("x", reset_timeout_seconds=0)


class CallReliablyTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.breaker = CircuitBreaker("logs", failure_threshold=5, reset_timeout_seconds=30, clock=self.clock)

    def test_happy_path_calls_once_and_does_not_sleep(self):
        fn = _upstream(0)
        self.assertEqual(_reliably(fn, self.breaker, self.clock), "ok")
        self.assertEqual(fn.state["calls"], 1)
        self.assertEqual(self.clock.sleeps, [])

    def test_transient_failures_are_retried_with_growing_delays(self):
        fn = _upstream(2)
        self.assertEqual(_reliably(fn, self.breaker, self.clock), "ok")
        self.assertEqual(fn.state["calls"], 3)
        self.assertEqual(self.clock.sleeps, [1.0, 2.0])
        self.assertEqual(self.breaker.state, CLOSED)

    def test_retries_are_capped_and_the_last_error_is_kept(self):
        fn = _upstream(99)
        with self.assertRaises(RetriesExhaustedError) as ctx:
            _reliably(fn, self.breaker, self.clock)
        self.assertEqual(fn.state["calls"], 3)
        self.assertEqual(ctx.exception.attempts, 3)
        self.assertIsInstance(ctx.exception.__cause__, TransientError)
        self.assertEqual(len(self.clock.sleeps), 2)  # no pointless sleep after the final attempt

    def test_a_non_retryable_error_propagates_immediately_and_does_not_trip_the_breaker(self):
        fn = _upstream(99, error=ValueError("400: bad request"))
        with self.assertRaises(ValueError):
            _reliably(fn, self.breaker, self.clock)
        self.assertEqual(fn.state["calls"], 1)
        breaker = CircuitBreaker("x", failure_threshold=1, clock=self.clock)
        with self.assertRaises(ValueError):
            _reliably(_upstream(99, error=ValueError("400")), breaker, self.clock)
        self.assertEqual(breaker.state, CLOSED)

    def test_breaker_opening_mid_retry_stops_hammering_the_upstream(self):
        breaker = CircuitBreaker("logs", failure_threshold=2, reset_timeout_seconds=30, clock=self.clock)
        fn = _upstream(99)
        with self.assertRaises(CircuitOpenError) as ctx:
            _reliably(fn, breaker, self.clock, policy=RetryPolicy(max_attempts=5))
        self.assertEqual(fn.state["calls"], 2)
        self.assertIsInstance(ctx.exception.__cause__, TransientError)

        # The next caller fails fast without touching the upstream at all.
        with self.assertRaises(CircuitOpenError):
            _reliably(fn, breaker, self.clock)
        self.assertEqual(fn.state["calls"], 2)

    def test_after_the_cool_down_a_healthy_upstream_closes_the_breaker(self):
        breaker = CircuitBreaker("logs", failure_threshold=2, reset_timeout_seconds=30, clock=self.clock)
        with self.assertRaises(CircuitOpenError):
            _reliably(_upstream(99), breaker, self.clock)
        self.clock.now += 30
        self.assertEqual(_reliably(_upstream(0), breaker, self.clock), "ok")
        self.assertEqual(breaker.state, CLOSED)

    def test_gives_up_rather_than_sleep_past_the_total_budget(self):
        policy = RetryPolicy(max_attempts=5, base_delay_seconds=4.0, max_delay_seconds=60, total_budget_seconds=10)
        fn = _upstream(99)
        with self.assertRaises(RetriesExhaustedError):
            _reliably(fn, self.breaker, self.clock, policy=policy)
        self.assertEqual(self.clock.sleeps, [4.0])  # the next delay (8s) would overrun 10s
        self.assertEqual(fn.state["calls"], 2)

    def test_per_attempt_timeout_shrinks_to_the_remaining_budget(self):
        policy = RetryPolicy(max_attempts=2, base_delay_seconds=7.0, total_budget_seconds=10)
        fn = _upstream(1)
        _reliably(fn, self.breaker, self.clock, policy=policy, timeout_seconds=5.0)
        self.assertEqual(fn.state["timeouts_seen"], [5.0, 3.0])

    def test_a_hanging_upstream_is_timed_out_and_retried(self):
        release = threading.Event()
        self.addCleanup(release.set)
        calls = []

        def hangs(*, timeout):
            calls.append(timeout)
            release.wait(5)

        with self.assertRaises(RetriesExhaustedError) as ctx:
            call_reliably(hangs, breaker=self.breaker, idempotent=True, timeout_seconds=0.05,
                          policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.01))
        self.assertEqual(len(calls), 2)
        self.assertIsInstance(ctx.exception.__cause__, CallTimeoutError)

    def test_each_attempt_is_logged_as_structured_json_with_the_correlation_id(self):
        with self.assertLogs("pipeline_incident_investigator.reliability", level="INFO") as logs:
            _reliably(_upstream(1), self.breaker, self.clock, correlation_id="corr-123")
        events = [json.loads(line.split(":", 2)[2]) for line in logs.output]
        attempts = [e for e in events if e["event"] == "call_attempt"]
        self.assertEqual([e["outcome"] for e in attempts], ["failure", "success"])
        self.assertTrue(all(e["correlation_id"] == "corr-123" for e in attempts))
        self.assertEqual(attempts[0]["error_class"], "UpstreamUnavailable")


if __name__ == "__main__":
    unittest.main()
