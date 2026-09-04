"""
Transport + state-model tests for docs/ADR-0001-transport.md.

  * resolve() maps the ADR's env vars to a config, and rejects bad values.
  * The STDIO path logs its transport + single-user state model at startup.
  * The Streamable HTTP path (MCP_TRANSPORT=streamable-http, MCP_STATELESS=true)
    logs a stateless state model, serves MCP over HTTP, keeps NO session map, and
    two independent clients see each other's writes — i.e. any request is
    self-contained and any instance could serve it.

Run from the mcp-server/ folder:
    python src/test_transport.py
"""

import asyncio
import contextlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import ListRootsResult, Root

import transport

_SRC = Path(__file__).resolve().parent
_CWD = _SRC.parent  # mcp-server/


def _clear_mcp_env(env: dict) -> dict:
    return {k: v for k, v in env.items() if not k.startswith("MCP_")}


def test_resolve() -> None:
    base = _clear_mcp_env(os.environ)

    def resolve_with(**over):
        os.environ.clear()
        os.environ.update({**base, **over})
        return transport.resolve()

    try:
        d = resolve_with()
        assert d.transport == "stdio" and not d.notes_read_through, d
        assert "single user" in d.state_model, d.state_model

        h = resolve_with(MCP_TRANSPORT="streamable-http")
        assert h.transport == "streamable-http", h
        assert h.stateless is False and h.notes_read_through is False, "HTTP default is stateful"
        assert h.json_response is False, "ADR step 2: json_response defaults false"
        assert h.host == "127.0.0.1" and h.port == 8000 and h.mount_path == "/mcp", h
        assert "back-channel works" in h.state_model, h.state_model

        sl = resolve_with(MCP_TRANSPORT="streamable-http", MCP_STATELESS="true")
        assert sl.stateless is True and sl.notes_read_through is True, sl
        assert "NO in-memory session map" in sl.state_model, sl.state_model
        assert "fail-safe deny" in sl.state_model, sl.state_model

        cfg = resolve_with(MCP_TRANSPORT="http", MCP_HOST="0.0.0.0", MCP_PORT="9001", MCP_MOUNT_PATH="/x")
        assert cfg.transport == "streamable-http" and cfg.port == 9001 and cfg.mount_path == "/x", cfg

        for bad in (
            {"MCP_TRANSPORT": "grpc"},
            {"MCP_TRANSPORT": "streamable-http", "MCP_PORT": "abc"},
            {"MCP_TRANSPORT": "streamable-http", "MCP_STATELESS": "maybe"},
        ):
            try:
                resolve_with(**bad)
            except SystemExit:
                pass
            else:
                raise AssertionError(f"expected SystemExit for {bad}")
    finally:
        os.environ.clear()
        os.environ.update(base)
    print("PASS: resolve() maps the ADR env surface and rejects bad values.")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _spawn(env_extra: dict, notes_root: Path, err_path: Path):
    """Spawn server.py with stderr redirected to `err_path` — a file, not a PIPE,
    so a hard terminate() on Windows can't lose the buffered startup line.
    Returns (proc, open file handle to close)."""
    env = {
        **os.environ,
        "MCP_NOTES_DATA_ROOT": str(notes_root),
        "MCP_SQL_DATA_ROOT": str(notes_root),
        **env_extra,
    }
    fh = open(err_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "src/server.py"],
        cwd=str(_CWD),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=fh,
    )
    return proc, fh


def _startup_line(stderr_text: str) -> dict:
    for line in stderr_text.splitlines():
        line = line.strip()
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("event") == "server.starting":
            return obj
    raise AssertionError(f"no server.starting log line found in:\n{stderr_text}")


def test_stdio_startup_log() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        err_path = Path(tmp) / "err.log"
        proc, fh = _spawn({}, Path(tmp), err_path)
        try:
            # stdin is DEVNULL, so the stdio server prints the startup line then
            # hits EOF and exits on its own.
            proc.wait(timeout=15)
        finally:
            proc.terminate()
            fh.close()
        line = _startup_line(err_path.read_text(encoding="utf-8"))
    assert line["transport"] == "stdio", line
    assert "single user" in line["state_model"], line
    assert "session map" not in line["state_model"], line
    print(f"PASS: STDIO logs its transport + single-user state model at startup:\n      {line}")


def _roots_cb_for(notes_root: Path):
    async def cb(context) -> ListRootsResult:
        return ListRootsResult(roots=[Root(uri=notes_root.resolve().as_uri())])

    return cb


def _serve_http(env_extra: dict, notes_root: Path, err_path: Path):
    """Spawn server.py over HTTP on a free port; return (proc, fh, url)."""
    port = _free_port()
    proc, fh = _spawn({**env_extra, "MCP_PORT": str(port)}, notes_root, err_path)
    deadline = time.time() + 20
    while time.time() < deadline:
        with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", port), 0.5):
            return proc, fh, f"http://127.0.0.1:{port}/mcp"
        if proc.poll() is not None:
            fh.close()
            raise AssertionError(f"server exited early:\n{err_path.read_text(encoding='utf-8')}")
        time.sleep(0.2)
    raise AssertionError("streamable-http server did not start listening in time")


async def _stateful_roundtrip(url: str, notes_root: Path) -> None:
    cb = _roots_cb_for(notes_root)
    async with streamable_http_client(url) as st:
        async with ClientSession(st[0], st[1], list_roots_callback=cb) as s:
            await s.initialize()
            tools = {t.name for t in (await s.list_tools()).tools}
            assert {"add_note", "run_sql_query", "assess_table_quality"} <= tools, tools
            # Back-channel works -> roots/list succeeds -> add_note is allowed.
            res = await s.call_tool("add_note", {"title": "over-http", "content": "stateful"})
            assert not res.is_error, res.content[0].text
    # A second, independent connection re-initializes and sees it (on disk + in
    # this single replica's cache).
    async with streamable_http_client(url) as st:
        async with ClientSession(st[0], st[1], list_roots_callback=cb) as s:
            await s.initialize()
            got = json.loads((await s.read_resource("notes://all")).contents[0].text)
    assert any(n["title"] == "over-http" for n in got), got
    assert any(n["title"] == "over-http" for n in json.loads((notes_root / "notes.json").read_text()))


async def _stateless_roundtrip(url: str, notes_root: Path) -> None:
    cb = _roots_cb_for(notes_root)
    async with streamable_http_client(url) as st:
        async with ClientSession(st[0], st[1], list_roots_callback=cb) as s:
            await s.initialize()  # no back-channel needed
            tools = {t.name for t in (await s.list_tools()).tools}
            assert "add_note" in tools, tools
            # No back-channel -> roots/list can't run -> filesystem tool fail-safe
            # denies, as an error RESULT (not a crash).
            res = await s.call_tool("add_note", {"title": "x", "content": "y"})
            assert res.is_error, "add_note must fail-safe deny over stateless HTTP"
            assert "AccessDenied" in res.content[0].text, res.content[0].text
            # The resource has no roots gate, so it still serves the seeded store.
            seeded = json.loads((await s.read_resource("notes://all")).contents[0].text)
            assert isinstance(seeded, list), seeded
    # A second independent client also connects with no shared session id.
    async with streamable_http_client(url) as st:
        async with ClientSession(st[0], st[1], list_roots_callback=cb) as s:
            assert (await s.initialize()).server_info.name == "ai-project-mcp-server"


def _run_http_case(env_extra: dict, roundtrip) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        err_path = Path(tmp) / "err.log"
        proc, fh, url = _serve_http(env_extra, Path(tmp), err_path)
        try:
            asyncio.run(roundtrip(url, Path(tmp)))
        finally:
            proc.terminate()
            with contextlib.suppress(Exception):
                proc.wait(timeout=10)
            proc.kill()
            fh.close()
        return _startup_line(err_path.read_text(encoding="utf-8"))


def test_streamable_http_stateful_default() -> None:
    line = _run_http_case({"MCP_TRANSPORT": "streamable-http"}, _stateful_roundtrip)
    assert line["transport"] == "streamable-http" and line["stateless"] is False, line
    assert "back-channel works" in line["state_model"], line
    print(f"PASS: Streamable HTTP (default, stateful) — roots back-channel works, add_note allowed.\n      {line}")


def test_streamable_http_stateless_optin() -> None:
    line = _run_http_case(
        {"MCP_TRANSPORT": "streamable-http", "MCP_STATELESS": "true"}, _stateless_roundtrip
    )
    assert line["transport"] == "streamable-http", line
    assert line["stateless"] is True and line["notes_read_through"] is True, line
    assert "NO in-memory session map" in line["state_model"], line
    assert "fail-safe deny" in line["state_model"], line
    print(f"PASS: Streamable HTTP stateless — no session map, filesystem tools fail-safe deny.\n      {line}")


if __name__ == "__main__":
    try:
        test_resolve()
        test_stdio_startup_log()
        test_streamable_http_stateful_default()
        test_streamable_http_stateless_optin()
        print("ALL PASS: transport selection, startup logging, stateful + stateless HTTP paths.")
    except Exception as exc:  # noqa: BLE001 - top-level test entry point
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
