'use strict';
// Documents 6-9: model card, control framework, vendor due diligence, monitoring and incidents.
const P = require('../kit/parts');
const { PEOPLE, CP, INCIDENTS } = require('./model');
const { CONTROLS, controlsFor, GATES } = require('./controls');

const reachText = (r) => (r === 4 ? 'All tiers' : r === 1 ? 'Tier 1' : `Tier 1 to ${r}`);

const modelCard = {
  key: 'model-card', title: 'Model Card: ClaimsPilot AI', owner: 'VP Claims Operations', question: 'What does ClaimsPilot do, how well, and where must it not be used?',
  sub: 'Intended use, limits, performance and oversight for the FNOL triage and fast-track system',
  desc: 'Intended and out-of-scope use, data, performance by class, limits and oversight',
  lens: ['Out-of-scope uses are listed as specifically as intended uses.', 'Performance is broken down by class, not just overall.', 'The limits section names conditions where it fails.', 'Oversight says who can override and how fast.'],
  people: { reviewed: PEOPLE.claims, approved: PEOPLE.cro },
  html: `
<h2>1. Model details</h2>
${P.table(['Field', 'Value'], [
    ['System', 'ClaimsPilot AI (TL-AI-01), Tier 1'], ['Version', 'cp-triage 3.4.1 (classifier) + pinned hosted LLM for loss-description parsing'],
    ['Business owner', `${PEOPLE.claims.name}, ${PEOPLE.claims.title}`], ['Technical owner', 'Claims Data Science'],
    ['Approved', 'AI Council, 2026-07-14, with conditions (see Risk Assessment CP-R4)'], ['Next re-assessment', '2027-07-14'],
  ])}
<h2>2. Intended use</h2>
${P.list(['Classify each new first notice of loss (FNOL) into fast-track, standard, complex/injury or SIU review.', `Fast-track pay glass, towing and rental claims up to $${CP.stpCap.toLocaleString('en-US')} where coverage is confirmed and no injury is reported.`, 'Route other claims to the right adjuster queue with the reasons shown.'])}
<h2>3. Out of scope (must not be used for)</h2>
${P.list(['Denying or reducing any claim. ClaimsPilot can only pay or route.', 'Any claim with a reported injury, a fatality, or a commercial policy.', 'Setting reserves or settlement amounts above the fast-track cap.', 'Evaluating adjuster performance.'])}
<h2>4. Data</h2>
<p>Trained on 212,000 closed personal auto and homeowners claims (2021 to 2025) from LedgerOne, with outcomes labeled by final handling path. Claimant names, contact details and free-text identifiers are removed before training. No protected characteristics are inputs.</p>
<h2>5. Performance (holdout of ${CP.holdout.toLocaleString('en-US')} claims, 2026 Q1)</h2>
${P.tiles([{ v: `${CP.accuracy}%`, l: 'Routing accuracy', s: 'all classes' }, { v: `${CP.severeMisroute}%`, l: 'Severe misroutes', s: `limit ${CP.severeMisrouteLimit}%`, tone: 'good' }, { v: `${CP.stpShare}%`, l: 'Claims fast-tracked' }, { v: `${CP.firstContactAfter}h`, l: 'FNOL to first contact', s: `was ${CP.firstContactBefore}h`, tone: 'good' }])}
${P.table(['Class', 'Share of claims', 'Precision'], CP.classes.map((c) => [c[0], `${c[1]}%`, `${c[2]}%`]))}
${P.chartRow(P.barChart({ title: 'Precision by class (%)', data: CP.classes.map((c) => ({ label: c[0], value: c[2], tone: c[2] < 90 ? 'cherry' : 'berry' })), unit: '%', max: 100 }))}
<p class="small">A severe misroute is a complex or injury claim routed to fast-track. It is the error that harms a claimant, so it has its own limit, separate from overall accuracy.</p>
<h2>6. Known limits</h2>
${P.list(['Catastrophe events shift the mix of claims; in August 2026 a hail event raised severe misroutes to 0.9% for 2 days (AI-INC-2026-007).', 'SIU-review precision is lowest (88.2%); every SIU route is checked by an investigator.', 'Loss descriptions in languages other than English and Spanish are routed to standard handling.'])}
<h2>7. Human oversight</h2>
${P.table(['Who', 'Can do', 'Within'], [['Claims adjuster', 'Override any route; reopen any fast-track payment', 'Any time before closure'], ['Claims QA team', 'Daily sample of 50 fast-track claims', '1 business day'], ['System owner or Governance Lead', 'Switch fast-track off (all claims go to people)', 'Immediately; tested quarterly']])}`,
};

const controls = {
  key: 'controls', title: 'Control Framework & Regulatory Crosswalk', owner: 'AI Governance Lead', question: 'Which controls apply, and which obligations do they meet?',
  sub: `${CONTROLS.length} controls by tier and gate, mapped to NIST AI RMF, ISO/IEC 42001 and the NAIC AI bulletin`,
  desc: 'Every control with tier reach, gate, evidence, owner, frequency and framework mapping',
  lens: ['Every control names evidence an auditor can inspect.', 'Each tier\'s control count matches the tiering rule.', 'Every NAIC theme is covered by at least one control.', 'Owners are roles that exist in the charter.'],
  people: { reviewed: PEOPLE.cco, approved: PEOPLE.cro },
  csv: [{ name: 'TrustLine_Control_Framework.csv', label: 'CSV', head: ['Control', 'Domain', 'Control statement', 'Applies to', 'Gate', 'NIST AI RMF', 'ISO/IEC 42001 clause', 'NAIC bulletin theme', 'Evidence', 'Owner', 'Frequency'],
    rows: CONTROLS.map((c) => [c.id, c.domain, c.control, reachText(c.reach), c.gate, c.nist, c.iso, c.naic, c.evidence, c.owner, c.freq]) }],
  html: `
<h2>1. Controls by tier</h2>
${P.chartRow(P.barChart({ title: 'Controls required by tier', data: [1, 2, 3, 4].map((t) => ({ label: `Tier ${t}`, value: controlsFor(t).length, tone: t === 1 ? 'cherry' : 'berry' })), max: 24 }),
    P.barChart({ title: 'Controls by NIST AI RMF function', data: ['GOVERN', 'MAP', 'MEASURE', 'MANAGE'].map((f) => ({ label: f, value: CONTROLS.filter((c) => c.nist === f).length })), max: 10 }))}
<h2>2. Control set</h2>
${P.table(['ID', 'Control', 'Applies to', 'Gate', 'Evidence', 'Owner', 'Frequency'], CONTROLS.map((c) => [`<span class="nw">${c.id}</span>`, `<strong>${c.domain}.</strong> ${c.control}`, `<span class="nw">${reachText(c.reach)}</span>`, c.gate, c.evidence, c.owner, c.freq]))}
<h2>3. Regulatory crosswalk</h2>
${P.table(['ID', 'NIST AI RMF', 'ISO/IEC 42001 clause', 'NAIC bulletin theme'], CONTROLS.map((c) => [`<span class="nw">${c.id}</span>`, c.nist, c.iso, c.naic]), 'matrix')}
<h2>4. Coverage of NAIC bulletin themes</h2>
${P.table(['Theme', 'Controls'], [...new Set(CONTROLS.map((c) => c.naic))].map((t) => [t, CONTROLS.filter((c) => c.naic === t).map((c) => c.id).join(', ')]))}
<h2>5. Gates</h2>
${P.table(['Gate', 'Question', 'Controls checked'], GATES.map((g) => [`${g[0]} ${g[1]}`, g[2], CONTROLS.filter((c) => c.gate === g[0]).map((c) => c.id).join(', ') || 'Decommission record (G5 checklist)']))}
${P.callout('warn', 'Mapping is not compliance', 'A control mapped to a framework is a claim. It becomes evidence when the control has been tested and the result is on file. Compliance confirms current state requirements each year before this crosswalk is re-issued.')}`,
};

const VD = [
  ['Model documentation (purpose, data sources, limits)', 'Met', 'Met', 'Partial'],
  ['Fairness test results shared', 'Met', 'n/a (no consumer decision)', 'Not met'],
  ['Right to run our own tests on a test endpoint', 'Met (clause V-04)', 'Met', 'Not met'],
  ['Notice 60 days before material model change', 'Met', 'Partial (30 days)', 'Not met'],
  ['No training on Meridian data without written consent', 'Met', 'Met', 'Met'],
  ['Data residency in the US; deletion on exit with certificate', 'Met', 'Met', 'Met'],
  ['SOC 2 Type II report, current', 'Met', 'Met', 'Met'],
  ['Incident notice within 72 hours', 'Met', 'Met', 'Partial (5 days)'],
  ['Audit rights', 'Met', 'Met', 'Not met'],
  ['Explanations or reason codes per output', 'Met (top 3 reasons)', 'Met (field confidence)', 'Partial'],
];
const tally = (i, v) => VD.filter((r) => r[i].startsWith(v)).length;
const vendor = {
  key: 'vendor', title: 'Third-Party AI Due Diligence', owner: 'AI Governance Lead', question: 'Can we trust and oversee the AI we buy?',
  sub: 'Assessment of SentinelRisk, Lumina Labs and VoxSight against the TrustLine vendor standard',
  desc: 'Ten-point vendor standard applied to three AI vendors, with findings and required clauses',
  lens: ['Every "Met" points to a clause or document.', 'Vendor marketing is not used as evidence.', 'Gaps become dated findings with owners.', 'Contract renewal dates are known.'],
  people: { reviewed: PEOPLE.ciso, approved: PEOPLE.cro },
  csv: [{ name: 'TrustLine_Vendor_Due_Diligence.csv', label: 'CSV', head: ['Requirement', 'SentinelRisk (TL-AI-02)', 'Lumina Labs (TL-AI-05)', 'VoxSight (TL-AI-06)'], rows: VD }],
  html: `
<h2>1. Scope</h2>
<p>All vendor AI systems in Tier 1 or 2. Evidence reviewed: executed contracts, SOC 2 reports, vendor model documentation, and our own test results.</p>
<h2>2. Results</h2>
${P.table(['Requirement', 'SentinelRisk', 'Lumina Labs', 'VoxSight'], VD.map((r) => [r[0], ...r.slice(1).map((v) => (v.startsWith('Not met') ? `<strong class="pii">${v}</strong>` : v))]))}
${P.chartRow(P.barChart({ title: 'Requirements fully met (of 10)', data: [['SentinelRisk', 1], ['Lumina Labs', 2], ['VoxSight', 3]].map(([l, i]) => ({ label: l, value: tally(i, 'Met'), tone: tally(i, 'Met') < 6 ? 'cherry' : 'leaf' })), max: 10 }))}
<h2>3. Findings</h2>
${P.table(['Finding', 'Vendor', 'Severity', 'Action', 'Owner', 'Due'], [
    ['VD-01', 'VoxSight', 'High', 'Amend contract: audit rights, test access, 60-day change notice, 72-hour incident notice', 'Procurement / Legal', '2026-12-31'],
    ['VD-02', 'VoxSight', 'High', 'Employee notice that calls are scored by AI; scores not sole basis for discipline', 'Contact Center Director', '2026-11-15'],
    ['VD-03', 'Lumina Labs', 'Medium', 'Extend change notice from 30 to 60 days at renewal', 'Procurement', '2027-01-31'],
  ])}
${P.callout('info', 'Standard clauses', 'New AI contracts use the TrustLine clause pack: V-01 data-use limits, V-02 change notice, V-03 incident notice, V-04 test endpoint, V-05 audit rights, V-06 deletion certificate. Procurement will not sign an AI contract that omits V-01 to V-04 without an approved exception.')}`,
};

const MON = [
  ['ClaimsPilot', 'Severe misroutes (daily)', '< 0.3%', '0.3% to 0.5%', '> 0.5%', 'Automatic fallback to human triage for the affected claim type', 'Rafael Ortiz'],
  ['ClaimsPilot', 'Input drift PSI (weekly)', '< 0.10', '0.10 to 0.25', '> 0.25', 'Amber: investigate; red: fallback and retrain review', 'Claims Data Science'],
  ['ClaimsPilot', 'Adjuster override rate (monthly)', '3% to 12%', '1% to 3% or 12% to 18%', '< 1% or > 18%', 'Reviewer-time study (low) or model review (high)', 'Rafael Ortiz'],
  ['SentinelRisk', 'Referral-rate ratio, any group (quarterly)', '< 1.15', '1.15 to 1.25', '> 1.25', 'Red: Council review within 10 days; consider cut-off freeze', 'Regina Asafor'],
  ['SentinelRisk', 'Referral precision (monthly)', '> 27%', '22% to 27%', '< 22%', 'Vendor model review', 'Nadia Sorensen'],
  ['PolicyLens', 'Answers with a valid current-form citation (weekly sample)', '> 98%', '95% to 98%', '< 95%', 'Red: show citations only, no generated answer', 'Rafael Ortiz'],
  ['Lumina', 'Field extraction error rate (weekly sample)', '< 2%', '2% to 4%', '> 4%', 'Red: adjuster confirms every field', 'Rafael Ortiz'],
  ['All Tier 1-2', 'Decision log completeness (daily)', '100%', '99.5% to 100%', '< 99.5%', 'Red: Sev 2 incident; stop if gap persists 24h', 'System owner'],
];
const monitoring = {
  key: 'monitoring', title: 'Monitoring & AI Incident Response Plan', owner: 'AI Governance Lead', question: 'How do we know AI is still safe, and what happens when it is not?',
  sub: 'Thresholds, red-line actions, severity levels, the response runbook and the 2026 incident log',
  desc: 'Green/amber/red thresholds per system, severity matrix, runbook and incident log',
  lens: ['Every red threshold has an automatic or named action.', 'Severity levels have response times.', 'The runbook covers the fallback, not just the investigation.', 'Past incidents list what changed afterward.'],
  people: { reviewed: PEOPLE.eng, approved: PEOPLE.cro },
  csv: [{ name: 'TrustLine_Monitoring_Thresholds.csv', label: 'Thresholds CSV', head: ['System', 'Metric', 'Green', 'Amber', 'Red', 'Red-line action', 'Owner'], rows: MON },
    { name: 'TrustLine_AI_Incident_Log.csv', label: 'Incidents CSV', head: ['Incident', 'Date', 'System', 'Severity', 'What happened', 'Response', 'Impact'], rows: INCIDENTS }],
  html: `
<h2>1. Thresholds</h2>
${P.table(['System', 'Metric', 'Green', 'Amber', 'Red', 'Red-line action', 'Owner'], MON)}
${P.chartRow(P.lineChart({ title: 'ClaimsPilot input drift (PSI), 2026', labels: CP.months, values: CP.psi, target: CP.psiAmber, min: 0, max: 0.14 }), P.lineChart({ title: 'ClaimsPilot override rate (%), 2026', labels: CP.months, values: CP.override, min: 0, max: 14 }))}
<h2>2. Severity</h2>
${P.table(['Severity', 'Examples', 'Contain within', 'Notify', 'Root cause due'], [
    ['Sev 1', 'Consumer harm at scale; legal breach; regulator inquiry; prohibited use with restricted data', '1 hour (kill switch)', 'Council chair, CCO, Privacy Counsel, CISO', '3 business days'],
    ['Sev 2', 'Red threshold; harm to identifiable people; shadow AI with PII', '4 hours (fallback)', 'Governance Lead, system owner, Compliance', '5 business days'],
    ['Sev 3', 'Amber threshold held 2 weeks; caught error, no harm', 'Next sprint', 'Governance Lead', '15 business days'],
  ])}
<h2>3. Response runbook</h2>
${P.list(['<strong>Detect</strong>: alert, complaint, employee report or audit. Open an AI incident ticket and assign a severity.', '<strong>Contain</strong>: fallback or kill switch per the threshold table. Containment comes before diagnosis.', '<strong>Assess harm</strong>: query the decision log for every affected decision; list affected people.', '<strong>Remediate</strong>: correct affected decisions (re-review, supplemental payment, apology letter).', '<strong>Notify</strong>: Compliance decides regulator and consumer notice; Privacy Counsel decides breach notice.', '<strong>Learn</strong>: root cause, control change, regression test, and a Council note within the due date.'], true)}
<h2>4. 2026 incident log</h2>
${P.table(['Incident', 'Date', 'System', 'Severity', 'What happened', 'Response', 'Impact'], INCIDENTS)}
${P.callout('tip', 'Tabletop exercises', 'Each Tier 1 system runs one tabletop a year against a scenario from this log. The 2026-11 exercise: SentinelRisk vendor ships an unannounced model change that doubles referrals in one state.')}`,
};

module.exports = { docsB: [modelCard, controls, vendor, monitoring] };
