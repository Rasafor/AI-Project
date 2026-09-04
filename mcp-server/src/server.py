import functools
import json
import uuid
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import anyio

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import EmptyResult, SamplingMessage, SetLevelRequestParams, TextContent
from pydantic import Field

import obs
import quality_review
import roots_fence
import sql_adapter
import token_adapter
import transport
from notes_store import load_notes, notes_path, save_notes

# Which transport + state model this process runs, resolved once from the
# environment (docs/ADR-0001-transport.md). Drives both how the server is served
# (see __main__) and whether the notes tools may use an in-process cache.
_CFG = transport.resolve()

# This name is what any connecting client (like the MCP Inspector) will show
# for this server.
mcp = MCPServer("ai-project-mcp-server")


# --- declare the MCP `logging` capability ---------------------------------
# MCPServer does not advertise `logging` unless a `logging/setLevel` handler is
# registered. Registering one flips ServerCapabilities.logging on, which is how
# a client learns this server emits structured log notifications and (on the
# modern protocol) knows to opt in per request.
#
# WITHOUT this capability the SDK SILENTLY DROPS every log notification: `ctx.log`
# returns without sending, no error is raised, and `obs.emit` looks like it
# worked. Nothing downstream sees the line. So this registration is load-bearing,
# not decoration.
#
# We keep no server-side log-level state — per-request level filtering is the
# SDK's job. `add_request_handler` is the documented way to add a spec method the
# MCPServer wrapper does not surface directly.
async def _handle_set_logging_level(_request_context, _params: SetLevelRequestParams) -> EmptyResult:
    return EmptyResult()


with warnings.catch_warnings():
    warnings.simplefilter("ignore")  # logging capability is deprecated (SEP-2577); still the channel
    mcp._lowlevel_server.add_request_handler(
        "logging/setLevel", SetLevelRequestParams, _handle_set_logging_level
    )

# Notes are persisted to mcp-server/data/notes.json by notes_store, which fences
# every file access to that one directory (see notes_store.resolve_within and
# ADR-0001 Consequences).
#
# STATE MODEL (ADR-0001):
#   * STDIO / stateful HTTP — one authoritative process. `notes` below is the
#     in-process working copy, loaded once at startup; add_note mutates it and
#     writes through to the file. Safe because it is not shared across processes.
#   * Stateless HTTP (_CFG.notes_read_through) — there is NO single authoritative
#     process. The in-process cache would go stale the instant another replica
#     writes, so it is not used: every request reads data/notes.json fresh (see
#     _read_notes) and add_note never touches `notes`. This is what lets any
#     replica serve any request.
#
# `_notes_lock` (anyio.Lock) still serialises add_note within one process so two
# concurrent calls cannot interleave their whole-file rewrites. Across replicas
# it does nothing — multi-writer safety needs ADR-0001 migration step 5 (a real
# datastore); until then, run stateless HTTP as a single replica or accept
# last-writer-wins on the notes file.
_notes_lock = anyio.Lock()
notes: list[dict] = [] if _CFG.notes_read_through else load_notes()


async def _read_notes() -> list[dict]:
    """The authoritative notes list for the current request. A fresh file read
    in stateless HTTP mode (no shared cache); the in-process list otherwise."""
    if _CFG.notes_read_through:
        return await anyio.to_thread.run_sync(load_notes)
    return notes


# --- shared: progress notifications -----------------------------------------
# Used by every tool whose work can run past a couple of seconds (run_sql_query,
# assess_table_quality). One helper, so the "did the client even ask?" check and
# the send live in exactly one place.
def _progress_token(ctx: Context):
    """The progress token the client attached to this request, or None if it
    sent none. MCP clients that want progress put an opaque `progressToken` in
    the request's `_meta`; clients that don't want it send nothing."""
    try:
        meta = ctx.request_context.meta
    except Exception:
        return None
    return meta.get("progress_token") if meta else None


async def _require_contained(ctx: Context, correlation_id: str, requested) -> Path:
    """Route one filesystem path through the single roots containment check
    (roots_fence.contained_path) and return the verified real path.

    On denial, roots_fence has already logged the warning (stable event name +
    requested path). We then raise ToolError — which in this SDK is NOT an
    unhandled throw: it is caught one frame up and returned to the client as
    CallToolResult(is_error=True) with this message, logged at info, never a
    traceback. A bare exception escaping instead would be logged as a crash.
    Every filesystem-touching tool calls this; none does its own path check.
    """
    decision = await roots_fence.contained_path(ctx, requested, correlation_id=correlation_id)
    if not decision.allowed:
        raise ToolError(
            f"[AccessDenied] roots containment ({decision.reason}): "
            f"{decision.requested_path!r} is not at or under any root the client declared"
        )
    return decision.path


async def _report_progress(
    ctx: Context, progress: float, total: float | None, message: str
) -> None:
    """Emit one progress notification for the in-flight tool call.

    - If the client sent no progress token, this returns without sending
      anything and the tool behaves exactly as it did before (req 1).
    - `total` is the real number of steps when that is known; pass `total=None`
      when it genuinely is not (e.g. a single SQL statement whose running time
      is not knowable up front). With no total the count still advances and the
      message says the total is unknown — no invented percentage (req 2).
    - Never raises: a progress hiccup must not change what the tool returns
      (req 3).
    """
    if _progress_token(ctx) is None:
        return
    try:
        await ctx.report_progress(progress, total, message)
    except Exception:  # pragma: no cover - best-effort notification
        pass


# --- TOOL: add_note ---------------------------------------------------------
# Tools are actions the MODEL decides to invoke. The type annotations below
# are the contract the model reads to know what arguments are valid — the
# SDK turns them into a JSON Schema automatically. Field(min_length=...)
# enforces that contract at the boundary, the same way a Zod schema does on
# the Node SDK: reject malformed input before it reaches business logic.
def _existing_note(
    current: list[dict], title: str, content: str, idempotency_key: str | None
) -> dict | None:
    """Return a note in `current` this call would duplicate, or None. Caller
    holds _notes_lock.

    With an idempotency_key: match that key (the key identifies the operation, so
    the stored note wins even if title/content now differ). Without one: match an
    exact title+content pair, so a plain retry does not create a second note.
    """
    for n in current:
        if idempotency_key is not None:
            if n.get("idempotency_key") == idempotency_key:
                return n
        elif n["title"] == title and n["content"] == content:
            return n
    return None


@mcp.tool()
async def add_note(
    title: Annotated[str, Field(min_length=1, max_length=200, description="Short title for the note")],
    content: Annotated[str, Field(min_length=1, max_length=5000, description="Body text of the note")],
    idempotency_key: Annotated[
        str | None,
        Field(
            default=None,
            max_length=200,
            description=(
                "Optional stable id for this add. Passing the same key again returns "
                "the note already stored under it instead of creating a duplicate — "
                "use it to make retries safe."
            ),
        ),
    ] = None,
    *,
    ctx: Context,
) -> str:
    """Add a note to the store, or return the existing one if this add is a duplicate.

    A duplicate is: the same `idempotency_key` seen before, or (with no key) an
    identical title and content. Returns the note's id either way.
    """
    cid = obs.new_correlation_id()
    # Only shape/length of the record — never its title or body text (req 5).
    await obs.emit(
        ctx,
        "info",
        obs.EVENT_TOOL_INVOKED,
        cid,
        tool="add_note",
        title_len=len(title),
        content_len=len(content),
        has_idempotency_key=idempotency_key is not None,
    )
    # The notes filename is hardcoded, but the roots gate must still see every
    # path the server writes: if the client's declared roots don't cover the
    # store, we don't get to write it.
    await _require_contained(ctx, cid, notes_path())

    async with _notes_lock:
        # In stateless HTTP mode `current` is a fresh read of data/notes.json;
        # otherwise it is the in-process list. Dedup and the write both work off
        # this one snapshot so a retry never creates a second note.
        current = await _read_notes()
        existing = _existing_note(current, title, content, idempotency_key)
        if existing is not None:
            await obs.emit(
                ctx, "info", obs.EVENT_TOOL_COMPLETED, cid,
                tool="add_note", note_id=existing["id"], deduplicated=True,
            )
            return (
                f'Note "{existing["title"]}" already stored with id {existing["id"]} '
                f"(no duplicate created)."
            )
        note = {
            "id": str(uuid.uuid4()),
            "title": title,
            "content": content,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if idempotency_key is not None:
            note["idempotency_key"] = idempotency_key
        # Persist first, then update the in-process copy (if we keep one). If
        # save_notes raises, we return an error without ever having reported the
        # note as stored, and the cache still matches disk. The lock keeps two
        # concurrent calls on this process from interleaving their whole-file
        # rewrites.
        async with obs.external_call(ctx, cid, target="notes_file", op="save"):
            await anyio.to_thread.run_sync(save_notes, current + [note])
        if not _CFG.notes_read_through:
            notes.append(note)
    await obs.emit(
        ctx, "info", obs.EVENT_TOOL_COMPLETED, cid,
        tool="add_note", note_id=note["id"], deduplicated=False,
    )
    return f'Note "{title}" added with id {note["id"]}.'


# --- TOOL: run_sql_query --------------------------------------------------
# The adapter for the "SQL" system named in .colaberry/plan.json (REQ-008,
# STORY-003). The implementation lives in sql_adapter.py; this wrapper is just
# the MCP contract. Every argument is declared and bounded here (the SDK turns
# these annotations into JSON Schema), AND re-validated inside the adapter, so a
# direct caller gets the same guarantees. sql_adapter raises SqlAdapterError for
# any handled failure — the SDK surfaces it as is_error=True with the message,
# never a traceback.
#
# A query may run for up to timeout_seconds (30s ceiling), so this tool reports
# progress. The work is a single opaque SQL statement: there is no honest step
# count and no way to know the duration or row count in advance, so progress is
# sent WITHOUT a total (a rising counter, and the message says the total is
# unknown) rather than faking a percentage. The blocking call runs in a worker
# thread so the event loop — and the progress notifications — are not stalled,
# matching how the SDK ran this tool when it was synchronous.
@mcp.tool()
async def run_sql_query(
    database: Annotated[
        str,
        Field(
            min_length=1,
            max_length=500,
            description=(
                "Path to a SQLite database file, relative to the SQL data root "
                "(env MCP_SQL_DATA_ROOT, default mcp-server/data/). Paths that "
                "resolve outside that directory are rejected."
            ),
        ),
    ],
    query: Annotated[
        str,
        Field(
            min_length=1,
            max_length=20_000,
            description=(
                "One read-only SQL statement (SELECT / WITH / EXPLAIN / PRAGMA). "
                "Write and DDL statements, multiple statements, and ATTACH are "
                "rejected."
            ),
        ),
    ],
    params: Annotated[
        list[str | int | float | bool | None] | None,
        Field(
            default=None,
            max_length=100,
            description=(
                "Optional positional values bound to '?' placeholders in the "
                "query. Use these instead of formatting values into the SQL."
            ),
        ),
    ] = None,
    timeout_seconds: Annotated[
        float,
        Field(default=5.0, gt=0, le=30, description="Abort the query if it runs longer than this."),
    ] = 5.0,
    max_rows: Annotated[
        int,
        Field(
            default=100,
            ge=1,
            le=1000,
            description="Max rows returned; extras are dropped and 'truncated' is set true.",
        ),
    ] = 100,
    *,
    ctx: Context,
) -> str:
    """Run a read-only SQL query against a SQLite data source; return rows as JSON.

    Validates every argument, fences the database path, enforces the timeout,
    and returns a structured error (not a crash) when the database is missing,
    corrupt, locked, or the query is invalid.
    """
    cid = obs.new_correlation_id()
    # `database` is a fenced relative filename (no host, no credentials), safe to
    # log and needed to trace which file was hit. The query text and bound
    # params are NOT logged — they can carry data values (req 5).
    await obs.emit(
        ctx,
        "info",
        obs.EVENT_TOOL_INVOKED,
        cid,
        tool="run_sql_query",
        database=database,
        query_chars=len(query),
        param_count=len(params) if params else 0,
        timeout_seconds=timeout_seconds,
        max_rows=max_rows,
    )
    # Roots gate: the candidate DB path (SQL data root + caller's `database`)
    # must resolve inside a client-declared root. contained_path collapses `..`
    # and symlinks before comparing — a str-prefix check on `database` would not.
    await _require_contained(ctx, cid, sql_adapter.SQL_DATA_ROOT / database)

    await _report_progress(
        ctx, 1, None, "validating the query and opening the database (read-only)"
    )
    await _report_progress(
        ctx,
        2,
        None,
        f"running the query - total unknown, this can take up to {timeout_seconds:g}s",
    )
    try:
        # external_call emits external_call.started / external_call.finished
        # (with duration_ms), or access.denied / error.caught (with a stable
        # error_class + duration_ms) if the adapter raises.
        async with obs.external_call(ctx, cid, target="sqlite", op="query") as call:
            result = await anyio.to_thread.run_sync(
                functools.partial(
                    sql_adapter.run_sql_query,
                    database=database,
                    query=query,
                    params=params,
                    timeout_seconds=timeout_seconds,
                    max_rows=max_rows,
                )
            )
            call.note(row_count=result["row_count"], truncated=result["truncated"])
    except sql_adapter.SqlAdapterError as exc:
        # A failure the adapter handled on purpose (bad input, path escape,
        # database unavailable, timeout, broken query); already logged by
        # external_call. Re-raise as ToolError so the SDK returns it to the
        # caller as is_error=True, not as an unexpected crash.
        raise ToolError(str(exc)) from exc
    await _report_progress(
        ctx,
        3,
        None,
        f"query returned {result['row_count']} row(s)"
        + (" (truncated to max_rows)" if result["truncated"] else ""),
    )
    await obs.emit(
        ctx,
        "info",
        obs.EVENT_TOOL_COMPLETED,
        cid,
        tool="run_sql_query",
        row_count=result["row_count"],
        truncated=result["truncated"],
    )
    return json.dumps(result, indent=2, default=str)


# --- TOOL: assess_table_quality -----------------------------------------------
# A judgement tool, not a lookup: it decides whether a table is safe to publish.
# The split of work is deliberate —
#   * the SERVER gathers the evidence itself (quality_review.gather_table_stats
#     runs plain read-only SELECTs through sql_adapter; no model is involved);
#   * the CLIENT'S model makes the call, reached over MCP *sampling*
#     (sampling/createMessage). This server holds no API key and names no model —
#     both belong to the client.
# If the client cannot sample (capability not advertised) or the request fails
# (refused, no back-channel, transport error, unparseable reply), the tool still
# returns a full rule-based verdict and logs a warning. It never crashes and
# never returns an empty answer.
def _client_supports_sampling(ctx: Context) -> bool:
    caps = getattr(ctx, "client_capabilities", None)
    if caps is None:
        caps = getattr(getattr(ctx, "session", None), "client_capabilities", None)
    return caps is not None and getattr(caps, "sampling", None) is not None


@mcp.tool()
async def assess_table_quality(
    database: Annotated[
        str,
        Field(
            min_length=1,
            max_length=500,
            description=(
                "Path to a SQLite database file, relative to the SQL data root "
                "(env MCP_SQL_DATA_ROOT, default mcp-server/data/). Same fence as "
                "run_sql_query — paths that resolve outside that directory are rejected."
            ),
        ),
    ],
    table: Annotated[
        str,
        Field(
            min_length=1,
            max_length=200,
            description=(
                "Name of the table to assess. Must be a plain SQLite identifier "
                "(letters, digits, underscore)."
            ),
        ),
    ],
    ctx: Context,
) -> str:
    """Judge whether a table is safe to publish: PASS, WARN or FAIL, with reasons.

    The server first gathers real statistics itself (row count, per-column null
    rate, duplicate counts on key-like columns) with read-only queries — no model
    call. It then asks the *client's* model to weigh that evidence via MCP
    sampling. If the client does not support sampling or the request fails, a
    rule-based verdict built from the same statistics is returned instead, and a
    warning is logged.

    Progress: five real steps — columns, null scan, duplicate scan, model review,
    verdict — reported as N/5 when the client asked for progress.

    Logging: one correlation id for the whole call; a tool.invoked line, an
    external_call.started/finished pair around each SQLite query and around the
    model sampling request, an error.caught / access.denied line if any of those
    fail, and a tool.completed line carrying the verdict.
    """
    cid = obs.new_correlation_id()
    await obs.emit(
        ctx,
        "info",
        obs.EVENT_TOOL_INVOKED,
        cid,
        tool="assess_table_quality",
        database=database,
        table=table,
    )
    steps = 5

    # Roots gate: same candidate DB path as run_sql_query. Checked once here,
    # before any of the three SQLite reads below.
    await _require_contained(ctx, cid, sql_adapter.SQL_DATA_ROOT / database)

    # 1. Gather the evidence ourselves, one measurement at a time. No model here.
    await _report_progress(ctx, 0, steps, "inspecting table columns")
    try:
        async with obs.external_call(ctx, cid, target="sqlite", op="fetch_columns") as call:
            columns = quality_review.fetch_columns(database, table)
            call.note(column_count=len(columns))
        names = [c["name"] for c in columns]

        await _report_progress(
            ctx, 1, steps, f"{len(names)} columns found; scanning for null values"
        )
        async with obs.external_call(ctx, cid, target="sqlite", op="null_counts"):
            total_rows, non_null = quality_review.null_counts(database, table, names)

        key_names = quality_review.key_column_names(names)
        await _report_progress(
            ctx,
            2,
            steps,
            f"checking {len(key_names)} key-like column(s) for duplicate values"
            if key_names
            else "no key-like columns to check for duplicates",
        )
        dup_counts: dict = {}
        if key_names and total_rows:
            async with obs.external_call(
                ctx, cid, target="sqlite", op="duplicate_counts", key_column_count=len(key_names)
            ):
                dup_counts = quality_review.duplicate_counts(database, table, key_names)
    except quality_review.QualityInputError as exc:
        raise ToolError(f"[ValidationError] {exc}") from exc
    except sql_adapter.SqlAdapterError as exc:
        raise ToolError(str(exc)) from exc

    stats = quality_review.assemble_stats(
        database, table, columns, total_rows, non_null, dup_counts
    )
    heuristic = quality_review.heuristic_verdict(stats)
    system_prompt, user_text = quality_review.build_sampling_prompt(stats, heuristic)

    async def _finish(result: str) -> str:
        """Emit the final progress tick + tool.completed line, reading the
        verdict and assessed_by straight from the body so the log matches what
        the caller receives."""
        try:
            body = json.loads(result)
            verdict, assessed_by = body["verdict"], body["assessed_by"]
        except (ValueError, KeyError):  # a log line must never break the result
            verdict, assessed_by = "unknown", "unknown"
        await _report_progress(ctx, 5, steps, f"assessment complete — verdict {verdict}")
        await obs.emit(
            ctx,
            "info",
            obs.EVENT_TOOL_COMPLETED,
            cid,
            tool="assess_table_quality",
            verdict=verdict,
            assessed_by=assessed_by,
        )
        return result

    # 2a. No sampling capability on the client -> degrade cleanly, log, return.
    if not _client_supports_sampling(ctx):
        await obs.emit(
            ctx,
            "warning",
            obs.EVENT_SAMPLING_UNSUPPORTED,
            cid,
            tool="assess_table_quality",
            reason="client did not negotiate the sampling capability",
        )
        await _report_progress(
            ctx, 3, steps, "client cannot run a model; scoring with built-in rules"
        )
        await _report_progress(ctx, 4, steps, "finalizing the verdict")
        return await _finish(
            quality_review.render(
                stats, heuristic, assessed_by="rule-based (client does not support sampling)"
            )
        )

    # 2b. Ask the client's model to make the judgement.
    await _report_progress(
        ctx, 3, steps, "asking the client model to review the statistics"
    )
    try:
        async with obs.external_call(
            ctx, cid, target="client_model", op="sampling", max_tokens=512
        ) as call:
            with warnings.catch_warnings():
                # MCP sampling is deprecated (SEP-2577) but is still the only way
                # to reach the client's model; silence the per-call warning.
                warnings.simplefilter("ignore")
                reply = await ctx.session.create_message(
                    messages=[
                        SamplingMessage(role="user", content=TextContent(type="text", text=user_text))
                    ],
                    system_prompt=system_prompt,
                    max_tokens=512,
                    temperature=0.0,
                )
            call.note(
                model=getattr(reply, "model", None),
                stop_reason=getattr(reply, "stop_reason", None),
            )
    except Exception:  # refusal / no back-channel / transport — already logged by external_call
        await _report_progress(
            ctx, 4, steps, "model unavailable; scoring with built-in rules"
        )
        result = quality_review.render(
            stats,
            heuristic,
            assessed_by="rule-based (client refused or could not complete sampling)",
            sampling_ms=call.duration_ms,
        )
        return await _finish(result)

    # 3. Fold the model's judgement in; fall back to the rule-based verdict if
    #    the reply does not parse. Never returns empty.
    await _report_progress(ctx, 4, steps, "interpreting the model's response")
    result = quality_review.render_from_model(
        stats, heuristic, reply, sampling_ms=call.duration_ms
    )
    return await _finish(result)


# --- TOOL: count_incident_tokens -------------------------------------------
# Reads one external HTTP system — the Anthropic token-count endpoint — to answer
# "how many input tokens would this incident write-up cost for <model>?", before
# anything is actually sent to a model. Implementation + the pooled client are in
# token_adapter.py; this wrapper is the MCP contract.
#
#   * `text` / `model` are model-influenced. token_adapter puts them in the JSON
#     body (bound values), never in the URL path or a query.
#   * Credentials (ANTHROPIC_API_KEY) and the host (ANTHROPIC_BASE_URL) come from
#     the environment only; they never appear here, in a log line, or in an error
#     message returned to the caller.
#   * The call has an explicit timeout; on expiry token_adapter raises
#     TokenAdapterError("Timeout", …). external_call logs that as
#     error_class="TimeoutError" (obs.classify), and we return it as an MCP
#     error RESULT (raise ToolError -> CallToolResult(is_error=True)), not a
#     raised crash — one bad call cannot kill the connection.
#   * A network call can exceed ~2s, so progress is reported (no total — the
#     duration is not knowable up front) and the call boundaries are logged with
#     the correlation id (tool.invoked / external_call.* / tool.completed).
@mcp.tool()
async def count_incident_tokens(
    text: Annotated[
        str,
        Field(
            min_length=1,
            max_length=200_000,
            description=(
                "The incident write-up or log excerpt whose input-token cost you want, "
                "before sending it to a model."
            ),
        ),
    ],
    model: Annotated[
        str,
        Field(
            default="claude-sonnet-4-5",
            max_length=100,
            description="Model id the count is for (token counts are model-family specific).",
        ),
    ] = "claude-sonnet-4-5",
    timeout_seconds: Annotated[
        float,
        Field(default=10.0, gt=0, le=30, description="Abort the call if it runs longer than this."),
    ] = 10.0,
    *,
    ctx: Context,
) -> str:
    """Count how many input tokens `text` would cost for `model`, via the
    Anthropic token-count API. Credentials are read from the environment. On any
    failure (timeout, service down, bad input) a tagged error result is returned
    — never a crash, never a leaked credential or host."""
    cid = obs.new_correlation_id()
    await obs.emit(
        ctx,
        "info",
        obs.EVENT_TOOL_INVOKED,
        cid,
        tool="count_incident_tokens",
        text_chars=len(text),  # length only — never the incident text itself
        model=model,
        timeout_seconds=timeout_seconds,
    )
    await _report_progress(
        ctx, 1, None, f"counting tokens via the Anthropic API - up to {timeout_seconds:g}s"
    )
    try:
        async with obs.external_call(ctx, cid, target="anthropic_api", op="count_tokens") as call:
            input_tokens = await anyio.to_thread.run_sync(
                functools.partial(
                    token_adapter.count_tokens, text, model=model, timeout_s=timeout_seconds
                )
            )
            call.note(input_tokens=input_tokens)
    except token_adapter.TokenAdapterError as exc:
        # external_call already logged error.caught with a stable error_class
        # (Timeout -> "TimeoutError"). Surface the MCP error result.
        raise ToolError(str(exc)) from exc

    await _report_progress(ctx, 2, None, f"counted {input_tokens} input tokens")
    await obs.emit(
        ctx,
        "info",
        obs.EVENT_TOOL_COMPLETED,
        cid,
        tool="count_incident_tokens",
        input_tokens=input_tokens,
    )
    return json.dumps(
        {"model": model, "input_tokens": input_tokens, "text_chars": len(text)}, indent=2
    )


# --- RESOURCE: notes://all --------------------------------------------------
# Resources are DATA the host app can attach to context (e.g. a user picks
# it, or the app auto-attaches it). The model doesn't "call" this the way it
# calls a tool — it's exposed as addressable content behind a URI.
@mcp.resource(
    "notes://all",
    name="all-notes",
    description="JSON list of every note currently in the store",
    mime_type="application/json",
)
async def get_all_notes() -> str:
    # async only so it can share add_note's anyio.Lock; a read never sees the
    # list mid-mutation. No Context here — the SDK does not inject Context into
    # a static (no-template) resource, so this handler cannot emit MCP log
    # notifications. Structured logging lives on the tool invocations.
    #
    # _read_notes() returns a fresh file read in stateless HTTP mode, so a client
    # that added a note through one replica sees it here even if this read is
    # served by a different replica.
    async with _notes_lock:
        return json.dumps(await _read_notes(), indent=2)


# --- PROMPT: capture_note ---------------------------------------------------
# Prompts are USER-controlled workflow templates: they appear in the client
# UI (e.g. as a slash command) and are invoked explicitly by the person, not
# silently chosen by the model. This one packages the "correct" way to use
# add_note so the user doesn't have to know the tool's argument shape.
@mcp.prompt()
async def capture_note(
    raw_text: Annotated[str, Field(min_length=1, description="Unstructured text to turn into a title + note body")],
    ctx: Context,
) -> list[dict]:
    """Turn a raw block of text into a structured note and save it with add_note."""
    cid = obs.new_correlation_id()
    # Length only — the raw text itself is never logged (req 5).
    await obs.emit(ctx, "info", "prompt.get", cid, prompt="capture_note", raw_text_len=len(raw_text))
    messages = [
        {
            "role": "user",
            "content": (
                "Read the text below. Derive a concise title (max 10 words) "
                "and a cleaned-up body (fix obvious typos, keep the meaning "
                "intact). Then call the add_note tool with that title and "
                f'content.\n\nText:\n"""\n{raw_text}\n"""'
            ),
        }
    ]
    await obs.emit(ctx, "info", "prompt.completed", cid, prompt="capture_note", message_count=len(messages))
    return messages


if __name__ == "__main__":
    # Transport + state model come from the environment, resolved into _CFG
    # above; the default is STDIO (docs/ADR-0001-transport.md "Decision").
    # transport.run() logs which transport/state model this process is running
    # before handing off to the SDK, and carries the single-user comment for the
    # STDIO path and the stateless-failure comment for the HTTP path.
    transport.run(mcp, _CFG)
