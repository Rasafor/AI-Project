# Order Desk Reliability Lab

A toy order desk (`desk.js`) that asks a stand-in vendor (`vendor.js`) to confirm an order, then appends one JSON line to `data/sent.log`.

Run it: `node desk.js confirm 1001`

Set the vendor's behavior with the `VENDOR_MODE` env var: `ok` (default, ~50ms, good message), `slow` (hangs 10s then returns the good message), `down` (fails fast with a 500-style error), `garbage` (fast but confidently wrong message).

Example: `VENDOR_MODE=down node desk.js confirm 1001`

Protections: 2s timeout per attempt, 3 retries, a circuit breaker (`data/breaker.json`), a template fallback when the vendor is down, and a dead-letter file (`data/dead-letter.jsonl`) that `node desk.js replay` re-sends.

Idempotency: each send is keyed `order:<orderId>` in `data/keys.json`, claimed before the vendor is called, so a repeat (or a simultaneous duplicate) returns the stored result with `"duplicate": true` instead of sending again. Re-check it any time with `npm test` (or `node tests/check-idempotency.js`); it exits non-zero on failure.
