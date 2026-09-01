// Runs ONE read-only SQL query in an isolated child process. The parent
// (sqlAdapter.js) SIGKILLs this process if it exceeds the timeout, which is the
// only reliable way to bound wall-clock time here: node:sqlite is fully
// synchronous and exposes no sqlite3_interrupt, so a watchdog in the same
// process (the approach ../src/sql_adapter.py uses) cannot fire while a query
// is running. A separate process can always be killed by the OS.
//
// Protocol: read a JSON job { dbPath, query, params, maxRows } from stdin, write
// exactly one JSON line to stdout, exit 0:
//   { "ok": true,  "columns": [...], "rows": [[...]], "truncated": bool }
//   { "ok": false, "errorClass": "...", "message": "..." }
// No output / non-zero exit / a signal means the parent killed it or it crashed.

import { constants, DatabaseSync } from "node:sqlite";

function readStdin() {
  return new Promise((resolve, reject) => {
    let buf = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (d) => (buf += d));
    process.stdin.on("end", () => resolve(buf));
    process.stdin.on("error", reject);
  });
}

function classify(message) {
  const m = String(message).toLowerCase();
  if (m.includes("not authorized"))
    return ["ValidationError", "ATTACH/DETACH is not permitted by this adapter."];
  if (m.includes("readonly") || m.includes("attempt to write") || m.includes("cannot modify"))
    return ["ValidationError", "this adapter is read-only; the statement tried to modify the database."];
  if (m.includes("locked") || m.includes("busy"))
    return ["Unavailable", "the database is locked by another process; try again shortly."];
  if (m.includes("no such table") || m.includes("no such column") || m.includes("syntax error"))
    return ["QueryError", `the query could not run: ${message}.`];
  if (m.includes("not a database") || m.includes("unable to open") || m.includes("file is not"))
    return [
      "Unavailable",
      `the database could not be opened (${message}). It may be missing, unreadable, or not a SQLite file.`,
    ];
  return ["QueryError", `the query failed: ${message}.`];
}

function emit(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

async function main() {
  const job = JSON.parse(await readStdin());
  const { dbPath, query, params, maxRows } = job;

  let db;
  try {
    db = new DatabaseSync(dbPath, { readOnly: true });
    db.setAuthorizer((action) =>
      action === constants.SQLITE_ATTACH || action === constants.SQLITE_DETACH
        ? constants.SQLITE_DENY
        : constants.SQLITE_OK,
    );
    // Force a header/schema read so a missing or corrupt file fails here,
    // classified as "system unavailable" rather than as a query error.
    db.prepare("SELECT 1 FROM sqlite_master LIMIT 1").get();
  } catch (err) {
    const [, message] = classify(err && err.message);
    emit({ ok: false, errorClass: "Unavailable", message });
    return;
  }

  try {
    const stmt = db.prepare(query);
    const rows = stmt.all(...(params ?? []));
    let columns = [];
    if (rows.length) {
      columns = Object.keys(rows[0]);
    } else if (typeof stmt.columns === "function") {
      columns = stmt.columns().map((c) => c.name ?? c.column ?? String(c));
    }
    const truncated = rows.length > maxRows;
    const trimmed = rows.slice(0, maxRows).map((row) =>
      columns.map((c) => {
        const v = row[c];
        return typeof v === "bigint" ? v.toString() : v;
      }),
    );
    emit({ ok: true, columns, rows: trimmed, truncated });
  } catch (err) {
    const [errorClass, message] = classify(err && err.message);
    emit({ ok: false, errorClass, message });
  } finally {
    try {
      db.close();
    } catch {
      /* already closed */
    }
  }
}

main().catch((err) => {
  emit({ ok: false, errorClass: "QueryError", message: String((err && err.message) || err) });
});
