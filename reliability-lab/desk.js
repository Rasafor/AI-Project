#!/usr/bin/env node
// Order desk:
//   confirm <orderId>  asks the vendor for a message, then appends one JSON
//                      line to data/sent.log. That append is the side effect a
//                      customer would notice.
//   replay             re-runs every order parked in data/dead-letter.jsonl and
//                      removes the ones that get sent.
//
// Layers, outermost first:
//   runOnce( gate( fallback( breaker( retry( timeout( vendor ) ) ) ) ) -> send )
// Anything that still cannot be sent is dead-lettered, never dropped.
// Every run gets a correlation id (identifies the RUN; the order id is the
// idempotency key) and ends with one JSON receipt on stdout.

const fs = require('fs');
const path = require('path');
const { randomUUID } = require('crypto');
const vendor = require('./vendor');
const {
  withTimeout,
  retry,
  createBreaker,
  withFallback,
  createDeadLetter,
  qualityGate,
  runOnce,
  UpstreamUnavailable,
  BadResponse,
} = require('./reliability');

// LAB_DATA_DIR lets tests run against a scratch directory instead of data/.
const DATA_DIR = process.env.LAB_DATA_DIR || path.join(__dirname, 'data');
const LOG_FILE = path.join(DATA_DIR, 'sent.log');
const KEYS_FILE = path.join(DATA_DIR, 'keys.json');

const ATTEMPT_TIMEOUT_MS = 2000;
const RETRY_ATTEMPTS = 3;
const RETRY_BASE_DELAY_MS = 500;

const breaker = createBreaker({
  statePath: path.join(DATA_DIR, 'breaker.json'),
  failureThreshold: 3,
  cooldownMs: 10000,
});

const deadLetter = createDeadLetter(path.join(DATA_DIR, 'dead-letter.jsonl'), {
  keyOf: (entry) => entry.orderId,
});

// Only failures that mean "the vendor is unavailable" earn the template.
// BadResponse and QualityGateRejected are deliberately absent: a wrong
// message is never sent under any name.
const FALLBACK_ON = ['UpstreamUnavailable', 'BreakerOpen'];

class SendFailed extends Error {
  constructor(message) {
    super(message);
    this.name = 'SendFailed';
  }
}

function idempotencyKey(orderId) {
  return `order:${orderId}`;
}

function expectedMessage(orderId) {
  return `Your order ${orderId} is confirmed and will ship within 2 days.`;
}

function fallbackMessage(orderId) {
  return `Your order ${orderId} is confirmed. Full details will follow shortly.`;
}

function runLogger(correlationId) {
  return {
    log: (msg) => console.log(`[cid=${correlationId}] ${msg}`),
    error: (msg) => console.error(`[cid=${correlationId}] ${msg}`),
  };
}

// Transport only: did we get a usable string back in time? Whether the
// content is any good is the quality gate's job, outside the breaker.
async function callVendorOnce(orderId) {
  let message;
  try {
    message = await withTimeout(() => vendor.confirmOrder(orderId), ATTEMPT_TIMEOUT_MS);
  } catch (err) {
    if (err.name === 'TimeoutError') throw err;
    // The vendor's own failure has no useful classification of its own
    // (just "it threw") — that's on us to name.
    throw new UpstreamUnavailable(err.message);
  }
  if (typeof message !== 'string' || message.length === 0) {
    throw new BadResponse(`Vendor returned no usable text: ${JSON.stringify(message)}`);
  }
  return message;
}

function appendSent(entry) {
  try {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    fs.appendFileSync(LOG_FILE, JSON.stringify(entry) + '\n');
  } catch (err) {
    throw new SendFailed(`Could not append to sent.log (${err.code || err.name}): ${err.message}`);
  }
}

// Gets a message (vendor or fallback), gates it, sends it. Throws if nothing
// was sent. `run` collects attempts and gate score for the receipt.
async function produceAndSend(orderId, run) {
  const { log } = run.logger;

  const vendorCall = () =>
    breaker.run(
      () =>
        retry(() => callVendorOnce(orderId), {
          attempts: RETRY_ATTEMPTS,
          baseDelayMs: RETRY_BASE_DELAY_MS,
          onAttempt: ({ attempt, outcome, errorName }) => {
            run.attempts = attempt;
            log(outcome === 'success' ? `Attempt ${attempt}: success` : `Attempt ${attempt}: failure (${errorName})`);
          },
        }),
      { log }
    );

  const outcome = await withFallback(vendorCall, () => fallbackMessage(orderId), { on: FALLBACK_ON, log });

  try {
    run.gateScore = qualityGate(outcome.value, orderId).score;
  } catch (err) {
    run.gateScore = err.score;
    run.gateReasons = err.reasons;
    throw err;
  }
  log(`Quality gate: score ${run.gateScore} (${outcome.fallback ? 'fallback template' : 'vendor message'})`);

  // Backstop: the gate's rules let a refusal that quotes the right order id
  // score exactly 70. A vendor message must also be the actual confirmation.
  if (!outcome.fallback && outcome.value !== expectedMessage(orderId)) {
    run.gateReasons = ['passed the gate but is not the expected confirmation text'];
    throw new BadResponse(`Vendor message is not the confirmation: ${JSON.stringify(outcome.value)}`);
  }

  const entry = {
    orderId,
    correlationId: run.correlationId,
    message: outcome.value,
    sentAt: new Date().toISOString(),
    gateScore: run.gateScore,
  };
  if (outcome.fallback) entry.fallback = true;
  appendSent(entry);
  log(`Sent${outcome.fallback ? ` FALLBACK (cause: ${outcome.cause})` : ''}: ${JSON.stringify(entry)}`);
  return entry;
}

function park(orderId, err, run) {
  const row = {
    orderId,
    correlationId: run.correlationId,
    error: err.name,
    failedAt: new Date().toISOString(),
  };
  if (run.gateScore !== null) row.gateScore = run.gateScore;
  if (run.gateReasons) row.gateReasons = run.gateReasons;
  deadLetter.add(row);
  run.logger.error(`NOT sent (${err.name}: ${err.message})`);
  run.logger.error(`Dead-lettered order ${orderId}: ${JSON.stringify(row)}`);
}

// One confirm run for one order. Never throws; always returns the receipt.
async function processOrder(orderId) {
  const correlationId = randomUUID();
  const run = { correlationId, logger: runLogger(correlationId), attempts: 0, gateScore: null };
  run.logger.log(`confirm ${orderId}`);

  let outcome;
  let error = null;
  let duplicate = false;
  try {
    // Duplicates return here, before the gate: a stored result was gated once.
    // The key is the ORDER, never the run: every arrival of order 4001 must map to
    // the same key, or a retry looks like a brand-new order and sends again.
    const once = await runOnce(idempotencyKey(orderId), () => produceAndSend(orderId, run), { storePath: KEYS_FILE });
    duplicate = once.duplicate;
    if (once.duplicate) {
      run.gateScore = once.result.gateScore ?? null;
      run.logger.log(`Duplicate: order ${orderId} was already sent (run ${once.result.correlationId}); nothing re-sent`);
      outcome = 'duplicate';
    } else {
      outcome = once.result.fallback ? 'fallback' : 'sent';
    }
  } catch (err) {
    park(orderId, err, run);
    outcome = 'dead-lettered';
    error = err.name;
  }

  const receipt = {
    orderId,
    correlationId,
    attempts: run.attempts,
    breakerState: breaker.state().state,
    gateScore: run.gateScore,
    outcome,
    duplicate,
    error,
  };
  console.log(JSON.stringify(receipt));
  return receipt;
}

async function confirm(orderId) {
  const receipt = await processOrder(orderId);
  if (receipt.outcome === 'dead-lettered') process.exitCode = 1;
}

async function replay() {
  const parked = deadLetter.list();
  console.log(`Replaying ${parked.length} dead-lettered order(s)`);

  for (const { orderId } of parked) {
    const receipt = await processOrder(orderId);
    if (receipt.outcome === 'dead-lettered') {
      process.exitCode = 1;
    } else {
      deadLetter.remove(orderId);
      console.log(`[cid=${receipt.correlationId}] Removed order ${orderId} from dead-letter`);
    }
  }

  console.log(`Dead-letter now holds ${deadLetter.list().length} order(s)`);
}

function main() {
  const [, , command, orderId] = process.argv;

  let work;
  if (command === 'confirm' && orderId) work = confirm(orderId);
  else if (command === 'replay') work = replay();
  else {
    console.error('Usage: node desk.js confirm <orderId> | node desk.js replay');
    process.exitCode = 1;
    return;
  }

  work
    .catch((err) => {
      // Only reached if parking itself failed — say so loudly.
      console.error(`Unhandled failure: ${err.name}: ${err.message}`);
      process.exitCode = 1;
    })
    .then(() => {
      // A "slow" attempt we gave up on is still ticking in the background
      // (vendor.js has no way to know we stopped waiting on it). Our own
      // work is genuinely done at this point, so exit rather than sit
      // around for an abandoned timer that can no longer affect anything.
      process.exit(process.exitCode || 0);
    });
}

main();
