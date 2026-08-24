/* ============================================================
   Command Center — tab content
   Every render()/detail() function below reads only from the
   `ctx` object passed in (plan.json + progress.json content,
   fetched at runtime in app.js) — nothing here is hard-coded
   project data. Delete a story from plan.json and reload: it
   disappears everywhere it's listed, because these functions
   re-derive from ctx on every call.
   ============================================================ */

const TAB_RENDERERS = {};

/* ============================================================
   1. Overview
   ============================================================ */

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

TAB_RENDERERS.overview = {
  render(ctx) {
    const { plan, progress, isSample } = ctx;
    const nums = isSample ? {
      phase: 'Building', phaseNote: 'Sample: shown as if the build were mid-way through r1.',
      stories_verified: 6, stories_total: 10, criteria_passed: 22, criteria_total: 30, points_awarded: 340,
    } : {
      phase: schedulePhase(plan.schedule), phaseNote: null,
      stories_verified: progress.totals.stories_verified, stories_total: progress.totals.stories_total,
      criteria_passed: progress.totals.criteria_passed, criteria_total: progress.totals.criteria_total,
      points_awarded: progress.totals.points_awarded,
    };
    return `
      ${sampleStrip(isSample, 'This tab is showing made-up totals so you can see the shape of it. Switch to Real above to see what your project has actually produced.')}
      <div class="cc-section-title"><h1>${escapeHtml(plan.project.name)}</h1></div>
      <p class="cc-section-sub">${escapeHtml(plan.project.descriptor)}</p>
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
  },
  detail(key, ctx) {
    const { plan, progress, isSample } = ctx;
    if (key === 'schedule') {
      return `
        <div class="cc-detail">
          <button class="back" data-back>&larr; Back</button>
          <h3>Release schedule</h3>
          ${isSample ? '<p class="cc-footnote" style="margin-top:0">Sample mode — the phase above is illustrative, but the dates below are your real plan.json dates.</p>' : ''}
          <table>
            <thead><tr><th>Release</th><th>Name</th><th>Starts</th><th>Ends</th><th>Demo target</th></tr></thead>
            <tbody>${plan.releases.map(r => `<tr><td>${escapeHtml(r.key)}</td><td>${escapeHtml(r.name)}</td><td>${escapeHtml(r.starts_on)}</td><td>${escapeHtml(r.ends_on)}</td><td>${r.is_demo_target ? '<span class="cc-pill green">Yes</span>' : ''}</td></tr>`).join('')}</tbody>
          </table>
          <p class="cc-footnote">Demo day: ${escapeHtml(plan.schedule.demo_day)}. Full Gantt view lives on the Project Management tab.</p>
        </div>`;
    }
    if (key === 'stories') {
      const rows = plan.stories.map(s => `<tr><td>${escapeHtml(s.id)}</td><td>${escapeHtml(s.title)}</td><td>${escapeHtml(s.release)}</td><td>${statePill(effectiveStoryState(s.id, ctx))}</td></tr>`).join('');
      return `
        <div class="cc-detail">
          <button class="back" data-back>&larr; Back</button>
          <h3>Stories</h3>
          <table><thead><tr><th>ID</th><th>Title</th><th>Release</th><th>State</th></tr></thead><tbody>${rows}</tbody></table>
        </div>`;
    }
    if (key === 'criteria') {
      return `
        <div class="cc-detail">
          <button class="back" data-back>&larr; Back</button>
          <h3>Acceptance criteria</h3>
          <p>This counts every acceptance criterion across every story, and how many are marked passed in <code>.colaberry/progress.json</code>.</p>
          ${progress.totals.criteria_total === 0 && !isSample
            ? '<p><strong>Currently 0 of 0.</strong> None of the 10 project stories have acceptance criteria defined in progress.json yet — that happens as each story is built, not before. This is not a bug.</p>'
            : ''}
        </div>`;
    }
    if (key === 'points') {
      return `
        <div class="cc-detail">
          <button class="back" data-back>&larr; Back</button>
          <h3>Points</h3>
          <p>Points are awarded per story in <code>.colaberry/progress.json</code> once its acceptance criteria are verified.
          ${!isSample ? '<strong>0 awarded so far</strong> — no story has been verified yet.' : ''}</p>
        </div>`;
    }
    return '';
  },
};

/* ============================================================
   2. Outcomes
   ============================================================ */

function sparklineSvg(points, target) {
  const w = 320, h = 70, pad = 6;
  const max = Math.max(...points, target) * 1.05;
  const min = 0;
  const step = (w - pad * 2) / (points.length - 1);
  const y = v => h - pad - ((v - min) / (max - min)) * (h - pad * 2);
  const path = points.map((v, i) => `${i === 0 ? 'M' : 'L'} ${pad + i * step} ${y(v).toFixed(1)}`).join(' ');
  const targetY = y(target).toFixed(1);
  return `<svg class="cc-sparkline" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="Trend toward target">
    <line x1="${pad}" y1="${targetY}" x2="${w - pad}" y2="${targetY}" stroke="var(--border)" stroke-width="1" stroke-dasharray="3,3" />
    <path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2" />
  </svg>`;
}

TAB_RENDERERS.outcomes = {
  render(ctx) {
    const { plan, isSample } = ctx;
    const measures = plan.derived.measures || [];
    return `
      ${sampleStrip(isSample, 'Shown as a believable trend toward the target. Switch to Real to see the actual figure — currently none, because nothing has run yet.')}
      <div class="cc-section-title"><h1>Outcomes</h1></div>
      <p class="cc-section-sub">The numbers this project committed to move.</p>
      <div class="cc-grid">
        ${measures.map(m => `
          <button class="cc-card" data-detail="${escapeHtml(m.id)}">
            <span class="kicker">${escapeHtml(m.id)}</span>
            <span class="big">${isSample ? '2.6h avg' : 'Not measured yet'}</span>
            <span class="caption">${escapeHtml(m.statement)}</span>
            <span class="arrow">How this is calculated &rarr;</span>
          </button>
        `).join('') || '<p class="cc-section-sub">No measures defined in plan.json yet.</p>'}
      </div>
    `;
  },
  detail(key, ctx) {
    const { plan, isSample } = ctx;
    const m = (plan.derived.measures || []).find(x => x.id === key);
    if (!m) return '';
    return `
      <div class="cc-detail">
        <button class="back" data-back>&larr; Back</button>
        <h3>${escapeHtml(m.id)} — ${escapeHtml(m.statement)}</h3>
        <p>Calculated as wall-clock time from investigation start to a recommendation being delivered,
        averaged per week, measured against a 4-hour baseline and a 1-hour target.</p>
        ${isSample ? `
          ${sparklineSvg([4.0, 3.8, 3.3, 3.0, 2.9, 2.7, 2.6, 2.6], 1.0)}
          <p class="cc-footnote">Sample trend, 8 illustrative weeks. Dashed line is the 1-hour target.</p>
        ` : `
          <p><strong>Not measured yet.</strong> No investigation has run, so there is no timing data to
          average. This becomes real once the analysis stories (STORY-001, STORY-003, STORY-004, STORY-010)
          and the pilot (STORY-009) are built and producing timed runs.</p>
        `}
      </div>`;
  },
};

/* ============================================================
   3. Users & Use Case
   ============================================================ */

TAB_RENDERERS.users = {
  render(ctx) {
    const { plan, isSample } = ctx;
    const roles = plan.derived.roles || [];
    return `
      ${sampleStrip(isSample, 'Role list and story counts are your real plan — nothing here is fabricated even in Sample mode.')}
      <div class="cc-section-title"><h1>Users &amp; Use Case</h1></div>
      <p class="cc-section-sub">Who this is for, taken from the "As a &lt;role&gt;" line in each story.</p>
      <div class="cc-grid">
        ${roles.map(r => `
          <button class="cc-card" data-detail="${escapeHtml(r.role)}">
            <span class="kicker">Role</span>
            <span class="big">${escapeHtml(r.role)}</span>
            <span class="caption">${r.story_ids.length} stor${r.story_ids.length === 1 ? 'y' : 'ies'}</span>
            <span class="arrow">View narrative &rarr;</span>
          </button>
        `).join('')}
      </div>
    `;
  },
  detail(key, ctx) {
    const { plan } = ctx;
    const r = (plan.derived.roles || []).find(x => x.role === key);
    if (!r) return '';
    const stories = r.story_ids.map(id => plan.stories.find(s => s.id === id)).filter(Boolean);
    return `
      <div class="cc-detail">
        <button class="back" data-back>&larr; Back</button>
        <h3>${escapeHtml(key)}</h3>
        ${stories.length ? stories.map(s => `<p><strong>${escapeHtml(s.id)}</strong> — ${escapeHtml(s.narrative)}</p>`).join('')
          : '<p><strong>No story currently gives this role a voice.</strong> That lines up with REQ-018 (role-based access control) having no fulfilling story yet — see the Guardrails and Knowledge Base tabs.</p>'}
      </div>`;
  },
};

/* ============================================================
   4. Guardrails
   ============================================================ */

TAB_RENDERERS.guardrails = {
  render(ctx) {
    const { plan, isSample } = ctx;
    const guardrails = plan.derived.guardrails || [];
    return `
      ${sampleStrip(isSample, 'A real gap (no fulfilling story) is shown the same in Sample and Real — that is a plan fact, not a runtime result, so it is never faked away.')}
      <div class="cc-section-title"><h1>Guardrails</h1></div>
      <p class="cc-section-sub">Promises this system makes, and whether anything in the build currently enforces each one.</p>
      <div class="cc-grid">
        ${guardrails.map(g => {
          const req = plan.requirements.find(r => r.id === g.id);
          const fulfilledBy = req ? req.fulfilled_by : [];
          let pill;
          if (fulfilledBy.length === 0) {
            pill = '<span class="cc-pill red">No story assigned</span>';
          } else {
            const states = fulfilledBy.map(id => effectiveStoryState(id, ctx));
            pill = states.every(s => s === 'verified')
              ? '<span class="cc-pill green">Enforced</span>'
              : '<span class="cc-pill amber">Not yet enforced</span>';
          }
          return `
            <button class="cc-card" data-detail="${escapeHtml(g.id)}">
              <span class="kicker">${escapeHtml(g.id)}</span>
              <span class="caption">${escapeHtml(g.statement)}</span>
              <span class="big" style="font-size:1.1rem">${pill}</span>
              <span class="arrow">View detail &rarr;</span>
            </button>`;
        }).join('') || '<p class="cc-section-sub">No SAFE requirements in this plan — worth fixing before the build finishes.</p>'}
      </div>
    `;
  },
  detail(key, ctx) {
    const { plan } = ctx;
    const g = (plan.derived.guardrails || []).find(x => x.id === key);
    const req = plan.requirements.find(r => r.id === key);
    if (!g) return '';
    const fulfilledBy = req ? req.fulfilled_by : [];
    return `
      <div class="cc-detail">
        <button class="back" data-back>&larr; Back</button>
        <h3>${escapeHtml(g.id)} — ${escapeHtml(g.statement)}</h3>
        ${fulfilledBy.length === 0
          ? '<p><strong>Real gap.</strong> No story in the current plan fulfills this requirement.</p>'
          : `<table><thead><tr><th>Story</th><th>Title</th><th>State</th></tr></thead><tbody>
              ${fulfilledBy.map(id => {
                const s = plan.stories.find(x => x.id === id);
                return `<tr><td>${escapeHtml(id)}</td><td>${escapeHtml(s ? s.title : '')}</td><td>${statePill(effectiveStoryState(id, ctx))}</td></tr>`;
              }).join('')}
            </tbody></table>`}
      </div>`;
  },
};

/* ============================================================
   5. Systems
   ============================================================ */

TAB_RENDERERS.systems = {
  render(ctx) {
    const { plan, isSample } = ctx;
    const systems = plan.derived.systems || [];
    return `
      ${sampleStrip(isSample, 'Connected/green here is illustrative only. In Real mode every system shows grey until this Command Center is wired to an actual connectivity check.')}
      <div class="cc-section-title"><h1>Systems</h1></div>
      <p class="cc-section-sub">What this project connects to.</p>
      <div class="cc-grid">
        ${systems.map(name => `
          <button class="cc-card" data-detail="${escapeHtml(name)}">
            <span class="kicker">System</span>
            <span class="big"><span class="cc-dot ${isSample ? 'green' : 'grey'}"></span>${escapeHtml(name)}</span>
            <span class="caption">${isSample ? 'Connected (sample) · checked 3 minutes ago' : 'Not checked from here · last checked: never'}</span>
            <span class="arrow">View detail &rarr;</span>
          </button>
        `).join('') || '<p class="cc-section-sub">No systems listed in plan.json yet.</p>'}
      </div>
    `;
  },
  detail(name, ctx) {
    const { isSample } = ctx;
    return `
      <div class="cc-detail">
        <button class="back" data-back>&larr; Back</button>
        <h3>${escapeHtml(name)}</h3>
        <p>plan.json only records that this project needs to connect to ${escapeHtml(name)} — it has no way of knowing
        whether that connection actually exists right now. That fact can only come from the running system.</p>
        <p>${isSample
          ? 'This card is showing a green "connected" indicator because Sample mode is on — treat it as illustrative, not a real status.'
          : '<strong>Not checked from here.</strong> This will turn into a real indicator once a connectivity check is built and reports its result into this Command Center.'}</p>
      </div>`;
  },
};

/* ============================================================
   6. Project Management
   ============================================================ */

TAB_RENDERERS.pm = {
  render(ctx) {
    const { plan, isSample } = ctx;
    const rangeStart = plan.schedule.build_start;
    const rangeEnd = plan.schedule.demo_day;
    const totalDays = daysBetween(rangeStart, rangeEnd) || 1;
    const todayPct = Math.min(100, Math.max(0, (daysBetween(rangeStart, new Date().toISOString().slice(0, 10)) / totalDays) * 100));

    const ganttRows = plan.releases.map(r => {
      const leftPct = (daysBetween(rangeStart, r.starts_on) / totalDays) * 100;
      const widthPct = Math.max(2, (daysBetween(r.starts_on, r.ends_on) + 1) / totalDays * 100);
      return `
        <div class="cc-gantt-row">
          <div class="cc-gantt-label">${escapeHtml(r.key)} · ${escapeHtml(r.name)}</div>
          <div class="cc-gantt-track">
            <button class="cc-gantt-bar ${r.is_demo_target ? 'demo' : ''}" style="left:${leftPct}%;width:${widthPct}%"
              data-detail="rel:${escapeHtml(r.key)}">${escapeHtml(r.starts_on)} &rarr; ${escapeHtml(r.ends_on)}</button>
          </div>
        </div>`;
    }).join('');

    const storyRows = plan.stories.map(s => {
      const slip = s.due_on !== s.due_baseline_on;
      return `<tr>
        <td>${escapeHtml(s.id)}</td><td>${escapeHtml(s.title)}</td><td>${escapeHtml(s.release)}</td>
        <td>${escapeHtml(s.due_baseline_on)}</td>
        <td>${escapeHtml(s.due_on)}${slip ? ' <span class="cc-pill amber">slipped</span>' : ''}</td>
        <td>${statePill(effectiveStoryState(s.id, ctx))}</td>
        <td><button class="cc-card" style="padding:.25rem .6rem;box-shadow:none" data-detail="story:${escapeHtml(s.id)}">Open &rarr;</button></td>
      </tr>`;
    }).join('');

    return `
      ${sampleStrip(isSample, 'Release dates and due dates are your real plan.json data. Only the story STATE column is illustrative in Sample mode.')}
      <div class="cc-section-title"><h1>Project Management</h1></div>
      <p class="cc-section-sub">Build ${plan.schedule.build_start} &rarr; ${plan.schedule.build_end} · Demo day ${plan.schedule.demo_day}</p>
      <div class="cc-gantt">
        ${ganttRows}
        <div class="cc-footnote">Click a bar for the stories in that release. Red marker (if visible) is today.</div>
      </div>
      <table>
        <thead><tr><th>ID</th><th>Title</th><th>Release</th><th>Due (baseline)</th><th>Due (current)</th><th>State</th><th></th></tr></thead>
        <tbody>${storyRows}</tbody>
      </table>
    `;
  },
  detail(key, ctx) {
    const { plan } = ctx;
    if (key.startsWith('rel:')) {
      const relKey = key.slice(4);
      const r = plan.releases.find(x => x.key === relKey);
      if (!r) return '';
      const stories = r.story_ids.map(id => plan.stories.find(s => s.id === id)).filter(Boolean);
      return `
        <div class="cc-detail">
          <button class="back" data-back>&larr; Back</button>
          <h3>${escapeHtml(r.key)} — ${escapeHtml(r.name)}</h3>
          <p>${escapeHtml(r.starts_on)} &rarr; ${escapeHtml(r.ends_on)}${r.is_demo_target ? ' · <strong>demo target release</strong>' : ''}</p>
          <table><thead><tr><th>ID</th><th>Title</th><th>Due</th><th>State</th></tr></thead><tbody>
            ${stories.map(s => `<tr><td>${escapeHtml(s.id)}</td><td>${escapeHtml(s.title)}</td><td>${escapeHtml(s.due_on)}</td><td>${statePill(effectiveStoryState(s.id, ctx))}</td></tr>`).join('')}
          </tbody></table>
        </div>`;
    }
    if (key.startsWith('story:')) {
      const id = key.slice(6);
      const s = plan.stories.find(x => x.id === id);
      if (!s) return '';
      return `
        <div class="cc-detail">
          <button class="back" data-back>&larr; Back</button>
          <h3>${escapeHtml(s.id)} — ${escapeHtml(s.title)}</h3>
          <p>${escapeHtml(s.narrative)}</p>
          <p>Release ${escapeHtml(s.release)} · Owner: ${escapeHtml(s.owner)} · Due ${escapeHtml(s.due_on)}
          (baseline ${escapeHtml(s.due_baseline_on)}) · ${statePill(effectiveStoryState(s.id, ctx))}</p>
        </div>`;
    }
    return '';
  },
};

/* ============================================================
   7. AI Agents (owners, not scoped agents yet)
   ============================================================ */

TAB_RENDERERS.agents = {
  render(ctx) {
    const { plan, isSample } = ctx;
    const owners = plan.derived.owners || [];
    return `
      ${sampleStrip(isSample, 'Story states below follow the Sample toggle like elsewhere, but skills and run history stay honest either way — these are story owners, not scoped agents, so there is nothing to fabricate a run history for.')}
      <div class="cc-section-title"><h1>AI Agents</h1></div>
      <p class="cc-section-sub">Your plan does not carry a scoped AI-agent roster yet. These cards show who owns each
      story today — job titles, not autonomous agents.</p>
      <div class="cc-grid">
        ${owners.map(o => `
          <button class="cc-card" data-detail="${escapeHtml(o.owner)}">
            <span class="kicker">Story owner</span>
            <span class="big">${escapeHtml(o.owner)}</span>
            <span class="caption">${o.story_ids.length} stor${o.story_ids.length === 1 ? 'y' : 'ies'} owned</span>
            <span class="arrow">View detail &rarr;</span>
          </button>
        `).join('')}
      </div>
    `;
  },
  detail(owner, ctx) {
    const { plan } = ctx;
    const o = (plan.derived.owners || []).find(x => x.owner === owner);
    if (!o) return '';
    const stories = o.story_ids.map(id => plan.stories.find(s => s.id === id)).filter(Boolean);
    return `
      <div class="cc-detail">
        <button class="back" data-back>&larr; Back</button>
        <h3>${escapeHtml(owner)}</h3>
        <p><strong>Skills:</strong> no skills registered yet. <strong>Runs:</strong> no runs recorded.</p>
        <table><thead><tr><th>Story</th><th>Title</th><th>State</th></tr></thead><tbody>
          ${stories.map(s => `<tr><td>${escapeHtml(s.id)}</td><td>${escapeHtml(s.title)}</td><td>${statePill(effectiveStoryState(s.id, ctx))}</td></tr>`).join('')}
        </tbody></table>
      </div>`;
  },
};

/* ============================================================
   8. Knowledge Base
   ============================================================ */

function kbSearchIndex(plan) {
  const items = [];
  plan.requirements.forEach(r => items.push({ tab: 'Knowledge Base', text: `${r.id} ${r.statement} ${r.kind} ${r.priority}`, answer: `${r.id} (${r.kind}, ${r.priority}): ${r.statement}` }));
  plan.stories.forEach(s => items.push({ tab: 'Project Management', text: `${s.id} ${s.title} ${s.narrative} ${s.owner}`, answer: `${s.id} — ${s.title}. ${s.narrative} Owned by ${s.owner}, due ${s.due_on}.` }));
  (plan.derived.guardrails || []).forEach(g => items.push({ tab: 'Guardrails', text: `${g.id} ${g.statement} guardrail`, answer: `Guardrail ${g.id}: ${g.statement}` }));
  (plan.derived.measures || []).forEach(m => items.push({ tab: 'Outcomes', text: `${m.id} ${m.statement} measure outcome`, answer: `Outcome ${m.id}: ${m.statement}` }));
  (plan.derived.systems || []).forEach(sys => items.push({ tab: 'Systems', text: `${sys} system connection`, answer: `${sys} is a listed system dependency. No connection status is known from this repo.` }));
  (plan.derived.owners || []).forEach(o => items.push({ tab: 'AI Agents', text: `${o.owner} owner stories`, answer: `${o.owner} owns ${o.story_ids.join(', ')}.` }));
  return items;
}

function kbAnswer(query, plan) {
  const q = query.toLowerCase().trim();
  if (!q) return null;
  const tokens = q.split(/\s+/).filter(t => t.length > 2);
  const index = kbSearchIndex(plan);
  let best = null, bestScore = 0;
  for (const item of index) {
    const hay = item.text.toLowerCase();
    let score = 0;
    if (hay.includes(q)) score += 10;
    tokens.forEach(t => { if (hay.includes(t)) score += 1; });
    if (score > bestScore) { bestScore = score; best = item; }
  }
  return bestScore > 0 ? best : null;
}

TAB_RENDERERS.kb = {
  render(ctx) {
    const { plan, isSample } = ctx;
    const rows = plan.requirements.map(r => {
      const stories = r.fulfilled_by.map(id => {
        const s = plan.stories.find(x => x.id === id);
        return s ? `${s.id} ${statePill(effectiveStoryState(id, ctx))}` : id;
      }).join('<br>');
      const gap = r.fulfilled_by.length === 0;
      return `<tr class="${gap && r.priority === 'must' ? 'cc-req-gap' : ''}">
        <td>${escapeHtml(r.id)}</td><td>${escapeHtml(r.statement)}</td>
        <td>${escapeHtml(r.kind)}</td><td>${escapeHtml(r.priority)}</td>
        <td>${stories || '<span class="cc-pill red">none</span>'}</td>
      </tr>`;
    }).join('');
    return `
      ${sampleStrip(isSample, 'The "Fulfilled by" state pills below follow the Sample toggle like elsewhere on this page. The requirements, stories, and gaps themselves are your real plan either way.')}
      <div class="cc-section-title"><h1>Knowledge Base</h1></div>
      <p class="cc-section-sub">Everything the project knows about itself — requirements, stories, and a traceability
      view. Rows highlighted red are a <code>must</code> requirement with no story covering it yet.</p>
      <table>
        <thead><tr><th>Req</th><th>Statement</th><th>Kind</th><th>Priority</th><th>Fulfilled by</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="cc-kb-ask">
        <h3>Ask the Knowledge Base</h3>
        <p class="cc-footnote" style="margin-top:0">Answers only from the data on this page — searches requirements, stories, guardrails, outcomes, systems, and owners, and cites which tab the answer came from. No external API.</p>
        <form id="kb-form"><input type="text" id="kb-input" placeholder="e.g. Who owns STORY-005? What does REQ-018 require?" autocomplete="off"><button type="submit">Ask</button></form>
        <div id="kb-answer"></div>
      </div>
    `;
  },
  detail() { return ''; },
  wire(ctx) {
    const form = document.getElementById('kb-form');
    if (!form) return;
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const input = document.getElementById('kb-input');
      const out = document.getElementById('kb-answer');
      const hit = kbAnswer(input.value, ctx.plan);
      out.innerHTML = hit
        ? `<div class="cc-kb-answer">${escapeHtml(hit.answer)}<div class="src">Source: ${escapeHtml(hit.tab)} tab</div></div>`
        : `<div class="cc-kb-answer">I can't answer that from the data on this page. Try a requirement ID, story ID, or a word from a requirement statement.</div>`;
    });
  },
};

/* ============================================================
   9. Data Model
   ============================================================ */

const DATA_MODEL_ENTITIES = [
  { name: 'Incident', motivatedBy: 'REQ-001–REQ-008', fields: ['id', 'pipeline_name', 'detected_at', 'status', 'current_owner_id'], note: 'The root aggregate — one row per pipeline incident under investigation.' },
  { name: 'LogFinding', motivatedBy: 'REQ-001', fields: ['id', 'incident_id', 'pattern_matched', 'log_excerpt', 'confidence'], note: 'One row per log pattern the analysis agent flags for an incident.' },
  { name: 'SqlFinding', motivatedBy: 'REQ-003', fields: ['id', 'incident_id', 'query_text', 'issue_type', 'confidence'], note: 'SQL-level issues found while analyzing queries involved in the pipeline.' },
  { name: 'DataQualityFinding', motivatedBy: 'REQ-004', fields: ['id', 'incident_id', 'check_name', 'result', 'confidence'], note: 'Data-quality check results considered as a possible root cause.' },
  { name: 'DependencyFinding', motivatedBy: 'REQ-002', fields: ['id', 'incident_id', 'upstream_pipeline', 'downstream_pipeline', 'issue_type'], note: 'Output of the dependency-analysis agent coordination.' },
  { name: 'RootCauseAssessment', motivatedBy: 'REQ-001–REQ-006', fields: ['id', 'incident_id', 'summary', 'confidence_level', 'contributing_finding_ids'], note: 'The synthesized root cause for an incident, with a confidence level so REQ-006 can flag uncertainty.' },
  { name: 'Recommendation', motivatedBy: 'REQ-005, REQ-010', fields: ['id', 'incident_id', 'action_description', 'requires_approval', 'approval_status', 'approved_by', 'approved_at'], note: 'A corrective action awaiting or having received human approval.' },
  { name: 'Notification', motivatedBy: 'REQ-006, REQ-014', fields: ['id', 'incident_id', 'reason', 'sent_to', 'sent_at', 'acknowledged_at'], note: 'Sent when a root cause is uncertain or an ops tool needs to be told.' },
  { name: 'AuditLogEntry', motivatedBy: 'REQ-011', fields: ['id', 'incident_id', 'actor', 'action', 'occurred_at', 'details'], note: 'Every investigation activity, for audit purposes.' },
  { name: 'InvestigationReport', motivatedBy: 'REQ-007, REQ-017', fields: ['id', 'incident_id', 'summary_for_ops', 'detailed_report_url', 'generated_at'], note: 'Simplified ops summary plus the detailed report.' },
  { name: 'UserRole', motivatedBy: 'REQ-018 (currently unfulfilled)', fields: ['id', 'name', 'permissions'], note: 'Proposed to close the REQ-018 gap flagged on the Guardrails tab — not yet built.' },
  { name: 'PilotMetric', motivatedBy: 'REQ-009, REQ-012, REQ-016', fields: ['id', 'week_of', 'avg_investigation_time_minutes', 'error_rate'], note: 'Weekly rollup feeding the Outcomes tab once the pilot runs.' },
];

TAB_RENDERERS.datamodel = {
  render() {
    return `
      <div class="cc-section-title"><h1>Data Model</h1></div>
      <p class="cc-section-sub">A starting point, not the answer — proposed by working through each requirement and
      asking what it needs to store. Nothing here is built yet; no tables exist. Review before anything is created.</p>
      <div class="cc-grid">
        ${DATA_MODEL_ENTITIES.map(e => `
          <button class="cc-card" data-detail="${escapeHtml(e.name)}">
            <span class="kicker">Proposed entity</span>
            <span class="big" style="font-size:1.3rem">${escapeHtml(e.name)}</span>
            <span class="caption">${e.fields.length} fields · motivated by ${escapeHtml(e.motivatedBy)}</span>
            <span class="arrow">View fields &rarr;</span>
          </button>
        `).join('')}
      </div>
    `;
  },
  detail(key) {
    const e = DATA_MODEL_ENTITIES.find(x => x.name === key);
    if (!e) return '';
    return `
      <div class="cc-detail">
        <button class="back" data-back>&larr; Back</button>
        <h3>${escapeHtml(e.name)} <span class="cc-pill grey">Proposed — not yet built</span></h3>
        <p>${escapeHtml(e.note)}</p>
        <p><strong>Motivated by:</strong> ${escapeHtml(e.motivatedBy)}</p>
        <table><thead><tr><th>Field</th></tr></thead><tbody>${e.fields.map(f => `<tr><td><code>${escapeHtml(f)}</code></td></tr>`).join('')}</tbody></table>
      </div>`;
  },
};
