# mcp-server

This is an MCP (Model Context Protocol) server. It started as an empty
shell (no tools, no resources, no prompts) to confirm the connection works,
and now implements a small "notes" example:

- **Tool** `add_note(title, content)` — the model calls this to save a note.
- **Resource** `notes://all` — exposes the current list of notes as JSON.
- **Prompt** `capture_note(raw_text)` — a reusable template that guides the
  model to turn unstructured text into a title + body and call `add_note`.

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
accepted.

To stop the server, go back to the terminal and press `Ctrl+C`.

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

It prints `PASS: ...` and exits `0` on success, or `FAIL: ...` with a
non-zero exit on any regression — useful for catching a broken server
without opening a browser each time.

---

## Folders

- `src/` — the server code (`server.py`) and its connection test
  (`test_connection.py`). This is the primary, maintained version.
- `nodejs/` — the same server rebuilt with the Node.js/TypeScript MCP SDK,
  kept as a side-by-side learning reference. See
  [`nodejs/README.md`](nodejs/README.md) for its own setup and test steps.
- `artifacts/week-05/` — empty for now. This is where your Inspector
  recording/screenshots go later. (Note: an empty folder doesn't get saved
  by git on its own — once you put a file in here, it'll show up normally.)
