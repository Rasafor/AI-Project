# field-guides/

Source for the weekly **Field Guide (Week N deep dive)** HTML files at the repo root.
Run `/deep-dive-field-guide` to build the next one; it follows the steps below.

- `kit/` holds the shared parts: `doc.css` and `guide.css` (brand tokens, layout), `engine.js` (search, Ask the guide, downloads), `logo.b64`, `parts.js` (table, callout, tiles, chart and diagram helpers), `build.js`, and `check.js`.
- `<NN>-<discipline>/content.js` holds one week's content. It requires that week's other files.

```
node field-guides/kit/build.js field-guides/10-ai-governance-lead     # writes AIGovernanceLead_FieldGuide.html
node field-guides/kit/check.js field-guides/10-ai-governance-lead     # headless Chrome checks; add --shots <dir> for screenshots
```

Builds are deterministic: the same content gives the same bytes, so a rebuild is always safe.
`build.js` rejects content that breaks the contract in `validate()`. `check.js` exits 0 when every check passes, 1 when a check fails, and 2 when the check could not run.
Weeks 1–9 were made before this kit existed, so they have no source here.
