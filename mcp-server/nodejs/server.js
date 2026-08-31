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

// In-memory store. A real server would back this with a file or DB —
// state must survive process restarts if the client expects persistence.
const notes = [
  {
    id: randomUUID(),
    title: "Welcome",
    content: "This is the first note in the demo store.",
    createdAt: new Date().toISOString(),
  },
];

const server = new McpServer({
  name: "notes-server",
  version: "1.0.0",
});

// --- TOOL: add_note -----------------------------------------------------
// Tools are actions the MODEL decides to invoke. The schema is the contract
// the model reads to know what arguments are valid — treat it exactly like
// an HTTP route's request validation: reject anything that doesn't match.
server.tool(
  "add_note",
  "Add a new note to the notes store. Returns the created note's id.",
  {
    title: z.string().min(1).max(200).describe("Short title for the note"),
    content: z.string().min(1).max(5000).describe("Body text of the note"),
  },
  async ({ title, content }) => {
    const note = {
      id: randomUUID(),
      title,
      content,
      createdAt: new Date().toISOString(),
    };
    notes.push(note);

    // Tool results are returned as "content" blocks — usually text,
    // but can include images or embedded resources too.
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
