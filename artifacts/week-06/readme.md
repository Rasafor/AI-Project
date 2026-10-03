# mcp-server

**▶ Walkthrough recording:**
[`artifacts/week-06/data-pipeline-incident-investigation.mp4`](artifacts/week-06/data-pipeline-incident-investigation.mp4)
(click through — GitHub plays it on the file page)

The recording is the server handling one real task end to end — an agent
calls `run_sql_query` six times to trace a revenue drop back to a partial
`orders_load` run and confirm the data-quality root cause (null `amount`s +
duplicate orders). It was rendered frame-for-frame from an actual stdio run
against a 119k-row SQLite warehouse; every query, wait time, and result shown
is what really came back.

This is an MCP (Model Context Protocol) server. It started as an empty
shell (no tools, no resources, no prompts) to confirm the connection works,
and now implements a small "notes" example plus one real integration
(`run_sql_query`):

- **Tool** `add_note(title, content, idempotency_key?)` — saves a note, or
  returns the existing one if this add is a duplicate (retry-safe).
- **Resource** `notes://all` — exposes the current list of notes as JSON.
- **Prompt** `capture_note(raw_text)` — a reusable template that guides the
  model to turn unstructured text into a title + body and call `add_note`.
- **Tool** `run_sql_query(database, query, …)` — the adapter for the "SQL"
  data source named in the project plan; runs one read-only query against a
  SQLite file and returns the rows. See "The `run_sql_query` tool" below.

**Language: Python** (`src/`) is the primary, maintained version — the rest
of this repo has no other Node.js project, so Python is what's already
here.

A second copy of the *same design* — same `add_note` tool, `notes://all`
resource, `capture_note` prompt — also exists in **[`nodejs/`](nodejs/)**,
written against the official Node.js/TypeScript MCP SDK. It's not a
competing implementation to maintain in parallel; it's a side-by-side
learning reference for comparing how two different official SDKs express
the same tool/resource/prompt concepts. If you only care about running the
project, use `src/`. If you want to see the same server built a second way,
see `nodejs/README` below.

---

## Step 0 — one-time computer setup (do this before anything else)

To *test* this server, you use a tool called the **MCP Inspector**. It opens
in your web browser and lets you see the server running. The Inspector tool
itself is launched through a command called `npx`, which comes from
**Node.js** — a separate program from Python.

Check if you already have it: open a terminal and type:

```
node --version
```

- If you see a version number (like `v20.11.0`), you're set — skip to Step 1.
- If you see an error like "node is not recognized" or "command not found",
  you need to install Node.js first: go to https://nodejs.org, download the
  "LTS" version, run the installer accepting the defaults, then **close and
  reopen your terminal** and run `node --version` again to confirm.

You'll also need Python installed (this machine already has it — Python 3.10).

---

## Step 1 — one-time project setup

Open a terminal **in the `mcp-server` folder** (this folder — the one this
README is in), and run:

```
pip install "mcp[cli]"
```

This installs the MCP toolkit, including the `mcp` command you'll use to
start the server. You only need to do this once.

---

## Step 2 — start the server

This server uses the **stdio** transport: the client (here, the Inspector)
launches `src/server.py` as a child process and talks to it over that
process's input/output. There is no network port and no address — the server
is only reachable by a program on the same machine that starts it. This is a
deliberate choice for "everyone runs their own copy"; see
[`docs/ADR-0001-transport.md`](docs/ADR-0001-transport.md) for the reasoning
and for what would have to change to make it reachable over a network instead.

From the `mcp-server` folder, run:

```
mcp dev src/server.py --with "mcp[cli]"
```

(The `--with "mcp[cli]"` part matters — without it, the Inspector's "Connect"
button fails with a "failed to connect to uv" error. This is a quirk in the
`mcp` tool itself: the command it auto-generates to launch your server is
missing a piece it needs, and this flag adds that piece back in.)

### What you should see

A few lines will print in the terminal, ending with something like:

```
🚀 MCP Inspector is up and running at http://127.0.0.1:6274/...
```

(The exact port number and the long token text after it will differ every
time you run this — that's normal. The part that matters is the line saying
"MCP Inspector is up and running.")

A new tab should also open automatically in your web browser showing the
Inspector. If it doesn't open by itself, copy the full `http://127.0.0.1:...`
link from the terminal and paste it into your browser.

In the browser tab, click **Connect**. Once connected, the status should
turn green. You should now see one entry in each of the "Tools,"
"Resources," and "Prompts" tabs — `add_note`, `notes://all`, and
`capture_note`.

Try it: open the Tools tab, run `add_note` with a title and content, then
open the Resources tab and read `notes://all` — your new note should be in
the returned JSON, proving the tool and resource share the same store.
Empty title should be rejected with a validation error, not silently
accepted. Stop the server (`Ctrl+C`), start it again, and read `notes://all`
once more — the note is still there, because the store is now a file on disk
(see "Where notes are stored" below).

To stop the server, go back to the terminal and press `Ctrl+C`.

---

## Where notes are stored

Notes persist to `mcp-server/data/notes.json`, created on first run. The
`data/` folder is runtime state, not source — it is git-ignored.

All file access for the store goes through one guard, `resolve_within()` in
`src/notes_store.py`, which refuses any path that resolves outside `data/`
(via `..`, an absolute path, or a symlink) by raising an error naming the
offending path — it never silently returns nothing. Today nothing passes a
caller-supplied path to the store (the filename is hardcoded), so the guard
is a safety net; it is also the check any future path-taking tool must call.
`src/test_notes_store.py` exercises it directly with traversal payloads.

Set `MCP_NOTES_DATA_ROOT` to point the store somewhere else (the automated
tests use this to run against a temp directory instead of your real notes).

---

## The `run_sql_query` tool

`.colaberry/plan.json` names one external system: **SQL** (REQ-008, "connect
to data sources for log and SQL analysis"; STORY-003, "analyze SQL queries").
`run_sql_query` is the adapter for it. Implementation: `src/sql_adapter.py`;
the MCP wrapper is in `src/server.py`.

**Backend:** SQLite, via Python's standard-library `sqlite3` — no extra
dependencies to install. The "system" is a database file under the SQL data
root (`MCP_SQL_DATA_ROOT`, default `mcp-server/data/`). Pointing it at a real
warehouse later (Postgres, Snowflake, …) is a driver swap *inside*
`sql_adapter.py`; the tool's inputs and behavior do not change.

**Inputs (all declared, all validated before anything else runs):**

| Argument | Rule |
|---|---|
| `database` | non-empty; path to a `.db`/`.sqlite` file that resolves **inside** the SQL data root (same fence as the notes store). `..`/absolute escapes are rejected. |
| `query` | non-empty, ≤ 20 000 chars, **one** statement, read-only. Leading `INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/ATTACH/…` is rejected with a clear message; the connection is also opened read-only and an authorizer blocks `ATTACH`/`DETACH`, so a write that slips past the keyword check still fails. |
| `params` | optional list (≤ 100) of string/number/boolean/null, bound to `?` placeholders — use these instead of formatting values into the SQL. |
| `timeout_seconds` | optional, `0 < t ≤ 30`, default `5`. A watchdog interrupts the query if it runs longer. |
| `max_rows` | optional, `1..1000`, default `100`. Extra rows are dropped and `truncated: true` is set. |

**Success** returns JSON: `{ database, columns, rows, row_count, truncated, elapsed_ms }`.

**When the SQL system is down / unreachable**, the tool returns an MCP tool
error (`is_error: true`) with a tagged message — never a crash, never a hang:

| Situation | What you get back |
|---|---|
| database file missing | `[Unavailable] database file not found: <path> … The SQL system is unreachable.` |
| file exists but is corrupt / not SQLite | `[Unavailable] the database at <path> could not be opened (file is not a database) …` |
| database locked by another process | `[Unavailable] the database is locked by another process; try again shortly.` |
| query runs longer than `timeout_seconds` | `[Timeout] the query was cancelled after exceeding the <n>s timeout …` |
| write / DDL / multiple statements / bad argument | `[ValidationError] …` (nothing touched the database) |
| valid read-only query that references a missing table, etc. | `[QueryError] the query could not run: no such table: … .` |

The server logs these as `INFO … Tool 'run_sql_query' failed`, not as an
error with a stack trace.

`src/test_sql_adapter.py` covers every row above:

```
python src/test_sql_adapter.py
```

---

## Automated connection test (no browser needed)

`src/test_connection.py` spawns the server the same way the Inspector does
(over stdio) and exercises every primitive with assertions: discovery, the
tool's happy path, the tool's rejection of an empty title, the resource
reflecting the tool's write, and the prompt's argument interpolation. Run
it from this folder:

```
python src/test_connection.py
```

`src/test_notes_store.py` covers the storage layer separately: the path
fence (feeding it `../../etc/hosts` and absolute paths and asserting each is
refused), the save/load round-trip, and that a corrupt store file raises
instead of being read as empty.

```
python src/test_notes_store.py
```

`src/test_sql_adapter.py` (above) covers the SQL adapter — validation, the
path fence, the timeout, and every "system unavailable" case — against
throwaway SQLite files.

```
python src/test_sql_adapter.py
```

`src/test_concurrency.py` fires 40 `add_note` calls at once, then checks
every note survives — in `notes://all` and, after a full restart, on disk.
It fails if the write lock in `server.py` is removed.

```
python src/test_concurrency.py
```

`src/test_idempotency.py` checks that a retried `add_note` — same
`idempotency_key`, or identical `title`+`content` with no key — returns the
existing note instead of creating a duplicate, and that a keyed note stays
deduped across a restart.

```
python src/test_idempotency.py
```

All five print `PASS: ...` and exit `0` on success, or `FAIL: ...` with a
non-zero exit on any regression — useful for catching a broken server
without opening a browser each time. None of them touch your real
`data/`; they run against temp directories.

---

## What this server assumes

Everything the server carries between calls, what a concurrent second call
does to it, and what a restart mid-call does to it.

### 1. `notes` — the in-memory list (`server.py`) · **had the silent-wrong-answer risk; now fixed**

`add_note` appends to it and `get_all_notes` reads it. It is loaded from
`data/notes.json` once at startup and never re-read.

- **Two calls at once:** the SDK runs synchronous tool functions on a thread
  pool, so two `add_note` calls genuinely overlap. Each one rewrites the
  *whole* notes file. Before the fix, two overlapping writes raced: one call
  would persist a snapshot taken before the other's note was added, so
  `data/notes.json` came out **missing a note** while the running process
  still looked correct — a wrong answer you only discover after a restart.
  **Fix:** `server.py` now guards the persist-then-update-memory step with a
  `threading.Lock`, and writes the file *before* touching the in-memory list.
  Concurrent `add_note` calls take turns; none is lost. `get_all_notes` takes
  the same lock, so a read never sees the list mid-change.
  (`_atomic_write` also now uses a per-write-unique temp filename.)
- **Restart mid-call:** the write is atomic (`os.replace`), so `notes.json`
  is always either the whole old list or the whole new one — never half a
  file. A note appended in memory but not yet persisted is lost on restart;
  because the file is now written first, a call that returned success is
  durable.

### 2. `data/notes.json` — the file

Rewritten in full on every `add_note` (not appended to line by line).

- **Two calls at once:** serialised by the lock above (§1).
- **Restart mid-call:** atomic replace — no torn file. If the process dies
  before the replace, the previous good file is untouched; a stray
  `notes.json.tmp-*` may be left behind and is ignored on next start.

### 3. `add_note` is idempotent (retry-safe)

If a call times out or the server dies after persisting but before the reply
is delivered, a client that **retries** does not create a second note:

- pass a stable **`idempotency_key`** — the same key returns the note already
  stored under it (first content wins; the key survives restarts because it is
  stored on the note);
- pass **no key** — an identical `title` + `content` returns the existing
  note.

Either way the response says `already stored with id … (no duplicate
created)` instead of `added with id …`, and the id is the same. The
`(title, content)` fallback means you cannot hold two byte-identical notes
without giving them distinct `idempotency_key`s — a deliberate trade for
making the common retry safe by default.

The dedup check runs inside the same lock as the write (§1), so two
simultaneous identical calls still produce one note.

### 4. `run_sql_query` — no connection or cache is kept

Each call opens its own read-only SQLite connection and closes it in a
`finally`. There is no connection pool, no prepared-statement cache, no
result cache.

- **Two calls at once:** fully independent — separate connections, separate
  timeout watchdogs, no shared variables. SQLite allows many concurrent
  readers, so this is safe.
- **Restart mid-call:** the query is abandoned and the connection dropped.
  The database is opened read-only and never written, so there is nothing to
  roll back and nothing to corrupt. The caller sees a transport error.

### 5. The target SQLite databases are external state

The server reads the `.db` files under the SQL data root; it does not own
them, cache them, or keep them open. Their schema and contents can change
between calls, and each call sees whatever is on disk at that moment. If
another process holds a write lock, the call returns
`[Unavailable] … locked …`, not a wrong answer.

### 6. `DATA_ROOT` / `SQL_DATA_ROOT` are resolved once, at startup

From `MCP_NOTES_DATA_ROOT` / `MCP_SQL_DATA_ROOT` (or the default next to the
code). Changing those env vars has no effect until the server is restarted.

### 7. One client, one process

The stdio transport means one client launches one server (see
[ADR-0001](docs/ADR-0001-transport.md)). Nothing coordinates *two* server
processes pointed at the same `data/` directory — there, the last writer
wins and updates are lost. The lock in §1 protects against concurrent
*threads* in one process, which is the only concurrency this deployment
actually has.

---

## Folders

- `src/` — the server code (`server.py`), the fenced file store
  (`notes_store.py`), the shared path fence (`fs_fence.py`), the SQL adapter
  (`sql_adapter.py`), and their tests (`test_connection.py`,
  `test_notes_store.py`, `test_sql_adapter.py`, `test_concurrency.py`,
  `test_idempotency.py`). This is the primary, maintained version.
- `data/` — the persisted notes store (`notes.json`), created at runtime.
  Git-ignored; safe to delete (it re-seeds on next start).
- `nodejs/` — the same server rebuilt with the Node.js/TypeScript MCP SDK,
  kept as a side-by-side learning reference. See
  [`nodejs/README.md`](nodejs/README.md) for its own setup and test steps.
- `artifacts/week-05/` — empty for now. This is where your Inspector
  recording/screenshots go later. (Note: an empty folder doesn't get saved
  by git on its own — once you put a file in here, it'll show up normally.)
