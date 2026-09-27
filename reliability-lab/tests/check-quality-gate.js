#!/usr/bin/env node
// Unit checks for score(): each rule, the whole-token rule, and the boundaries.

const assert = require('assert');
const { score, qualityGate } = require('../reliability');

const cases = [
  ['Your order 5002 is confirmed and will ship within 2 days.', '5002', 100, 'good vendor message'],
  ['Your order 5002 is confirmed. Full details will follow shortly.', '5002', 100, 'fallback template'],
  ['Your order 5002 is confirmed and will ship within 2 days.', '5001', 60, 'wrong order number'],
  ['Your order 50012 is confirmed and will ship within 2 days.', '5001', 60, 'id only as a substring'],
  ['As an AI I cannot confirm order 5001 at this time.', '5001', 70, 'refusal quoting the id (gate hole)'],
  ["I'M SORRY, order 5001 failed.", '5001', 70, 'phrase check is case-insensitive'],
  ['Order 5001 ok', '5001', 70, '13 chars: too short'],
  ['x'.repeat(15) + ' 5001', '5001', 100, 'exactly 20 chars'],
  ['5001 ' + 'x'.repeat(296), '5001', 70, '301 chars: too long'],
  ['', '5001', 30, 'empty'],
  [undefined, '5001', 30, 'not a string'],
];

for (const [msg, id, expected, name] of cases) {
  assert.strictEqual(score(msg, id), expected, `${name}: expected ${expected}, got ${score(msg, id)}`);
  console.log(`ok - ${name} -> ${expected}`);
}

assert.throws(() => qualityGate('Your order 5002 is confirmed.', '5001'), { name: 'QualityGateRejected' });
assert.strictEqual(qualityGate('As an AI I cannot confirm order 5001 at this time.', '5001').score, 70);
console.log('ok - qualityGate rejects 60, admits 70');
console.log(`\ncheck-quality-gate: ${cases.length + 1} passed, 0 failed`);
