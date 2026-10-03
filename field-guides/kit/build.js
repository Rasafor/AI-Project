#!/usr/bin/env node
'use strict';
// Build one weekly field guide from field-guides/<NN-slug>/content.js into a single
// self-contained HTML file at the repo root (meta.file).
//
//   node field-guides/kit/build.js field-guides/10-devops-engineer
//
// Deterministic: same content.js -> byte-identical output (no clocks, no randomness;
// dates come from content.meta). Safe to re-run; it overwrites only meta.file.
// Fails loud (exit 1, message on stderr) on any contract violation instead of
// writing a half-valid guide.

const fs = require('fs');
const path = require('path');
const { esc, table } = require('./parts');

const KIT = __dirname;
const REPO = path.resolve(KIT, '..', '..');
const read = (f) => fs.readFileSync(path.join(KIT, f), 'utf8');

function fail(msg) { process.stderr.write(`build: ${msg}\n`); process.exit(1); }

function validate(c) {
  const need = (cond, msg) => { if (!cond) fail(msg); };
  const m = c.meta || {};
  for (const k of ['week', 'discipline', 'title', 'file', 'date', 'buildNumber', 'description', 'studentId', 'projectId', 'author', 'authorTitle'])
    need(m[k] !== undefined && m[k] !== '', `meta.${k} is required`);
  need(/^[A-Za-z]+_FieldGuide\.html$/.test(m.file), 'meta.file must look like <Discipline>_FieldGuide.html');
  need(/^\d{4}-\d{2}-\d{2}$/.test(m.date), 'meta.date must be YYYY-MM-DD');
  const ex = c.example || {};
  for (const k of ['industry', 'organization', 'initiative', 'short', 'docPrefix']) need(ex[k], `example.${k} is required`);
  need(c.hero && c.hero.lede, 'hero.lede is required');
  need(c.start, 'start (the "How to use this guide" body) is required');
  need(Array.isArray(c.sections) && c.sections.length >= 8, 'sections: at least 8 teaching sections');
  need(Array.isArray(c.documents) && c.documents.length >= 3, 'documents: at least 3');
  need(Array.isArray(c.faq) && c.faq.length >= 15, 'faq: at least 15 grounded entries');
  need(c.people && c.people.reviewed && c.people.approved, 'people.reviewed and people.approved are required');
  const ids = new Set(['start', 'library', 'glossary']);
  for (const s of c.sections) {
    need(s.id && s.title && s.group && s.html, `section ${s.id || '?'} needs id, title, group, html`);
    need(!ids.has(s.id), `duplicate section id ${s.id}`); ids.add(s.id);
  }
  for (const d of c.documents) {
    need(d.key && d.title && d.sub && d.desc && d.owner && d.question && d.html, `document ${d.key || '?'} needs key, title, sub, desc, owner, question, html`);
    need(Array.isArray(d.lens) && d.lens.length >= 3, `document ${d.key}: lens needs 3+ review points`);
    need(!ids.has('doc-' + d.key), `duplicate document key ${d.key}`); ids.add('doc-' + d.key);
    for (const csv of d.csv || []) for (const r of csv.rows) need(r.length === csv.head.length, `document ${d.key}: CSV ${csv.name} row width != header width`);
  }
  for (const f of c.faq) need(f.q && f.a && f.ref && ids.has(f.ref), `faq "${f.q}" must reference an existing section id (got ${f.ref})`);
  const a = c.ask || {};
  need(Array.isArray(a.suggestions) && a.suggestions.length >= 4 && a.placeholder && a.noMatchHint && a.notCovered, 'ask needs suggestions (4+), placeholder, noMatchHint, notCovered');
}

function documentSection(c, d, i) {
  const m = c.meta, ex = c.example, n = i + 1, total = c.documents.length;
  const docId = `${ex.docPrefix}-${String(n).padStart(2, '0')}`;
  const status = d.status || 'Approved';
  const prepared = c.people.prepared || { name: m.author, title: m.authorTitle };
  const sig = (role, p, date) => `<div class="sig"><div class="sig-role">${role}</div><div class="sig-line"></div><div class="sig-name">${esc(p.name)}</div><div class="sig-title">${esc(p.title)}</div><div class="sig-date">${date}</div></div>`;
  const fmts = ['HTML', 'PDF'].concat((d.csv || []).length ? ['CSV'] : [], d.sql ? ['SQL'] : []);
  const btns = [`<button class="btn primary" data-act="html" data-doc="${d.key}">Download HTML</button>`, `<button class="btn" data-act="pdf" data-doc="${d.key}">Save as PDF</button>`]
    .concat((d.csv || []).map((csv, k) => `<button class="btn" data-act="csv" data-doc="${d.key}" data-i="${k}">Download ${esc(csv.label || 'CSV')}</button>`))
    .concat(d.sql ? [`<button class="btn" data-act="sql" data-doc="${d.key}">Download .sql</button>`] : []);
  const revisions = d.revisions || [['1.0', m.date, m.author, 'Issued for sign-off']];
  const html =
    `<section class="sec docsec" id="doc-${d.key}" data-title="Document ${n}: ${esc(d.title)}"><div class="sec-head"><div class="eyebrow">Document ${n} of ${total} &middot; ${docId}</div><h2 class="sec-title">${esc(d.title)}</h2></div>\n` +
    `<div class="doc-toolbar">${btns.join('')}</div>\n` +
    `<div class="lens"><b>Review lens for this document</b><ul>${d.lens.map((l) => `<li>${l}</li>`).join('')}</ul></div>\n` +
    `<article class="doc" id="art-${d.key}" data-doc="${d.key}" data-title="${esc(d.title)}">\n` +
    `<header class="doc-cover">\n  <img class="doc-logo" data-logo alt="Colaberry" />\n  <div class="doc-kicker">${esc(ex.organization)} &middot; ${esc(ex.short)} Program</div>\n` +
    `  <h1 class="doc-title">${esc(d.title)}</h1>\n  <div class="doc-sub">${esc(d.sub)}</div>\n  <div class="doc-cover-meta">Document ${docId} &middot; Version 1.0 &middot; ${m.date}</div>\n</header>\n` +
    `<div class="doc-control">\n  <div><span>Document ID</span>${docId}</div><div><span>Version</span>1.0</div><div><span>Owner</span>${esc(m.author)}</div>\n` +
    `  <div><span>Status</span><b class="st ${status === 'Approved' ? 'ok' : 'warn'}">${esc(status)}</b></div><div><span>Date</span>${m.date}</div><div><span>Classification</span>Internal</div>\n</div>\n` +
    `<div class="doc-body">\n${d.html}\n<h2>Revision history</h2>\n${table(['Version', 'Date', 'Author', 'Change'], revisions)}\n</div>\n` +
    `<div class="signoff"><div class="signoff-t">Sign-off</div><div class="sigs">${sig('Prepared by', prepared, m.date)}${sig('Reviewed by', (d.people && d.people.reviewed) || c.people.reviewed, m.date)}${sig('Approved by', (d.people && d.people.approved) || c.people.approved, m.date)}</div></div>\n` +
    `<footer class="doc-foot"><span>${esc(ex.organization)} &middot; ${esc(ex.short)} &middot; ${docId} v1.0</span><span>Internal &middot; Illustrative teaching example, Colaberry Enterprise AI Leadership Accelerator</span></footer>\n` +
    `</article></section>`;
  const file = `${ex.short.replace(/[^A-Za-z0-9]+/g, '')}_${docId}_${d.title.replace(/[^A-Za-z0-9]+/g, '_').replace(/^_|_$/g, '')}`;
  return { html, docId, fmts, data: { file, csv: d.csv || [], sql: d.sql || null } };
}

// JSON inside <script>: escape "<" so "</script>" in content cannot end the block.
const jsonBlock = (id, obj, pretty) => `<script type="application/json" id="${id}">${JSON.stringify(obj, null, pretty ? 2 : 0).replace(/</g, '\\u003c')}</script>`;

function build(dir) {
  const contentPath = path.resolve(dir, 'content.js');
  if (!fs.existsSync(contentPath)) fail(`no content.js in ${dir}`);
  const c = require(contentPath);
  validate(c);
  const m = c.meta, ex = c.example;
  const docs = c.documents.map((d, i) => documentSection(c, d, i));
  const docData = Object.fromEntries(c.documents.map((d, i) => [d.key, docs[i].data]));
  const groups = [];
  for (const s of c.sections) { let g = groups.find((x) => x.name === s.group); if (!g) groups.push(g = { name: s.group, items: [] }); g.items.push(s); }

  const nav = '<nav class="side" id="side" aria-label="Topics"><div class="ng">Start here</div><a href="#start" data-nav="start">How to use this guide</a>' +
    groups.map((g) => `<div class="ng">${esc(g.name)}</div>` + g.items.map((s) => `<a href="#${s.id}" data-nav="${s.id}">${esc(s.title)}</a>`).join('')).join('') +
    '<div class="ng">Documents</div><a href="#library" data-nav="library">Document library</a>' +
    c.documents.map((d, i) => `<a href="#doc-${d.key}" data-nav="doc-${d.key}">${i + 1}. ${esc(d.title)}</a>`).join('') +
    '<div class="ng">Reference</div><a href="#glossary" data-nav="glossary">Glossary</a></nav>';

  const sec = (id, eyebrow, title, body) => `<section class="sec" id="${id}" data-title="${esc(title)}"><div class="sec-head"><div class="eyebrow">${eyebrow}</div><h2 class="sec-title">${esc(title)}</h2></div>\n${body}</section>`;
  const nDocs = c.documents.length;
  const hero = `<div class="hero"><div class="eyebrow">Colaberry Enterprise AI Leadership Accelerator &middot; Week ${m.week} deep dive</div>\n<h1>${esc(m.title)}</h1>\n<p>${c.hero.lede}</p>\n` +
    `<div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn primary" data-ask-open>Ask the guide</button><a class="btn" href="#library" style="text-decoration:none">Open the ${nDocs} documents</a></div>\n` +
    `<div class="hero-meta">${[`${c.sections.length} topics`, `${nDocs} full documents`].concat(c.hero.chips || [], ['offline, self-contained']).map((x) => `<span class="chip">${esc(x)}</span>`).join('')}</div></div>`;
  const library = sec('library', 'Documents', 'Document library', (c.libraryIntro || `<p>${nDocs} deliverables for ${esc(ex.short)}, each a complete, designed document with a cover, document control, sign-off block and footer. Every document downloads as a standalone HTML file and prints to PDF with the same design; tabular documents also export CSV.</p>`) +
    `\n<div class="lib">${c.documents.map((d, i) => `<a href="#doc-${d.key}"><div class="n">${docs[i].docId} &middot; Document ${i + 1}</div><div class="t">${esc(d.title)}</div><div class="d">${esc(d.desc)}</div><div class="f">${docs[i].fmts.join(' &middot; ')}</div></a>`).join('')}</div>\n` +
    table(['Document', 'Owner', 'Status', 'Answers the question'], c.documents.map((d, i) => [`${docs[i].docId} ${esc(d.title)}`, esc(d.owner), esc(d.status || 'Approved'), esc(d.question)])));
  const glossary = sec('glossary', 'Reference', 'Glossary', table(['Term', 'Meaning'], (c.glossary || []).slice().sort((a, b) => a[0].localeCompare(b[0]))));

  const metadata = {
    guide_type: m.title, curriculum_type: 'deep_dive', week: m.week, discipline: m.discipline,
    student_id: m.studentId, project_id: m.projectId, repository: m.repository || 'https://github.com/Rasafor/AI-Project',
    generated_by: 'Claude Code', generated_date: m.date, version: m.version || '1.0.0', build_number: m.buildNumber,
    example: { industry: ex.industry, organization: ex.organization, initiative: ex.initiative },
    documents: c.documents.map((d, i) => ({ id: docs[i].docId, title: d.title, formats: docs[i].fmts.map((f) => f.toLowerCase()) })),
  };
  const config = { themeKey: m.file.replace(/_FieldGuide\.html$/, '').toLowerCase() + '-theme', short: ex.short, suggestions: c.ask.suggestions, noMatchHint: c.ask.noMatchHint, notCovered: c.ask.notCovered };
  const logo = read('logo.b64').trim();

  const out = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(m.title)}</title>
<meta name="description" content="${esc(m.description)}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;600;700&family=Roboto+Mono:wght@400;600&display=swap" rel="stylesheet">
<style id="doc-css">
${read('doc.css')}</style>
<style>
${read('guide.css')}</style>
${jsonBlock('deepdive-metadata', metadata, true)}
${jsonBlock('guide-config', config)}
</head>
<body>
<header class="top">
  <button class="btn icon-btn" id="menu-btn" aria-label="Show topics" aria-expanded="false">Topics</button>
  <img id="cb-logo" src="data:image/png;base64,${logo}" alt="Colaberry">
  <div class="top-title">${esc(m.title)}<small>Week ${m.week} deep dive</small></div>
  <div class="search" role="search">
    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg>
    <input id="q" type="search" placeholder="${esc(c.ask.searchPlaceholder || 'Search topics, documents, terms...')}" aria-label="Search the guide" autocomplete="off">
    <span class="kbd">/</span>
    <div id="qres" role="listbox" aria-label="Search results"></div>
  </div>
  <button class="btn primary" data-ask-open>Ask</button>
  <button class="btn icon-btn" id="theme-btn" aria-label="Toggle dark mode" title="Toggle dark mode">Theme</button>
</header>
<div class="layout">
${nav}
<main id="main">${hero}${sec('start', 'Start here', 'How to use this guide', c.start)}
${c.sections.map((s) => sec(s.id, s.eyebrow || esc(s.group), s.title, s.html)).join('\n')}
${library}
${docs.map((d) => d.html).join('\n')}
${glossary}
<div class="site-foot">Colaberry Enterprise AI Leadership Accelerator &middot; ${esc(m.title)} v${esc(metadata.version)} &middot; build ${esc(m.buildNumber)} &middot; generated ${m.date} by Claude Code. ${esc(ex.organization)} and all figures are illustrative.</div>
</main>
</div>
<aside id="ask" aria-label="Ask the guide" aria-hidden="true">
  <div class="ask-h"><b>Ask the guide</b><button class="btn icon-btn" id="ask-close" aria-label="Close">Close</button></div>
  <div class="ask-log" id="ask-log" aria-live="polite">
    <p class="note">Answers come only from this guide's own content, matched offline. Each answer names the section it came from. No external service is called.</p>
    <div class="sugs" id="sugs"></div>
  </div>
  <form class="ask-f" id="ask-form"><input id="ask-in" placeholder="${esc(c.ask.placeholder)}" aria-label="Your question" autocomplete="off"><button class="btn primary" type="submit">Ask</button></form>
</aside>
${jsonBlock('doc-data', docData)}
${jsonBlock('faq-data', c.faq)}
<script>${read('engine.js')}</script>
</body>
</html>
`;
  const dest = path.join(REPO, m.file);
  fs.writeFileSync(dest, out, 'utf8');
  process.stdout.write(`build: wrote ${m.file} (${Math.round(out.length / 1024)} KB, ${c.sections.length} sections, ${nDocs} documents, ${c.faq.length} FAQ)\n`);
  return dest;
}

if (require.main === module) {
  if (process.argv.length !== 3) fail('usage: node field-guides/kit/build.js field-guides/<NN-slug>');
  build(process.argv[2]);
}
module.exports = { build };
