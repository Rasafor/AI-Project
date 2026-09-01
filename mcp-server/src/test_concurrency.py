"""
Concurrency test for add_note.

The SDK runs synchronous tool functions on a thread pool, so two add_note calls
can execute at the same time. Each call rewrites the whole notes file. Without
server.py's write lock, two overlapping calls race on that write and one note is
silently dropped from data/notes.json — the running process still looks right,
but the loss shows up after a restart, and nobody notices.

This test fires many add_note calls concurrently, then checks every note is
present both in notes://all and — after a full restart — on disk.

Run from the mcp-server/ folder:
    python src/test_concurrency.py
"""

import asyncio
import json
import os
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

N = 40


def _params(data_root: str) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["src/server.py"],
        env={**os.environ, "MCP_NOTES_DATA_ROOT": data_root},
    )


async def _titles(session: ClientSession) -> list[str]:
    result = await session.read_resource("notes://all")
    return [n["title"] for n in json.loads(result.contents[0].text)]


async def main() -> None:
    with tempfile.TemporaryDirectory() as data_root:
        expected = {f"concurrent-{i:03d}" for i in range(N)}

        # Round 1: fire N add_note calls at once against one running server.
        async with stdio_client(_params(data_root)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                results = await asyncio.gather(
                    *(
                        session.call_tool("add_note", {"title": t, "content": "x"})
                        for t in sorted(expected)
                    ),
                    return_exceptions=True,
                )
                errors = [r for r in results if isinstance(r, BaseException)]
                assert not errors, f"{len(errors)} add_note call(s) raised: {errors[:3]}"
                tool_errors = [r for r in results if getattr(r, "is_error", False)]
                assert not tool_errors, f"{len(tool_errors)} add_note call(s) returned is_error"

                live = set(await _titles(session))
                missing_live = expected - live
                assert not missing_live, f"notes://all is missing {len(missing_live)}: {sorted(missing_live)[:5]}"

        # Round 2: a brand-new process reads the persisted file. This is where a
        # lost write would show up.
        async with stdio_client(_params(data_root)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                after_restart = set(await _titles(session))

        missing_disk = expected - after_restart
        assert not missing_disk, (
            f"{len(missing_disk)} note(s) never reached disk: {sorted(missing_disk)[:5]}"
        )
        print(f"PASS: all {N} concurrent add_note calls persisted; none lost across a restart.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:  # noqa: BLE001 - top-level test entry point
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
