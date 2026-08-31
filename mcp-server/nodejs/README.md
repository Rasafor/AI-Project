# mcp-server/nodejs

Node.js/TypeScript-SDK reference implementation of the same "notes" MCP
server as [`../src`](../src) (Python). Same design, different SDK:

- **Tool** `add_note(title, content)` — the model calls this to save a note.
- **Resource** `notes://all` — exposes the current list of notes as JSON.
- **Prompt** `capture_note(raw_text)` — a reusable template that guides the
  model to turn unstructured text into a title + body and call `add_note`.

**This folder exists as a learning comparison, not a second product to
maintain.** `../src` (Python) is the version this repo actually builds on.
Use this folder when you want to see how the Node.js MCP SDK expresses the
same tool/resource/prompt contracts Python's does — e.g. Zod schemas here
vs. Pydantic `Field(...)` there, `server.tool(name, description, schema,
handler)` here vs. the `@mcp.tool()` decorator there.

---

## Setup

```
npm install
```

Installs `@modelcontextprotocol/sdk` and `zod`.

## Run the server directly

```
npm start
```

This runs `node server.js`, which just sits there speaking JSON-RPC over
stdio — not useful to look at directly. Use the Inspector or the test
client below to actually interact with it.

## Test with the MCP Inspector

```
npm run inspect
```

Opens the Inspector UI in your browser (same tool the Python version uses).
Click **Connect** — you should see `add_note`, `notes://all`, and
`capture_note` in their respective tabs. Try running `add_note`, then read
`notes://all` to confirm the new note shows up.

## Automated connection test (no browser needed)

```
npm test
```

Runs `test-connection.js`, which spawns the server over stdio and asserts
on: discovery of all three primitives, the tool's happy path, the tool's
rejection of an empty title, the resource reflecting the tool's write, and
the prompt's argument interpolation. Prints `PASS: ...` and exits `0` on
success, or throws with a non-zero exit on any regression.

## Exploratory client

`client.js` (`node client.js`) runs the same sequence as the test but logs
everything instead of asserting — useful for seeing the raw shape of every
response (tool result, resource JSON, rendered prompt messages) while
you're still learning what each primitive returns.

## Files

- `server.js` — the server: one tool, one resource, one prompt.
- `client.js` — a programmatic MCP client that connects, calls everything,
  and logs the results. This is the shape a real host application takes —
  the Inspector is a generic tool for humans; this is what your own code
  would look like embedding the server.
- `test-connection.js` — the same client interactions as `client.js`, but
  with assertions and a proper exit code, so it can gate a build.
- `package.json` / `package-lock.json` — dependencies (`node_modules/` is
  gitignored; run `npm install` after cloning).
