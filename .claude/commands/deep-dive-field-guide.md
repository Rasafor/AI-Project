---
description: Build this week's deep-dive Field Guide end to end (content, build, browser check, PROGRESS.md, commit)
argument-hint: [discipline, e.g. "DevOps Engineer"]
---

Build the next weekly **Field Guide (Week N deep dive)**: a single self-contained HTML knowledge base at the repo root, made from one content file and the shared kit in `field-guides/kit/`. Do the whole job. Stop only at the questions marked **ASK**.

## 0. Session
Use this session's ID (`CC-<YYYYMMDD>-<4 random alphanumerics>`; mint one if this session has none yet). It goes on the PROGRESS.md entry and in the commit body.

## 1. Gather the inputs
Work out without asking:
- **Week**: read the `"week"` value from the `deepdive-metadata` block of every `*_FieldGuide.html` at the root and in `docs/`. Next week = max + 1. If a guide for the discipline already exists, say so and ask whether to rebuild it or stop.
- `studentId` = `regina.asafor@gmail.com`; `projectId` = `project_id` from `.colaberry/manifest.json`; `author` = Regina Asafor, `authorTitle` = AI Solution Architect; `date` = today.
- `buildNumber` = `<2-3 letter discipline code>-<YYYYMMDD>-01`. `file` = `<DisciplineNoSpaces>_FieldGuide.html`.

**ASK** in one AskUserQuestion call, leaving out anything `$ARGUMENTS` already answers:
1. The discipline (if `$ARGUMENTS` is empty).
2. "Paste this week's assignment brief." It decides the topics, the documents and the quality bar. If none is pasted, use the house standard below and say so in the final report.
3. The worked example. Default: keep **Meridian Mutual Insurance** (the accelerator's running example) with a new initiative for this discipline that reuses its existing systems (PAS-7, ClaimDesk, SettleFlow, ClaimsPilot, LedgerOne). Offer one alternative industry.

## 2. Write the content: `field-guides/<NN>-<discipline-slug>/content.js`
Copy the shape of the most recent week folder (Week 10: `field-guides/10-ai-governance-lead/`). It keeps numbers in `model.js`, prose in `sections.js`, `docs-*.js` and `faq.js`, and `content.js` puts them together, so every file stays under the repo's 500-line limit. The contract is enforced by `field-guides/kit/build.js` (`validate()`): `meta`, `example`, `people`, `hero`, `start`, `sections[]`, `documents[]`, `glossary[]`, `faq[]`, `ask`, `checks`. Use the helpers in `field-guides/kit/parts.js` (`table`, `callout`, `tiles`, `fig`, `barChart`, `lineChart`, `donut`, `flow`, `pre`, `list`). Do not write CSS. If a page needs a style the kit lacks, add it to `kit/doc.css` or `kit/guide.css` and say so in the report.

House standard, unless the brief says otherwise:
- **One numbers model.** Define every figure once, as constants at the top of `content.js` (volumes, costs, rates, targets). Teaching sections, documents, charts and CSVs read from those constants, so the documents can never disagree. Label all figures as illustrative.
- **Teaching sections, about 10.** Group them as `The discipline` (the 20% an AI Solution Architect needs to direct, evaluate and approve AI-generated work), then `Judgment` (Good vs bad, KPIs, The review lens: approving AI-generated <discipline> work, plus a reusable prompt brief in `pre()`), then `The worked example` (one section introducing the initiative). Each section gets at least one table or visual, one callout, and a pointer to the document that applies it.
- **Documents.** Use the brief's list, otherwise the 6 to 9 deliverables a practitioner in this discipline actually produces. Each one is complete and specific to the example: no placeholders, no "TBD", every table filled. Each has 3+ review-lens bullets, an owner, a one-line question it answers, and real reviewer and approver names in `people`. Tabular documents ship their rows as `csv`; schema work ships `sql`. Include failure paths and edge cases, not just the happy path.
- **Ask the guide.** At least 30 FAQ entries, each with `ref` set to the section that grounds it and an answer that agrees with that section. At least 8 suggestions. `notCovered` lists the topics the guide does cover.
- **Glossary**: at least 20 terms.
- **`checks`**: at least 6 `search` and 8 `ask` cases (`{ q, expect: '<section id>' }`), plus one `offTopic` question that must be refused. Pick real reader questions, not phrasings copied from headings.

## 3. Build and verify (loop, at most 3 rounds)
```
node field-guides/kit/build.js field-guides/<NN>-<slug>
node field-guides/kit/check.js field-guides/<NN>-<slug> --shots "<scratchpad>/shots-<NN>"
```
- A `build:` error is a content-contract violation. Fix `content.js` and rebuild.
- In `check.js` output, FAIL means fix the content (or the kit, if the bug is in the kit) and rerun. Exit 2 means the check could not run. Report that; never count it as a pass.
- Open the screenshots with Read. Look at the page top (light, dark, 390px) and every document cover. Fix collisions, clipped labels, empty charts or unreadable contrast.
- After 3 rounds with failures still open, stop the loop and list them in the report. Never mark them passed.

## 4. Record it (CLAUDE.md hard gate)
Re-read the tail of `PROGRESS.md`, then append:
```
- [x] <Discipline> Field Guide (Week <N> deep dive)
  - Date: <today>
  - Session: <session id>
  - What changed: <file, KB size, sections/documents/FAQ counts, example initiative, notable visuals and exports>
  - Verification: <the check.js summary line, plus which screenshots you reviewed and anything you fixed after review>
  - Notes: <assumptions (e.g. no brief pasted), kit changes, anything still open>
```

## 5. Commit, then ASK before pushing
Stage by explicit path only: `field-guides/<NN>-<slug>/content.js`, `<Discipline>_FieldGuide.html`, `PROGRESS.md`, plus any `field-guides/kit/` files you changed. Never use `git add -A`, and never stage other people's untracked or modified files. Commit as `Add <Discipline> Field Guide (Week <N> deep dive)`. The body gives the session ID, counts and verification line, then the attribution trailer.

**ASK**: "Push to `origin` and `colaberry`?" On yes, push to both.

## 6. Report
Give five lines: the file and its size; the counts; the check result; what you fixed after reviewing the screenshots; and what is still open or assumed. Do not describe the guide's content in the report; the guide speaks for itself.
