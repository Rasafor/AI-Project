import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

// Idempotency test for add_note — the Node mirror of ../src/test_idempotency.py.
// A retry is made safe two ways: a stable `idempotency_key`, or (with no key) an
// identical title+content. Either way: no duplicate, same id back.
//
// Run from the nodejs/ folder:  node test-idempotency.js

const dataRoot = fs.mkdtempSync(path.join(os.tmpdir(), "mcp-idem-"));

async function withClient(fn) {
  const t = new StdioClientTransport({
    command: "node",
    args: ["server.js"],
    env: { ...process.env, MCP_NOTES_DATA_ROOT: dataRoot },
  });
  const c = new Client({ name: "idem-test", version: "1.0.0" });
  await c.connect(t);
  try {
    return await fn(c);
  } finally {
    await c.close();
  }
}

const text = (r) => r.content[0].text;
const notesOf = async (c) => JSON.parse((await c.readResource({ uri: "notes://all" })).contents[0].text);

async function main() {
  await withClient(async (c) => {
    const start = (await notesOf(c)).length;

    // 1. No key: identical title+content twice -> one note.
    const r1 = await c.callTool({ name: "add_note", arguments: { title: "Deploy failed", content: "pod OOMKilled" } });
    const r2 = await c.callTool({ name: "add_note", arguments: { title: "Deploy failed", content: "pod OOMKilled" } });
    assert.match(text(r1), /added with id/, text(r1));
    assert.match(text(r2), /already stored/, `retry was not deduped: ${text(r2)}`);
    assert.equal((await notesOf(c)).length, start + 1, "identical retry created a second note");

    // 2. No key: same title, different content -> a real second note.
    const r3 = await c.callTool({ name: "add_note", arguments: { title: "Deploy failed", content: "different cause" } });
    assert.match(text(r3), /added with id/, text(r3));
    assert.equal((await notesOf(c)).length, start + 2);

    // 3. Explicit key: same key twice -> one note, first content wins, same id.
    const r4 = await c.callTool({
      name: "add_note",
      arguments: { title: "Retme", content: "first", idempotency_key: "op-42" },
    });
    const r5 = await c.callTool({
      name: "add_note",
      arguments: { title: "Retme", content: "SECOND try", idempotency_key: "op-42" },
    });
    const id4 = text(r4).trim().replace(/\.$/, "").split(" ").pop();
    assert.ok(text(r5).includes(id4), `same key returned a different note: ${text(r5)}`);
    assert.equal((await notesOf(c)).length, start + 3, "reused key created a second note");
    const stored = (await notesOf(c)).filter((n) => n.idempotencyKey === "op-42");
    assert.equal(stored.length, 1);
    assert.equal(stored[0].content, "first");
  });

  // 4. Survives a restart: a fresh process still dedups the keyed note.
  await withClient(async (c) => {
    const before = (await notesOf(c)).length;
    const r6 = await c.callTool({
      name: "add_note",
      arguments: { title: "x", content: "y", idempotency_key: "op-42" },
    });
    assert.match(text(r6), /already stored/, text(r6));
    assert.equal((await notesOf(c)).length, before);
  });

  console.log("PASS: add_note dedups on idempotency_key and on identical title+content.");
}

main()
  .then(() => {
    fs.rmSync(dataRoot, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
    process.exit(0);
  })
  .catch((err) => {
    console.error("FAIL:", err);
    fs.rmSync(dataRoot, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
    process.exit(1);
  });
