import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { performance } from "node:perf_hooks";
import { DatabaseSync } from "node:sqlite";

import { MAX_TIMEOUT_SECONDS, SqlAdapterError, runSqlQuery } from "./sqlAdapter.js";

// Unit tests for sqlAdapter — the Node mirror of ../src/test_sql_adapter.py.
// Input validation, the path fence, the timeout, and graceful failure when the
// SQLite "system" is missing, corrupt, or the query is bad. No framework:
// assertions plus an exit code. Each interesting failure is printed.
//
// Run from the nodejs/ folder:  node test-sqlAdapter.js   (or: npm run test:sql)

let failed = false;

async function run(name, fn) {
  try {
    await fn();
    console.log(`PASS: ${name}`);
  } catch (err) {
    failed = true;
    console.error(`FAIL: ${name}: ${err && err.message}`);
  }
}

function makeDb(dir, name = "incidents.db") {
  const db = new DatabaseSync(path.join(dir, name));
  db.exec(`
    CREATE TABLE incidents (id INTEGER PRIMARY KEY, severity TEXT, service TEXT);
    INSERT INTO incidents (severity, service) VALUES
      ('high', 'ingest'), ('low', 'ingest'), ('high', 'transform'),
      ('medium', 'load'), ('high', 'load');
  `);
  db.close();
  return name;
}

async function expectError(fn, errorClass) {
  try {
    await fn();
  } catch (err) {
    assert.ok(err instanceof SqlAdapterError, `expected SqlAdapterError, got ${err}`);
    assert.equal(
      err.errorClass,
      errorClass,
      `expected ${errorClass}, got ${err.errorClass}: ${err.message}`,
    );
    return err;
  }
  throw new Error(`expected SqlAdapterError[${errorClass}], nothing was thrown`);
}

function tmp() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "mcp-sql-"));
}

await run("validation runs before any DB access", async () => {
  const missingRoot = path.join(os.tmpdir(), "definitely-not-here-xyz");
  const cases = [
    ["empty query", { database: "x.db", query: "   " }],
    ["write statement", { database: "x.db", query: "DELETE FROM incidents" }],
    ["DDL statement", { database: "x.db", query: "DROP TABLE incidents" }],
    ["two statements", { database: "x.db", query: "SELECT 1; SELECT 2" }],
    ["bad timeout (0)", { database: "x.db", query: "SELECT 1", timeoutSeconds: 0 }],
    ["bad timeout (big)", { database: "x.db", query: "SELECT 1", timeoutSeconds: 999 }],
    ["bad maxRows", { database: "x.db", query: "SELECT 1", maxRows: 0 }],
    ["params not array", { database: "x.db", query: "SELECT 1", params: "nope" }],
    ["param wrong type", { database: "x.db", query: "SELECT ?", params: [{ a: 1 }] }],
    ["ATTACH anywhere", { database: "x.db", query: "SELECT 1 /* then */ ATTACH x" }],
  ];
  for (const [label, kwargs] of cases) {
    const exc = await expectError(() => runSqlQuery({ dataRoot: missingRoot, ...kwargs }), "ValidationError");
    console.log(`       ${label}: ${exc}`);
  }
});

await run("happy path with a bound parameter", async () => {
  const root = tmp();
  try {
    const db = makeDb(root);
    const out = await runSqlQuery({
      database: db,
      query:
        "SELECT service, COUNT(*) AS n FROM incidents WHERE severity = ? GROUP BY service ORDER BY service",
      params: ["high"],
      dataRoot: root,
    });
    assert.deepEqual(out.columns, ["service", "n"]);
    assert.deepEqual(out.rows, [
      ["ingest", 1],
      ["load", 1],
      ["transform", 1],
    ]);
    assert.equal(out.row_count, 3);
    assert.equal(out.truncated, false);
    console.log(`       rows=${JSON.stringify(out.rows)} elapsed_ms=${out.elapsed_ms}`);
  } finally {
    fs.rmSync(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  }
});

await run("maxRows truncates", async () => {
  const root = tmp();
  try {
    const db = makeDb(root);
    const out = await runSqlQuery({
      database: db,
      query: "SELECT id FROM incidents ORDER BY id",
      maxRows: 2,
      dataRoot: root,
    });
    assert.equal(out.row_count, 2);
    assert.equal(out.truncated, true);
  } finally {
    fs.rmSync(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  }
});

await run("missing database -> Unavailable", async () => {
  const root = tmp();
  try {
    const exc = await expectError(
      () => runSqlQuery({ database: "nope.db", query: "SELECT 1", dataRoot: root }),
      "Unavailable",
    );
    assert.match(String(exc).toLowerCase(), /not found/);
    console.log(`       ${exc}`);
  } finally {
    fs.rmSync(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  }
});

await run("corrupt database -> Unavailable", async () => {
  const root = tmp();
  try {
    fs.writeFileSync(path.join(root, "bad.db"), "this is definitely not a sqlite file");
    const exc = await expectError(
      () => runSqlQuery({ database: "bad.db", query: "SELECT 1", dataRoot: root }),
      "Unavailable",
    );
    console.log(`       ${exc}`);
  } finally {
    fs.rmSync(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  }
});

await run("path fence rejects escape", async () => {
  const root = tmp();
  try {
    const exc = await expectError(
      () => runSqlQuery({ database: "../../../../etc/passwd", query: "SELECT 1", dataRoot: root }),
      "ValidationError",
    );
    assert.match(String(exc), /escapes/);
    console.log(`       ${exc}`);
  } finally {
    fs.rmSync(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  }
});

await run("ATTACH rejected", async () => {
  const root = tmp();
  try {
    const db = makeDb(root);
    const exc = await expectError(
      () =>
        runSqlQuery({
          database: db,
          query: "ATTACH DATABASE '/etc/hosts' AS evil",
          dataRoot: root,
        }),
      "ValidationError",
    );
    console.log(`       ${exc}`);
  } finally {
    fs.rmSync(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  }
});

await run("write via WITH blocked by readOnly", async () => {
  const root = tmp();
  try {
    const db = makeDb(root);
    const exc = await expectError(
      () =>
        runSqlQuery({
          database: db,
          query: "WITH x AS (SELECT 1) DELETE FROM incidents",
          dataRoot: root,
        }),
      "ValidationError",
    );
    assert.match(String(exc), /read-only/);
    console.log(`       ${exc}`);
  } finally {
    fs.rmSync(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  }
});

await run("broken query -> QueryError", async () => {
  const root = tmp();
  try {
    const db = makeDb(root);
    const exc = await expectError(
      () => runSqlQuery({ database: db, query: "SELECT * FROM no_such_table", dataRoot: root }),
      "QueryError",
    );
    console.log(`       ${exc}`);
  } finally {
    fs.rmSync(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  }
});

await run("slow query times out, no hang", async () => {
  const root = tmp();
  try {
    const db = makeDb(root);
    const slow =
      "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 2000000000) " +
      "SELECT COUNT(*) FROM c";
    const start = performance.now();
    const exc = await expectError(
      () => runSqlQuery({ database: db, query: slow, timeoutSeconds: 0.5, dataRoot: root }),
      "Timeout",
    );
    const elapsed = (performance.now() - start) / 1000;
    assert.ok(elapsed < MAX_TIMEOUT_SECONDS, `took ${elapsed.toFixed(1)}s — timeout did not fire`);
    console.log(`       cancelled after ${elapsed.toFixed(2)}s: ${exc}`);
  } finally {
    fs.rmSync(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  }
});

if (failed) {
  console.error("\nSOME TESTS FAILED");
  process.exit(1);
}
console.log("\nALL PASS: sqlAdapter validates, fences, times out, and fails gracefully.");
