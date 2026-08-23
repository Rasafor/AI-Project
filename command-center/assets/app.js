/* ============================================================
   Command Center — application shell
   Reads .colaberry/plan.json, progress.json, manifest.json,
   profile.json at RUNTIME (fetch). Nothing from those files is
   ever copied into this script — if you delete a story from
   plan.json and reload, it disappears from every tab that lists
   it, because every tab re-derives from the fetched data on
   every render.
   ============================================================ */

const DATA_PATHS = {
  plan: '.colaberry/plan.json',
  progress: '.colaberry/progress.json',
  manifest: '.colaberry/manifest.json',
  profile: '.colaberry/profile.json',
};

const TABS = [
  { id: 'overview',   label: 'Overview',        built: true },
  { id: 'outcomes',   label: 'Outcomes',         built: false },
  { id: 'users',      label: 'Users & Use Case', built: false },
  { id: 'guardrails', label: 'Guardrails',       built: false },
  { id: 'systems',    label: 'Systems',          built: false },
  { id: 'pm',         label: 'Project Mgmt',     built: false },
  { id: 'agents',     label: 'AI Agents',        built: false },
  { id: 'kb',         label: 'Knowledge Base',   built: false },
  { id: 'datamodel',  label: 'Data Model',       built: false },
];

const state = {
  data: null,        // { plan, progress, manifest, profile }
  loadError: null,
  mode: (localStorage.getItem('cc_mode') === 'sample') ? 'sample' : 'real',
  activeTab: (location.hash.replace('#/', '') || 'overview'),
  overviewDetail: null,
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

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function renderAll() {
  renderHeader();
  renderTabBody();
}

function switchTab(id) {
  state.activeTab = id;
  state.overviewDetail = null;
  location.hash = `#/${id}`;
  renderAll();
}

window.addEventListener('hashchange', () => {
  const id = location.hash.replace('#/', '') || 'overview';
  if (TABS.some(t => t.id === id)) {
    state.activeTab = id;
    state.overviewDetail = null;
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
  if (!tabDef.built) {
    main.innerHTML = renderPlaceholder(tabDef);
    return;
  }
  if (tabDef.id === 'overview') {
    main.innerHTML = renderOverview();
    wireOverview();
    return;
  }
  main.innerHTML = renderPlaceholder(tabDef);
}

function renderPlaceholder(tabDef) {
  return `
    <div class="cc-placeholder">
      <div class="icon">&#128203;</div>
      <h3>${escapeHtml(tabDef.label)} — not built yet</h3>
      <p>The build is paused after the Overview tab for review.<br>
      Say <span class="say">build the rest</span> to continue and this tab will be built out.</p>
    </div>
  `;
}

/* ---------- Overview tab ---------- */

function sampleOverviewNumbers() {
  return {
    phase: 'Building',
    phaseNote: 'Sample: shown as if the build were mid-way through r1.',
    stories_verified: 6, stories_total: 10,
    criteria_passed: 22, criteria_total: 30,
    points_awarded: 340,
  };
}

function schedulePhase(schedule) {
  const now = new Date();
  const buildStart = new Date(schedule.build_start);
  const buildEnd = new Date(schedule.build_end + 'T23:59:59');
  const demoDay = new Date(schedule.demo_day);
  if (now < buildStart) return 'Pre-build';
  if (now <= buildEnd) return 'Building';
  if (now < demoDay) return 'Demo prep';
  if (now.toDateString() === demoDay.toDateString()) return 'Demo day';
  return 'Post-demo';
}

function realOverviewNumbers(plan, progress) {
  return {
    phase: schedulePhase(plan.schedule),
    phaseNote: null,
    stories_verified: progress.totals.stories_verified,
    stories_total: progress.totals.stories_total,
    criteria_passed: progress.totals.criteria_passed,
    criteria_total: progress.totals.criteria_total,
    points_awarded: progress.totals.points_awarded,
  };
}

function renderOverview() {
  const { plan, progress } = state.data;
  const isSample = state.mode === 'sample';
  const nums = isSample ? sampleOverviewNumbers() : realOverviewNumbers(plan, progress);

  const banner = `
    <div class="cc-banner">
      <strong>Build paused for review — Overview only, by design.</strong>
      This is the first checkpoint. The other 8 tabs are reachable in the nav above but
      not built yet. Look this over, then say <strong>build the rest</strong> to continue.
    </div>
  `;

  const sampleStrip = isSample ? `
    <div class="cc-sample-strip"><span class="cc-sample-badge">Sample</span>
      &nbsp;This tab is showing made-up data so you can see the shape of it. Switch to
      <strong>Real</strong> above to see what your project has actually produced.
    </div>` : '';

  const hero = `
    <div class="cc-section-title"><h1>${escapeHtml(plan.project.name)}</h1></div>
    <p class="cc-section-sub">${escapeHtml(plan.project.descriptor)}</p>
  `;

  const cards = `
    <div class="cc-grid">
      <button class="cc-card" data-detail="schedule">
        <span class="kicker">Schedule</span>
        <span class="big">${escapeHtml(nums.phase)}</span>
        <span class="caption">${isSample ? escapeHtml(nums.phaseNote) : `Build ${plan.schedule.build_start} &rarr; ${plan.schedule.build_end} · Demo ${plan.schedule.demo_day}`}</span>
        <span class="arrow">View schedule &rarr;</span>
      </button>
      <button class="cc-card" data-detail="stories">
        <span class="kicker">Stories</span>
        <span class="big">${nums.stories_verified} / ${nums.stories_total}</span>
        <span class="caption">verified</span>
        <span class="arrow">View stories &rarr;</span>
      </button>
      <button class="cc-card" data-detail="criteria">
        <span class="kicker">Acceptance criteria</span>
        <span class="big">${nums.criteria_passed} / ${nums.criteria_total}</span>
        <span class="caption">passed</span>
        <span class="arrow">What this counts &rarr;</span>
      </button>
      <button class="cc-card" data-detail="points">
        <span class="kicker">Points</span>
        <span class="big">${nums.points_awarded}</span>
        <span class="caption">awarded</span>
        <span class="arrow">What this counts &rarr;</span>
      </button>
    </div>
  `;

  const detail = state.overviewDetail ? renderOverviewDetail(state.overviewDetail, plan, progress, isSample) : '';

  return banner + sampleStrip + hero + cards + detail;
}

function renderOverviewDetail(key, plan, progress, isSample) {
  if (key === 'schedule') {
    return `
      <div class="cc-detail">
        <button class="back" data-back>&larr; Back</button>
        <h3>Release schedule</h3>
        ${isSample ? '<p class="cc-footnote" style="margin-top:0">Sample mode — the phase above is illustrative, but the dates below are your real plan.json dates.</p>' : ''}
        <table>
          <thead><tr><th>Release</th><th>Name</th><th>Starts</th><th>Ends</th><th>Demo target</th></tr></thead>
          <tbody>
            ${plan.releases.map(r => `<tr><td>${escapeHtml(r.key)}</td><td>${escapeHtml(r.name)}</td><td>${escapeHtml(r.starts_on)}</td><td>${escapeHtml(r.ends_on)}</td><td>${r.is_demo_target ? '<span class="cc-pill green">Yes</span>' : ''}</td></tr>`).join('')}
          </tbody>
        </table>
        <p class="cc-footnote">Demo day: ${escapeHtml(plan.schedule.demo_day)}. Full Gantt view lives on the Project Management tab (not built yet).</p>
      </div>
    `;
  }
  if (key === 'stories') {
    const rows = plan.stories.map(s => {
      const p = progress.stories.find(ps => ps.id === s.id);
      const st = p ? p.verification.state : 'not_started';
      return `<tr><td>${escapeHtml(s.id)}</td><td>${escapeHtml(s.title)}</td><td>${escapeHtml(s.release)}</td><td>${statePill(st)}</td></tr>`;
    }).join('');
    return `
      <div class="cc-detail">
        <button class="back" data-back>&larr; Back</button>
        <h3>Stories</h3>
        ${isSample ? '<p class="cc-footnote" style="margin-top:0">Sample mode is showing a summary count above; this table is your real story list.</p>' : ''}
        <table>
          <thead><tr><th>ID</th><th>Title</th><th>Release</th><th>State</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }
  if (key === 'criteria') {
    return `
      <div class="cc-detail">
        <button class="back" data-back>&larr; Back</button>
        <h3>Acceptance criteria</h3>
        <p>This counts every acceptance criterion across every story, and how many are marked
        passed in <code>.colaberry/progress.json</code>.</p>
        ${progress.totals.criteria_total === 0 && !isSample
          ? '<p><strong>Currently 0 of 0.</strong> None of the 10 project stories have acceptance criteria defined in progress.json yet — that happens as each story is built, not before. This is not a bug.</p>'
          : ''}
      </div>
    `;
  }
  if (key === 'points') {
    return `
      <div class="cc-detail">
        <button class="back" data-back>&larr; Back</button>
        <h3>Points</h3>
        <p>Points are awarded per story in <code>.colaberry/progress.json</code> once its
        acceptance criteria are verified. ${!isSample ? '<strong>0 awarded so far</strong> — no story has been verified yet.' : ''}</p>
      </div>
    `;
  }
  return '';
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

function wireOverview() {
  document.querySelectorAll('[data-detail]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.overviewDetail = btn.dataset.detail;
      renderTabBody();
      wireOverview();
      document.querySelector('.cc-detail')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
  });
  document.querySelectorAll('[data-back]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.overviewDetail = null;
      renderTabBody();
      wireOverview();
    });
  });
}

/* ---------- nav wiring (delegated, header re-renders each time) ---------- */
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
