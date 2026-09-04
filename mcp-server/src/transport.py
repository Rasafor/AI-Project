"""
Transport + state-model selection for the MCP server.

Implements docs/ADR-0001-transport.md:

  * STDIO is the shipped, documented default. One server process per client,
    launched by the client as a child; peak concurrency 1.
  * Streamable HTTP is a selectable, tested code path behind MCP_TRANSPORT.
    Switching the *deployment* to it is a separate, escalation-gated decision
    (ADR "Revisit triggers"); this module only makes the path selectable.

Environment surface — exactly the ADR's "Migration outline":

  MCP_TRANSPORT     stdio (default) | streamable-http
  MCP_HOST          HTTP bind address                     (default 127.0.0.1)
  MCP_PORT          HTTP bind port                        (default 8000)
  MCP_MOUNT_PATH    HTTP route the MCP endpoint lives at  (default /mcp)
  MCP_JSON_RESPONSE true|false — false keeps the SSE response path so progress,
                    logging and sampling can stream server->client mid-request
                    (ADR migration step 2; default false)
  MCP_STATELESS     true|false — true = no MCP session map, horizontally
                    scalable, but NO server->client back-channel (roots/list and
                    sampling do not work, so filesystem tools fail-safe deny);
                    false = one pinned replica with a session map and a working
                    back-channel, needs sticky routing / a shared store to scale.
                    ADR migration step 4 says "decide": this server actively uses
                    stateful capabilities (roots enforcement on every filesystem
                    tool, sampling in assess_table_quality), which is the ADR's
                    "if stateful capabilities are needed" case — so the default
                    is false. Set true only when you accept losing those.

STDIO ignores every HTTP variable.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    raise SystemExit(f"{name}={raw!r} is not a boolean (use true/false).")


@dataclass(frozen=True)
class TransportConfig:
    transport: str  # "stdio" | "streamable-http"
    host: str
    port: int
    mount_path: str
    json_response: bool
    stateless: bool

    @property
    def notes_read_through(self) -> bool:
        """True when there is no single authoritative process, so the in-memory
        notes list cannot be the source of truth and every request must read
        data/notes.json fresh. Only stateless HTTP is in that situation; STDIO
        (one process per client) and stateful HTTP (one pinned replica) keep the
        in-memory list."""
        return self.transport == "streamable-http" and self.stateless

    @property
    def state_model(self) -> str:
        if self.transport == "stdio":
            return (
                "process-per-client; in-memory notes list; single user, peak "
                "concurrency 1 (ADR-0001 Decision)"
            )
        if self.stateless:
            return (
                "stateless HTTP; NO in-memory session map (fresh transport per "
                "request); notes read per request from data/notes.json; any "
                "replica can serve any request; NO server->client back-channel "
                "so roots/list + sampling are unavailable and filesystem tools "
                "fail-safe deny"
            )
        return (
            "stateful HTTP; in-memory MCP session map + in-memory notes list; "
            "server->client back-channel works (roots, sampling); single replica "
            "only — needs sticky routing / a shared store to scale (ADR-0001 "
            "migration step 4)"
        )


def resolve() -> TransportConfig:
    """Read the environment once and return the resolved transport config.
    Pure — safe to call at import. Raises SystemExit on an unusable value."""
    raw = (os.environ.get("MCP_TRANSPORT") or "stdio").strip().lower()
    if raw in ("", "stdio"):
        transport = "stdio"
    elif raw in ("streamable-http", "streamable_http", "http"):
        transport = "streamable-http"
    else:
        raise SystemExit(
            f"MCP_TRANSPORT={raw!r} is not supported — use 'stdio' (default) or "
            f"'streamable-http'. See docs/ADR-0001-transport.md."
        )
    try:
        port = int(os.environ.get("MCP_PORT", "8000"))
    except ValueError:
        raise SystemExit(f"MCP_PORT={os.environ.get('MCP_PORT')!r} is not an integer.")
    return TransportConfig(
        transport=transport,
        host=os.environ.get("MCP_HOST", "127.0.0.1"),
        port=port,
        mount_path=os.environ.get("MCP_MOUNT_PATH", "/mcp"),
        json_response=_flag("MCP_JSON_RESPONSE", False),
        # Default false: this server uses server->client requests (roots on every
        # filesystem tool, sampling in assess_table_quality), which the SDK's
        # stateless mode cannot deliver. ADR-0001 migration step 4 "decide"
        # resolves to stateful here.
        stateless=_flag("MCP_STATELESS", False),
    )


def run(mcp, cfg: TransportConfig) -> None:
    """State which transport + state model this process runs, then hand off to
    the SDK.

    The startup line is written as ONE flushed JSON line to STDERR — never
    stdout (on STDIO stdout is the JSON-RPC stream, ADR-0001 Consequences) — and
    deliberately as a direct write rather than through the structured logger, so
    it stays a single greppable line and survives an early SIGTERM. An operator
    can read the transport and state model from this line alone.
    """
    http = cfg.transport == "streamable-http"
    line = {
        "event": "server.starting",
        "transport": cfg.transport,
        "state_model": cfg.state_model,
        "stateless": cfg.stateless if http else None,
        "notes_read_through": cfg.notes_read_through if http else None,
        "host": cfg.host if http else None,
        "port": cfg.port if http else None,
        "mount_path": cfg.mount_path if http else None,
        "json_response": cfg.json_response if http else None,
    }
    print(json.dumps({k: v for k, v in line.items() if v is not None}), file=sys.stderr, flush=True)

    if cfg.transport == "stdio":
        # SINGLE-USER ASSUMPTION. Do NOT scale this by launching more processes
        # behind a router: STDIO is one server process per client, spawned by the
        # client as a child (ADR-0001 "Decision"). Peak concurrency is 1. The
        # in-memory notes list is correct ONLY because it is never shared. The
        # moment two people need one running instance, or a client is not a local
        # subprocess, this is the wrong transport — that is an ADR revisit, not a
        # config change.
        mcp.run(transport="stdio")
        return

    # Streamable HTTP.
    #
    # stateless=True: the SDK creates a fresh transport per request and keeps NO
    # session map (StreamableHTTPSessionManager._server_instances stays empty);
    # combined with notes_read_through, every request is fully self-contained and
    # any replica can serve any request.
    #   Failure this avoids: stale-replica / split-brain state. With a per-process
    #   session map — or an in-memory notes cache — a client's follow-up request
    #   routed to a different replica (or to the same replica after a restart)
    #   lands on a process that never saw the earlier request: the MCP session is
    #   unknown so the call fails, or the notes list is missing the note just
    #   added. Stateless transport + per-request file reads make "which process
    #   answered" irrelevant.
    #   Cost (SDK behaviour, also flagged in ADR-0001): stateless mode gives NO
    #   back-channel for server-initiated requests, so roots/list raises
    #   NoBackChannelError and every filesystem tool fail-safe denies, and
    #   assess_table_quality falls back to its rule-based verdict.
    #
    # stateless=False (default): the SDK keeps a session map keyed by
    # Mcp-Session-Id; the back-channel works so roots + sampling function. This
    # deployment is a single replica unless you add sticky routing / a shared
    # session store (ADR-0001 migration step 4).
    mcp.run(
        transport="streamable-http",
        host=cfg.host,
        port=cfg.port,
        streamable_http_path=cfg.mount_path,
        json_response=cfg.json_response,
        stateless_http=cfg.stateless,
    )
