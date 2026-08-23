# MVP Plan Template

> This template keeps `project-blueprint/mvp-plan.md` structured the same way every time `/mvp-scoper` runs. Copy the structure below, then replace every `[BRACKET]` with content specific to the idea in `project-blueprint/architecture.md`. Delete this instruction line and the guidance notes (the indented italics under each heading) from the final output — they exist to guide the fill-in, not to ship in the finished plan.

---

```markdown
# [Idea Name] — Week 1 MVP Plan

*Maps to `project-blueprint/architecture.md` and `project-blueprint/tech-stack.md`.*

## The One Thing Week 1 Must Prove

[One sentence. Name the single riskiest assumption in the idea — the thing that, if it doesn't work, means the rest of the build isn't worth doing. Pull this from the architecture's "make-or-break" component or its Build Order, not from a generic "build the login page" instinct.]

## The Smallest Real Slice

*A short, literal checklist — each line is one concrete, buildable task, not a phase or an epic. Order matters: earlier items unblock later ones. Ground every line in a named component from architecture.md and a named technology from tech-stack.md — no line should be so abstract it could belong to any project.*

- [ ] [Task 1 — names a specific component and what it does at minimum]
- [ ] [Task 2]
- [ ] [Task 3]
- [ ] [Task 4]
- [ ] [Add or remove lines as the idea actually requires — this is not a fixed-length list]

## Explicitly Out of Scope for Week 1

*Bullets. Things the architecture names that are deliberately deferred, so nobody mistakes silence for an oversight.*

- [Deferred item 1 — one line on why it can wait]
- [Deferred item 2]

## What "Done" Looks Like

[One to three sentences describing the observable, demoable proof that Week 1 succeeded — something a person could watch happen on screen, not an internal metric. If this can't be demoed, the slice is still too abstract.]
```
