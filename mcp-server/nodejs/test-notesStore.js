import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  DATA_ROOT,
  NOTES_FILENAME,
  loadNotes,
  resolveWithin,
  saveNotes,
} from "./notesStore.js";

// Unit tests for notesStore: the path fence and the persistence round-trip.
// Mirrors ../src/test_notes_store.py. No test framework — assertions and an
// exit code, so it can gate a build. Each refusal is printed so you can see
// exactly what a caller would get back.
//
// Run from the nodejs/ folder:  node test-notesStore.js   (or: npm run test:store)

function run(name, fn) {
  try {
    fn();
  } catch (err) {
    console.error(`FAIL: ${name}: ${err.message}`);
    process.exit(1);
  }
  console.log(`PASS: ${name}`);
}

run("fence allows the notes file", () => {
  const resolved = resolveWithin(DATA_ROOT, NOTES_FILENAME);
  assert.equal(resolved, path.join(fs.realpathSync(path.dirname(DATA_ROOT)), path.basename(DATA_ROOT), NOTES_FILENAME));
});

run("fence rejects ../ traversal", () => {
  const payloads = [
    "../../etc/hosts",
    "../../../../etc/passwd",
    "notes/../../../secret.txt",
  ];
  for (const payload of payloads) {
    let refused = false;
    try {
      resolveWithin(DATA_ROOT, payload);
    } catch (err) {
      refused = true;
      console.log(`       refused ${JSON.stringify(payload)} -> ${err.message}`);
    }
    assert.ok(refused, `${JSON.stringify(payload)} was NOT refused`);
  }
});

run("fence rejects absolute path outside root", () => {
  const outside = process.platform === "win32" ? "C:\\Windows\\win.ini" : "/etc/hosts";
  let refused = false;
  try {
    resolveWithin(DATA_ROOT, outside);
  } catch (err) {
    refused = true;
    console.log(`       refused ${JSON.stringify(outside)} -> ${err.message}`);
  }
  assert.ok(refused, `${JSON.stringify(outside)} was NOT refused`);
});

run("persistence round-trips", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "mcp-notes-"));
  try {
    const seeded = loadNotes(root);
    assert.ok(fs.existsSync(path.join(root, NOTES_FILENAME)), "first load did not create the store file");
    assert.ok(Array.isArray(seeded) && seeded.length > 0, "seeded store should be a non-empty array");

    seeded.push({ id: "marker", title: "persisted", content: "x", createdAt: "now" });
    saveNotes(seeded, root);

    const reloaded = loadNotes(root);
    assert.ok(reloaded.some((n) => n.id === "marker"), "saved note did not survive reload");
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

run("corrupt store errors loudly", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "mcp-notes-"));
  try {
    fs.writeFileSync(path.join(root, NOTES_FILENAME), "{ not valid json", "utf8");
    let raised = false;
    try {
      loadNotes(root);
    } catch (err) {
      raised = true;
      console.log(`       corrupt store raised -> ${err.message}`);
    }
    assert.ok(raised, "corrupt store was read as empty instead of throwing");
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

console.log("\nALL PASS: fence holds, persistence works.");
