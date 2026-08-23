# Skill Template

> **What is a "Skill"?** A Skill is a reusable, packaged set of instructions that tells an AI assistant exactly how to perform a specific, repeatable task — the same way a recipe tells a cook how to make a dish, every time, the same way. Once written, you (or a teammate) can trigger it by name instead of re-explaining the task from scratch each time.
>
> **How to use this template:** Copy everything below into a new file, then replace the placeholder text (in `[BRACKETS]`) with your own content. Each section below has an explanation *above* it telling you what to write and why it matters. Delete the explanation boxes once you're done — they're just here to guide you.
>
> **Where finished Skills live in this project:** Each real Skill gets its own folder under `.claude/skills/<skill-name>/` with a `SKILL.md` file inside (see `.claude/skills/github-repo-connect/` or `.claude/skills/safe-commit-and-push/` for examples). This file is the template you copy *from* — it is not itself a Skill.

---

## SECTION 1: Frontmatter

**What this is:** Frontmatter is a small block of structured information at the very top of the file, wrapped in three dashes (`---`) above and below it. Think of it like the label on a filing folder — it doesn't contain the instructions themselves, it just tells the system *what this Skill is called* and *when to use it*, so the AI can find and trigger the right Skill at the right moment.

**Why it matters:** If the frontmatter is vague or missing, the AI won't know this Skill exists or when to reach for it. Be specific — imagine you're labeling a folder in a filing cabinet that a new employee will need to find without asking you.

**How to fill it out:**
- `name`: A short, unique identifier, using lowercase letters and hyphens (no spaces). This is how the Skill gets triggered (e.g., typed as `/name`). Keep it under 3-4 words.
- `description`: One or two sentences, written in the third person, describing (a) what the Skill does and (b) exactly when it should be used. Be concrete — vague descriptions ("helps with reports") get ignored; specific ones ("use when the user asks to summarize weekly sales numbers into a one-page PDF") get triggered correctly.

```markdown
---
name: [short-kebab-case-name]
description: [One to two sentences: what this Skill does, and the specific situations or trigger phrases that should cause it to be used. Include example phrases a user might say.]
---
```

**Example (filled out):**
```markdown
---
name: weekly-sales-summary
description: Use when the user asks to summarize weekly sales data into a one-page executive report. Triggers on phrases like "summarize this week's sales" or "build the weekly report."
---
```

---

## SECTION 2: Detailed Description

**What this is:** A longer, plain-language explanation of the Skill that goes just below the frontmatter. While the frontmatter `description` is a quick summary for the AI to decide *whether* to use the Skill, this section is for *humans* — it explains the full purpose, so that anyone opening the file (including someone non-technical, six months from now) understands what it's for without having to read all the instructions below.

**Why it matters:** People (including future-you) forget why a Skill was created. This section is your insurance policy against confusion later.

**How to fill it out, in plain sentences:**
1. **Purpose** — In 1-3 sentences, what problem does this Skill solve? Why does it exist?
2. **When to use it** — What situation, request, or trigger should make someone reach for this Skill?
3. **When NOT to use it** — Are there similar-sounding requests this Skill should NOT handle? (This prevents mix-ups with other Skills.)
4. **Who it's for** — Is this meant for a specific role, team, or type of user?

```markdown
## Description

**Purpose:** [Why does this Skill exist? What problem does it solve?]

**When to use it:** [Describe the specific situations, requests, or phrases that should trigger this Skill.]

**When NOT to use it:** [Describe similar-but-different situations this Skill should NOT be used for, to avoid confusion with other Skills.]

**Who it's for:** [Name the role, team, or person this Skill is designed to help, if relevant.]
```

**Example (filled out):**
```markdown
## Description

**Purpose:** Sales managers need a clean, one-page summary of weekly numbers to share with leadership, without manually pulling and formatting spreadsheet data every Friday.

**When to use it:** Use when someone asks to "summarize this week's sales," "build the weekly report," or "turn the sales spreadsheet into a summary."

**When NOT to use it:** Do not use this for monthly or quarterly reports — those follow a different format and live in a separate Skill. Do not use this for raw data requests ("just give me the numbers") — only for the formatted summary.

**Who it's for:** Sales managers and their assistants preparing the Friday leadership update.
```

---

## SECTION 3: Instruction Body

**What this is:** This is the heart of the Skill — the actual step-by-step instructions the AI will follow every time this Skill is triggered. Think of it as the recipe steps, written clearly enough that someone with no prior context could follow along and get the same result every time.

**Why it matters:** Vague instructions produce inconsistent results. The more concrete and ordered your steps are, the more reliably the Skill will work the same way every time it's used.

**How to fill it out:**
1. **Inputs needed** — What information, files, or context does the AI need before it can start? (e.g., "the current week's sales spreadsheet," "the recipient's name")
2. **Step-by-step instructions** — Write out each step in order, as a numbered list. Be specific: name exact file locations, formats, tools, or wording where it matters. If a step has a decision point ("if X, do Y; otherwise do Z"), spell it out.
3. **Output / end result** — What should exist when the Skill is done? (a file, a message, a specific format?) Describe exactly what "finished" looks like.
4. **Things to avoid** — Any common mistakes, edge cases, or things the AI should never do while running this Skill.

```markdown
## Instructions

### Inputs needed
- [List anything the AI needs before starting: files, data, names, dates, etc.]

### Steps
1. [First step — be specific and concrete.]
2. [Second step.]
3. [Third step — include any "if this, then that" decision points.]
4. [Continue numbering until the task is complete.]

### Expected output
[Describe exactly what the finished result should look like: a document, a message, a specific file name/location, a formatted table, etc.]

### Things to avoid
- [Common mistake or edge case #1]
- [Common mistake or edge case #2]
```

**Example (filled out):**
```markdown
## Instructions

### Inputs needed
- The current week's sales spreadsheet (usually shared as an attachment or file path)
- The recipient list for the summary (default: sales leadership team)

### Steps
1. Open the provided spreadsheet and locate the "Weekly Totals" tab.
2. Pull total revenue, number of new deals closed, and top 3 performing reps.
3. If any number is missing or blank, flag it clearly instead of guessing or leaving it out silently.
4. Format the results into a one-page summary with a title, date range, and three sections: Revenue, Deals Closed, Top Performers.
5. Save the summary as a PDF named `Weekly-Sales-Summary-[date].pdf`.

### Expected output
A single PDF file, one page long, titled with the correct week's date range, containing the three sections listed above.

### Things to avoid
- Do not guess at missing numbers — flag them instead.
- Do not include raw spreadsheet data in the summary; it should be readable by someone without spreadsheet experience.
```

---

## Quick Checklist Before You're Done

- [ ] `name` is short, lowercase, and hyphenated
- [ ] `description` in the frontmatter clearly states what it does AND when to use it
- [ ] The longer Description section explains purpose, when to use it, when NOT to use it, and who it's for
- [ ] The Instructions section lists what inputs are needed
- [ ] The Instructions section is a numbered, step-by-step list anyone could follow
- [ ] You've described exactly what the finished output should look like
- [ ] You've listed any common mistakes or things to avoid
- [ ] All `[BRACKETED PLACEHOLDER TEXT]` has been replaced with real content
