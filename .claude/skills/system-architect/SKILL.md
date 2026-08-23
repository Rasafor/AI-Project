---
name: system-architect
description: Use when the user has a project idea and wants a system architecture, a technical design, or a diagram of how it would work. Triggers on phrases like "design the architecture for...", "how would this system work?", or "give me a technical design for this idea."
---

## Description

**Purpose:** People with a project idea often can't picture how the pieces fit together — what talks to what, where data lives, what's frontend versus backend. This Skill turns a plain-language idea into a concrete, idea-specific architecture: the real components that idea needs, a diagram of how they connect, and a plain-English explanation anyone can follow.

**When to use it:** Use when someone describes a project idea (even briefly, one paragraph) and asks for a system architecture, technical design, or diagram of how it would work — e.g., "design the architecture for a tool that lets students upload homework and get AI feedback."

**When NOT to use it:** Do not use this for reviewing or refactoring an *existing* codebase's architecture — that's a codebase-exploration task, not a from-scratch design. Do not use it just because someone mentions "backend" or "database" in passing; the trigger is a request for a system design or diagram.

**Who it's for:** Anyone with a project idea who wants to see how it would be built — including non-technical stakeholders, so the explanation layer matters as much as the diagram.

---

## Instructions

### Inputs needed
- A one-paragraph (or similar length) description of the project idea, in the user's own words. If the user has given less than a sentence, ask them to describe what the project should do before proceeding — a generic architecture can't be produced from nothing.

### Steps

1. **Read the idea closely and extract what it actually implies.** Do not reach for a stock "frontend + backend + database" template. Ask, for this specific idea: Does it need a user-facing interface at all (web app? CLI? chat interface? none)? Does it need a backend/API layer, or could logic run client-side? Does it need persistent storage, and if so what kind (relational, document store, vector store, file storage)? Does it call out to external services (payment processor, email provider, third-party API, auth provider)? Does it involve an AI/agent/LLM layer — and if so, is that layer doing classification, generation, retrieval, orchestration, or agentic tool use? Only include a component category if the idea actually implies it.

2. **Name the concrete components**, not generic placeholders. E.g. instead of "Database," write "Postgres store for student submissions and grades." Instead of "AI layer," write "LLM grading agent that reads submitted homework and returns structured feedback." Each component should be traceable back to something the user actually described.

3. **Map the data flow between components.** For each connection, know and be able to state: what data moves across it, and in which direction. This is what the diagram will encode.

4. **Produce a genuine Mermaid flowchart** (use `flowchart TD` or `flowchart LR`, whichever reads more clearly for the shape of this system) showing the components as nodes and the data flow as directed, labeled edges. The diagram must reflect the actual components and flow identified in steps 1–3 — never a copy-pasted generic diagram. Label edges with what actually moves (e.g. `-->|submitted homework file|`, not an unlabeled arrow).

5. **Write a one-paragraph-per-component explanation**, each in one plain-English sentence a non-technical person could follow — no jargon like "REST endpoint" or "ORM" without a plain-language gloss. Explain what the component does and why it's there, not how it's implemented internally.

6. **Assemble and save the result** to `project-blueprint/architecture.md` (create the `project-blueprint/` directory if it doesn't exist), containing, in order:
   - A short restatement of the project idea
   - The component list (concrete names, one line each)
   - The Mermaid flowchart
   - The plain-English explanation of each component

7. **Report back to the user**: the exact file path, the final description used for this Skill invocation's framing (i.e., what the architecture is for, in one line), and the component list identified.

### Expected output
A file at `project-blueprint/architecture.md` containing the restated idea, a concrete (non-generic) component list, a real Mermaid diagram of those specific components and their data flows, and a plain-English explanation of each component. The calling response reports the file path, description, and component list back to the user.

### Things to avoid
- Do not default to "frontend / backend / database" if the idea doesn't need all three (e.g., a CLI script idea may need no frontend at all; a static content idea may need no database).
- Do not produce a Mermaid diagram that is decorative or generic — every node and edge must map to something real in the idea.
- Do not write component explanations that use unexplained technical jargon — the audience includes non-technical readers.
- Do not skip the AI/agent layer if the idea implies one, and do not invent one if the idea doesn't.
- Do not overwrite an existing `project-blueprint/architecture.md` silently if it looks like it belongs to a different, unrelated project — check its contents first if it already exists.
