# How the order desk survives a bad vendor

Four questions about `desk.js` and `reliability.js`, answered from the code as it is today.

## 1. What happens when the vendor fails?

Every call to `vendor.confirmOrder` goes through `callVendorOnce`, which wraps it in `withTimeout` with a 2-second deadline (`ATTEMPT_TIMEOUT_MS`). A call that runs past the deadline fails as `TimeoutError`. Any other error the vendor throws is renamed `UpstreamUnavailable`, and an empty or non-text reply becomes `BadResponse`. A reply that arrives in time still has to pass two checks before anything is sent. First, `qualityGate` scores it out of 100 and refuses anything under 70 with `QualityGateRejected`. Second, it has to be exactly the expected confirmation text, or it is refused as `BadResponse`. Only a message that passes both is appended to `data/sent.log`. Whatever happens, each run ends with one JSON receipt on stdout carrying the same `correlationId` as every log line it printed.

## 2. Does it retry? With what strategy?

Yes, a little. `retry` makes at most 3 attempts (`RETRY_ATTEMPTS`), and each attempt has its own 2-second deadline. The gap starts at 500 ms (`RETRY_BASE_DELAY_MS`) and doubles, so the waits are about 0.5 s and then 1 s. Each wait also gets up to 0.1 s of random jitter so many clients don't retry at the same instant. Only `TimeoutError` and `UpstreamUnavailable` are retried (`RETRYABLE_ERROR_NAMES`), because they might work next time. `BadResponse` and `QualityGateRejected` are never retried: asking again just gets another wrong answer. `BreakerOpen` is never retried either. Around the whole retried operation sits `createBreaker`. After 3 operations in a row fail (`failureThreshold`), it opens and refuses calls instantly with `BreakerOpen`, without calling the vendor at all. After a 10-second cooldown (`cooldownMs`) it lets one trial operation through: success closes it, failure opens it again. Its state lives in `data/breaker.json`, so separate runs of the command share it. The worst case for one order is about 7.7 seconds and 3 vendor calls.

## 3. What is the recovery path when the retries are exhausted?

That depends on why it failed. For `UpstreamUnavailable` or `BreakerOpen`, `withFallback` sends a plain template instead: "Your order <id> is confirmed. Full details will follow shortly." The template goes through the same quality gate (it scores 100) and is marked `"fallback": true` in `sent.log`. Everything else is never sent under any name, and goes through `park` into `data/dead-letter.jsonl` with the order id, the error name, the time and the `correlationId`. That covers `TimeoutError`, `BadResponse`, `QualityGateRejected`, a failed append (`SendFailed`), a stuck claim (`ClaimPending`) and an unreadable `keys.json`. Gate refusals also record the score and the reasons it lost points. `node desk.js replay` runs every parked order through the normal path again and removes the ones that get sent. Sends are idempotent: `runOnce` claims the key `order:<orderId>` in `data/keys.json` under a file lock *before* the vendor is called. A repeat, even one that arrives at the same moment, returns the stored result with `"duplicate": true` instead of sending again.

## 4. Which failures does this code handle, and which does it NOT handle?

It handles a vendor that hangs, errors, or answers with nonsense; a vendor that stays down (the breaker stops calling it after 3 failed orders); the same order confirmed twice, including at the same instant; and a refused order being lost. Here is what it does **not** cover:

- **Two processes at once.** Only `keys.json` is protected by a lock. `breaker.json` and `dead-letter.jsonl` are read, changed and rewritten with no lock, so two runs finishing together can lose a breaker failure count or, worse, a dead-letter row.
- **A process killed mid-send.** A process killed after appending to `sent.log` but before recording the key as done leaves that key "claimed" forever. Later runs are dead-lettered as `ClaimPending` rather than risk a second send. A person has to check `sent.log` and remove the key by hand.
- **A corrupted `keys.json`.** It fails safe, because nothing is sent and the order is dead-lettered as `SyntaxError`. But *every* order fails that way until someone repairs the file. Nothing detects or fixes it automatically.
- **A corrupted `breaker.json`.** The opposite: the desk logs a warning, treats it as closed, and keeps calling the vendor.
- **A vendor that is slow but under the deadline.** One that answers in 1.9 seconds every time passes every check. Nothing measures latency or raises an alarm, so the desk is quietly slow.
- **Calls we gave up on.** A call abandoned at the deadline keeps running at the vendor. A real model may finish that work and bill for it, and the retry asks it to do the same work again.
- **No fallback for timeouts.** `TimeoutError` gets no fallback: a slow vendor's orders are parked, not answered.
- **A strict text check.** The exact-text check means any legitimate change in the vendor's wording is refused as `BadResponse`.
- **The gate's own rules.** They let a polite refusal that quotes the order id score exactly 70, which passes. Only that exact-text check stops it.
- **Dead-letter history.** Rows are keyed by order, so a second failure replaces the first row and its reason.
- **Replay.** `replay` has no backoff of its own. Running it while the vendor is still down just parks the orders again.
- **Old idempotency records.** Keys recorded by the older `data/processed.json` are no longer read.
