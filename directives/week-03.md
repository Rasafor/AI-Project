# Week 03 Directive

## Goal
Implement `add(a, b)`, a function that returns the sum of two numbers.
Used as a minimal worked example for the Plan Mode workflow.

## Inputs
Two numbers, `a` and `b`.

## Outputs
The numeric sum `a + b`.

## Edge cases
- Negative numbers (`add(-1, 1)` → `0`)
- Zero (`add(0, 0)` → `0`)

## Safety / constraints
Plain JavaScript, no external libraries, no build tooling — matches the
existing static-file stack in this repo.

## Verification
Run `node -e "console.log(require('./src/week-03/add.js').add(2,3))"` and
check output against `tests/week-03/add.test.md`.
