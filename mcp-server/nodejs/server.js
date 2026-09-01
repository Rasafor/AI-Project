// Node.js / TypeScript-SDK reference implementation of the notes MCP
// server. Same tool ("add_note"), resource ("notes://all"), and prompt
// ("capture_note") as ../src/server.py — kept side by side deliberately,
// as a comparison of how the two official MCP SDKs express the same
// design. ../src (Python) is the primary, maintained version of this
// project; this folder is a learning reference, not a second product.
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { randomUUID } from "node:crypto";
import { z } from "zod";

import { loadNotes, saveNotes } from "./notesStore.js";
import { runSqlQuery, SqlAdapterError } from "./sqlAdapter.js";

// Notes are persisted to nodejs/data/notes.json by notesStore, which fences
// every file access to that one directory (see notesStore.resolveWithin and
// ADR-0001 Consequences). This array is the in-process working copy; each
// mutation is written straight back through saveNotes().
//
// No lock here (unlike ../src/server.py): the Node SDK runs each tool handler's
// synchronous body to completion on the one event-loop thread, so two add_note
// calls cannot interleave their save + push. add_note still writes the file
// before touching this array, so a failed save never leaves memory ahead of disk.
const notes = loadNotes();

const server = new McpServer({
  name: "notes-server",
  version: "1.0.0",
});

// --- TOOL: add_note -----------------------------------------------------
// Tools are actions the MODEL decides to invoke. The schema is the contract
// the model reads to know what arguments are valid — treat it exactly like
// an HTTP route's request validation: reject anything that doesn't match.

// Return a note this add would duplicate, or undefined. With an
// idempotency_key: match that key (it identifies the operation, so the stored
// note wins even if title/content now differ). Without one: match an exact
// title+content pair, so a plain retry does not create a second note.
// Mirrors ../src/server.py's _existing_note.
function existingNote(title, content, idempotencyKey) {
  return notes.find((n) =>
    idempotencyKey != null
      ? n.idempotencyKey === idempotencyKey
      : n.title === title && n.content === content,
  );
}

server.tool(
  "add_note",
  "Add a note to the store, or return the existing one if this add is a duplicate " +
    "(same idempotency_key, or identical title+content with no key). Returns the note's id.",
  {
    title: z.string().min(1).max(200).describe("Short title for the note"),
    content: z.string().min(1).max(5000).describe("Body text of the note"),
    idempotency_key: z
      .string()
      .max(200)
      .optional()
      .describe(
        "Optional stable id for this add. Passing the same key again returns the note " +
          "already stored under it instead of creating a duplicate — use it to make retries safe.",
      ),
  },
  async ({ title, content, idempotency_key }) => {
    const existing = existingNote(title, content, idempotency_key);
    if (existing) {
      return {
        content: [
          {
            type: "text",
            text: `Note "${existing.title}" already stored with id ${existing.id} (no duplicate created).`,
          },
        ],
      };
    }

    const note = {
      id: randomUUID(),
      title,
      content,
      createdAt: new Date().toISOString(),
    };
    if (idempotency_key != null) note.idempotencyKey = idempotency_key;

    // Persist first, then update memory. If saveNotes throws, the call fails
    // without ever reporting the note as stored, and `notes` still matches the
    // file. Matches ../src/server.py.
    saveNotes([...notes, note]);
    notes.push(note);

    return {
      content: [
        {
          type: "text",
          text: `Note "${title}" added with id ${note.id}.`,
        },
      ],
    };
  }
);

// --- TOOL: run_sql_query ----------------------------------------------
// The adapter for the "SQL" system named in .colaberry/plan.json (REQ-008,
// STORY-003). Mirror of ../src/server.py's run_sql_query. Implementation is in
// sqlAdapter.js; this is just the MCP contract. Every argument is declared and
// bounded here (zod), AND re-validated inside the adapter. A handled failure
// comes back as SqlAdapterError and is returned to the caller as isError:true
// with the message — never an unhandled throw.
server.tool(
  "run_sql_query",
  "Run a read-only SQL query against a SQLite data source and return the rows as JSON. " +
    "Validates every argument, fences the database path, enforces an explicit timeout, and " +
    "returns a structured error (not a crash) when the database is missing, corrupt, locked, " +
    "or the query is invalid.",
  {
    database: z
      .string()
      .min(1)
      .max(500)
      .describe(
        "Path to a SQLite database file, relative to the SQL data root (env " +
          "MCP_SQL_DATA_ROOT, default nodejs/data/). Paths that resolve outside that " +
          "directory are rejected.",
      ),
    query: z
      .string()
      .min(1)
      .max(20000)
      .describe(
        "One read-only SQL statement (SELECT / WITH / EXPLAIN / PRAGMA). Write and DDL " +
          "statements, multiple statements, and ATTACH are rejected.",
      ),
    params: z
      .array(z.union([z.string(), z.number(), z.boolean(), z.null()]))
      .max(100)
      .optional()
      .describe(
        "Optional positional values bound to '?' placeholders in the query. Use these " +
          "instead of formatting values into the SQL.",
      ),
    timeout_seconds: z
      .number()
      .gt(0)
      .lte(30)
      .default(5)
      .describe("Abort the query if it runs longer than this."),
    max_rows: z
      .number()
      .int()
      .gte(1)
      .lte(1000)
      .default(100)
      .describe("Max rows returned; extras are dropped and 'truncated' is set true."),
  },
  async ({ database, query, params, timeout_seconds, max_rows }) => {
    try {
      const result = await runSqlQuery({
        database,
        query,
        params: params ?? null,
        timeoutSeconds: timeout_seconds,
        maxRows: max_rows,
      });
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (err) {
      if (err instanceof SqlAdapterError) {
        return { content: [{ type: "text", text: err.toString() }], isError: true };
      }
      throw err;
    }
  },
);

// --- RESOURCE: notes://all -----------------------------------------------
// Resources are DATA the host app can attach to context (e.g. a user picks
// it, or the app auto-attaches it). The model doesn't "call" this the way
// it calls a tool — it's exposed as addressable content behind a URI.
server.resource(
  "all-notes",
  "notes://all",
  {
    description: "JSON list of every note currently in the store",
    mimeType: "application/json",
  },
  async (uri) => {
    return {
      contents: [
        {
          uri: uri.href,
          mimeType: "application/json",
          text: JSON.stringify(notes, null, 2),
        },
      ],
    };
  }
);

// --- PROMPT: capture_note -------------------------------------------------
// Prompts are USER-controlled workflow templates: they appear in the client
// UI (e.g. as a slash command or menu item) and are invoked explicitly by
// the person, not silently chosen by the model. This one packages the
// "correct" way to use add_note so the user doesn't have to know the tool's
// argument shape or write the instruction themselves each time.
server.prompt(
  "capture_note",
  "Turn a raw block of text into a structured note and save it with add_note",
  {
    raw_text: z
      .string()
      .min(1)
      .describe("Unstructured text to turn into a title + note body"),
  },
  ({ raw_text }) => ({
    messages: [
      {
        role: "user",
        content: {
          type: "text",
          text:
            "Read the text below. Derive a concise title (max 10 words) " +
            "and a cleaned-up body (fix obvious typos, keep the meaning " +
            "intact). Then call the add_note tool with that title and " +
            `content.\n\nText:\n"""\n${raw_text}\n"""`,
        },
      },
    ],
  })
);

// --- Transport ------------------------------------------------------------
// stdio is the standard transport for a locally-spawned server (Claude
// Desktop, Claude Code, most CLI-based MCP clients launch the server as a
// child process and speak JSON-RPC over its stdin/stdout).
const transport = new StdioServerTransport();
await server.connect(transport);
