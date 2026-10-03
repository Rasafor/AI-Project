// Generic call protections: a deadline per attempt, a capped, backed-off
// retry around it, a circuit breaker around the retry, a fallback, and a
// dead-letter file. Knows nothing about orders or vendors.

const fs = require('fs');
const path = require('path');

class TimeoutError extends Error {
  constructor(ms) {
    super(`Timed out after ${ms}ms`);
    this.name = 'TimeoutError';
  }
}

class UpstreamUnavailable extends Error {
  constructor(message) {
    super(message || 'Upstream is unavailable');
    this.name = 'UpstreamUnavailable';
  }
}

class BadResponse extends Error {
  constructor(message) {
    super(message || 'Response failed validation');
    this.name = 'BadResponse';
  }
}

class QualityGateRejected extends Error {
  constructor({ score, reasons, threshold }) {
    super(`Quality score ${score} is below ${threshold}: ${reasons.join('; ')}`);
    this.name = 'QualityGateRejected';
    this.score = score;
    this.reasons = reasons;
  }
}

class BreakerOpen extends Error {
  constructor(remainingMs) {
    super(`Circuit breaker is open; next probe allowed in ${Math.ceil(remainingMs / 1000)}s`);
    this.name = 'BreakerOpen';
  }
}

// Only failures that might succeed on a second try are worth retrying.
// A BadResponse is a wrong answer, not a dropped connection — retrying
// it just asks the same broken question again.
const RETRYABLE_ERROR_NAMES = new Set(['TimeoutError', 'UpstreamUnavailable']);

function isRetryable(err) {
  return RETRYABLE_ERROR_NAMES.has(err.name);
}

function withTimeout(fn, ms) {
  return new Promise((resolve, reject) => {
    let settled = false;

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      reject(new TimeoutError(ms));
    }, ms);

    Promise.resolve()
      .then(fn)
      .then((result) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(result);
      })
      .catch((err) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(err);
      });
  });
}

async function retry(fn, { attempts = 3, baseDelayMs = 500, onAttempt } = {}) {
  let lastErr;

  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      const result = await fn(attempt);
      if (onAttempt) onAttempt({ attempt, outcome: 'success' });
      return result;
    } catch (err) {
      lastErr = err;
      if (onAttempt) onAttempt({ attempt, outcome: 'failure', errorName: err.name });

      const isLastAttempt = attempt === attempts;
      if (!isRetryable(err) || isLastAttempt) {
        throw err;
      }

      // Exponential growth so a thousand retrying clients don't all land on
      // the vendor in the same second; jitter spreads them further apart.
      const backoff = baseDelayMs * 2 ** (attempt - 1);
      const jitter = Math.random() * baseDelayMs * 0.2;
      await sleep(backoff + jitter);
    }
  }

  throw lastErr;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Circuit breaker, meant to wrap the WHOLE retried operation: one failed
// operation (all its attempts) counts as one failure. State lives in a JSON
// file so separate runs of a command share it.
//   closed    -> calls pass; `failureThreshold` consecutive failures -> open
//   open      -> calls fail instantly with BreakerOpen until `cooldownMs` passes
//   half-open -> exactly one probe is in flight; success -> closed, failure -> open
// A probe that never reports back (process killed) is treated as stale after
// another cooldown, so the breaker cannot get stuck half-open forever.
// Not handled: two processes racing on the file at the same instant.
const CLOSED_STATE = { state: 'closed', consecutiveFailures: 0, openedAt: null };

function createBreaker({ statePath, failureThreshold = 3, cooldownMs = 10000 }) {
  function load() {
    try {
      return JSON.parse(fs.readFileSync(statePath, 'utf8'));
    } catch (err) {
      if (err.code !== 'ENOENT') {
        console.error(`Breaker state unreadable (${err.name}: ${err.message}); treating as closed`);
      }
      return { ...CLOSED_STATE };
    }
  }

  async function run(fn, { log = console.log } = {}) {
    const current = load();

    if (current.state !== 'closed') {
      const since = current.state === 'open' ? current.openedAt : current.probeStartedAt;
      const elapsed = Date.now() - since;
      if (elapsed < cooldownMs) throw new BreakerOpen(cooldownMs - elapsed);
      writeJsonAtomic(statePath, { ...current, state: 'half-open', probeStartedAt: Date.now() });
      log('Breaker half-open: letting one probe call through');
    }

    try {
      const result = await fn();
      writeJsonAtomic(statePath, { ...CLOSED_STATE });
      return result;
    } catch (err) {
      const failures = current.consecutiveFailures + 1;
      const trips = current.state !== 'closed' || failures >= failureThreshold;
      writeJsonAtomic(
        statePath,
        trips
          ? { state: 'open', consecutiveFailures: failures, openedAt: Date.now() }
          : { state: 'closed', consecutiveFailures: failures, openedAt: null }
      );
      if (trips) log(`Breaker OPEN after ${failures} consecutive failed operation(s)`);
      throw err;
    }
  }

  return { run, state: load };
}

// Runs fn; if it fails with one of the named errors, runs fallbackFn instead.
// Any other error (e.g. BadResponse) propagates untouched — never disguised.
async function withFallback(fn, fallbackFn, { on, log = console.log }) {
  try {
    return { value: await fn(), fallback: false };
  } catch (err) {
    if (!on.includes(err.name)) throw err;
    log(`Falling back after ${err.name}`);
    return { value: await fallbackFn(err), fallback: true, cause: err.name };
  }
}

// Quality gate. Reliability gets an answer back; this decides whether it is
// worth using. Deterministic, no I/O.
const REFUSAL_PHRASES = ['as an ai', 'i cannot', "i'm sorry", 'as a language model'];
const QUALITY_THRESHOLD = 70;

function scoreDetail(message, id) {
  const text = typeof message === 'string' ? message : '';
  const reasons = [];
  let points = 0;

  // Whole token: not preceded or followed by a letter or digit, so "5001"
  // does not match inside "50012". The id is escaped — it is user input.
  const escaped = String(id).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  if (new RegExp(`(?<![A-Za-z0-9])${escaped}(?![A-Za-z0-9])`).test(text)) points += 40;
  else reasons.push(`-40 does not contain order id ${id} as a whole token`);

  const lower = text.toLowerCase();
  const found = REFUSAL_PHRASES.filter((p) => lower.includes(p));
  if (found.length === 0) points += 30;
  else reasons.push(`-30 contains refusal phrase(s): ${found.map((p) => JSON.stringify(p)).join(', ')}`);

  if (text.length >= 20 && text.length <= 300) points += 30;
  else reasons.push(`-30 length ${text.length} is outside 20..300`);

  return { score: points, reasons };
}

function score(message, id) {
  return scoreDetail(message, id).score;
}

// Returns { score, reasons } when the message passes; throws QualityGateRejected otherwise.
function qualityGate(message, id, { threshold = QUALITY_THRESHOLD } = {}) {
  const detail = scoreDetail(message, id);
  if (detail.score < threshold) throw new QualityGateRejected({ ...detail, threshold });
  return detail;
}

class ClaimPending extends Error {
  constructor(key, claimedAt) {
    super(`Key ${key} was claimed at ${claimedAt} and that run has not finished`);
    this.name = 'ClaimPending';
  }
}

class KeyStoreBusy extends Error {
  constructor(lockPath) {
    super(`Could not lock ${lockPath} in time`);
    this.name = 'KeyStoreBusy';
  }
}

const DEFAULT_KEYS_PATH = path.join(__dirname, 'data', 'keys.json');

// Runs fn at most once per idempotency key, across separate processes.
//   1. CLAIM: under a file lock, if the key is new, write it as "claimed" BEFORE
//      fn runs. A second arrival now sees the claim instead of "not sent yet".
//   2. RUN fn once.
//   3. STORE: mark the key "done" with fn's result. Later calls return that
//      result with duplicate=true and never call fn.
// A caller that finds someone else's claim waits (up to waitMs) for it to
// finish and then returns the stored result. If fn fails, the claim is
// released, so a retry or replay can run it again.
// Not handled automatically: a process killed after fn's side effect but before
// STORE leaves the key "claimed" forever. Later calls fail with ClaimPending
// (and are dead-lettered) rather than risk a second send; a person checks
// sent.log and removes the key from keys.json.
async function runOnce(key, fn, { storePath = DEFAULT_KEYS_PATH, waitMs = 10000, pollMs = 50 } = {}) {
  const lockPath = `${storePath}.lock`;
  const update = (change) =>
    withFileLock(lockPath, () => {
      const store = readJson(storePath);
      const outcome = change(store);
      writeJsonAtomic(storePath, store);
      return outcome;
    });

  const deadline = Date.now() + waitMs;
  for (;;) {
    const existing = update((store) => {
      if (store[key]) return store[key];
      store[key] = { state: 'claimed', claimedAt: new Date().toISOString(), pid: process.pid };
      return null;
    });
    if (existing === null) break; // the claim is ours
    if (existing.state === 'done') return { duplicate: true, result: existing.result };
    if (Date.now() >= deadline) throw new ClaimPending(key, existing.claimedAt);
    await sleep(pollMs);
  }

  let result;
  try {
    result = await fn();
  } catch (err) {
    try {
      update((store) => {
        delete store[key];
      });
    } catch (releaseErr) {
      console.error(`runOnce: could not release claim ${key} (${releaseErr.name}: ${releaseErr.message})`);
      err.claimReleaseError = releaseErr;
    }
    throw err;
  }

  update((store) => {
    store[key] = { state: 'done', result, completedAt: new Date().toISOString() };
  });
  return { duplicate: false, result };
}

function readJson(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (err) {
    if (err.code === 'ENOENT') return {};
    throw err;
  }
}

// Mutual exclusion across processes: creating the lock file with 'wx' fails if
// it already exists, and the OS makes that check-and-create atomic. A lock older
// than staleMs belongs to a process that died holding it and is removed.
// Gives up with KeyStoreBusy after timeoutMs rather than waiting forever.
function withFileLock(lockPath, fn, { timeoutMs = 3000, staleMs = 5000 } = {}) {
  fs.mkdirSync(path.dirname(lockPath), { recursive: true });
  const start = Date.now();
  for (;;) {
    try {
      fs.closeSync(fs.openSync(lockPath, 'wx'));
      break;
    } catch (err) {
      if (err.code !== 'EEXIST') throw err;
    }
    let age;
    try {
      age = Date.now() - fs.statSync(lockPath).mtimeMs;
    } catch (err) {
      if (err.code === 'ENOENT') continue; // released between our two calls; try again
      throw err;
    }
    if (age > staleMs) {
      fs.rmSync(lockPath, { force: true });
      continue;
    }
    if (Date.now() - start > timeoutMs) throw new KeyStoreBusy(lockPath);
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 5); // short synchronous pause
  }
  try {
    return fn();
  } finally {
    fs.rmSync(lockPath, { force: true });
  }
}

// Dead-letter file (one JSON object per line), keyed so the same item is
// parked once, not once per failure. Rewritten atomically on every change.
function createDeadLetter(filePath, { keyOf }) {
  function list() {
    let text;
    try {
      text = fs.readFileSync(filePath, 'utf8');
    } catch (err) {
      if (err.code === 'ENOENT') return [];
      throw err;
    }
    return text.split('\n').filter(Boolean).map((line) => JSON.parse(line));
  }

  function write(entries) {
    const text = entries.map((e) => JSON.stringify(e) + '\n').join('');
    writeFileAtomic(filePath, text);
  }

  function add(entry) {
    write([...list().filter((e) => keyOf(e) !== keyOf(entry)), entry]);
  }

  function remove(key) {
    write(list().filter((e) => keyOf(e) !== key));
  }

  return { list, add, remove };
}

function writeJsonAtomic(filePath, value) {
  writeFileAtomic(filePath, JSON.stringify(value, null, 2) + '\n');
}

function writeFileAtomic(filePath, text) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const tmp = `${filePath}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, text);
  fs.renameSync(tmp, filePath);
}

module.exports = {
  withTimeout,
  retry,
  isRetryable,
  createBreaker,
  withFallback,
  createDeadLetter,
  score,
  qualityGate,
  runOnce,
  ClaimPending,
  KeyStoreBusy,
  TimeoutError,
  UpstreamUnavailable,
  BadResponse,
  BreakerOpen,
  QualityGateRejected,
};
