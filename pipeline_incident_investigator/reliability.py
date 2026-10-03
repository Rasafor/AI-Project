"""Reliability wrapper for calls to external APIs: timeout, capped retries with
exponential backoff, and a circuit breaker.

Implements the CLAUDE.md rule "every external call gets an explicit timeout and
capped retries" as one reusable function, call_reliably(), so each integration
(log store, SQL engine, notification channel, LLM provider) does not hand-roll
its own loop.

How the three protections fit together, per attempt:

    breaker.before_call()        -- circuit open? fail fast, do not call at all
    call_with_timeout(fn, t)     -- never wait longer than t for one attempt
    success -> breaker closes    -- return the value
    failure -> classify_exception() decides (error_classification.py):
               trips_breaker?  count it against the upstream, else release
               should_retry?   sleep a jittered, exponentially growing delay
                               and try again, until max_attempts or the total
                               time budget runs out; otherwise re-raise

Failure-first answers (CLAUDE.md "Failure-First Design"):

1. What happens if the call fails? The classifier decides. Transient failures
   (5xx, 429, timeouts, dropped connections) are retried. Anything else -- a
   caller bug, a 4xx validation error, an exhausted quota -- propagates
   unchanged on the first attempt, because retrying cannot fix it.
2. Retry strategy: capped attempts (default 3), exponential backoff with full
   jitter, capped per delay (max_delay_seconds) and overall
   (total_budget_seconds). A server's Retry-After hint is honored.
3. Recovery when retries are exhausted: RetriesExhaustedError carries the
   attempt count and the last error (as __cause__); the caller decides the
   fallback (mark the investigation inconclusive, dead-letter the job).
4. Handled: hangs, slow responses, connection drops, upstream 5xx/429,
   sustained outages (breaker), and duplicate side effects from retries: every
   caller must declare idempotent=True/False. A non-idempotent call is retried
   only when the request provably never reached the upstream (connection
   refused, DNS failure, 503, 429) -- never after a read timeout or a 500,
   where it may already have been processed.

Known limit: Python cannot kill a thread. A timed-out attempt keeps running in
a daemon thread until fn returns. fn receives the attempt's timeout as a
keyword argument and must pass it to its own client (e.g.
requests.get(..., timeout=timeout)) so abandoned threads end promptly. The
circuit breaker also caps the damage: while it is open, no new threads start.
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable, TypeVar

# The exception types live in error_classification (one-way dependency); re-exported here.
from pipeline_incident_investigator.error_classification import (  # noqa: F401
    CallTimeoutError,
    CircuitOpenError,
    ErrorInfo,
    RetriesExhaustedError,
    TransientError,
    classify_exception,
)

T = TypeVar("T")

logger = logging.getLogger(__name__)

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


def _emit(event: str, **context: object) -> None:
    """Structured JSON log line (CLAUDE.md "Observability Framework")."""
    logger.info(json.dumps({"timestamp": time.time(), "service": "reliability", "event": event, **context}))


# --- 1. Timeout -------------------------------------------------------------


def call_with_timeout(fn: Callable[..., T], timeout_seconds: float) -> T:
    """Run fn(timeout=timeout_seconds) and give up after timeout_seconds.

    Raises CallTimeoutError if fn has not returned in time; re-raises whatever
    fn raised otherwise.
    """
    if timeout_seconds <= 0:
        raise ValueError(f"timeout_seconds must be positive, got {timeout_seconds}")

    outcome: dict[str, object] = {}

    def runner() -> None:
        try:
            outcome["value"] = fn(timeout=timeout_seconds)
        except BaseException as exc:  # noqa: BLE001 -- not swallowed: re-raised in the caller's thread below
            outcome["error"] = exc

    worker = threading.Thread(target=runner, daemon=True, name="reliability-call")
    worker.start()
    worker.join(timeout_seconds)

    if worker.is_alive():
        raise CallTimeoutError(f"call did not finish within {timeout_seconds:.3f}s")
    if "error" in outcome:
        raise outcome["error"]  # type: ignore[misc]
    return outcome["value"]  # type: ignore[return-value]


# --- 2. Retry policy --------------------------------------------------------


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    multiplier: float = 2.0
    max_delay_seconds: float = 10.0
    total_budget_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0 or self.total_budget_seconds <= 0:
            raise ValueError("delays must be non-negative and total_budget_seconds positive")

    def delay_for(
        self, attempt: int, retry_after_seconds: float | None = None, rand: Callable[[], float] = random.random
    ) -> float:
        """Seconds to wait after failed attempt number `attempt` (1-based).

        Full jitter: a random point in [0, base * multiplier^(attempt-1)],
        capped at max_delay_seconds. A Retry-After hint from the server is a
        floor -- retrying sooner than the server asked only earns another 429.
        """
        ceiling = min(self.max_delay_seconds, self.base_delay_seconds * self.multiplier ** (attempt - 1))
        delay = ceiling * rand()
        if retry_after_seconds is not None:
            delay = max(delay, retry_after_seconds)
        return delay


# --- 3. Circuit breaker -----------------------------------------------------


class CircuitBreaker:
    """Stops calling an upstream that keeps failing, then probes it for recovery.

    CLOSED    -- normal. Consecutive failures are counted; at failure_threshold
                 the breaker OPENs.
    OPEN      -- every call fails fast with CircuitOpenError, without touching
                 the upstream, for reset_timeout_seconds.
    HALF_OPEN -- after the cool-down, exactly one trial call is let through.
                 Success closes the breaker; failure re-opens it for another
                 full cool-down.

    Share one instance per upstream dependency (e.g. one module-level breaker
    for the log store). A breaker created per call never accumulates failures
    and protects nothing. Thread-safe.
    """

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        reset_timeout_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1 or reset_timeout_seconds <= 0:
            raise ValueError("failure_threshold must be >= 1 and reset_timeout_seconds positive")
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._state = CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._trial_in_flight = False

    @property
    def state(self) -> str:
        with self._lock:
            return self._current_state()

    def _current_state(self) -> str:  # caller holds the lock
        if self._state == OPEN and self._clock() - self._opened_at >= self.reset_timeout_seconds:
            self._state = HALF_OPEN
            self._trial_in_flight = False
        return self._state

    def before_call(self) -> None:
        """Raise CircuitOpenError unless a call is allowed right now."""
        with self._lock:
            state = self._current_state()
            if state == OPEN:
                retry_in = self.reset_timeout_seconds - (self._clock() - self._opened_at)
                raise CircuitOpenError(f"circuit '{self.name}' is open; next probe in {retry_in:.1f}s")
            if state == HALF_OPEN:
                if self._trial_in_flight:
                    raise CircuitOpenError(f"circuit '{self.name}' is half-open and a trial call is in flight")
                self._trial_in_flight = True

    def record_success(self) -> None:
        with self._lock:
            if self._state != CLOSED:
                _emit("circuit_closed", circuit=self.name)
            self._state = CLOSED
            self._failures = 0
            self._trial_in_flight = False

    def record_failure(self) -> None:
        with self._lock:
            state = self._current_state()
            self._failures += 1
            if state == HALF_OPEN or self._failures >= self.failure_threshold:
                self._state = OPEN
                self._opened_at = self._clock()
                self._trial_in_flight = False
                _emit("circuit_opened", circuit=self.name, consecutive_failures=self._failures)

    def release(self) -> None:
        """End a call that proved nothing about upstream health (e.g. a caller
        bug), so a half-open breaker's trial slot is not held forever."""
        with self._lock:
            self._trial_in_flight = False


# --- Putting it together ----------------------------------------------------


def call_reliably(
    fn: Callable[..., T],
    *,
    breaker: CircuitBreaker,
    idempotent: bool,
    timeout_seconds: float = 5.0,
    policy: RetryPolicy = RetryPolicy(),
    classify: Callable[[BaseException], ErrorInfo] = classify_exception,
    correlation_id: str | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    rand: Callable[[], float] = random.random,
) -> T:
    """Call fn(timeout=...) with a per-attempt timeout, capped retries and a circuit breaker.

    idempotent is required on purpose: the caller must decide whether a repeat of
    this call is harmless. With idempotent=False, a failure whose outcome is
    unknown (read timeout, 500, dropped connection) is raised, not retried.

    Raises CircuitOpenError (fast, nothing called) when the breaker is open or
    opens mid-retry; RetriesExhaustedError (with the last failure as __cause__)
    when attempts or the time budget run out; and any failure the classifier
    says not to retry, unchanged, on its first occurrence.

    sleep, clock and rand are injectable so tests run instantly and deterministically.
    """
    correlation_id = correlation_id or str(uuid.uuid4())
    deadline = clock() + policy.total_budget_seconds
    last_error: BaseException | None = None
    last_info: ErrorInfo | None = None
    attempts_made = 0

    for attempt in range(1, policy.max_attempts + 1):
        breaker.before_call()
        remaining = deadline - clock()
        if remaining <= 0:
            breaker.release()
            break

        attempts_made += 1
        started = clock()
        log = {"correlation_id": correlation_id, "circuit": breaker.name, "attempt": attempt}
        try:
            value = call_with_timeout(fn, min(timeout_seconds, remaining))
        except BaseException as exc:
            info = classify(exc)
            if info.trips_breaker:
                breaker.record_failure()
            else:
                breaker.release()
            retry = info.should_retry(idempotent=idempotent)
            _emit("call_attempt", **log, outcome="failure", error_class=info.error_class,
                  error_category=info.category, retryable=retry, outcome_unknown=info.outcome_unknown,
                  status_code=info.status_code, duration_ms=round((clock() - started) * 1000))
            if not retry:
                raise
            last_error, last_info = exc, info
        else:
            breaker.record_success()
            _emit("call_attempt", **log, outcome="success", duration_ms=round((clock() - started) * 1000))
            return value

        if attempt == policy.max_attempts:
            break
        if breaker.state == OPEN:
            raise CircuitOpenError(f"circuit '{breaker.name}' opened after attempt {attempt}") from last_error
        delay = policy.delay_for(attempt, last_info.retry_after_seconds, rand)
        if clock() + delay >= deadline:
            break  # waiting would overrun the budget; give up now rather than late
        sleep(delay)

    raise RetriesExhaustedError(
        f"call via circuit '{breaker.name}' failed after {attempts_made} attempt(s)", attempts=attempts_made
    ) from last_error
