// File-backed persistence for the notes store, fenced to nodejs/data/.
//
// This mirrors ../src/notes_store.py (Python). server.js previously held notes
// in a module-level array that vanished when the process exited; ADR-0001
// (Consequences) requires persistence to be an external store. This is it.
//
// The fence: every path this module opens is first run through resolveWithin(),
// which throws — naming the offending input — for anything resolving outside
// DATA_ROOT (via "..", an absolute path, or a symlink out of the tree). It is
// never a silent clamp or empty return. No client-supplied path reaches here
// today (the filename is hardcoded), so the guard is a safety net; its real job
// is to be the one check any future path-taking surface must call. It is tested
// directly against traversal payloads in test-notesStore.js.
//
// No console.log anywhere in this module: on the stdio transport, stdout is the
// MCP protocol stream (ADR-0001). Failures throw; the SDK surfaces them.

import { randomUUID } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { resolveWithin } from "./fsFence.js";

// Re-exported so existing callers can keep importing it from here.
export { resolveWithin };

const HERE = path.dirname(fileURLToPath(import.meta.url));

// Narrowest root that still does the job: this server's own data directory,
// located relative to THIS FILE — never process.cwd(), which varies with how
// the server is launched and is influenceable by whatever spawns it.
// MCP_NOTES_DATA_ROOT overrides it (config from env); the tests point it at a
// temp directory so they never touch the real store.
export const DATA_ROOT = process.env.MCP_NOTES_DATA_ROOT
  ? path.resolve(process.env.MCP_NOTES_DATA_ROOT)
  : path.join(HERE, "data");

// The only file this store ever reads or writes. Not a parameter, not derived
// from any input.
export const NOTES_FILENAME = "notes.json";

function seedNotes() {
  return [
    {
      id: randomUUID(),
      title: "Welcome",
      content: "This is the first note in the demo store.",
      createdAt: new Date().toISOString(),
    },
  ];
}

// Return the persisted notes array, creating a seeded store on first run. A
// store that exists but cannot be read or parsed throws rather than being
// treated as empty — returning [] here would let the next saveNotes() overwrite
// a file we simply failed to read.
export function loadNotes(root = DATA_ROOT) {
  const file = resolveWithin(root, NOTES_FILENAME);
  if (!fs.existsSync(file)) {
    const notes = seedNotes();
    atomicWrite(file, notes);
    return notes;
  }
  let data;
  try {
    data = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (err) {
    throw new Error(
      `notes store at ${file} could not be read (${err.message}); refusing to ` +
        `continue with an empty store that would overwrite it`,
    );
  }
  if (!Array.isArray(data)) {
    throw new Error(
      `notes store at ${file} is not a JSON array (found ${typeof data})`,
    );
  }
  return data;
}

// Persist `notes` to the fenced store. Idempotent: same array, same file.
export function saveNotes(notes, root = DATA_ROOT) {
  atomicWrite(resolveWithin(root, NOTES_FILENAME), notes);
}

// Write to a temp file in the same directory, then rename over the target, so a
// crash mid-write leaves the previous good store intact rather than a truncated
// file. Concurrent server processes (not the deployed case — see ADR-0001)
// still last-writer-wins; this guards corruption, not lost updates.
function atomicWrite(file, notes) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  // Unique per write (not just per process) so two writers can never scribble
  // on the same temp file. Node's single event-loop thread already serialises
  // synchronous saves, but this keeps atomicWrite correct on its own — matches
  // ../src/notes_store.py.
  const tmp = `${file}.tmp-${process.pid}-${randomUUID()}`;
  fs.writeFileSync(tmp, JSON.stringify(notes, null, 2), "utf8");
  fs.renameSync(tmp, file);
}
