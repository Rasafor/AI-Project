"""
Adapter for the one external HTTP system this tool reads from: the Anthropic
token-count endpoint (`POST {base}/v1/messages/count_tokens`). It answers a
single question — "how many input tokens would this text cost for a given
model?" — without sending anything to a model.

Contract (mirrors sql_adapter):
  * Declared, validated inputs.
  * The caller's `text` and `model` are sent as JSON **body** values — bound,
    never string-built into the URL path or a query. The path is a constant.
  * One pooled httpx client for the whole process; the per-call connection is
    released in a `finally`.
  * An explicit per-call timeout; on expiry a `TokenAdapterError("Timeout", …)`.
  * Every failure raises `TokenAdapterError` with a stable `error_class`
    (ValidationError | Timeout | Unavailable) whose message is safe to hand a
    caller — it never contains the API key, the host, or a raw httpx error
    string (those can carry the URL).

Configuration comes only from the environment, read on every call:
  ANTHROPIC_API_KEY   – credential; goes in the x-api-key header, never logged,
                        never returned to a caller.
  ANTHROPIC_BASE_URL  – service host (e.g. https://api.anthropic.com). Not
                        hard-coded here so no host string lives in source.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # annotations only — never imported at runtime
    import httpx

# `httpx` is imported lazily inside the functions that need it, NOT at module
# top: the MCP SDK ships `httpx2`, not plain `httpx`, so a minimal environment
# (e.g. `mcp dev` / `uv run --with "mcp[cli]"`, which the Inspector uses) has no
# `httpx`. Importing it here would crash server.py on startup — and the Inspector
# "Connect" with it — even for someone who never calls count_incident_tokens.
# A missing `httpx` now surfaces only when the tool is actually invoked, as a
# clean TokenAdapterError, consistent with this module's no-crash contract.

_ENDPOINT = "/v1/messages/count_tokens"  # constant path — never interpolated
_API_VERSION = "2023-06-01"

DEFAULT_TIMEOUT_S = 10.0
MAX_TIMEOUT_S = 30.0
MAX_TEXT_CHARS = 200_000
_MODEL_RE = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")

# One pooled client for the whole process: keep-alive connections are reused
# across calls (requirement: pooled/reused connection). Built lazily so import
# does no I/O and needs no configuration.
_client: httpx.Client | None = None


def _require_httpx():
    """Import httpx on demand; raise a tagged, caller-safe error if it's absent."""
    try:
        import httpx

        return httpx
    except ImportError as exc:
        raise TokenAdapterError(
            "Unavailable",
            "the token-count tool requires the 'httpx' package (pip install httpx).",
        ) from exc


def _pool() -> httpx.Client:
    global _client
    httpx = _require_httpx()
    if _client is None or _client.is_closed:
        _client = httpx.Client(
            limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
        )
    return _client


class TokenAdapterError(Exception):
    """A handled failure, tagged with a stable class. `str()` is caller-safe."""

    def __init__(self, error_class: str, message: str) -> None:
        super().__init__(message)
        self.error_class = error_class

    def __str__(self) -> str:  # what the MCP client ultimately sees
        return f"[{self.error_class}] {super().__str__()}"


def count_tokens(text: str, *, model: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> int:
    """Return the input-token count for `text` under `model`. Raises
    TokenAdapterError (never a bare httpx error, never a hang, never a leak)."""
    if not isinstance(text, str) or not text.strip():
        raise TokenAdapterError("ValidationError", "`text` must be a non-empty string.")
    if len(text) > MAX_TEXT_CHARS:
        raise TokenAdapterError(
            "ValidationError", f"`text` is {len(text)} characters; the limit is {MAX_TEXT_CHARS}."
        )
    if not isinstance(model, str) or not _MODEL_RE.match(model):
        raise TokenAdapterError(
            "ValidationError",
            "`model` must be a short model id (letters, digits, . _ : -).",
        )
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
        raise TokenAdapterError("ValidationError", "`timeout_seconds` must be a number.")
    if not 0 < float(timeout_s) <= MAX_TIMEOUT_S:
        raise TokenAdapterError(
            "ValidationError", f"`timeout_seconds` must be > 0 and <= {MAX_TIMEOUT_S}."
        )

    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not base_url or not api_key:
        # Name the missing variables, never their values.
        missing = " and ".join(
            n for n, v in (("ANTHROPIC_BASE_URL", base_url), ("ANTHROPIC_API_KEY", api_key)) if not v
        )
        raise TokenAdapterError(
            "Unavailable", f"the token-count service is not configured ({missing} unset)."
        )

    httpx = _require_httpx()  # lazy — see module note

    # `text` and `model` are model-influenced values. They go in the JSON body,
    # which httpx serialises — they are never concatenated into the URL or a
    # query. `_ENDPOINT` is a fixed constant.
    request = _pool().build_request(
        "POST",
        base_url.rstrip("/") + _ENDPOINT,
        json={"model": model, "messages": [{"role": "user", "content": text}]},
        headers={
            "x-api-key": api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        },
        timeout=httpx.Timeout(min(float(timeout_s), MAX_TIMEOUT_S)),
    )

    response: httpx.Response | None = None
    try:
        # stream=True so the pooled connection is held until we close it below —
        # the `finally` is what returns it to the pool.
        response = _pool().send(request, stream=True)
        response.read()
        if response.status_code == 200:
            try:
                tokens = response.json().get("input_tokens")
            except ValueError as exc:
                raise TokenAdapterError(
                    "Unavailable", "the token-count service returned an unparseable response."
                ) from exc
            if not isinstance(tokens, int) or tokens < 0:
                raise TokenAdapterError(
                    "Unavailable", "the token-count service returned an unexpected response shape."
                )
            return tokens
        if response.status_code in (401, 403):
            raise TokenAdapterError(
                "Unavailable", "the token-count service rejected the request credentials."
            )
        if response.status_code == 429:
            raise TokenAdapterError(
                "Unavailable", "the token-count service is rate-limiting; try again shortly."
            )
        raise TokenAdapterError(
            "Unavailable", f"the token-count request failed with HTTP {response.status_code}."
        )
    except httpx.TimeoutException as exc:
        raise TokenAdapterError(
            "Timeout", f"token counting exceeded the {float(timeout_s):g}s timeout."
        ) from exc
    except httpx.HTTPError as exc:
        # Deliberately NOT str(exc): httpx error text can contain the full URL.
        raise TokenAdapterError(
            "Unavailable", "the token-count service could not be reached."
        ) from exc
    finally:
        if response is not None:
            response.close()  # release the pooled connection
