"""
Connection smoke test for server.py.

Spawns the server as a subprocess over stdio (the same transport the MCP
Inspector and Claude Desktop/Code use), then exercises every primitive the
server registers: discovery, the tool's happy path, the tool's rejection of
invalid input, the resource, and the prompt. Exits 0 on success, 1 (with a
message) on any failure — no test framework required, so it can gate a
build the same way `tsc --noEmit` gates a TypeScript change elsewhere in
this repo.

The spawned server is pointed at throwaway notes and SQL directories via
MCP_NOTES_DATA_ROOT / MCP_SQL_DATA_ROOT, so this test never reads or writes the
real data/ directory.

Run from the mcp-server/ folder:
    python src/test_connection.py
"""

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CreateMessageResult, ListRootsResult, Root, TextContent


def _roots_cb(*dirs):
    """A client list_roots_callback that declares `dirs` as file:// roots."""
    roots = [Root(uri=Path(d).resolve().as_uri()) for d in dirs]

    async def cb(context) -> ListRootsResult:
        return ListRootsResult(roots=roots)

    return cb


async def exercise(session: ClientSession) -> None:
    # Handshake
    await session.initialize()

    # Discovery: fail loudly if a primitive silently disappears (e.g. a typo
    # in a decorator's uri/name, or an exception during import that got
    # swallowed).
    tools = (await session.list_tools()).tools
    assert any(t.name == "add_note" for t in tools), "add_note tool not registered"
    assert any(t.name == "run_sql_query" for t in tools), "run_sql_query tool not registered"
    assert any(t.name == "assess_table_quality" for t in tools), (
        "assess_table_quality tool not registered"
    )

    resources = (await session.list_resources()).resources
    assert any(str(r.uri) == "notes://all" for r in resources), "notes://all resource not registered"

    prompts = (await session.list_prompts()).prompts
    assert any(p.name == "capture_note" for p in prompts), "capture_note prompt not registered"

    # Tool happy path
    result = await session.call_tool(
        "add_note", {"title": "Smoke test note", "content": "written by test_connection.py"}
    )
    tool_text = result.content[0].text
    assert "Smoke test note" in tool_text, f"unexpected tool response: {tool_text}"

    # Tool failure path: empty title should be rejected by the
    # Field(min_length=1) constraint, not silently accepted. This is the BREAK
    # half of BUILD/BREAK/HARDEN — a connection test that only checks the
    # happy path isn't complete.
    bad_result = await session.call_tool("add_note", {"title": "", "content": "x"})
    print("Empty-title call result:", bad_result)
    assert bad_result.is_error, "expected is_error=True for an empty title"

    # Resource reflects the tool's write: parse the JSON and check the note
    # just added is actually in there.
    resource_result = await session.read_resource("notes://all")
    notes = json.loads(resource_result.contents[0].text)
    assert any(n["title"] == "Smoke test note" for n in notes), (
        "expected notes://all to include the note just added via add_note"
    )

    # Prompt renders with the argument interpolated in.
    prompt_result = await session.get_prompt("capture_note", {"raw_text": "UNIQUE_MARKER_12345"})
    prompt_text = prompt_result.messages[0].content.text
    assert "UNIQUE_MARKER_12345" in prompt_text, "prompt did not interpolate raw_text"

    print("PASS: connection, tool, resource, and prompt all verified.")


async def exercise_sampling_degraded(session: ClientSession) -> None:
    """A client with NO sampling capability must still get a full verdict back,
    tagged as rule-based — never an error, never an empty answer."""
    await session.initialize()
    result = await session.call_tool(
        "assess_table_quality", {"database": "wh.db", "table": "bad_orders"}
    )
    assert not result.is_error, f"degraded path should not error: {result}"
    body = json.loads(result.content[0].text)
    assert body["verdict"] in {"PASS", "WARN", "FAIL"}, body
    assert body["verdict"] == "FAIL", body  # dup key + 30% null amount
    assert "does not support sampling" in body["assessed_by"], body
    assert body["reasons"], "degraded verdict must explain itself"
    print("PASS: assess_table_quality degrades cleanly when the client cannot sample.")


async def exercise_sampling_ok(session: ClientSession) -> None:
    """A client that DOES implement sampling: the tool's verdict is the model's."""
    await session.initialize()
    result = await session.call_tool(
        "assess_table_quality", {"database": "wh.db", "table": "clean_orders"}
    )
    assert not result.is_error, f"sampling path errored: {result}"
    body = json.loads(result.content[0].text)
    assert body["assessed_by"] == "client model via MCP sampling", body
    assert body["verdict"] == "WARN", body  # the stub model below always says WARN
    assert body["suspect_columns"] == ["region"], body
    assert "sampling_ms" in body, body
    print("PASS: assess_table_quality uses the client model's verdict when sampling works.")


class _Ticks:
    """Collects progress notifications for one call_tool, as (progress, total, message)."""

    def __init__(self) -> None:
        self.items: list[tuple[float, float | None, str | None]] = []

    async def __call__(self, progress: float, total: float | None, message: str | None) -> None:
        self.items.append((progress, total, message))

    def progresses(self) -> list[float]:
        return [p for p, _, _ in self.items]


async def exercise_run_sql_query(session: ClientSession) -> None:
    """run_sql_query still returns the same JSON whether or not progress is asked
    for, and with a token it emits a rising count with NO total (duration/rows
    are not knowable up front)."""
    await session.initialize()

    plain = await session.call_tool(
        "run_sql_query",
        {"database": "wh.db", "query": "SELECT COUNT(*) AS n FROM clean_orders"},
    )
    assert not plain.is_error, plain
    assert json.loads(plain.content[0].text)["rows"] == [[100]], plain.content[0].text

    ticks = _Ticks()
    withprog = await session.call_tool(
        "run_sql_query",
        {"database": "wh.db", "query": "SELECT COUNT(*) AS n FROM clean_orders"},
        progress_callback=ticks,
    )
    assert not withprog.is_error, withprog
    # Same result as the no-progress call — progress must not change the return.
    assert withprog.content[0].text == plain.content[0].text, "progress changed the result"
    assert len(ticks.items) >= 3, ticks.items
    assert all(total is None for _, total, _ in ticks.items), (
        f"run_sql_query must send NO total (unknown): {ticks.items}"
    )
    assert ticks.progresses() == sorted(ticks.progresses()), ticks.items
    assert any("unknown" in (m or "") for _, _, m in ticks.items), ticks.items
    assert any("returned" in (m or "") for _, _, m in ticks.items), ticks.items
    print("PASS: run_sql_query emits a rising no-total progress count; result unchanged.")


async def exercise_assess_progress(session: ClientSession) -> None:
    """assess_table_quality reports five real steps as N/5 when a token is sent,
    and returns the same body as the no-progress call."""
    await session.initialize()

    plain = await session.call_tool(
        "assess_table_quality", {"database": "wh.db", "table": "bad_orders"}
    )
    ticks = _Ticks()
    withprog = await session.call_tool(
        "assess_table_quality",
        {"database": "wh.db", "table": "bad_orders"},
        progress_callback=ticks,
    )
    assert not withprog.is_error, withprog
    assert withprog.content[0].text == plain.content[0].text, "progress changed the result"
    assert len(ticks.items) >= 5, ticks.items
    assert all(total == 5 for _, total, _ in ticks.items), (
        f"every assess_table_quality tick must count against total=5: {ticks.items}"
    )
    assert ticks.progresses() == sorted(ticks.progresses()), ticks.items
    assert max(ticks.progresses()) == 5, ticks.items
    print("PASS: assess_table_quality emits N/5 progress against a real total; result unchanged.")


def _make_sql_db(sql_root: Path) -> None:
    conn = sqlite3.connect(sql_root / "wh.db")
    conn.executescript(
        """
        CREATE TABLE clean_orders (order_id INTEGER, amount REAL, region TEXT);
        CREATE TABLE bad_orders   (order_id INTEGER, amount REAL, region TEXT);
        """
    )
    conn.executemany(
        "INSERT INTO clean_orders VALUES (?,?,?)", [(i, i * 1.5, "us") for i in range(100)]
    )
    bad = [(i, (None if i % 10 < 3 else i * 2.0), "us") for i in range(96)] + [(1, 9.0, "us")] * 4
    conn.executemany("INSERT INTO bad_orders VALUES (?,?,?)", bad)
    conn.commit()
    conn.close()


async def _stub_sampling_callback(context, params):
    """Stand in for the client's LLM: always answers WARN / region."""
    return CreateMessageResult(
        role="assistant",
        model="stub-model",
        stop_reason="endTurn",
        content=TextContent(
            type="text",
            text='{"verdict": "WARN", "reasons": ["stub reviewer"], "suspect_columns": ["region"]}',
        ),
    )


class _LogSink:
    """Collects the structured MCP log notifications the client receives."""

    def __init__(self) -> None:
        self.records: list = []

    async def __call__(self, params) -> None:
        self.records.append(params)

    def take(self) -> list[dict]:
        out = [p.data for p in self.records]
        self.records.clear()
        return out


_FORBIDDEN_LOG_KEYS = {
    "query", "params", "content", "title", "raw_text", "system_prompt",
    "user_text", "prompt_text", "api_key", "apikey", "connection_string", "dsn", "rows",
}


async def exercise_structured_logging(session: ClientSession, sink: _LogSink) -> None:
    init = await session.initialize()
    assert init.capabilities.logging is not None, "server must advertise the logging capability"
    sink.take()  # discard anything from init

    # --- one successful invocation is fully traceable -----------------------
    res = await session.call_tool("assess_table_quality", {"database": "wh.db", "table": "bad_orders"})
    assert not res.is_error, res
    lines = sink.take()
    assert lines, "a successful invocation must produce log notifications"
    for d in lines:
        assert isinstance(d, dict), d
        assert d.get("correlation_id"), f"every log line needs a correlation id: {d}"
        assert d.get("event"), f"every log line needs a stable event name: {d}"
        assert _FORBIDDEN_LOG_KEYS.isdisjoint(d), f"log line leaked a raw/secret field: {d}"
    cids = {d["correlation_id"] for d in lines}
    assert len(cids) == 1, f"one invocation must use exactly one correlation id, got {cids}"
    events = [d["event"] for d in lines]
    assert events[0] == "tool.invoked" and events[-1] == "tool.completed", events
    assert "external_call.started" in events and "external_call.finished" in events, events
    for d in lines:
        if d["event"] == "external_call.finished":
            assert isinstance(d.get("duration_ms"), (int, float)), d
    print("PASS: one successful invocation emits a single-correlation-id structured trace, no secrets.")

    # --- access denied by the inner fs_fence -----------------------------
    # `../notes/probe.db` is INSIDE a declared root (notes_root) so it passes the
    # roots gate, then fails sql_adapter's own fence to SQL_DATA_ROOT.
    denied = await session.call_tool(
        "run_sql_query", {"database": "../notes/probe.db", "query": "SELECT 1"}
    )
    assert denied.is_error, "path escape must still be a tool error (unchanged behavior)"
    ev = {d["event"]: d for d in sink.take()}
    assert "access.denied" in ev, list(ev)
    assert ev["access.denied"].get("error_class") == "AccessDenied", ev["access.denied"]
    print("PASS: a path-fence escape emits access.denied with error_class=AccessDenied.")

    # --- error caught with a stable class --------------------------------
    broke = await session.call_tool(
        "run_sql_query", {"database": "wh.db", "query": "SELECT * FROM no_such_table"}
    )
    assert broke.is_error, broke
    ev = {d["event"]: d for d in sink.take()}
    assert "error.caught" in ev, list(ev)
    assert ev["error.caught"].get("error_class") == "QueryError", ev["error.caught"]
    print("PASS: a broken query emits error.caught with error_class=QueryError.")


async def exercise_roots_enforced(session: ClientSession, sink: _LogSink) -> None:
    """Client declares roots covering the data dirs: FS tools work, and a path
    that resolves outside every root is denied as an error result (not a crash)
    with a roots.denied warning."""
    await session.initialize()
    sink.take()

    ok = await session.call_tool("run_sql_query", {"database": "wh.db", "query": "SELECT 1"})
    assert not ok.is_error, f"a path inside a declared root must be allowed: {ok}"

    esc = await session.call_tool(
        "run_sql_query", {"database": "../wh.db", "query": "SELECT 1"}
    )
    assert esc.is_error, "a '..' escape must be denied"
    assert "AccessDenied" in esc.content[0].text, esc.content[0].text
    ev = {d["event"]: d for d in sink.take()}
    assert "roots.denied" in ev, list(ev)
    assert ev["roots.denied"]["requested_path"], "denial log must carry the requested path"
    assert ev["roots.denied"].get("reason") == "resolved_path_outside_all_declared_roots", ev["roots.denied"]
    print("PASS: with roots declared, an out-of-root path is an AccessDenied result + roots.denied log.")


async def exercise_roots_default_deny(session: ClientSession, sink: _LogSink) -> None:
    """Client declares an EMPTY roots list -> every filesystem tool is denied by
    default and logs roots.no_roots_declared."""
    await session.initialize()
    for tool, args in (
        ("add_note", {"title": "x", "content": "y"}),
        ("run_sql_query", {"database": "wh.db", "query": "SELECT 1"}),
        ("assess_table_quality", {"database": "wh.db", "table": "bad_orders"}),
    ):
        sink.take()
        res = await session.call_tool(tool, args)
        assert res.is_error, f"{tool} must be denied when the client declares no roots"
        assert "AccessDenied" in res.content[0].text, res.content[0].text
        ev = {d["event"]: d for d in sink.take()}
        assert "roots.no_roots_declared" in ev, (tool, list(ev))
        assert ev["roots.no_roots_declared"]["reason"] == "empty_roots_list", ev["roots.no_roots_declared"]
    print("PASS: no roots declared -> add_note / run_sql_query / assess_table_quality all default-deny + log.")


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        notes_root = Path(tmp) / "notes"
        sql_root = Path(tmp) / "sql"
        notes_root.mkdir()
        sql_root.mkdir()
        _make_sql_db(sql_root)

        server_params = StdioServerParameters(
            command=sys.executable,
            args=["src/server.py"],
            env={
                **os.environ,
                "MCP_NOTES_DATA_ROOT": str(notes_root),
                "MCP_SQL_DATA_ROOT": str(sql_root),
            },
        )
        # Every session below declares roots covering both data dirs — that is
        # now required for any filesystem tool to run.
        roots_cb = _roots_cb(notes_root, sql_root)

        # Primitives + the sampling-unavailable path (default client: no sampling).
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write, list_roots_callback=roots_cb) as session:
                await exercise(session)
                await exercise_sampling_degraded(session)
                await exercise_run_sql_query(session)
                await exercise_assess_progress(session)

        # The sampling-available path (client provides a sampling callback).
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(
                read, write, sampling_callback=_stub_sampling_callback, list_roots_callback=roots_cb
            ) as session:
                await exercise_sampling_ok(session)

        # Structured log notifications: client opts in (log_level) and collects them.
        sink = _LogSink()
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(
                read,
                write,
                sampling_callback=_stub_sampling_callback,
                logging_callback=sink,
                log_level="debug",
                list_roots_callback=roots_cb,
            ) as session:
                await exercise_structured_logging(session, sink)
                await exercise_roots_enforced(session, sink)

        # Default-deny: a client that declares NO roots at all.
        sink2 = _LogSink()
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(
                read,
                write,
                logging_callback=sink2,
                log_level="debug",
                list_roots_callback=_roots_cb(),  # returns an empty roots list
            ) as session:
                await exercise_roots_default_deny(session, sink2)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:  # noqa: BLE001 - top-level test entry point, deliberately broad
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
