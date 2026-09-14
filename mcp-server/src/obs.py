"""
Structured log-notification helpers for the MCP server.

Every tool invocation mints one correlation id (`new_correlation_id`) and passes
it to `emit` on *every* line it logs, so one run can be traced end to end. Log
payloads are flat dicts with a stable `event` name and safe scalar fields only —
never a note body, a bound SQL parameter, a full row, an API key, or a
connection string. Callers are responsible for that discipline; this module just
guarantees `event` + `correlation_id` are always present and that a lost log
line can never break a tool (`emit` and `external_call` never raise).

Delivery: the server advertises the MCP `logging` capability (see server.py).
MCP log notifications are an opt-in channel — the SDK sends nothing to a client
that has not negotiated logging, so without that capability declared (and,
on the modern protocol, without the client's per-request opt-in) these lines
are silently dropped.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
import warnings
from contextlib import asynccontextmanager

_log = logging.getLogger("ai-project-mcp-server")

# --- stable event names ------------------------------------------------------
EVENT_TOOL_INVOKED = "tool.invoked"
EVENT_TOOL_COMPLETED = "tool.completed"
EVENT_EXTERNAL_STARTED = "external_call.started"
EVENT_EXTERNAL_FINISHED = "external_call.finished"
EVENT_ACCESS_DENIED = "access.denied"
EVENT_ERROR_CAUGHT = "error.caught"
EVENT_SAMPLING_UNSUPPORTED = "sampling.unsupported"
# roots containment (see roots_fence.py)
EVENT_ROOTS_DENIED = "roots.denied"              # a requested path resolved outside every declared root
EVENT_ROOTS_NO_ROOTS = "roots.no_roots_declared"  # client declared no roots at all -> default deny

# --- stable error-class names (never a bare message string) ----------------
ERR_VALIDATION = "ValidationError"
ERR_ACCESS_DENIED = "AccessDenied"
ERR_TIMEOUT = "TimeoutError"
ERR_UPSTREAM_UNAVAILABLE = "UpstreamUnavailable"
ERR_QUERY = "QueryError"
ERR_INTERNAL = "InternalError"

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}

# Substrings that mark an fs_fence / authorizer rejection as an access-control
# failure rather than a plain bad argument.
_DENY_MARKERS = ("escapes the allowed directory", "not authorized", "not permitted")


def new_correlation_id() -> str:
    """A fresh id for one invocation. Goes on every log line for that run."""
    return uuid.uuid4().hex


def classify(exc: BaseException) -> str:
    """Map any caught exception to ONE stable error-class name.

    Never returns the exception's message. sql_adapter tags its own failures
    with `.error_class`; those are translated into this module's vocabulary.
    """
    tagged = getattr(exc, "error_class", None)
    msg = str(exc).lower()

    if tagged == "Timeout":
        return ERR_TIMEOUT
    if tagged == "Unavailable":
        return ERR_UPSTREAM_UNAVAILABLE
    if tagged == "QueryError":
        return ERR_QUERY
    if tagged == "ValidationError":
        return ERR_ACCESS_DENIED if any(m in msg for m in _DENY_MARKERS) else ERR_VALIDATION

    if type(exc).__name__ == "QualityInputError":
        return ERR_VALIDATION
    if isinstance(exc, ValueError) and any(m in msg for m in _DENY_MARKERS):
        return ERR_ACCESS_DENIED
    if isinstance(exc, TimeoutError):
        return ERR_TIMEOUT
    if type(exc).__name__ in ("NoBackChannelError", "MCPError", "McpError"):
        return ERR_UPSTREAM_UNAVAILABLE
    return ERR_INTERNAL


async def emit(ctx, level: str, event: str, correlation_id: str, **fields) -> None:
    """Send one structured MCP log notification; mirror it to the local logger.

    `data` is always `{event, correlation_id, **fields}`. Best-effort: a
    transport hiccup here must not change what the tool returns.
    """
    payload = {"event": event, "correlation_id": correlation_id, **fields}
    try:
        _log.log(_LEVELS.get(level, logging.INFO), json.dumps(payload, default=str))
    except Exception:  # pragma: no cover
        pass
    try:
        with warnings.catch_warnings():
            # MCP logging capability is deprecated (SEP-2577) but is still the
            # channel for a client-visible structured log notification.
            warnings.simplefilter("ignore")
            await ctx.log(level, payload)
    except Exception:  # pragma: no cover - a lost log line must not fail the tool
        pass


class _Call:
    """Handle yielded by `external_call`. `.note(**fields)` adds fields to the
    `external_call.finished` line; `.duration_ms` is filled in on the way out
    (both on success and on error) so the caller can reuse the measured value."""

    __slots__ = ("extra", "duration_ms")

    def __init__(self) -> None:
        self.extra: dict = {}
        self.duration_ms: float | None = None

    def note(self, **fields) -> None:
        self.extra.update(fields)


@asynccontextmanager
async def external_call(ctx, correlation_id: str, target: str, op: str, **fields):
    """Wrap one call across an external boundary (SQLite, the client's model,
    the notes file on disk).

    Emits `external_call.started`, then on the way out either
    `external_call.finished` with `duration_ms` (success) or a failure line with
    a stable `error_class` + `duration_ms` and re-raises. The failure line is
    `access.denied` when the error classifies as an access-control rejection,
    otherwise `error.caught`.
    """
    await emit(ctx, "debug", EVENT_EXTERNAL_STARTED, correlation_id, target=target, op=op, **fields)
    call = _Call()
    started = time.monotonic()
    try:
        yield call
    except BaseException as exc:  # noqa: BLE001 - logged with a stable class, then re-raised
        call.duration_ms = round((time.monotonic() - started) * 1000, 1)
        error_class = classify(exc)
        denied = error_class == ERR_ACCESS_DENIED
        await emit(
            ctx,
            "warning" if denied else "error",
            EVENT_ACCESS_DENIED if denied else EVENT_ERROR_CAUGHT,
            correlation_id,
            target=target,
            op=op,
            error_class=error_class,
            duration_ms=call.duration_ms,
            **fields,
        )
        raise
    call.duration_ms = round((time.monotonic() - started) * 1000, 1)
    await emit(
        ctx,
        "info",
        EVENT_EXTERNAL_FINISHED,
        correlation_id,
        target=target,
        op=op,
        duration_ms=call.duration_ms,
        **fields,
        **call.extra,
    )
