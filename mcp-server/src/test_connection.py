"""
Connection smoke test for server.py.

Spawns the server as a subprocess over stdio (the same transport the MCP
Inspector and Claude Desktop/Code use), then exercises every primitive the
server registers: discovery, the tool's happy path, the tool's rejection of
invalid input, the resource, and the prompt. Exits 0 on success, 1 (with a
message) on any failure — no test framework required, so it can gate a
build the same way `tsc --noEmit` gates a TypeScript change elsewhere in
this repo.

Run from the mcp-server/ folder:
    python src/test_connection.py
"""

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PARAMS = StdioServerParameters(command=sys.executable, args=["src/server.py"])


async def main() -> None:
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            # Handshake
            await session.initialize()

            # Discovery: fail loudly if a primitive silently disappears
            # (e.g. a typo in a decorator's uri/name, or an exception
            # during import that got swallowed).
            tools = (await session.list_tools()).tools
            assert any(t.name == "add_note" for t in tools), "add_note tool not registered"

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
            # Field(min_length=1) constraint, not silently accepted. This
            # is the BREAK half of BUILD/BREAK/HARDEN — a connection test
            # that only checks the happy path isn't complete.
            bad_result = await session.call_tool("add_note", {"title": "", "content": "x"})
            print("Empty-title call result:", bad_result)
            assert bad_result.is_error, "expected is_error=True for an empty title"

            # Resource reflects the tool's write: parse the JSON and check
            # the note just added is actually in there.
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


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:  # noqa: BLE001 - top-level test entry point, deliberately broad
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
