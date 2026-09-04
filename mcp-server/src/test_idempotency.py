"""
Idempotency test for add_note.

add_note is a side-effecting operation and clients retry. Two ways a retry is
made safe:
  - pass a stable `idempotency_key`: the same key returns the note already
    stored under it;
  - pass no key: an identical title+content returns the existing note.
Either way, no duplicate row and the same id comes back.

Run from the mcp-server/ folder:
    python src/test_idempotency.py
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import ListRootsResult, Root


def _params(data_root: str) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["src/server.py"],
        env={**os.environ, "MCP_NOTES_DATA_ROOT": data_root},
    )


def _roots_cb(data_root: str):
    """add_note now requires the client to declare a root covering the store."""
    roots = [Root(uri=Path(data_root).resolve().as_uri())]

    async def cb(context) -> ListRootsResult:
        return ListRootsResult(roots=roots)

    return cb


async def _notes(session: ClientSession) -> list[dict]:
    result = await session.read_resource("notes://all")
    return json.loads(result.contents[0].text)


def _text(result) -> str:
    return result.content[0].text


async def main() -> None:
    with tempfile.TemporaryDirectory() as data_root:
        async with stdio_client(_params(data_root)) as (read, write):
            async with ClientSession(read, write, list_roots_callback=_roots_cb(data_root)) as session:
                await session.initialize()
                start = len(await _notes(session))

                # 1. No key: identical title+content twice -> one note.
                r1 = await session.call_tool("add_note", {"title": "Deploy failed", "content": "pod OOMKilled"})
                r2 = await session.call_tool("add_note", {"title": "Deploy failed", "content": "pod OOMKilled"})
                assert "added with id" in _text(r1), _text(r1)
                assert "already stored" in _text(r2), f"retry was not deduped: {_text(r2)}"
                assert len(await _notes(session)) == start + 1, "identical retry created a second note"

                # 2. No key: same title, different content -> a real second note.
                r3 = await session.call_tool("add_note", {"title": "Deploy failed", "content": "different cause"})
                assert "added with id" in _text(r3), _text(r3)
                assert len(await _notes(session)) == start + 2

                # 3. Explicit key: same key twice -> one note, first content wins,
                #    same id returned both times.
                k = {"title": "Retme", "content": "first", "idempotency_key": "op-42"}
                r4 = await session.call_tool("add_note", k)
                r5 = await session.call_tool(
                    "add_note", {"title": "Retme", "content": "SECOND try", "idempotency_key": "op-42"}
                )
                id4 = _text(r4).rsplit(" ", 1)[-1].rstrip(".")
                assert id4 in _text(r5), f"same key returned a different note: {_text(r5)}"
                assert len(await _notes(session)) == start + 3, "reused key created a second note"
                stored = [n for n in await _notes(session) if n.get("idempotency_key") == "op-42"]
                assert len(stored) == 1 and stored[0]["content"] == "first", stored

        # 4. Survives a restart: the keyed note is still deduped by a fresh process.
        async with stdio_client(_params(data_root)) as (read, write):
            async with ClientSession(read, write, list_roots_callback=_roots_cb(data_root)) as session:
                await session.initialize()
                before = len(await _notes(session))
                r6 = await session.call_tool(
                    "add_note", {"title": "x", "content": "y", "idempotency_key": "op-42"}
                )
                assert "already stored" in _text(r6), _text(r6)
                assert len(await _notes(session)) == before

        print("PASS: add_note dedups on idempotency_key and on identical title+content.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:  # noqa: BLE001 - top-level test entry point
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
