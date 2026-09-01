import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

// A minimal connection smoke test: no test framework, just assertions and
// a process exit code, so it can gate a build the same way `tsc --noEmit`
// does elsewhere in this repo. Exits 0 on success, 1 (with a stack trace)
// on any failure — nothing here is allowed to fail silently.

// Point the spawned server's notes store at a throwaway directory so this
// test never reads or writes the real data/notes.json.
const dataRoot = fs.mkdtempSync(path.join(os.tmpdir(), "mcp-notes-"));

const transport = new StdioClientTransport({
  command: "node",
  args: ["server.js"],
  env: { ...process.env, MCP_NOTES_DATA_ROOT: dataRoot, MCP_SQL_DATA_ROOT: dataRoot },
});
const client = new Client({ name: "notes-test-client", version: "1.0.0" });

async function main() {
  // Connection / handshake
  await client.connect(transport);

  // Discovery: fail loudly if a primitive silently disappears (e.g. a
  // typo in a registration name, or an exception during server startup
  // that got swallowed).
  const { tools } = await client.listTools();
  assert.ok(
    tools.some((t) => t.name === "add_note"),
    "expected 'add_note' tool to be registered"
  );
  assert.ok(
    tools.some((t) => t.name === "run_sql_query"),
    "expected 'run_sql_query' tool to be registered"
  );

  const { resources } = await client.listResources();
  assert.ok(
    resources.some((r) => r.uri === "notes://all"),
    "expected 'notes://all' resource to be registered"
  );

  const { prompts } = await client.listPrompts();
  assert.ok(
    prompts.some((p) => p.name === "capture_note"),
    "expected 'capture_note' prompt to be registered"
  );

  // Tool happy path: call add_note, check the confirmation text mentions
  // the title we sent.
  const toolResult = await client.callTool({
    name: "add_note",
    arguments: { title: "Smoke test note", content: "written by test-connection.js" },
  });
  const toolText = toolResult.content[0].text;
  assert.match(toolText, /Smoke test note/, `unexpected tool response: ${toolText}`);

  // Tool failure path: empty title should be rejected by the zod schema,
  // not silently accepted. This is the BREAK half of BUILD/BREAK/HARDEN —
  // a connection test that only checks the happy path isn't complete.
  //
  // NOTE: invalid tool input in this SDK version comes back as a normal
  // *resolved* result with isError: true (an execution-level error), not
  // as a rejected promise (a protocol-level error) — so we assert on the
  // result shape instead of assuming a throw.
  const badResult = await client.callTool({
    name: "add_note",
    arguments: { title: "", content: "x" },
  });
  console.log("Empty-title call result:", JSON.stringify(badResult, null, 2));
  assert.equal(badResult.isError, true, "expected isError: true for an empty title");

  // Resource reflects the tool's write: parse the JSON and check the note
  // we just added is actually in there, not just that the call didn't throw.
  const resourceResult = await client.readResource({ uri: "notes://all" });
  const notes = JSON.parse(resourceResult.contents[0].text);
  assert.ok(
    notes.some((n) => n.title === "Smoke test note"),
    "expected notes://all to include the note just added via add_note"
  );

  // Prompt renders with the argument interpolated in.
  const promptResult = await client.getPrompt({
    name: "capture_note",
    arguments: { raw_text: "UNIQUE_MARKER_12345" },
  });
  const promptText = promptResult.messages[0].content.text;
  assert.match(promptText, /UNIQUE_MARKER_12345/, "prompt did not interpolate raw_text");

  console.log("PASS: connection, tool, resource, and prompt all verified.");
}

function cleanup() {
  try {
    fs.rmSync(dataRoot, { recursive: true, force: true });
  } catch {
    /* temp dir already gone */
  }
}

main()
  .then(() => client.close())
  .then(() => {
    cleanup();
    process.exit(0);
  })
  .catch(async (err) => {
    console.error("FAIL:", err);
    try {
      await client.close();
    } catch {
      /* already closed or never connected */
    }
    cleanup();
    process.exit(1);
  });
