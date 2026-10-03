# mcp-server

This is an MCP (Model Context Protocol) server. Right now it does nothing —
it has no tools, no resources, and no prompts. It's just the empty shell,
started and confirmed working before anything is added to it.

**Language: Python.** The rest of this repo has no Node.js project (no
`package.json`), just a couple of standalone Python scripts and notebooks —
so Python is what's already here, and it's what this server is written in.

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
turn green. The "Tools," "Resources," and "Prompts" tabs will all be
**empty** — that's expected, since none have been built yet. Seeing a green
"Connected" status with empty tabs means the server is working correctly.

To stop the server, go back to the terminal and press `Ctrl+C`.

---

## Folders

- `src/` — the server code (`server.py`).
- `artifacts/week-05/` — empty for now. This is where your Inspector
  recording/screenshots go later. (Note: an empty folder doesn't get saved
  by git on its own — once you put a file in here, it'll show up normally.)
