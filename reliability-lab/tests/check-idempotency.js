#!/usr/bin/env node
// Runs `confirm` twice per order in a scratch data dir (inside data/) and proves the second
// run sends nothing: one sent.log line per order, receipt outcome "duplicate",
// zero vendor attempts. Also proves refused orders are parked once, not twice.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

const DESK = path.join(__dirname, '..', 'desk.js');
// Scratch dir inside the lab's own (git-ignored) data/ folder, so a run never
// touches the real data/sent.log and nothing is written outside reliability-lab/.
const LAB_DATA = path.join(__dirname, '..', 'data');
fs.mkdirSync(LAB_DATA, { recursive: true });
const dataDir = fs.mkdtempSync(path.join(LAB_DATA, 'check-idempotency-'));

function confirm(orderId, mode) {
  const res = spawnSync(process.execPath, [DESK, 'confirm', orderId], {
    env: { ...process.env, VENDOR_MODE: mode, LAB_DATA_DIR: dataDir },
    encoding: 'utf8',
    timeout: 30000,
  });
  if (res.error) throw res.error;
  const lines = res.stdout.trim().split('\n');
  return JSON.parse(lines[lines.length - 1]);
}

function readLines(file) {
  const p = path.join(dataDir, file);
  return fs.existsSync(p) ? fs.readFileSync(p, 'utf8').split('\n').filter(Boolean).map(JSON.parse) : [];
}

function sentFor(orderId) {
  return readLines('sent.log').filter((l) => l.orderId === orderId);
}

// Starts a confirm run without waiting for it, so two can be in flight at once.
function confirmAsync(orderId, mode) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [DESK, 'confirm', orderId], {
      env: { ...process.env, VENDOR_MODE: mode, LAB_DATA_DIR: dataDir },
    });
    let out = '';
    const timer = setTimeout(() => child.kill(), 30000);
    child.stdout.on('data', (chunk) => (out += chunk));
    child.on('error', reject);
    child.on('close', () => {
      clearTimeout(timer);
      const lines = out.trim().split('\n');
      resolve(JSON.parse(lines[lines.length - 1]));
    });
  });
}

let passed = 0;
async function check(name, fn) {
  await fn();
  passed++;
  console.log(`ok - ${name}`);
}

async function main() {
  await check('order 4001 confirmed twice: one line in sent.log, second run reports duplicate: true', () => {
    const first = confirm('4001', 'ok');
    const second = confirm('4001', 'ok');
    const lines = sentFor('4001');
    assert.strictEqual(
      lines.length,
      1,
      `sent.log has ${lines.length} lines for 4001:\n${lines.map((l) => '    ' + JSON.stringify(l)).join('\n')}\n`
    );
    assert.strictEqual(first.duplicate, false);
    assert.strictEqual(second.duplicate, true, 'second run must report duplicate: true');
  });

  await check('two confirms for one order at the same moment: sent once (claim before send)', async () => {
    const [a, b] = await Promise.all([confirmAsync('4002', 'ok'), confirmAsync('4002', 'ok')]);
    assert.strictEqual(sentFor('4002').length, 1, `sent.log has ${sentFor('4002').length} lines for 4002`);
    assert.deepStrictEqual([a.duplicate, b.duplicate].sort(), [false, true]);
  });

  await check('ok mode: second confirm is a duplicate, sent once, gate not re-run', () => {
    const first = confirm('9001', 'ok');
    const second = confirm('9001', 'ok');
    assert.strictEqual(first.outcome, 'sent');
    assert.strictEqual(first.gateScore, 100);
    assert.strictEqual(second.outcome, 'duplicate');
    assert.strictEqual(second.attempts, 0, 'vendor must not be called for a duplicate');
    assert.strictEqual(second.gateScore, 100, 'duplicate reports the stored gate score');
    assert.notStrictEqual(first.correlationId, second.correlationId, 'each run has its own correlation id');
    assert.strictEqual(sentFor('9001').length, 1);
  });

  await check('down mode: fallback is sent once; second confirm is a duplicate', () => {
    const first = confirm('9002', 'down');
    const second = confirm('9002', 'down');
    assert.strictEqual(first.outcome, 'fallback');
    assert.strictEqual(second.outcome, 'duplicate');
    assert.strictEqual(second.attempts, 0);
    assert.strictEqual(sentFor('9002').length, 1);
    assert.strictEqual(sentFor('9002')[0].fallback, true);
  });

  await check('garbage mode: never sent, parked exactly once across two runs', () => {
    const first = confirm('9003', 'garbage');
    const second = confirm('9003', 'garbage');
    assert.strictEqual(first.outcome, 'dead-lettered');
    assert.strictEqual(second.outcome, 'dead-lettered');
    assert.strictEqual(sentFor('9003').length, 0);
    const rows = readLines('dead-letter.jsonl').filter((r) => r.orderId === '9003');
    assert.strictEqual(rows.length, 1);
    assert.strictEqual(rows[0].correlationId, second.correlationId, 'row carries the latest run id');
  });

  console.log(`\ncheck-idempotency: ${passed} passed, 0 failed`);
}

main()
  .catch((err) => {
    console.error(`not ok - ${err.message}`);
    console.error(`\ncheck-idempotency: ${passed} passed, 1 failed (scratch dir kept: ${dataDir})`);
    process.exitCode = 1;
  })
  .finally(() => {
    if (!process.exitCode) fs.rmSync(dataDir, { recursive: true, force: true });
  });
