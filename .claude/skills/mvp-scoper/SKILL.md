---
name: mvp-scoper
description: Use when the user wants to know what to build first, see what their idea could look like, and get a short pitch for it. Triggers on phrases like "what should I build first?", "show me what this would look like," "give me a pitch for this," or "scope the MVP."
allowed-tools: Read, Write, Bash
---

## Description

**Purpose:** An architecture and a tech stack tell you what the whole system looks like, but not where to start, what it would feel like to use, or how to explain it to someone in ten seconds. This Skill produces the three artifacts a person actually needs to start building and start talking about the idea: a scoped Week 1 build plan, a real-looking mockup of the main screen, and a one-page pitch PDF.

**When to use it:** Use when the user asks what to build first, wants to see what their idea could look like, or wants a short pitch for it — e.g. "what's the smallest thing I could build this week?", "show me what the main screen would look like," "give me something I could show someone in 30 seconds."

**When NOT to use it:** Do not use this to design the architecture itself (`/system-architect`) or to recommend technologies (`/tech-stack-recommender`) — this Skill depends on both existing first. Do not use it for a full product roadmap or multi-week plan; it produces exactly one week's slice, not a backlog.

**Who it's for:** Anyone with a project idea who needs to start building or start pitching this week — including non-technical users who need the mockup and one-pager to explain the idea before a single line of code exists.

---

## Instructions

### Inputs needed
- `project-blueprint/architecture.md` must already exist. If it doesn't, tell the user to run `/system-architect` first — do not invent an architecture to fill the gap.
- `project-blueprint/tech-stack.md` must already exist. If it doesn't, tell the user to run `/tech-stack-recommender` first — do not invent technology choices to fill the gap.

### Steps

1. **Read `project-blueprint/architecture.md` and `project-blueprint/tech-stack.md` in full.** Everything produced in this Skill must trace back to a real component, data flow, or technology named in those two files — never a generic template unrelated to this idea.

2. **Identify the smallest real Week 1 slice.** Use the architecture's Build Order and "make-or-break" callouts as the starting signal, but don't copy its Phase 1 blindly — ask specifically: what is the single riskiest assumption in this idea, and what is the smallest buildable thing that proves it true? Every task in the slice must name a real component (from architecture.md) and a real technology (from tech-stack.md).

3. **Write `project-blueprint/mvp-plan.md`** following the structure in `template.md` in this Skill's folder exactly — same headings, same order. Fill in: the one thing Week 1 must prove, the checklist of concrete tasks, what's explicitly deferred, and what "done" looks like as an observable demo. Strip the template's own guidance notes from the output — they're instructions for filling it in, not content to ship.

4. **Design and write `project-blueprint/mockup.html`** — a single, self-contained static HTML file (all CSS inline in a `<style>` block, no external stylesheets, fonts, or CDN links, so it opens correctly offline with a double-click) showing the idea's main screen: a landing page if the idea is something you'd pitch to a visitor, or the core in-app view if the idea is something you'd open and use. Requirements:
   - Real layout with real visual hierarchy (header, nav where it makes sense, primary content area, calls to action) — not a wireframe of gray boxes.
   - Real sample content written for *this specific idea* — actual names, actual copy, actual numbers/labels a user of this exact product would see. Never "Lorem ipsum," never "Item 1 / Item 2," never placeholder brand names unless the idea itself has no name yet (in which case invent one short, fitting name and use it consistently).
   - Use color deliberately (a real palette, not default black-on-white) and icons (inline SVG or Unicode/emoji glyphs are fine — no external icon font CDN).
   - Should look like a real, shippable screen a design-competent person made, not a prototype.

5. **Write the one-pager's marketing content**, then render it to PDF:
   - Compose the copy first: what it does (one line), who needs it (one line), one sentence on why it matters, plus 3-5 short punchy supporting lines or feature bullets with icons — no technical/architecture language, this is a pitch, not a spec.
   - Build this content as a single HTML file with inline CSS (letter/A4 page sized, print-friendly styling, real color and icons matching the mockup's visual identity) and save it as a **temporary** file in the session scratchpad directory (not inside `project-blueprint/`) — it is an intermediate artifact, not one of the three deliverables.
   - Convert it to PDF with headless Chrome print-to-PDF, since Chrome is present on this machine at `C:\Program Files\Google\Chrome\Application\chrome.exe` (fall back to Edge at `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` only if Chrome isn't present — check with the same command before falling back). Run exactly one Bash command of this shape, using absolute Windows paths:
     ```
     "C:\Program Files\Google\Chrome\Application\chrome.exe" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf="C:\...\project-blueprint\one-pager.pdf" "C:\...\scratchpad\one-pager-source.html"
     ```
   - Confirm `project-blueprint/one-pager.pdf` now exists and is a non-trivial size (a few KB at minimum) as evidence the render succeeded, then delete the temporary scratchpad HTML source.
   - Never save the one-pager as a `.md` or `.html` file renamed to `.pdf` — it must be an actual rendered PDF.

6. **Report back to the user**: the exact paths of all three files (`project-blueprint/mvp-plan.md`, `project-blueprint/mockup.html`, `project-blueprint/one-pager.pdf`), one line on what each contains, and which tool rendered the PDF.

### Expected output
Three files under `project-blueprint/`:
- `mvp-plan.md` — a short, idea-grounded Week 1 checklist following `template.md`'s structure.
- `mockup.html` — a self-contained, visually real static mockup of the idea's main screen, with idea-specific content, color, and icons.
- `one-pager.pdf` — an actual rendered single-page PDF pitch, generated via headless-Chrome (or Edge) print-to-PDF, not a renamed text file.

The calling response states all three paths, a one-line description of each, and the PDF rendering tool used.

### Things to avoid
- Do not generate any of the three files before both `architecture.md` and `tech-stack.md` have been read — every detail must be traceable to those files.
- Do not write `mockup.html` as a wireframe of unlabeled boxes or with lorem-ipsum/placeholder content — it must read as a real, idea-specific screen.
- Do not skip straight to a generic SaaS-landing-page template disconnected from what the idea actually is.
- Do not use any external CDN, font, or script link in `mockup.html` or the one-pager source HTML — both must be fully self-contained.
- Do not save the one-pager as `.md` or `.html` renamed to `.pdf`, and do not leave the intermediate one-pager source HTML behind in `project-blueprint/`.
- Do not use Bash for anything beyond the single PDF-rendering command (and the existence/size check on the output, and deleting the temp source file) — file creation and edits go through Write, not shell redirection.
- Do not overwrite existing `project-blueprint/mvp-plan.md`, `mockup.html`, or `one-pager.pdf` silently if their contents look like they belong to a different, unrelated project — check with the user first.
