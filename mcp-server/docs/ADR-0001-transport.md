# ADR-0001: Transport choice for the MCP server deployment

- **Status:** Accepted
- **Date:** 2026-08-31
- **Author:** Regina
- **Scope:** `mcp-server/` (Python server in `src/`, Node.js reference in `nodejs/`)
- **Supersedes:** none

---

## Context

`mcp-server/` is a Model Context Protocol server. Today it exposes one tool
(`add_note`), one resource (`notes://all`), and one prompt (`capture_note`),
backed by an in-memory store. It is exercised two ways:

1. The **MCP Inspector**, launched locally with `mcp dev src/server.py`.
2. `src/test_connection.py`, which spawns the server over stdio and asserts on
   every primitive.

Current operating reality:

- **One developer** uses the server at a time. Peak concurrency is 1.
- It runs **on the same machine** as the client. There is no requirement for a
  client on another host to reach it.
- The data is a **demo store**, not shared between people and not persistent.
- There is **no SLA, no uptime target, no multi-tenant requirement**.
- The server is a **reference implementation** in a learning repo, iterated on
  frequently.

The MCP specification defines two transports relevant to a deployment decision:

- **STDIO** — the client launches the server as a child process and speaks
  JSON-RPC over the process's stdin/stdout.
- **Streamable HTTP** — the server is a long-lived HTTP service with a single
  endpoint; responses may upgrade to Server-Sent Events so the server can push
  messages (progress, logging, sampling requests) while a request is in flight.

(A third transport, HTTP+SSE, was deprecated in the 2025-03-26 spec revision and
is not considered here.)

This ADR records which transport the deployment uses and why.

---

## Decision

**The server ships with STDIO as its transport.**

The upgraded server (see `transport.py` in the build plan) keeps Streamable HTTP
as a selectable, tested code path behind the `MCP_TRANSPORT` environment
variable, but the **deployed and documented default is STDIO**. Switching the
deployment to Streamable HTTP is a separate, explicit decision gated on the
revisit triggers below.

---

## Options considered

| Dimension | STDIO | Streamable HTTP |
|---|---|---|
| Client relationship | One child process per client; lifecycle owned by the host | One service, many concurrent clients |
| Network exposure | None — no port, no listener | Open port; needs TLS, auth, CORS, rate limiting |
| Server→client streaming (progress, logs, sampling) | Native over the pipe | Requires the SSE response path (`json_response = false`) |
| Deployment unit | Code + a launch command | Code + process manager + reverse proxy + secrets + deploy pipeline |
| Remote access | Not possible | The point of it |
| Shared state across users | Not possible (process-per-client) | Possible, via a shared datastore |
| Failure blast radius | One client session; host restarts the process | All connected clients |
| Governance cost in this repo | Reversible, local — "proceed autonomously" zone | Touches production infra + security posture — escalation triggers per `CLAUDE.md` |

---

## Rationale

### 1. The performance characteristic that matters here is iteration speed

STDIO has no TCP handshake, no HTTP header parsing, and no TLS. A request/response
round trip is dominated by JSON-RPC serialization and the tool's own work — IPC
over OS pipes is sub-millisecond. For a server being edited and re-run many times
a day against the Inspector, "start it with one command, no ports, no config" is
the property with the highest daily value.

Streamable HTTP would add a TCP + HTTP (+ TLS + reverse-proxy) path on every
call. On localhost that overhead is small in absolute terms, but it buys nothing
the current usage needs.

### 2. Scalability need is effectively zero, and provisioning for absent scale has real cost

"Scaling" STDIO means the host spawns more child processes, bounded by the one
machine. There is no horizontal story and no multi-tenancy — each process serves
exactly one client. For a single developer that is a perfect fit, not a
limitation.

Streamable HTTP's advantages — one process amortizing an async event loop and
shared connection pools across many clients, N replicas behind a load balancer,
one deployment serving a whole team — are all answers to problems this server
does not have. Adopting them now means standing up and maintaining a
network-exposed service (auth rotation, DoS surface, health checks, monitoring,
rate limiting) to serve a peak concurrency of one.

### 3. STDIO keeps the change inside the repo's "proceed autonomously" boundary

Per `CLAUDE.md`'s Autonomy Model, "production infrastructure or environment
modification" and "compliance or security posture" are escalation triggers.
A network-listening HTTP service with authentication and TLS crosses both.
STDIO keeps the server a reversible, local, low-blast-radius component that does
not require a strategic decision to deploy. Moving to Streamable HTTP should be
made deliberately, when a trigger below actually fires — not pre-emptively.

### 4. Security surface

STDIO exposes nothing to the network. There is no port to firewall, no auth to
implement or rotate, no token to leak, no CORS policy to get wrong. The server's
trust boundary is the local user account that launched it. This is the smallest
possible attack surface and it is free.

---

## Performance and scalability analysis

### STDIO

- **Latency:** sub-millisecond transport overhead (OS pipes). End-to-end latency
  is essentially the cost of the tool logic plus JSON-RPC framing.
- **Throughput:** bounded by a single client and a single machine. One
  interpreter process per session.
- **Concurrency model:** none across sessions — each client gets an isolated
  process with its own memory. In-process state (the notes list) is safe because
  it is never shared.
- **Resource model:** process lifetime equals session lifetime. No idle network
  listeners. Cold start per session equals Python import time — currently
  negligible; worth watching if the server gains heavy dependencies.
- **Where it hits a wall:** the moment two humans need the same running instance,
  or any client is not a local subprocess.

### Streamable HTTP

- **Latency:** adds TCP + HTTP (+ TLS + reverse-proxy) hops — low milliseconds on
  a LAN, more over WAN. An SSE connection is held open for the duration of
  streamed server→client messages.
- **Throughput:** one process serves many clients concurrently on an async event
  loop; interpreter, caches, and adapter connection pools are shared and
  amortized.
- **Concurrency model:** many sessions in one process. Stateful sessions require
  sticky routing or a shared session store; `stateless_http = true` removes
  per-session state and makes horizontal scaling clean at the cost of
  server-initiated messages outside a request and stream resumability.
- **Scalability:** horizontal — N replicas behind nginx (already in this repo) or
  a load balancer. Scales with demand, not with the number of client machines.
  Enables one deployment serving a team against a shared datastore.
- **Operational cost:** monitoring, health checks, rate limiting, auth issuance
  and rotation, DoS mitigation, and a real build/release/run pipeline.

### Alignment with this server's needs

| Need | Current value | Transport that serves it |
|---|---|---|
| Fast edit-run-test loop | High | STDIO |
| Zero operational overhead | High | STDIO |
| Minimal security surface | High | STDIO |
| Remote access | None | — |
| Multiple concurrent users | None | — |
| Shared/persistent notes store across users | None | — |
| Horizontal scaling / high availability | None | — |

Every need with non-trivial value points to STDIO. Every capability that would
justify Streamable HTTP currently has zero demand.

---

## Consequences

Accepting STDIO means accepting, until a revisit trigger fires:

- The server **cannot be reached from another machine**.
- The server **cannot serve more than one client per process**; there is no
  shared instance and no cross-session state.
- Every client session pays a **cold start** (interpreter + imports).
- **Logging must never go to stdout** — stdout is the protocol stream. The server
  uses MCP logging notifications (`ctx.info` / `ctx.debug` / …) for all
  diagnostics. A stray `print()` corrupts the session.
- If persistence is added, it must be an **external store** (file or DB), because
  in-memory state dies with the process.

The Streamable HTTP code path remains in the tree and under test so that a future
migration is a configuration change plus an infrastructure decision, not a
rewrite.

> **Update 2026-08-31:** The in-memory store called out above has been replaced
> with file-backed persistence — `src/notes_store.py` writing to `data/notes.json`
> (override with `MCP_NOTES_DATA_ROOT`). Every file access is fenced to that one
> directory by `resolve_within()`, which rejects `..`, absolute, and symlink
> escapes with a raised error rather than a silent empty result. Transport is
> unchanged (still stdio). This satisfies the "external store" requirement and
> keeps the store contained to the narrowest root that does the job.

---

## Revisit triggers

Re-open this decision and evaluate migrating the deployment to Streamable HTTP
when **any** of the following becomes true:

1. More than one person needs to use the **same running server instance** or a
   **shared notes store**.
2. The server must run **remotely** — near the data or credentials it needs, or
   reachable from a machine other than the client's.
3. The server must be embedded in a **hosted product or multi-user portal**.
4. **Automated, non-desktop clients** (CI jobs, schedulers, other services) must
   reach it over the network.
5. Centralized **auth, audit, rate limiting, or cross-session observability** is
   required.

Because triggers 2, 3, and 5 involve production infrastructure and security
posture, acting on them is an escalation per `CLAUDE.md`, not an autonomous
change.

---

## Migration outline (for reference, not yet in effect)

1. Set `MCP_TRANSPORT=streamable-http` and configure `MCP_HOST`, `MCP_PORT`,
   `MCP_MOUNT_PATH`.
2. Keep `MCP_JSON_RESPONSE=false` so progress, logging, and sampling can stream
   server→client during a request.
3. Front the ASGI app with authentication middleware and TLS termination
   (nginx already exists in this repo for the latter).
4. Decide stateful vs. stateless: set `MCP_STATELESS=true` for clean horizontal
   scaling, or add sticky routing / a shared session store if stateful
   capabilities are needed.
5. Move the notes store to an external datastore.
6. Add health-check, rate-limit, and structured-log-forwarding config.
7. Re-run the full connection and capability test matrix over HTTP.

---

## References

- MCP transports specification (STDIO, Streamable HTTP; HTTP+SSE deprecation,
  2025-03-26).
- `mcp-server/README.md` — current Inspector-based workflow.
- `mcp-server/src/test_connection.py` — stdio connection and capability tests.
- `CLAUDE.md` — Autonomy Model (escalation triggers), Production Readiness
  Principles (build/release/run separation, config from env).
