'use strict';
// Documents 1-5: charter, policy, inventory, risk assessment, impact assessment.
const P = require('../kit/parts');
const { ORG, PEOPLE, TIER_RULES, SYSTEMS, tierName, tierCount, scoreOf, FAIR } = require('./model');
const { controlsFor } = require('./controls');

const pct = (v) => `${v.toFixed(1)}%`;
const addYears = (d, n) => `${+d.slice(0, 4) + n}${d.slice(4)}`;
const nextReview = (s) => (s.tier === 0 ? 'n/a (blocked)' : addYears(s.reviewed, s.tier <= 2 ? 1 : 2));
const registered = SYSTEMS.filter((s) => s.tier > 0);

const charter = {
  key: 'charter', title: 'AI Governance Charter & Operating Model', owner: 'AI Governance Lead', question: 'Who decides what about AI, and how?',
  sub: 'Authority, membership, decision rights and cadence for the TrustLine program',
  desc: 'The council, its decision rights, the three lines of defense and how escalation works',
  lens: ['Every decision type has exactly one Accountable role.', 'The council can say no, and the charter says how.', 'Escalation has time limits, not just a path.', 'The charter names how its own effectiveness is reviewed.'],
  html: `
<h2>1. Purpose and authority</h2>
<p>This charter establishes the ${ORG.name} AI Council and the TrustLine AI governance program. The Board Risk Committee delegates to the Council the authority to approve, condition, pause or prohibit any AI system used by the company or by vendors on its behalf. No Tier 1 system may enter production without a Council decision.</p>
<h2>2. Scope</h2>
<p>All AI systems as defined in the Responsible AI Policy (TL-AG-02): built, bought, or enabled as a feature of a vendor product, used by any employee, contractor or vendor acting for ${ORG.name}.</p>
<h2>3. AI Council membership</h2>
${P.table(['Member', 'Role on the Council', 'Vote'], [
    [`${PEOPLE.cro.name}, Chief Risk Officer`, 'Chair; casts the deciding vote on ties', 'Yes'],
    [`${PEOPLE.cco.name}, Chief Compliance Officer`, 'Regulatory obligations; may block on legal grounds', 'Yes (block)'],
    [`${PEOPLE.cdo.name}, Chief Data Officer`, 'Data use and quality', 'Yes'],
    [`${PEOPLE.ciso.name}, CISO`, 'Security and vendor access', 'Yes'],
    [`${PEOPLE.claims.name}, VP Claims Operations`, 'Business owner voice (rotates by agenda)', 'Yes'],
    [`${PEOPLE.privacy.name}, Privacy Counsel`, 'Privacy and consumer notice', 'Advisory'],
    [`${PEOPLE.lead.name}, AI Governance Lead`, 'Secretary; presents assessments and recommendations', 'No'],
    [`${PEOPLE.audit.name}, Director Internal Audit`, 'Observer (third line independence)', 'No'],
  ])}
<h2>4. Decision rights (RACI)</h2>
${P.table(['Decision', 'System owner', 'Governance Lead', 'Compliance', 'AI Council', 'Internal Audit'], [
    ['Register a system and assign a tier', 'R', 'A', 'C', 'I', 'I'],
    ['Approve Tier 3 and 4 systems', 'R', 'A', 'I', 'I', '-'],
    ['Approve Tier 2 systems', 'R', 'A', 'C', 'I', '-'],
    ['Approve Tier 1 systems and material changes', 'R', 'R', 'C', 'A', 'I'],
    ['Grant a policy exception (max 12 months)', 'R', 'C', 'C', 'A', 'I'],
    ['Pause a system (kill switch)', 'R', 'A', 'I', 'I', 'I'],
    ['Prohibit a use', 'C', 'R', 'C', 'A', 'I'],
    ['Assess control effectiveness', 'C', 'C', 'C', 'I', 'A'],
  ], 'matrix')}
<p class="small">R = responsible, A = accountable (exactly one), C = consulted, I = informed. Any system owner, the Governance Lead or the CISO may pause a system immediately; the Council reviews every pause within 5 business days.</p>
<h2>5. Operating cadence</h2>
${P.table(['Forum', 'Frequency', 'Inputs', 'Outputs'], [
    ['Intake triage', 'Weekly (30 min)', 'New intake forms, change tickets', 'Tier assignments; Tier 3-4 decisions'],
    ['AI Council', 'Monthly, plus ad hoc for Sev 1', 'Tier 1 assessments, exceptions, KPI pack, incidents', 'Decision records with conditions and dissent'],
    ['Board Risk Committee report', 'Quarterly', 'Program KPIs, top risks, findings', 'Direction on risk appetite'],
  ])}
<h2>6. Escalation</h2>
${P.list(['A Sev 1 AI incident goes to the Council chair and Compliance within 1 hour.', 'A finding not closed by its due date escalates to the owner\'s executive at +15 days and the Council at +30 days.', 'A disagreement between the Governance Lead and a system owner on tier goes to the next weekly triage, then the Council.'])}
${P.callout('info', 'Quorum and records', 'Quorum is the chair plus three voting members, including Compliance. Every decision is recorded with the evidence reviewed, conditions, owner and due dates, and any dissent by name.')}
<h2>7. Charter review</h2>
<p>Internal Audit assesses the program annually against this charter. The Council reviews the charter every year or after any Sev 1 incident.</p>`,
};

const policy = {
  key: 'policy', title: 'Responsible AI Policy', owner: 'Chief Risk Officer', question: 'What must everyone do, and never do, with AI?',
  sub: 'Principles turned into testable requirements, prohibited uses and acceptable use of generative AI',
  desc: 'Testable must-statements, prohibited uses, GenAI acceptable use and the exception process',
  lens: ['Every requirement uses "must" and could be audited yes or no.', 'Prohibited uses are specific, not "unethical uses".', 'Exceptions expire and have an approver.', 'The definition of AI is broad enough to catch vendor features.'],
  html: `
<h2>1. Purpose and scope</h2>
<p>This policy sets the minimum requirements for using AI at ${ORG.name}. It applies to all employees, contractors and vendors acting on the company's behalf, and to every AI system as defined below.</p>
<h2>2. Definition</h2>
<p><strong>AI system</strong>: any system that produces predictions, classifications, recommendations, scores or generated content from data, including AI features of vendor products. A system with fixed, hand-written rules only is not an AI system.</p>
<h2>3. Requirements</h2>
${P.table(['ID', 'Principle', 'Requirement (must)', 'Control'], [
    ['RAI-01', 'Accountable', 'Every AI system must be registered with a named business owner before first use.', 'TL-C-01'],
    ['RAI-02', 'Proportionate', 'Every AI system must be tiered and meet the controls for its tier before use.', 'TL-C-05'],
    ['RAI-03', 'Fair', 'Tier 1 systems affecting consumers must pass unfair-discrimination testing before use and quarterly.', 'TL-C-20'],
    ['RAI-04', 'Transparent', 'Consumers and employees must be told when AI materially contributes to a decision about them.', 'TL-C-14'],
    ['RAI-05', 'Explainable', 'Tier 1 and 2 outputs must carry reasons the person acting on them can check.', 'TL-C-13'],
    ['RAI-06', 'Human oversight', 'A named role must be able to override or stop every Tier 1 and 2 system.', 'TL-C-07, TL-C-22'],
    ['RAI-07', 'Private and secure', 'Restricted data must only be used in systems approved for that data class.', 'TL-C-03'],
    ['RAI-08', 'Reliable', 'Tier 1 and 2 systems must be monitored against thresholds with a named responder.', 'TL-C-12'],
    ['RAI-09', 'Traceable', 'Tier 1 decisions must be logged in a tamper-evident store for 7 years.', 'TL-C-21'],
    ['RAI-10', 'Controlled change', 'Material changes must re-enter intake before release.', 'TL-C-08'],
  ])}
<h2>4. Prohibited uses</h2>
${P.list([
    'Denying a claim, cancelling or non-renewing a policy without a person reviewing the decision.',
    'Using protected characteristics, or inferred ones, as inputs to underwriting, pricing or claims decisions. (Inferred labels are allowed only for aggregate fairness testing.)',
    'Emotion recognition or biometric categorization of customers or employees.',
    'Uploading claimant, health, payment or employee data to any AI tool not approved for that data class.',
    'Generating content that impersonates a real person, or customer communications not identified as from Meridian.',
  ])}
<h2>5. Generative AI acceptable use</h2>
${P.table(['You may', 'You must not'], [
    ['Use DeskAssist and CodeAssist for drafting, summarizing and coding', 'Use consumer AI tools, browser extensions or note-takers for company work'],
    ['Paste internal, non-restricted information into approved tools', 'Paste claimant, health, payment or SSN data into any tool not approved for it'],
    ['Use AI drafts as a starting point', 'Send AI output to a customer or regulator without reading and owning it'],
  ])}
<h2>6. Exceptions</h2>
<p>Exceptions are requested through intake, must state the compensating control, and expire within 12 months. The AI Council approves exceptions for Tier 1 and 2 systems; the Governance Lead for Tier 3 and 4. Expired exceptions are findings.</p>
${P.callout('warn', 'Enforcement', 'Use of a prohibited or unregistered AI system is a policy violation handled under the Code of Conduct. Self-reported shadow AI registered within 30 days of discovery is treated as intake, not as a violation.')}`,
};

const inventory = {
  key: 'inventory', title: 'AI System Inventory', owner: 'AI Governance Lead', question: 'What AI do we run, who owns it, and how risky is it?',
  sub: `Register of all ${SYSTEMS.length} AI systems found at ${ORG.name}, with owner, purpose, tier and review dates`,
  desc: 'Every AI system with owner, decision, data, tier, status and next review',
  lens: ['Every row has a named owner (a person).', 'The tier matches the risk assessment score.', 'Shadow AI discoveries are recorded, not hidden.', 'Next review dates follow the tier schedule.'],
  csv: [{ name: 'TrustLine_AI_Inventory.csv', label: 'CSV', head: ['ID', 'System', 'Owner', 'Source', 'Purpose', 'Decision influenced', 'Data', 'Score', 'Tier', 'Status', 'Last review', 'Next review', 'Found by'],
    rows: SYSTEMS.map((s) => [s.id, s.name, s.owner, s.source, s.purpose, s.decision, s.data, s.tier ? s.score : '', tierName(s.tier), s.status, s.reviewed, nextReview(s), s.found]) }],
  html: `
<h2>1. Summary</h2>
${P.tiles([
    { v: String(SYSTEMS.length), l: 'Systems found' }, { v: String(registered.length), l: 'Registered and tiered' },
    { v: String(tierCount(1)), l: 'Tier 1', tone: 'warn' }, { v: String(tierCount(2)), l: 'Tier 2' },
    { v: String(tierCount(3) + tierCount(4)), l: 'Tier 3 and 4' }, { v: String(tierCount(0)), l: 'Prohibited (blocked)', tone: 'warn' },
  ])}
<h2>2. Register</h2>
${P.table(['ID', 'System', 'Owner', 'Decision influenced', 'Tier', 'Status', 'Next review'], SYSTEMS.map((s) => [s.id, `<strong>${s.name}</strong><br><span class="small">${s.purpose}</span>`, s.owner, s.decision, tierName(s.tier), s.status, nextReview(s)]))}
<h2>3. Data and sourcing</h2>
${P.table(['ID', 'Source', 'Data used', 'Found by'], SYSTEMS.map((s) => [s.id, s.source, s.data, s.found]))}
<h2>4. Notes</h2>
${P.list([
    'TL-AI-06 VoxSight was bought by the contact center in 2025 without intake. It was found by the September expense scan, registered, tiered Tier 2 and given until 2026-12-31 to close two findings (employee notice, vendor change-notice clause).',
    'TL-AI-11 was a free browser note-taker used by adjusters. It processed claimant PII in a consumer service, a prohibited use. It was blocked on 2026-09-11 (incident AI-INC-2026-009).',
    'TL-AI-03 RateSense is not in production. It cannot be used for any renewal until the Council decision scheduled for 2026-11-12.',
  ])}
${P.callout('info', 'How the inventory stays complete', 'Intake is required by policy (RAI-01), procurement will not issue a purchase order for software with AI features without an inventory ID, and the CISO runs a quarterly proxy-log and expense scan for AI services.')}`,
};

const tierRows = registered.map((s) => [s.id, s.short, s.impact, s.autonomy, s.exposure, s.sensitivity, scoreOf(s), s.consequentialNoHuman ? 'Yes' : 'No', tierName(s.tier), controlsFor(s.tier).length]);
const risk = {
  key: 'risk', title: 'AI Risk Assessment & Tiering', owner: 'AI Governance Lead', question: 'How risky is each system, and what must be in place?',
  sub: 'Scored tiering for every registered system, and the full risk assessment for ClaimsPilot AI',
  desc: 'Scoring method, scores for every system, and the full ClaimsPilot risk register',
  lens: ['Every score shows its four factors, not just a total.', 'The floor rule is applied and visible.', 'Each risk has a control and a residual rating.', 'Residual risks above appetite have a decision, not a hope.'],
  csv: [{ name: 'TrustLine_Tiering_Scores.csv', label: 'CSV', head: ['ID', 'System', 'Impact', 'Autonomy', 'Exposure', 'Sensitivity', 'Score', 'Floor rule applied', 'Tier', 'Controls required'], rows: tierRows }],
  html: `
<h2>1. Method</h2>
<p>Score = 2 &times; impact + autonomy + exposure + data sensitivity, each rated 1 to 5 by the Governance Lead with the system owner, using the rubric in the Responsible AI Policy. Floor rule: a consequential decision about a consumer with no human review is Tier 1.</p>
${P.table(['Tier', 'Threshold', 'Controls'], TIER_RULES.map((r) => [r.name, `score ${r.min} or more`, r.controls]))}
<h2>2. Scores</h2>
${P.table(['ID', 'System', 'Impact', 'Autonomy', 'Exposure', 'Sensitivity', 'Score', 'Floor', 'Tier', 'Controls'], tierRows, 'matrix')}
<h2>3. Full assessment: ClaimsPilot AI (TL-AI-01)</h2>
<p>ClaimsPilot scores 21 and also meets the floor rule, because fast-track payments up to $2,500 are made with no adjuster review. It is Tier 1 and needs all 24 controls.</p>
${P.table(['Risk ID', 'Risk', 'Likelihood', 'Impact', 'Controls', 'Residual'], [
    ['CP-R1', 'Complex or injury claim misrouted to fast-track, so the claimant is underpaid', 'Medium', 'High', 'Severe-misroute red line 0.5% with automatic fallback (TL-C-23); daily sample of 50 fast-track claims', 'Low'],
    ['CP-R2', 'Fast-track rates differ by state or claimant group without justification', 'Low', 'High', 'Quarterly fairness test (TL-C-20) on fast-track and payment amounts', 'Low'],
    ['CP-R3', 'Prompt injection through claimant-submitted text or photos', 'Medium', 'Medium', 'Text treated as data; model has no payment tool, only a recommendation; red-team tests (TL-C-17)', 'Low'],
    ['CP-R4', 'Adjusters rubber-stamp recommendations', 'Medium', 'Medium', 'Override band 3% to 12% monitored; reasons shown for every route (TL-C-13)', 'Medium'],
    ['CP-R5', 'Hosted LLM provider changes the model version silently', 'Medium', 'Medium', 'Version pinned; change notice clause (TL-C-16); regression golden set on any change', 'Low'],
    ['CP-R6', 'Decision cannot be reconstructed for a complaint or exam', 'Low', 'High', 'Hash-chained decision log, 7 years (TL-C-21)', 'Low'],
  ])}
${P.callout('warn', 'Residual risk above appetite', 'CP-R4 remains Medium: adjusters accepted 97% of recommendations in the first pilot month. Accepted by the AI Council on 2026-07-14 on condition that the override rate is reported monthly and a reviewer-time study is completed by 2026-12-31 (owner: Rafael Ortiz).')}`,
};

const fairRows = FAIR.groups.map((g) => [g.g, g.n.toLocaleString('en-US'), g.refBefore, pct(g.before), g.ratioBefore.toFixed(2), g.refAfter, pct(g.after), g.ratioAfter.toFixed(2)]);
const impact = {
  key: 'impact', title: 'Algorithmic Impact Assessment: SentinelRisk', owner: 'AI Governance Lead', question: 'Does fraud scoring treat claimants fairly, and what did we change?',
  sub: 'Unfair-discrimination testing of SIU referrals, the proxy found, the fix and its cost',
  desc: 'Fairness test of fraud referrals by group, the ZIP proxy, the fix and the accuracy trade-off',
  lens: ['Group rates come with counts, not just percentages.', 'The threshold was set before the test.', 'The driving features are named.', 'The accuracy cost of the fix is stated and accepted by name.'],
  people: { reviewed: PEOPLE.privacy, approved: PEOPLE.cro },
  csv: [{ name: 'SentinelRisk_Fairness_Test.csv', label: 'CSV', head: ['Group (BIFSG inferred)', 'Claims scored', 'Referrals before', 'Referral rate before', 'Ratio before', 'Referrals after', 'Referral rate after', 'Ratio after'], rows: fairRows }],
  html: `
<h2>1. System and decision</h2>
<p>SentinelRisk (TL-AI-02, Tier 1, vendor) scores every claim. Claims scoring above 0.82 are referred to the Special Investigations Unit, where an investigator decides whether to open an investigation. A referral delays payment by a median of 9 days, so it is an adverse outcome for an honest claimant.</p>
<h2>2. Method</h2>
${P.list([`Population: all ${FAIR.total.toLocaleString('en-US')} claims scored, ${FAIR.window}.`, 'Group membership inferred with BIFSG in aggregate; labels kept in a restricted test environment and deleted after the test.', `Metric: referral rate per group divided by the ${FAIR.reference} group's rate. Threshold ${FAIR.threshold}, set in the policy before testing.`, 'Driver analysis: drop-one-feature re-scoring on the vendor\'s test endpoint (contract clause V-04).'])}
<h2>3. Results</h2>
${P.table(['Group', 'Claims', 'Referrals before', 'Rate before', 'Ratio before', 'Referrals after', 'Rate after', 'Ratio after'], fairRows, 'matrix')}
${P.chartRow(P.barChart({ title: 'Referral-rate ratio before fix', data: FAIR.groups.map((g) => ({ label: g.g, value: g.ratioBefore, tone: g.ratioBefore > FAIR.threshold ? 'cherry' : 'berry' })), max: 1.8 }),
    P.barChart({ title: 'Referral-rate ratio after fix', data: FAIR.groups.map((g) => ({ label: g.g, value: g.ratioAfter, tone: g.ratioAfter > FAIR.threshold ? 'cherry' : 'leaf' })), max: 1.8 }))}
<p>Before the fix, ${FAIR.flaggedBefore.join(' and ')} claimants exceeded the threshold. After the fix, ${FAIR.flaggedAfter.length ? FAIR.flaggedAfter.join(', ') : 'no group'} exceeds it.</p>
<h2>4. Cause</h2>
<p>Two features carried most of the gap: <code>${FAIR.removed}</code> (claims per 1,000 policies in the claimant's ZIP code), which tracks neighborhood demographics more than fraud, and <code>${FAIR.capped}</code>, which counts claims by anyone at an address and penalizes multi-unit housing.</p>
<h2>5. Alternatives and trade-off</h2>
${P.table(['Option', 'Groups over threshold', 'Referral precision', 'Fraud found (annual)', 'Decision'], [
    ['A. Keep current model', String(FAIR.flaggedBefore.length), pct(FAIR.precisionBefore), `$${FAIR.fraudFoundBefore}M`, 'Rejected: fails threshold'],
    ['B. Raise referral cut-off for flagged groups', '0', '30.2%', '$13.1M', 'Rejected: uses group membership in a decision (prohibited)'],
    [`C. Remove ${FAIR.removed}; cap ${FAIR.capped} at 2`, String(FAIR.flaggedAfter.length), pct(FAIR.precisionAfter), `$${FAIR.fraudFoundAfter}M`, 'Selected'],
  ])}
${P.callout('info', 'Accepted cost', `Option C finds an estimated $${(FAIR.fraudFoundBefore - FAIR.fraudFoundAfter).toFixed(1)}M less fraud a year. ${PEOPLE.siu.name} (Head of SIU) and ${PEOPLE.cro.name} (CRO) accepted this on 2026-09-22 as the less discriminatory alternative that still meets the business purpose.`)}
<h2>6. Decision and conditions</h2>
<p><strong>Approved with conditions</strong> by the AI Council, 2026-09-22.</p>
${P.list(['Vendor deploys option C by 2026-10-15; Governance Lead verifies on the test endpoint before switch-over.', 'Fairness re-test quarterly, and on any vendor model change.', 'SIU referral letters state that referral is a routine review, not an accusation, and give a contact for questions.', 'Vendor contract renewal (2027-03) must keep the test-endpoint clause.'])}`,
};

module.exports = { docsA: [charter, policy, inventory, risk, impact] };
