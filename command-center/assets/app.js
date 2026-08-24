/* ============================================================
   Command Center — application shell
   Reads .colaberry/plan.json, progress.json, manifest.json,
   profile.json at RUNTIME (fetch). Nothing from those files is
   ever copied into this script — if you delete a story from
   plan.json and reload, it disappears from every tab that lists
   it, because every tab re-derives from the fetched data on
   every render. Tab content itself lives in tabs.js (loaded
   before this file); this file is routing and chrome only.
   ============================================================ */

const DATA_PATHS = {
  plan: '.colaberry/plan.json',
  progress: '.colaberry/progress.json',
  manifest: '.colaberry/manifest.json',
  profile: '.colaberry/profile.json',
};

const TABS = [
  { id: 'overview',   label: 'Overview' },
  { id: 'outcomes',   label: 'Outcomes' },
  { id: 'users',      label: 'Users & Use Case' },
  { id: 'guardrails', label: 'Guardrails' },
  { id: 'systems',    label: 'Systems' },
  { id: 'pm',         label: 'Project Mgmt' },
  { id: 'agents',     label: 'AI Agents' },
  { id: 'kb',         label: 'Knowledge Base' },
  { id: 'datamodel',  label: 'Data Model' },
];

// Sample-mode illustrative story states. Used ONLY when the Sample
// toggle is on; Real mode always reads state from progress.json.
const SAMPLE_STORY_STATES = {
  'STORY-001': 'verified', 'STORY-002': 'verified', 'STORY-003': 'verified',
  'STORY-004': 'verified', 'STORY-010': 'verified', 'STORY-005': 'verified',
  'STORY-006': 'in_progress', 'STORY-007': 'in_progress',
  'STORY-008': 'submitted',
  'STORY-009': 'not_started',
};

const state = {
  data: null,        // { plan, progress, manifest, profile }
  loadError: null,
  mode: (localStorage.getItem('cc_mode') === 'sample') ? 'sample' : 'real',
  activeTab: (location.hash.replace('#/', '') || 'overview'),
  detail: null,       // generic drilldown key for the active tab
};

async function loadAll() {
  const entries = Object.entries(DATA_PATHS);
  const results = {};
  for (const [key, path] of entries) {
    try {
      const res = await fetch(path, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      results[key] = await res.json();
    } catch (err) {
      throw new Error(`Could not load ${path}: ${err.message}`);
    }
  }
  return results;
}

/* ---------- shared helpers (used across tabs.js) ---------- */

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function fmtAbsoluteDate(d) {
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
}

function fmtRelative(diffMs) {
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'moments ago';
  if (mins < 60) return `${mins} minute${mins === 1 ? '' : 's'} ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return '1 day ago';
  return `${days} days ago`;
}

function dataAsOf(generatedAtISO) {
  const gen = new Date(generatedAtISO);
  const now = new Date();
  const diffMs = now - gen;
  const days = diffMs / 86400000;
  return {
    text: `Data as of ${fmtAbsoluteDate(gen)} (${fmtRelative(diffMs)})`,
    warn: days > 7,
  };
}

function daysBetween(a, b) {
  return (new Date(b) - new Date(a)) / 86400000;
}

function statePill(st) {
  const map = {
    not_started: ['grey', 'Not started'],
    in_progress: ['amber', 'In progress'],
    submitted: ['amber', 'Submitted'],
    verified: ['green', 'Verified'],
  };
  const [cls, label] = map[st] || ['grey', st];
  return `<span class="cc-pill ${cls}">${escapeHtml(label)}</span>`;
}

function effectiveStoryState(storyId, ctx) {
  if (ctx.isSample) return SAMPLE_STORY_STATES[storyId] || 'not_started';
  const p = ctx.progress.stories.find(ps => ps.id === storyId);
  return p ? p.verification.state : 'not_started';
}

function sampleStrip(isSample, note) {
  if (!isSample) return '';
  return `<div class="cc-sample-strip"><span class="cc-sample-badge">Sample</span>&nbsp;${escapeHtml(note)}</div>`;
}

/* ---------- shell rendering ---------- */

function renderHeader() {
  const el = document.getElementById('cc-header');
  let stampHtml = '';
  if (state.data) {
    const stamp = dataAsOf(state.data.manifest.generated_at);
    stampHtml = `<span class="cc-dataof ${stamp.warn ? 'warn' : ''}">${stamp.warn ? 'Stale — sync from the portal to refresh · ' : ''}${escapeHtml(stamp.text)}</span>`;
  }
  el.innerHTML = `
    <div class="cc-header-top">
      <div class="cc-brand"><span class="dot"></span>Command Center</div>
      ${stampHtml}
      <div class="cc-spacer"></div>
      <div class="cc-toggle" role="group" aria-label="Sample or real data">
        <button data-mode="real" class="${state.mode === 'real' ? 'active' : ''}">Real</button>
        <button data-mode="sample" class="${state.mode === 'sample' ? 'active' : ''}">Sample</button>
      </div>
    </div>
    <nav class="cc-nav">
      ${TABS.map(t => `<a href="#/${t.id}" data-tab="${t.id}" class="${state.activeTab === t.id ? 'active' : ''}">${t.label}</a>`).join('')}
    </nav>
  `;
  el.querySelectorAll('[data-mode]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.mode = btn.dataset.mode;
      localStorage.setItem('cc_mode', state.mode);
      renderAll();
    });
  });
}

function renderAll() {
  renderHeader();
  renderTabBody();
}

function switchTab(id) {
  state.activeTab = id;
  state.detail = null;
  location.hash = `#/${id}`;
  renderAll();
}

window.addEventListener('hashchange', () => {
  const id = location.hash.replace('#/', '') || 'overview';
  if (TABS.some(t => t.id === id)) {
    state.activeTab = id;
    state.detail = null;
    renderAll();
  }
});

function renderTabBody() {
  const main = document.getElementById('cc-main');
  if (state.loadError) {
    main.innerHTML = `
      <div class="cc-error">
        <strong>Could not load the Command Center's data files.</strong>
        ${escapeHtml(state.loadError)}<br><br>
        This almost always means the page was opened directly from disk
        (a <code>file://</code> address) instead of served over http — browsers
        block a static page from reading local JSON files that way.
        From the repo root, run <code>python -m http.server</code> (or any static
        file server) and open <code>http://localhost:8000/</code> instead.
        On GitHub Pages this works automatically, no server needed.
      </div>
    `;
    return;
  }
  const tabDef = TABS.find(t => t.id === state.activeTab) || TABS[0];
  const entry = TAB_RENDERERS[tabDef.id];
  const ctx = { plan: state.data.plan, progress: state.data.progress, isSample: state.mode === 'sample' };
  const bodyHtml = entry.render(ctx);
  const detailHtml = state.detail ? entry.detail(state.detail, ctx) : '';
  main.innerHTML = bodyHtml + detailHtml;
  wireDetailButtons();
  if (entry.wire) entry.wire(ctx);
}

function wireDetailButtons() {
  document.querySelectorAll('[data-detail]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.detail = btn.dataset.detail;
      renderTabBody();
      document.querySelector('.cc-detail')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
  });
  document.querySelectorAll('[data-back]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.detail = null;
      renderTabBody();
    });
  });
}

/* ---------- nav wiring (delegated) ---------- */
document.addEventListener('click', (e) => {
  const a = e.target.closest('[data-tab]');
  if (a) {
    e.preventDefault();
    switchTab(a.dataset.tab);
  }
});

/* ---------- boot ---------- */
(async function boot() {
  try {
    state.data = await loadAll();
  } catch (err) {
    state.loadError = err.message;
  }
  renderAll();
})();
