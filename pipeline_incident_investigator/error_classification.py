"""Classify failed API calls into stable categories that drive recovery decisions.

One function answers, for any failure, the four questions every caller used to
answer on its own (and inconsistently):

    retryable        -- can trying again help?
    trips_breaker    -- is this evidence the upstream is unhealthy?
    outcome_unknown  -- might the upstream have processed the request anyway?
                        (then a retry is only safe if the operation is idempotent)
    error_class      -- a stable name for logs, metrics and alert routing

classify_response() handles HTTP status codes (plus Retry-After and quota markers in
the body). classify_exception() handles exceptions: this package's own, Python's
network errors, and third-party HTTP clients by duck typing (an exception carrying
.status_code / .response.status_code is classified by its status; requests/httpx
timeout classes are recognized by name) -- so no client library is a dependency.

Defaults are conservative. A failure nothing recognizes is "Unclassified": not
retried (a blind retry might duplicate a side effect), not counted against the
breaker (it may be our bug), and visible in metrics so the gap gets closed. Modules
with their own exception types call register() instead of editing this file.
"""

from __future__ import annotations

import json
import socket
import ssl
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Mapping

REQUEST = "request"
AUTH = "auth"
RATE_LIMIT = "rate_limit"
QUOTA = "quota"
UPSTREAM = "upstream"
NETWORK = "network"
TIMEOUT = "timeout"
CONTRACT = "contract"
AI_OUTPUT = "ai_output"
INTERNAL = "internal"
RESILIENCE = "resilience"
CONSISTENCY = "consistency"
SECURITY = "security"
UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class ErrorInfo:
    error_class: str
    category: str
    retryable: bool
    trips_breaker: bool
    outcome_unknown: bool
    retry_after_seconds: float | None = None
    status_code: int | None = None

    def should_retry(self, *, idempotent: bool) -> bool:
        """Retry only what can succeed next time, and never risk a duplicate side effect."""
        return self.retryable and (idempotent or not self.outcome_unknown)


def _info(error_class, category, retryable, trips_breaker, outcome_unknown) -> ErrorInfo:
    return ErrorInfo(error_class, category, retryable, trips_breaker, outcome_unknown)


# --- Exceptions callers raise to say what went wrong --------------------------------


class TransientError(Exception):
    """An upstream failure worth retrying (HTTP 5xx, 429). Pass status_code when known:
    it decides whether the request might have been processed (500/502/504) or not (503/429)."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None, status_code: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
        self.status_code = status_code


class CallTimeoutError(Exception):
    """One attempt took longer than its timeout. The request may already have been sent."""


class CircuitOpenError(Exception):
    """The breaker is open: the upstream failed repeatedly, so the call was not made."""


class RetriesExhaustedError(Exception):
    """Every allowed attempt failed, or the total time budget ran out."""

    def __init__(self, message: str, *, attempts: int) -> None:
        super().__init__(message)
        self.attempts = attempts


class ContractViolationError(Exception):
    """The call returned, but the response is unusable: wrong shape, truncated, renamed field."""


class OutputQualityError(Exception):
    """An AI output is well-formed but fails a quality gate (ungrounded, hallucinated, unsafe verdict)."""


class SecurityBlockedError(Exception):
    """A call or output was blocked for security reasons (prompt injection, secret in output)."""


# --- HTTP responses -----------------------------------------------------------------

_STATUS: dict[int, ErrorInfo] = {
    400: _info("ValidationError", REQUEST, False, False, False),
    401: _info("AuthError", AUTH, False, False, False),
    402: _info("QuotaExhausted", QUOTA, False, True, False),
    403: _info("Forbidden", AUTH, False, False, False),
    404: _info("NotFound", REQUEST, False, False, False),
    408: _info("RequestTimeout", TIMEOUT, True, True, False),
    409: _info("Conflict", CONSISTENCY, False, False, False),
    413: _info("PayloadTooLarge", REQUEST, False, False, False),
    422: _info("ValidationError", REQUEST, False, False, False),
    429: _info("RateLimitError", RATE_LIMIT, True, False, False),
    500: _info("UpstreamError", UPSTREAM, True, True, True),
    502: _info("BadGateway", UPSTREAM, True, True, True),
    503: _info("UpstreamUnavailable", UPSTREAM, True, True, False),
    504: _info("GatewayTimeout", TIMEOUT, True, True, True),
    529: _info("UpstreamOverloaded", UPSTREAM, True, True, False),  # Anthropic API: overloaded_error
}
_OTHER_4XX = _info("ClientError", REQUEST, False, False, False)
_OTHER_5XX = _info("UpstreamError", UPSTREAM, True, True, True)
_UNEXPECTED_3XX = _info("UnexpectedRedirect", CONTRACT, False, True, False)

# Wordings providers use when the account is out of quota or credit. Unlike a per-minute
# rate limit, these do not clear by waiting, so retrying only burns attempts.
_QUOTA_MARKERS = ("insufficient_quota", "quota exceeded", "exceeded your current quota", "billing",
                  "credit balance")


def parse_retry_after(headers: Mapping[str, str] | None, *, now: datetime | None = None) -> float | None:
    """Seconds from a Retry-After header (delta-seconds or HTTP-date), or None if absent/invalid."""
    if not headers:
        return None
    value = next((v for k, v in headers.items() if k.lower() == "retry-after"), None)
    if value is None:
        return None
    value = str(value).strip()
    if value.replace(".", "", 1).isdigit():
        return float(value)  # delta-seconds
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    return max(0.0, (when - (now or datetime.now(timezone.utc))).total_seconds())


def classify_response(
    status_code: int, headers: Mapping[str, str] | None = None, body: str | None = None
) -> ErrorInfo | None:
    """Classify an HTTP status. Returns None for 2xx (not an error)."""
    if 200 <= status_code < 300:
        return None
    if 300 <= status_code < 400:
        info = _UNEXPECTED_3XX
    else:
        info = _STATUS.get(status_code) or (_OTHER_5XX if status_code >= 500 else _OTHER_4XX)
        if 400 <= status_code < 500 and body and any(m in body.lower() for m in _QUOTA_MARKERS):
            info = _STATUS[402]
    return replace(info, status_code=status_code, retry_after_seconds=parse_retry_after(headers))


# --- Exceptions ---------------------------------------------------------------------

_REGISTRY: list[tuple[type[BaseException], ErrorInfo]] = []

_OWN: tuple[tuple[type[BaseException], ErrorInfo], ...] = (
    (CircuitOpenError, _info("CircuitOpen", RESILIENCE, False, False, False)),
    (RetriesExhaustedError, _info("RetriesExhausted", RESILIENCE, False, False, False)),
    (CallTimeoutError, _info("CallTimeout", TIMEOUT, True, True, True)),
    (ContractViolationError, _info("ContractViolation", CONTRACT, False, True, False)),
    (OutputQualityError, _info("OutputQuality", AI_OUTPUT, False, False, False)),
    (SecurityBlockedError, _info("SecurityBlocked", SECURITY, False, False, False)),
)

# Python's own network errors, most specific first.
_BUILTIN_NETWORK: tuple[tuple[type[BaseException], ErrorInfo], ...] = (
    (ssl.SSLCertVerificationError, _info("TLSError", NETWORK, False, True, False)),  # fixed by config, not time
    (ssl.SSLError, _info("TLSError", NETWORK, True, True, True)),
    (socket.gaierror, _info("DNSError", NETWORK, True, True, False)),
    (ConnectionRefusedError, _info("ConnectionRefused", NETWORK, True, True, False)),
    (ConnectionResetError, _info("ConnectionDropped", NETWORK, True, True, True)),
    (ConnectionAbortedError, _info("ConnectionDropped", NETWORK, True, True, True)),
    (BrokenPipeError, _info("ConnectionDropped", NETWORK, True, True, True)),
)

# Third-party client exceptions (requests, httpx, urllib3), recognized by class name.
_BY_NAME: dict[str, ErrorInfo] = {
    "ConnectTimeout": _info("ConnectTimeout", TIMEOUT, True, True, False),  # never connected: not sent
    "PoolTimeout": _info("PoolTimeout", TIMEOUT, True, False, False),       # waited for our own pool: not sent
    "ReadTimeout": _info("ReadTimeout", TIMEOUT, True, True, True),         # sent, no reply: outcome unknown
    "WriteTimeout": _info("WriteTimeout", TIMEOUT, True, True, True),
}

_GENERIC: tuple[tuple[type[BaseException], ErrorInfo], ...] = (
    (TimeoutError, _info("Timeout", TIMEOUT, True, True, True)),
    (ConnectionError, _info("NetworkError", NETWORK, True, True, True)),
    (json.JSONDecodeError, _info("ContractViolation", CONTRACT, False, True, False)),
    ((TypeError, LookupError, AttributeError, ValueError, NameError, AssertionError, NotImplementedError,
      ArithmeticError), _info("InternalError", INTERNAL, False, False, False)),  # type: ignore[misc]
)

_UNCLASSIFIED = _info("Unclassified", UNCLASSIFIED, False, False, False)
_INTERRUPT = _info("Interrupted", INTERNAL, False, False, False)


def register(exc_type: type[BaseException], info: ErrorInfo) -> Callable[[], None]:
    """Teach the classifier a module's own exception type. Returns a function that undoes it.
    Registered types are checked before the built-in rules, so they can override them."""
    entry = (exc_type, info)
    _REGISTRY.append(entry)
    return lambda: _REGISTRY.remove(entry)


def _status_of(exc: BaseException) -> int | None:
    for holder in (exc, getattr(exc, "response", None)):
        for attr in ("status_code", "status"):
            value = getattr(holder, attr, None)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
    return None


def _from_http_exception(exc: BaseException, status: int) -> ErrorInfo:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    body = getattr(response, "text", None)
    info = classify_response(status, headers if isinstance(headers, Mapping) else None,
                             body[:2000] if isinstance(body, str) else None)
    return info or _info("ContractViolation", CONTRACT, False, True, False)  # a 2xx raised as an error


def classify_exception(exc: BaseException) -> ErrorInfo:
    """Classify any exception raised by, or while handling, an API call."""
    if not isinstance(exc, Exception):
        return _INTERRUPT  # KeyboardInterrupt, SystemExit: never retried, never swallowed

    for exc_type, info in (*_REGISTRY, *_OWN):
        if isinstance(exc, exc_type):
            return info

    if isinstance(exc, TransientError):
        if exc.status_code is not None:
            info = classify_response(exc.status_code) or _STATUS[503]
        else:
            info = _info("UpstreamUnavailable", UPSTREAM, True, True, True)  # status unknown: assume the worst
        return replace(info, retry_after_seconds=exc.retry_after_seconds)

    status = _status_of(exc)
    if status is not None:
        return _from_http_exception(exc, status)

    for exc_type, info in _BUILTIN_NETWORK:
        if isinstance(exc, exc_type):
            return info

    for cls in type(exc).__mro__:
        if cls.__name__ in _BY_NAME:
            return _BY_NAME[cls.__name__]

    for exc_type, info in _GENERIC:
        if isinstance(exc, exc_type):
            return info

    if any(cls.__name__ in ("ConnectionError", "TransportError") for cls in type(exc).__mro__):
        return _info("NetworkError", NETWORK, True, True, True)  # requests/httpx connection failures

    return _UNCLASSIFIED
