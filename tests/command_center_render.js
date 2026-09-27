/* Renders every Command Center tab, and every drill-down its cards
   offer, in both Real and Sample mode — outside a browser.

   Input (stdin, JSON):  { plan, progress, investigations }
   Output (stdout, JSON): { "<mode>/<tab>": { html, details: { key: html }, error } }

   Used by tests/test_command_center_render.py. It loads the page's own
   scripts (command-center/assets/tabs.js and the helper half of app.js)
   into a sandbox, so it tests the code that ships, not a copy of it. */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ASSETS = path.join(__dirname, '..', 'command-center', 'assets');
const tabsSrc = fs.readFileSync(path.join(ASSETS, 'tabs.js'), 'utf8');
// app.js = constants + helpers, then the DOM shell. Only the first half is
// needed (and safe) without a browser.
const appSrc = fs.readFileSync(path.join(ASSETS, 'app.js'), 'utf8')
  .split('/* ---------- shell rendering')[0];

const sandbox = {
  console, Date, Math, JSON,
  localStorage: { getItem: () => null, setItem: () => {} },
  location: { hash: '' },
};
vm.createContext(sandbox);
vm.runInContext(`${tabsSrc}\n${appSrc}\nthis.__tabs = TAB_RENDERERS;`, sandbox);

const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const unescape = s => s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
  .replace(/&quot;/g, '"').replace(/&#39;/g, "'");

const out = {};
for (const mode of ['real', 'sample']) {
  for (const [id, tab] of Object.entries(sandbox.__tabs)) {
    const ctx = { ...input, isSample: mode === 'sample' };
    const result = { html: null, details: {}, error: null };
    try {
      result.html = tab.render(ctx);
      const keys = [...result.html.matchAll(/data-detail="([^"]+)"/g)].map(m => unescape(m[1]));
      for (const key of keys) {
        try {
          result.details[key] = tab.detail(key, ctx);
        } catch (err) {
          result.details[key] = `ERROR: ${err.message}`;
        }
      }
    } catch (err) {
      result.error = err.message;
    }
    out[`${mode}/${id}`] = result;
  }
}
process.stdout.write(JSON.stringify(out));
