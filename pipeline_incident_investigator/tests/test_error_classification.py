import json
import socket
import ssl
import unittest
from datetime import datetime, timezone

from pipeline_incident_investigator.error_classification import (
    AI_OUTPUT,
    AUTH,
    CONSISTENCY,
    CONTRACT,
    INTERNAL,
    NETWORK,
    QUOTA,
    RATE_LIMIT,
    REQUEST,
    RESILIENCE,
    SECURITY,
    TIMEOUT,
    UNCLASSIFIED,
    UPSTREAM,
    CallTimeoutError,
    CircuitOpenError,
    ContractViolationError,
    ErrorInfo,
    OutputQualityError,
    RetriesExhaustedError,
    SecurityBlockedError,
    TransientError,
    classify_exception,
    classify_response,
    parse_retry_after,
    register,
)
from pipeline_incident_investigator.reliability import CLOSED, CircuitBreaker, call_reliably


# Stand-ins for third-party client exceptions (requests / httpx), matched by shape and name only.
class _Response:
    def __init__(self, status_code, headers=None, text=""):
        self.status_code, self.headers, self.text = status_code, headers or {}, text


class FakeHTTPError(Exception):
    def __init__(self, status_code, headers=None, text=""):
        super().__init__(f"HTTP {status_code}")
        self.response = _Response(status_code, headers, text)


class ConnectTimeout(Exception):
    pass


class ReadTimeout(Exception):
    pass


class PoolTimeout(Exception):
    pass


class TransportError(Exception):
    pass


def _shape(info):
    return (info.category, info.retryable, info.trips_breaker, info.outcome_unknown)


class ClassifyResponseTests(unittest.TestCase):
    def test_success_is_not_an_error(self):
        for code in (200, 201, 204):
            self.assertIsNone(classify_response(code))

    def test_each_status_maps_to_its_category_and_decisions(self):
        cases = {
            400: (REQUEST, False, False, False),
            401: (AUTH, False, False, False),
            402: (QUOTA, False, True, False),
            403: (AUTH, False, False, False),
            404: (REQUEST, False, False, False),
            408: (TIMEOUT, True, True, False),
            409: (CONSISTENCY, False, False, False),
            413: (REQUEST, False, False, False),
            422: (REQUEST, False, False, False),
            429: (RATE_LIMIT, True, False, False),
            500: (UPSTREAM, True, True, True),
            502: (UPSTREAM, True, True, True),
            503: (UPSTREAM, True, True, False),
            504: (TIMEOUT, True, True, True),
            529: (UPSTREAM, True, True, False),
            418: (REQUEST, False, False, False),   # unlisted 4xx
            599: (UPSTREAM, True, True, True),     # unlisted 5xx
            302: (CONTRACT, False, True, False),   # a redirect the client did not follow
        }
        for code, expected in cases.items():
            with self.subTest(status=code):
                info = classify_response(code)
                self.assertEqual(_shape(info), expected)
                self.assertEqual(info.status_code, code)

    def test_quota_wording_in_the_body_turns_a_429_into_a_non_retryable_quota_error(self):
        info = classify_response(429, body='{"error": {"type": "insufficient_quota"}}')
        self.assertEqual((info.error_class, info.retryable, info.trips_breaker), ("QuotaExhausted", False, True))
        low_credit = classify_response(400, body="Your credit balance is too low to access the API")
        self.assertEqual(low_credit.category, QUOTA)

    def test_retry_after_is_carried_on_the_classification(self):
        self.assertEqual(classify_response(429, headers={"Retry-After": "12"}).retry_after_seconds, 12.0)


class ParseRetryAfterTests(unittest.TestCase):
    def test_delta_seconds_header_name_is_case_insensitive(self):
        self.assertEqual(parse_retry_after({"retry-after": "3"}), 3.0)
        self.assertEqual(parse_retry_after({"RETRY-AFTER": "1.5"}), 1.5)

    def test_http_date_form_is_converted_to_seconds_from_now(self):
        now = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(parse_retry_after({"Retry-After": "Fri, 02 Oct 2026 12:00:30 GMT"}, now=now), 30.0)
        self.assertEqual(parse_retry_after({"Retry-After": "Fri, 02 Oct 2026 11:00:00 GMT"}, now=now), 0.0)

    def test_missing_or_garbage_values_give_none(self):
        for headers in (None, {}, {"Retry-After": "soon"}, {"Retry-After": "-5"}, {"Other": "1"}):
            with self.subTest(headers=headers):
                self.assertIsNone(parse_retry_after(headers))


class ClassifyExceptionTests(unittest.TestCase):
    def test_every_category_has_a_representative(self):
        cases = [
            (FakeHTTPError(400), "ValidationError", REQUEST),
            (FakeHTTPError(401), "AuthError", AUTH),
            (FakeHTTPError(429, {"Retry-After": "2"}), "RateLimitError", RATE_LIMIT),
            (FakeHTTPError(429, text="exceeded your current quota"), "QuotaExhausted", QUOTA),
            (FakeHTTPError(503), "UpstreamUnavailable", UPSTREAM),
            (TransientError("overloaded", status_code=529), "UpstreamOverloaded", UPSTREAM),
            (socket.gaierror("name resolution failed"), "DNSError", NETWORK),
            (ConnectionRefusedError(), "ConnectionRefused", NETWORK),
            (ConnectionResetError(), "ConnectionDropped", NETWORK),
            (ssl.SSLCertVerificationError("certificate has expired"), "TLSError", NETWORK),
            (TransportError("httpx-style transport failure"), "NetworkError", NETWORK),
            (ConnectTimeout(), "ConnectTimeout", TIMEOUT),
            (ReadTimeout(), "ReadTimeout", TIMEOUT),
            (PoolTimeout(), "PoolTimeout", TIMEOUT),
            (CallTimeoutError(), "CallTimeout", TIMEOUT),
            (TimeoutError(), "Timeout", TIMEOUT),
            (ContractViolationError("field 'logs' missing"), "ContractViolation", CONTRACT),
            (json.JSONDecodeError("Expecting value", "<html>", 0), "ContractViolation", CONTRACT),
            (OutputQualityError("evidence not in source"), "OutputQuality", AI_OUTPUT),
            (KeyError("oops"), "InternalError", INTERNAL),
            (TypeError("bad arg"), "InternalError", INTERNAL),
            (CircuitOpenError(), "CircuitOpen", RESILIENCE),
            (RetriesExhaustedError("x", attempts=3), "RetriesExhausted", RESILIENCE),
            (FakeHTTPError(409), "Conflict", CONSISTENCY),
            (SecurityBlockedError("prompt injection in log line"), "SecurityBlocked", SECURITY),
            (OSError("something new"), "Unclassified", UNCLASSIFIED),
        ]
        for exc, error_class, category in cases:
            with self.subTest(exc=type(exc).__name__, error_class=error_class):
                info = classify_exception(exc)
                self.assertEqual((info.error_class, info.category), (error_class, category))

    def test_not_sent_vs_outcome_unknown_is_told_apart(self):
        not_sent = [ConnectionRefusedError(), socket.gaierror(), ConnectTimeout(), PoolTimeout(), FakeHTTPError(503),
                    FakeHTTPError(429)]
        maybe_processed = [ReadTimeout(), CallTimeoutError(), ConnectionResetError(), FakeHTTPError(500),
                           FakeHTTPError(504), TransientError("no status given")]
        for exc in not_sent:
            with self.subTest(exc=repr(exc)):
                self.assertFalse(classify_exception(exc).outcome_unknown)
        for exc in maybe_processed:
            with self.subTest(exc=repr(exc)):
                self.assertTrue(classify_exception(exc).outcome_unknown)

    def test_retry_after_comes_through_from_an_http_exception_and_a_transient_error(self):
        self.assertEqual(classify_exception(FakeHTTPError(429, {"Retry-After": "9"})).retry_after_seconds, 9.0)
        self.assertEqual(classify_exception(TransientError("x", retry_after_seconds=4.0)).retry_after_seconds, 4.0)

    def test_an_expired_certificate_is_not_retried_but_a_handshake_blip_is(self):
        self.assertFalse(classify_exception(ssl.SSLCertVerificationError()).retryable)
        self.assertTrue(classify_exception(ssl.SSLError()).retryable)

    def test_interrupts_are_never_retryable(self):
        for exc in (KeyboardInterrupt(), SystemExit()):
            self.assertFalse(classify_exception(exc).retryable)

    def test_registered_types_are_used_and_can_be_unregistered(self):
        class LogsUnavailable(Exception):
            pass

        undo = register(LogsUnavailable, ErrorInfo("LogsUnavailable", UPSTREAM, True, True, False))
        try:
            self.assertEqual(classify_exception(LogsUnavailable()).error_class, "LogsUnavailable")
        finally:
            undo()
        self.assertEqual(classify_exception(LogsUnavailable()).category, UNCLASSIFIED)

    def test_should_retry_respects_idempotency(self):
        unknown = classify_exception(ReadTimeout())
        self.assertTrue(unknown.should_retry(idempotent=True))
        self.assertFalse(unknown.should_retry(idempotent=False))
        self.assertTrue(classify_exception(ConnectionRefusedError()).should_retry(idempotent=False))
        self.assertFalse(classify_exception(FakeHTTPError(400)).should_retry(idempotent=True))


class CallReliablyUsesTheClassifierTests(unittest.TestCase):
    def setUp(self):
        self.now = [0.0]
        self.sleeps = []
        self.breaker = CircuitBreaker("api", failure_threshold=3, reset_timeout_seconds=30, clock=self.clock)

    def clock(self):
        return self.now[0]

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now[0] += seconds

    def call(self, errors, *, idempotent):
        """Raise each error in turn, then return 'ok'. Returns (result or exception, calls made)."""
        calls = []

        def fn(*, timeout):
            calls.append(timeout)
            if len(calls) <= len(errors):
                raise errors[len(calls) - 1]
            return "ok"

        try:
            result = call_reliably(fn, breaker=self.breaker, idempotent=idempotent, sleep=self.sleep,
                                   clock=self.clock, rand=lambda: 1.0)
        except Exception as exc:  # noqa: BLE001 -- the test inspects whatever was raised
            result = exc
        return result, len(calls)

    def test_non_idempotent_call_is_not_retried_when_the_outcome_is_unknown(self):
        result, calls = self.call([ReadTimeout()], idempotent=False)
        self.assertIsInstance(result, ReadTimeout)
        self.assertEqual(calls, 1)

    def test_non_idempotent_call_is_retried_when_the_request_never_arrived(self):
        result, calls = self.call([ConnectionRefusedError(), FakeHTTPError(503)], idempotent=False)
        self.assertEqual((result, calls), ("ok", 3))

    def test_idempotent_call_is_retried_after_an_unknown_outcome(self):
        result, calls = self.call([ReadTimeout(), FakeHTTPError(500)], idempotent=True)
        self.assertEqual((result, calls), ("ok", 3))

    def test_exhausted_quota_is_not_retried_but_counts_against_the_breaker(self):
        breaker = CircuitBreaker("api", failure_threshold=1, clock=self.clock)
        self.breaker = breaker
        result, calls = self.call([FakeHTTPError(429, text="insufficient_quota")], idempotent=True)
        self.assertIsInstance(result, FakeHTTPError)
        self.assertEqual(calls, 1)
        self.assertNotEqual(breaker.state, CLOSED)

    def test_rate_limits_are_retried_after_retry_after_and_do_not_trip_the_breaker(self):
        breaker = CircuitBreaker("api", failure_threshold=1, clock=self.clock)
        self.breaker = breaker
        result, calls = self.call([FakeHTTPError(429, {"Retry-After": "6"})], idempotent=True)
        self.assertEqual((result, calls), ("ok", 2))
        self.assertEqual(self.sleeps, [6.0])
        self.assertEqual(breaker.state, CLOSED)

    def test_request_errors_and_unclassified_errors_are_raised_at_once_without_tripping_the_breaker(self):
        breaker = CircuitBreaker("api", failure_threshold=1, clock=self.clock)
        self.breaker = breaker
        for error in (FakeHTTPError(400), OSError("unknown"), KeyError("bug")):
            with self.subTest(error=repr(error)):
                result, calls = self.call([error], idempotent=True)
                self.assertIs(result, error)
                self.assertEqual(calls, 1)
                self.assertEqual(breaker.state, CLOSED)

    def test_attempt_logs_carry_category_and_outcome_unknown(self):
        with self.assertLogs("pipeline_incident_investigator.reliability", level="INFO") as logs:
            self.call([FakeHTTPError(504)], idempotent=True)
        first = json.loads(logs.output[0].split(":", 2)[2])
        self.assertEqual((first["error_class"], first["error_category"], first["outcome_unknown"], first["status_code"]),
                         ("GatewayTimeout", TIMEOUT, True, 504))


if __name__ == "__main__":
    unittest.main()
