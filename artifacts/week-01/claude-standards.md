# Project Standards — Retail Analytics Dashboard (Sample)

This document defines the coding, naming, and documentation standards for the
**Retail Analytics Dashboard** sample project. It is intended to be clear
enough for a new contributor to follow without additional guidance.

---

## 1. Coding Conventions

- **Language & style:** Follow the standard style guide for the project's
  primary language (e.g., PEP 8 for Python, Airbnb/Standard for
  JavaScript/TypeScript). Run the project's linter/formatter before every
  commit; do not commit code that fails linting.
- **Function size:** Keep functions focused on one responsibility. Aim for
  under ~50 lines; if a function grows past ~100 lines, split it.
- **File size:** Aim for files under ~300 lines. A file that grows past
  ~500 lines should be split into smaller modules on its next change.
- **No dead code:** Remove commented-out code and unused variables/imports
  before merging. Version control preserves history — don't keep it in the
  source.
- **Error handling:** Never silently swallow errors (no empty
  `catch {}` blocks). Every caught error is logged with enough context to
  diagnose it, and a specific error type/class where possible (avoid
  generic `Exception`/`Error` in production code paths).
- **No hardcoded secrets or environment values:** Connection strings, API
  keys, and environment-specific URLs belong in configuration/environment
  variables, never in source code.
- **Tests accompany logic:** Any new calculation, transformation, or
  business rule (e.g., sales aggregation, inventory forecasting) ships with
  at least one test covering its happy path plus one edge case (empty
  input, zero values, missing data).
- **Comments explain "why," not "what":** Only comment on non-obvious
  reasoning, workarounds, or constraints. Well-named code should make the
  "what" self-evident.

## 2. Naming Standards

| Element | Convention | Example |
|---|---|---|
| Variables & functions | `camelCase` | `calculateMonthlySales()` |
| Classes / Components | `PascalCase` | `SalesTrendChart` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RETRY_ATTEMPTS` |
| Files (components) | `PascalCase.ext` | `RevenueSummary.tsx` |
| Files (utilities/scripts) | `camelCase.ext` | `formatCurrency.ts` |
| Database tables | `snake_case`, plural | `store_transactions` |
| Database columns | `snake_case` | `transaction_date` |
| Branches | `type/short-description` | `feature/inventory-alerts` |

**General rules:**
- Names describe intent, not implementation (`getActiveStores()`, not
  `getStoresWhereFlagIsOne()`).
- Avoid abbreviations unless they are domain-standard (`sku`, `qty`, `id`
  are fine; `calcRevAmt` is not).
- Boolean variables/functions read as a question or state:
  `isOutOfStock`, `hasDiscount`, `canReorder`.
- Avoid single-letter names outside of short-lived loop counters (`i`, `j`).

## 3. Documentation Guidelines

- **README first:** Every top-level module/folder has a short `README.md`
  stating its purpose, what belongs there, and what doesn't.
- **Function-level docs:** Any function with non-obvious business logic
  (e.g., a demand-forecasting formula, a discount-eligibility rule) gets a
  short doc comment describing inputs, outputs, and any assumptions —
  not a restatement of the code.
- **Data dictionary:** Any new database table or report field is added to
  the project's data dictionary with its name, type, meaning, and source.
- **Change documentation:** Non-trivial changes (new metrics, new charts,
  schema changes) are noted in a changelog or progress log with what
  changed, why, and how it was verified.
- **No stale docs:** If a change makes existing documentation inaccurate,
  updating that documentation is part of the change, not a follow-up task.
- **Diagrams for data flow:** Any new data pipeline or integration (e.g.,
  POS system → dashboard) includes a simple diagram or written data-flow
  description so a new contributor can trace where data comes from and
  where it goes.

---

*This is a sample standards document for the Retail Analytics Dashboard
project, generated as a coursework exercise.*
