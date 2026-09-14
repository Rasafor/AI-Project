# mcp-server/nodejs

Node.js/TypeScript-SDK reference implementation of the same MCP server as
[`../src`](../src) (Python) — the "notes" example plus the `run_sql_query`
integration. Same design, different SDK:

- **Tool** `add_note(title, content, idempotency_key?)` — saves a note, or
  returns the existing one if this add is a duplicate (retry-safe).
- **Resource** `notes://all` — exposes the current list of notes as JSON.
- **Prompt** `capture_note(raw_text)` — a reusable template that guides the
  model to turn unstructured text into a title + body and call `add_note`.
- **Tool** `run_sql_query(database, query, …)` — the adapter for the "SQL"
  data source named in the project plan. See "The `run_sql_query` tool".

**This folder exists as a learning comparison, not a second product to
maintain.** `../src` (Python) is the version this repo actually builds on.
Use this folder when you want to see how the Node.js MCP SDK expresses the
same tool/resource/prompt contracts Python's does — e.g. Zod schemas here
vs. Pydantic `Field(...)` there, `server.tool(name, description, schema,
handler)` here vs. the `@mcp.tool()` decorator there.

---

## Setup

```
npm install
```

Installs `@modelcontextprotocol/sdk` and `zod`.

## Run the server directly

```
npm start
```

This runs `node server.js`, which just sits there speaking JSON-RPC over
stdio — not useful to look at directly. Use the Inspector or the test
client below to actually interact with it.

## Test with the MCP Inspector

```
npm run inspect
```

Opens the Inspector UI in your browser (same tool the Python version uses).
Click **Connect** — you should see `add_note`, `notes://all`, and
`capture_note` in their respective tabs. Try running `add_note`, then read
`notes://all` to confirm the new note shows up.

## Automated connection test (no browser needed)

```
npm test
```

Runs `test-connection.js`, `test-notesStore.js`, `test-sqlAdapter.js`, then
`test-idempotency.js`.

`test-connection.js` spawns the server over stdio and asserts on: discovery
of every primitive (`add_note`, `run_sql_query`, `notes://all`,
`capture_note`), the tool's happy path, the tool's rejection of an empty
title, the resource reflecting the tool's write, and the prompt's argument
interpolation.

`test-notesStore.js` (also `npm run test:store`) covers the storage layer:
the path fence — feeding it `../../etc/hosts` and absolute paths and
asserting each is refused — the save/load round-trip, and that a corrupt
store file throws instead of being read as empty.

`test-sqlAdapter.js` (also `npm run test:sql`) covers the SQL adapter:
argument validation, the path fence, every "system unavailable" case, and
the timeout — including a deliberately runaway query that is cancelled in
~0.5s instead of hanging.

`test-idempotency.js` (also `npm run test:idempotency`) checks that a retried
`add_note` — same `idempotency_key`, or identical `title`+`content` with no
key — returns the existing note instead of a duplicate, across a restart too.

All print `PASS: ...` and exit `0` on success, or fail with a non-zero exit
on any regression. None touch the real `data/`; they run against temp
directories (`test-connection.js` passes `MCP_NOTES_DATA_ROOT` and
`MCP_SQL_DATA_ROOT` to the spawned server).

## Where notes are stored

Notes persist to `nodejs/data/notes.json`, created on first run. `data/` is
runtime state, not source — it is git-ignored (by the `data/` rule in
`../.gitignore`, which matches at any depth).

All file access for the store goes through one guard, `resolveWithin()` in
`notesStore.js`, which refuses any path resolving outside `data/` (via `..`,
an absolute path, or a symlink) by throwing an error naming the offending
path — it never silently returns nothing. Nothing passes a caller-supplied
path to the store today (the filename is hardcoded); the guard is a safety
net and the check any future path-taking tool must call. This mirrors
`../src/notes_store.py` and its `resolve_within()`.

Set `MCP_NOTES_DATA_ROOT` to point the store elsewhere.

**Cross-call state** — see `../README.md` "What this server assumes" for the
full inventory. Node-specific points: `add_note` writes the file *before*
pushing to the in-memory array, so a failed save never leaves memory ahead of
disk; `atomicWrite` uses a per-write-unique temp filename; `add_note` is
retry-safe (dedups on `idempotency_key`, or on identical `title`+`content`
with no key). There is no lock (the Python version has one) because the Node
SDK runs each tool handler's synchronous body to completion on the single
event-loop thread, so two `add_note` calls cannot interleave.

## The `run_sql_query` tool

The Node mirror of `../src/sql_adapter.py` — the adapter for the one external
system named in `.colaberry/plan.json` (`derived.systems: ["SQL"]`, REQ-008,
STORY-003).

**Backend:** the built-in `node:sqlite` module (Node ≥ 22.5) — nothing to
`npm install`. The database is a file under the SQL data root
(`MCP_SQL_DATA_ROOT`, default `nodejs/data/`). Pointing it at a real
warehouse later is a change inside `sqlAdapter.js` / `sqlChild.js`.

**Inputs** (declared in `server.js` via zod, re-validated in `sqlAdapter.js`):
`database` (must resolve inside the SQL data root), `query` (one read-only
statement; `INSERT/UPDATE/DELETE/DROP/…/ATTACH` rejected; also opened
`readOnly` with an ATTACH/DETACH authorizer in the child), optional `params`
(≤ 100, bound to `?`), `timeout_seconds` (`0 < t ≤ 30`, default 5),
`max_rows` (`1..1000`, default 100).

**Success** returns JSON `{ database, columns, rows, row_count, truncated, elapsed_ms }`.

**When the SQL system is down**, the tool returns `isError: true` with a
tagged message — never a crash, never a hang:

| Situation | Message |
|---|---|
| file missing | `[Unavailable] database file not found: … The SQL system is unreachable.` |
| corrupt / not SQLite | `[Unavailable] the database could not be opened (file is not a database) …` |
| locked by another process | `[Unavailable] the database is locked by another process; try again shortly.` |
| query exceeds `timeout_seconds` | `[Timeout] the query was cancelled after exceeding the <n>s timeout …` |
| write / DDL / multi-statement / bad argument | `[ValidationError] …` (database untouched) |
| missing table, etc. | `[QueryError] the query could not run: … .` |

**One implementation difference from Python:** `node:sqlite` is synchronous
and has no interrupt call, so a same-process watchdog (what the Python
adapter uses) cannot stop a running query. Instead the query runs in a
short-lived child process (`sqlChild.js`) that the parent `SIGKILL`s on
timeout — the server thread never blocks and the OS reclaims a runaway
query. `test-sqlAdapter.js` proves a billion-row query is killed in ~0.5s.

## Exploratory client

`client.js` (`node client.js`) runs the same sequence as the test but logs
everything instead of asserting — useful for seeing the raw shape of every
response (tool result, resource JSON, rendered prompt messages) while
you're still learning what each primitive returns.

## Files

- `server.js` — the server: two tools, one resource, one prompt.
- `notesStore.js` — file-backed persistence for the notes. Mirrors
  `../src/notes_store.py`.
- `fsFence.js` — the shared path fence (`resolveWithin`), used by both
  `notesStore.js` and `sqlAdapter.js`. Mirrors `../src/fs_fence.py`.
- `sqlAdapter.js` — the `run_sql_query` implementation: validation, path
  fence, child-process timeout, structured errors. Mirrors
  `../src/sql_adapter.py`.
- `sqlChild.js` — runs one query in an isolated process so it can be
  SIGKILLed on timeout.
- `client.js` — a programmatic MCP client that connects, calls everything,
  and logs the results. This is the shape a real host application takes —
  the Inspector is a generic tool for humans; this is what your own code
  would look like embedding the server.
- `test-connection.js` — the same client interactions as `client.js`, but
  with assertions and a proper exit code, so it can gate a build.
- `test-notesStore.js` — unit tests for `notesStore.js`: the path fence and
  the persistence round-trip.
- `test-sqlAdapter.js` — unit tests for `sqlAdapter.js`: validation, fence,
  timeout, and the "system unavailable" cases.
- `test-idempotency.js` — checks `add_note` dedups a retry (by key or by
  identical title+content).
- `package.json` / `package-lock.json` — dependencies (`node_modules/` is
  gitignored; run `npm install` after cloning).
