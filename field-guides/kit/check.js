#!/usr/bin/env node
'use strict';
// Verify a built field guide in headless Chrome (no npm dependencies).
//
//   node field-guides/kit/check.js field-guides/10-devops-engineer [--shots <dir>]
//
// Loads <repo>/<meta.file> with an injected harness and checks: zero script errors,
// metadata block, logo on every document cover, doc-data <-> article agreement,
// nav links resolve, the search and Ask questions in content.checks land on the
// expected section (expect may list several acceptable ids), an off-topic question is refused, no horizontal overflow at
// 1280px or 390px. --shots also writes light/dark/narrow screenshots for review.
// Read-only on the repo: harness copies go to the OS temp dir and are removed.
// Exit 0 = every check passed; 1 = a check failed; 2 = could not run (no Chrome,
// timeout, harness produced no result).

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const REPO = path.resolve(__dirname, '..', '..');
const CHROME_TIMEOUT_MS = 60000;
// Headless Chrome will not open a window narrower than 500px, so the phone-width
// run pins the page itself to 390px inside a 500px window and measures against that.
const PHONE = 390, PHONE_WINDOW = 500;
const PIN = `<style>html{width:${PHONE}px;max-width:${PHONE}px}</style>`;

function die(code, msg) { process.stderr.write(`check: ${msg}\n`); process.exit(code); }

function findChrome() {
  const c = [process.env.CHROME_PATH,
    'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', '/usr/bin/google-chrome', '/usr/bin/chromium',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'].filter(Boolean);
  const hit = c.find((p) => fs.existsSync(p));
  if (!hit) die(2, 'no Chrome/Edge found; set CHROME_PATH');
  return hit;
}

function chrome(bin, args) {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'fg-profile-'));
  try {
    return execFileSync(bin, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', `--user-data-dir=${profile}`, ...args],
      { encoding: 'utf8', timeout: CHROME_TIMEOUT_MS, maxBuffer: 64 * 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'] });
  } catch (e) {
    die(2, `Chrome failed or timed out after ${CHROME_TIMEOUT_MS} ms: ${e.code || ''} ${String(e.stderr || e.message).slice(0, 400)}`);
  } finally {
    fs.rmSync(profile, { recursive: true, force: true });
  }
}

// Runs inside the page. Writes its result as JSON into <pre id="__check">.
function harness(CHECKS, EXPECT) {
  const out = { errors: window.__errs, fails: [], passes: [] };
  const ok = (cond, name, detail) => (cond ? out.passes : out.fails).push(name + (cond || !detail ? '' : ' -- ' + detail));
  const sectionOf = (id) => { const el = id && document.getElementById(id); const s = el && el.closest('section'); return s ? s.id : null; };
  try {
    const meta = JSON.parse(document.getElementById('deepdive-metadata').textContent);
    ok(meta.week === EXPECT.week && meta.discipline === EXPECT.discipline, 'metadata week/discipline match content.js', JSON.stringify([meta.week, meta.discipline]));
    ['guide_type', 'curriculum_type', 'student_id', 'project_id', 'generated_date', 'build_number'].forEach((k) => ok(!!meta[k], 'metadata has ' + k));
    const logos = [...document.querySelectorAll('img[data-logo]')];
    ok(logos.length === EXPECT.docs && logos.every((i) => /^data:image\/png;base64,/.test(i.getAttribute('src'))), `logo on all ${EXPECT.docs} document covers`, `${logos.length} found`);
    const data = JSON.parse(document.getElementById('doc-data').textContent);
    const arts = [...document.querySelectorAll('article.doc')].map((a) => a.dataset.doc);
    ok(JSON.stringify(Object.keys(data)) === JSON.stringify(arts), 'doc-data matches articles', JSON.stringify([Object.keys(data), arts]));
    Object.entries(data).forEach(([k, d]) => d.csv.forEach((c) => ok(c.rows.length > 0, `CSV ${c.name} has rows`)));
    const dead = [...document.querySelectorAll('a[href^="#"]')].map((a) => a.getAttribute('href').slice(1)).filter((id) => id && !document.getElementById(id));
    ok(dead.length === 0, 'every in-page link resolves', dead.slice(0, 5).join(', '));
    const q = document.getElementById('q');
    (CHECKS.search || []).forEach((t) => {
      q.value = t.q; q.dispatchEvent(new Event('focus'));
      const first = document.querySelector('#qres .qr[data-id]');
      const got = first ? sectionOf(first.dataset.id) : null;
      ok([].concat(t.expect).indexOf(got) >= 0, `search "${t.q}" -> ${[].concat(t.expect).join(' | ')}`, 'got ' + got);
    });
    q.value = ''; q.dispatchEvent(new Event('focus'));
    const form = document.getElementById('ask-form'), inp = document.getElementById('ask-in');
    const ask = (text) => { inp.value = text; form.dispatchEvent(new Event('submit', { cancelable: true })); const b = [...document.querySelectorAll('#ask-log .abub')]; return b[b.length - 1]; };
    (CHECKS.ask || []).forEach((t) => {
      const b = ask(t.q), a = b && b.querySelector('.src a[data-go]');
      const got = a ? sectionOf(a.dataset.go) : null;
      ok([].concat(t.expect).indexOf(got) >= 0, `ask "${t.q}" -> ${[].concat(t.expect).join(' | ')}`, 'got ' + got);
    });
    if (CHECKS.offTopic) { const b = ask(CHECKS.offTopic); ok(b && b.classList.contains('none'), `off-topic "${CHECKS.offTopic}" is refused`); }
  } catch (e) { out.fails.push('harness exception: ' + e.message); }
  out.overflow = document.documentElement.scrollWidth - window.innerWidth;
  const pre = document.createElement('pre'); pre.id = '__check'; pre.textContent = JSON.stringify(out); document.body.appendChild(pre);
}

function instrument(html, extraHead, extraBody) {
  const head = '<script>window.__errs=[];addEventListener("error",function(e){__errs.push(String(e.message))});addEventListener("unhandledrejection",function(e){__errs.push(String(e.reason))});</script>';
  // Inject before the LAST </body>: engine.js itself contains the string '</body></html>'.
  const out = html.replace('<head>', '<head>' + head + (extraHead || ''));
  const at = out.lastIndexOf('</body>');
  return out.slice(0, at) + (extraBody || '') + out.slice(at);
}

function main() {
  const args = process.argv.slice(2);
  const dir = args[0];
  if (!dir) die(2, 'usage: node field-guides/kit/check.js field-guides/<NN-slug> [--shots <dir>]');
  const shots = args[1] === '--shots' ? path.resolve(args[2] || '') : null;
  const c = require(path.resolve(dir, 'content.js'));
  const file = path.join(REPO, c.meta.file);
  if (!fs.existsSync(file)) die(2, `${c.meta.file} not built yet; run build.js first`);
  const html = fs.readFileSync(file, 'utf8');
  const bin = findChrome();
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'fg-check-'));
  const fails = [];
  try {
    const expect = { week: c.meta.week, discipline: c.meta.discipline, docs: c.documents.length };
    const runner = `<script>setTimeout(function(){(${harness.toString()})(${JSON.stringify(c.checks || {})},${JSON.stringify(expect)})},400);</script>`;
    for (const [w, h, full] of [[1280, 900, true], [PHONE, 844, false]]) {
      const p = path.join(tmp, `check-${w}.html`);
      fs.writeFileSync(p, instrument(html, full ? '' : PIN, full ? runner : `<script>setTimeout(function(){var p=document.createElement('pre');p.id='__check';p.textContent=JSON.stringify({errors:window.__errs,fails:[],passes:[],overflow:document.body.scrollWidth-${PHONE}});document.body.appendChild(p)},400);</script>`));
      const dom = chrome(bin, ['--virtual-time-budget=10000', `--window-size=${full ? w : PHONE_WINDOW},${h}`, '--dump-dom', 'file:///' + p.replace(/\\/g, '/')]);
      const m = dom.match(/<pre id="__check">([\s\S]*?)<\/pre>/);
      if (!m) die(2, `harness produced no result at ${w}px (page script likely failed before it ran)`);
      const r = JSON.parse(m[1].replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&'));
      r.passes.forEach((x) => console.log(`PASS  ${x}`));
      r.fails.forEach((x) => { console.log(`FAIL  ${x}`); fails.push(x); });
      const errLine = `no script errors at ${w}px`;
      if (r.errors.length) { console.log(`FAIL  ${errLine} -- ${r.errors.join(' | ')}`); fails.push(errLine); } else console.log(`PASS  ${errLine}`);
      const ovLine = `no horizontal overflow at ${w}px`;
      if (r.overflow > 1) { console.log(`FAIL  ${ovLine} -- ${r.overflow}px too wide`); fails.push(ovLine); } else console.log(`PASS  ${ovLine}`);
    }
    if (shots) {
      fs.mkdirSync(shots, { recursive: true });
      const plan = [['light-1280', 1280, 2400, 'light', ''], ['dark-1280', 1280, 2400, 'dark', ''], ['light-390', PHONE_WINDOW, 2400, 'light', '']]
        .concat(c.documents.map((d) => [`doc-${d.key}`, 1280, 1800, 'light', `#doc-${d.key}`]), c.documents.slice(0, 1).map((d) => [`doc-${d.key}-dark`, 1280, 1800, 'dark', `#doc-${d.key}`]));
      for (const [name, w, h, theme, hash] of plan) {
        const p = path.join(tmp, `shot-${name}.html`);
        // Document shots isolate one document instead of scrolling to its anchor
        // (anchor scrolling is not captured reliably in headless screenshots).
        const pin = name === 'light-390' ? PIN : '';
        const only = hash ? `<style>.top,nav.side{display:none!important}.layout{display:block}main>*:not(${hash}){display:none!important}</style>` : '';
        fs.writeFileSync(p, html.replace('<html lang="en">', `<html lang="en" data-theme="${theme}">`).replace('</head>', pin + only + '</head>'));
        chrome(bin, ['--virtual-time-budget=5000', '--hide-scrollbars', `--window-size=${w},${h}`, `--screenshot=${path.join(shots, name + '.png')}`, 'file:///' + p.replace(/\\/g, '/')]);
      }
      console.log(`shots written to ${shots} (page top in light/dark/narrow, plus each document)`);
    }
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  console.log(fails.length ? `\ncheck: ${fails.length} FAILED` : '\ncheck: all passed');
  process.exit(fails.length ? 1 : 0);
}

main();
