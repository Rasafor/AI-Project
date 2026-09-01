// SQL query adapter — the Node.js mirror of ../src/sql_adapter.py.
//
// Plan reference: .colaberry/plan.json `derived.systems: ["SQL"]`, REQ-008
// ("connect to data sources for log and SQL analysis"), STORY-003.
//
// Backend: the built-in `node:sqlite` module (Node >= 22.5) — no dependency to
// install. The "system" is a database file under SQL_DATA_ROOT.
//
// Same guarantees as the Python adapter:
//   - every argument is validated before any file/DB access (validate()).
//   - the database path is fenced to SQL_DATA_ROOT (shared guard in fsFence.js).
//   - the query runs read-only; ATTACH/DETACH is rejected by keyword AND denied
//     by an authorizer in the child.
//   - an explicit timeout bounds wall-clock time.
//   - failures raise SqlAdapterError (tagged error class), never a bare throw
//     from the driver and never a hang.
//
// One implementation difference from Python, forced by the runtime: node:sqlite
// is synchronous with no interrupt call, so a same-process watchdog cannot stop
// a running query. Instead the query runs in a short-lived child process
// (sqlChild.js) that the parent SIGKILLs on timeout — the parent thread never
// blocks, and the OS reclaims a runaway query.

import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { performance } from "node:perf_hooks";
import { fileURLToPath } from "node:url";

import { resolveWithin } from "./fsFence.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CHILD = path.join(HERE, "sqlChild.js");

// Narrowest root that still does the job; override with MCP_SQL_DATA_ROOT.
export const SQL_DATA_ROOT = process.env.MCP_SQL_DATA_ROOT
  ? path.resolve(process.env.MCP_SQL_DATA_ROOT)
  : path.join(HERE, "data");

export const DEFAULT_TIMEOUT_SECONDS = 5;
export const MAX_TIMEOUT_SECONDS = 30;
export const DEFAULT_MAX_ROWS = 100;
export const MAX_MAX_ROWS = 1000;
export const MAX_QUERY_CHARS = 20000;
export const MAX_PARAMS = 100;

// Leading keywords that can never be read-only. `readOnly: true` on the
// connection is the real enforcement; this set produces a clearer message.
const WRITE_VERBS = new Set([
  "insert", "update", "delete", "replace", "upsert",
  "drop", "create", "alter", "truncate", "rename",
  "attach", "detach", "vacuum", "reindex", "analyze",
  "begin", "commit", "end", "rollback", "savepoint",
  "grant", "revoke",
]);

export class SqlAdapterError extends Error {
  constructor(errorClass, message) {
    super(message);
    this.name = "SqlAdapterError";
    this.errorClass = errorClass; // ValidationError | Unavailable | Timeout | QueryError
  }

  toString() {
    return `[${this.errorClass}] ${this.message}`;
  }
}

function stripComments(sql) {
  return sql.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/--[^\n]*/g, " ");
}

function validate(database, query, params, timeoutSeconds, maxRows) {
  if (typeof database !== "string" || !database.trim()) {
    throw new SqlAdapterError(
      "ValidationError",
      "`database` must be a non-empty string: a path to a SQLite file under the SQL data root.",
    );
  }
  if (typeof query !== "string" || !query.trim()) {
    throw new SqlAdapterError("ValidationError", "`query` must be a non-empty SQL string.");
  }
  if (query.length > MAX_QUERY_CHARS) {
    throw new SqlAdapterError(
      "ValidationError",
      `\`query\` is ${query.length} characters; the limit is ${MAX_QUERY_CHARS}.`,
    );
  }

  const body = stripComments(query).trim().replace(/;+\s*$/, "").trim();
  if (body.includes(";")) {
    throw new SqlAdapterError(
      "ValidationError",
      "one SQL statement per call; multiple ';'-separated statements were found.",
    );
  }
  const first = (body.split(/\s+/)[0] || "").toLowerCase();
  if (!first) {
    throw new SqlAdapterError("ValidationError", "could not read a leading SQL keyword from `query`.");
  }
  if (WRITE_VERBS.has(first)) {
    throw new SqlAdapterError(
      "ValidationError",
      `this adapter is read-only; a statement beginning with '${first.toUpperCase()}' is ` +
        "rejected. Use SELECT, WITH, EXPLAIN or PRAGMA.",
    );
  }
  if (/\b(attach|detach)\b/i.test(body)) {
    throw new SqlAdapterError("ValidationError", "ATTACH/DETACH is not permitted by this adapter.");
  }

  let list = params;
  if (list === null || list === undefined) list = [];
  if (!Array.isArray(list)) {
    throw new SqlAdapterError("ValidationError", "`params` must be an array when provided.");
  }
  if (list.length > MAX_PARAMS) {
    throw new SqlAdapterError(
      "ValidationError",
      `\`params\` has ${list.length} items; the limit is ${MAX_PARAMS}.`,
    );
  }
  list.forEach((value, i) => {
    const t = typeof value;
    if (value !== null && t !== "string" && t !== "number" && t !== "boolean") {
      throw new SqlAdapterError(
        "ValidationError",
        `\`params[${i}]\` is ${value === null ? "null" : t}; only string, number, boolean and ` +
          "null are allowed.",
      );
    }
  });

  if (typeof timeoutSeconds !== "number" || Number.isNaN(timeoutSeconds)) {
    throw new SqlAdapterError("ValidationError", "`timeoutSeconds` must be a number.");
  }
  if (!(timeoutSeconds > 0 && timeoutSeconds <= MAX_TIMEOUT_SECONDS)) {
    throw new SqlAdapterError(
      "ValidationError",
      `\`timeoutSeconds\` must be greater than 0 and at most ${MAX_TIMEOUT_SECONDS}.`,
    );
  }

  if (!Number.isInteger(maxRows)) {
    throw new SqlAdapterError("ValidationError", "`maxRows` must be an integer.");
  }
  if (!(maxRows >= 1 && maxRows <= MAX_MAX_ROWS)) {
    throw new SqlAdapterError("ValidationError", `\`maxRows\` must be between 1 and ${MAX_MAX_ROWS}.`);
  }

  // SQLite has no boolean type; bind booleans as 0/1.
  return list.map((v) => (typeof v === "boolean" ? (v ? 1 : 0) : v));
}

export async function runSqlQuery({
  database,
  query,
  params = null,
  timeoutSeconds = DEFAULT_TIMEOUT_SECONDS,
  maxRows = DEFAULT_MAX_ROWS,
  dataRoot = null,
} = {}) {
  const normParams = validate(database, query, params, timeoutSeconds, maxRows);
  const root = dataRoot || SQL_DATA_ROOT;

  let dbPath;
  try {
    dbPath = resolveWithin(root, database, "database path");
  } catch (err) {
    throw new SqlAdapterError("ValidationError", err.message);
  }

  if (!fs.existsSync(dbPath)) {
    throw new SqlAdapterError(
      "Unavailable",
      `database file not found: ${dbPath} (looked under the SQL data root ${root}). ` +
        "The SQL system is unreachable.",
    );
  }
  if (!fs.statSync(dbPath).isFile()) {
    throw new SqlAdapterError("Unavailable", `the database path is not a file: ${dbPath}.`);
  }

  const started = performance.now();
  const child = spawn(process.execPath, [CHILD], { stdio: ["pipe", "pipe", "ignore"] });
  child.stdin.end(JSON.stringify({ dbPath, query, params: normParams, maxRows }));

  let out = "";
  child.stdout.on("data", (d) => (out += d));

  const outcome = await new Promise((resolve) => {
    const timer = setTimeout(() => resolve({ kind: "timeout" }), timeoutSeconds * 1000);
    child.once("exit", (code, signal) => {
      clearTimeout(timer);
      resolve({ kind: "exit", code, signal });
    });
    child.once("error", (err) => {
      clearTimeout(timer);
      resolve({ kind: "spawn-error", err });
    });
  });

  if (outcome.kind === "timeout") {
    child.kill("SIGKILL");
    // Reap it before returning so no killed process is left holding the
    // database file open (on Windows that would block deleting it).
    await new Promise((resolve) => child.once("exit", resolve));
    throw new SqlAdapterError(
      "Timeout",
      `the query was cancelled after exceeding the ${timeoutSeconds}s timeout. ` +
        `Narrow the query or raise timeoutSeconds (max ${MAX_TIMEOUT_SECONDS}).`,
    );
  }
  if (outcome.kind === "spawn-error") {
    throw new SqlAdapterError(
      "Unavailable",
      `could not start the SQL query worker (${outcome.err.message}).`,
    );
  }

  const line = out.trim().split("\n").filter(Boolean).pop();
  if (!line) {
    throw new SqlAdapterError(
      "Unavailable",
      `the SQL query worker exited without a result (code ${outcome.code}, signal ${outcome.signal}).`,
    );
  }

  let payload;
  try {
    payload = JSON.parse(line);
  } catch {
    throw new SqlAdapterError("QueryError", "the SQL query worker returned an unreadable result.");
  }
  if (!payload.ok) {
    throw new SqlAdapterError(payload.errorClass || "QueryError", payload.message || "the query failed.");
  }

  return {
    database: dbPath,
    columns: payload.columns,
    rows: payload.rows,
    row_count: payload.rows.length,
    truncated: payload.truncated,
    elapsed_ms: Math.round((performance.now() - started) * 10) / 10,
  };
}
