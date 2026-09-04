"""
Show the structured log notifications ONE successful tool invocation produces,
in order — so you can confirm a single run is traceable end to end.

Spawns server.py over stdio with a stub sampling client, opts in to logging
(log_level="debug"), calls assess_table_quality once against a throwaway
SQLite file, and prints every notifications/message the client receives:

    python src/demo_trace.py            # assess_table_quality (the richest trace)
    python src/demo_trace.py run_sql_query
    python src/demo_trace.py add_note
"""

import asyncio
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CreateMessageResult, ListRootsResult, Root, TextContent


async def _stub_sampling(context, params):
    return CreateMessageResult(
        role="assistant",
        model="stub-model-v1",
        stop_reason="endTurn",
        content=TextContent(
            type="text",
            text='{"verdict": "FAIL", "reasons": ["duplicate order_id", "amount 30% null"], '
            '"suspect_columns": ["order_id", "amount"]}',
        ),
    )


def _make_db(root: Path) -> None:
    conn = sqlite3.connect(root / "warehouse.db")
    conn.executescript("CREATE TABLE orders (order_id INTEGER, amount REAL, region TEXT);")
    rows = [(i, (None if i % 10 < 3 else i * 2.0), "us") for i in range(96)] + [(1, 9.0, "us")] * 4
    conn.executemany("INSERT INTO orders VALUES (?,?,?)", rows)
    conn.commit()
    conn.close()


CALLS = {
    "assess_table_quality": {"database": "warehouse.db", "table": "orders"},
    "run_sql_query": {"database": "warehouse.db", "query": "SELECT region, COUNT(*) FROM orders GROUP BY region"},
    "add_note": {"title": "demo", "content": "written by demo_trace.py"},
}


async def main() -> None:
    tool = sys.argv[1] if len(sys.argv) > 1 else "assess_table_quality"
    if tool not in CALLS:
        sys.exit(f"unknown tool {tool!r}; pick one of {list(CALLS)}")

    lines: list = []

    async def logging_callback(params) -> None:
        lines.append(params)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "notes").mkdir()
        _make_db(root)

        async def list_roots_cb(context) -> ListRootsResult:
            return ListRootsResult(roots=[Root(uri=root.resolve().as_uri())])

        server = StdioServerParameters(
            command=sys.executable,
            args=["src/server.py"],
            env={
                "MCP_NOTES_DATA_ROOT": str(root / "notes"),
                "MCP_SQL_DATA_ROOT": str(root),
                "PATH": __import__("os").environ.get("PATH", ""),
                "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
            },
        )
        async with stdio_client(server) as (r, w):
            async with ClientSession(
                r,
                w,
                logging_callback=logging_callback,
                sampling_callback=_stub_sampling,
                list_roots_callback=list_roots_cb,
                log_level="debug",
            ) as session:
                init = await session.initialize()
                print(f"server 'logging' capability advertised: {init.capabilities.logging is not None}\n")
                result = await session.call_tool(tool, CALLS[tool])

    print(f"log notifications from ONE successful {tool} call, in order:\n")
    seen_cids = set()
    for i, p in enumerate(lines, 1):
        data = p.data if isinstance(p.data, dict) else {"message": p.data}
        cid = data.get("correlation_id", "")
        seen_cids.add(cid)
        event = data.get("event", "?")
        rest = {k: v for k, v in data.items() if k not in ("event", "correlation_id")}
        print(f"{i:>2}. cid={cid[:8]} [{p.level:<7}] {event:<22} {json.dumps(rest, default=str)}")

    print(f"\ndistinct correlation ids across those {len(lines)} lines: {len(seen_cids)}  -> {seen_cids}")
    is_err = getattr(result, "is_error", None)
    print(f"tool returned (unchanged): is_error={is_err}, {len(result.content[0].text)} chars of JSON")


if __name__ == "__main__":
    asyncio.run(main())
