'use strict';
// The one numbers model for the Week 10 guide. Every figure that appears in a
// teaching section, document, chart or CSV is defined (or derived) here, so the
// documents cannot disagree. All figures are illustrative teaching data.

const ORG = {
  name: 'Meridian Mutual Insurance', states: 6, policies: 412000, employees: 1840,
  claimsPerYear: 58400, program: 'TrustLine', date: '2026-10-03',
};

const PEOPLE = {
  lead: { name: 'Regina Asafor', title: 'AI Governance Lead' },
  cro: { name: 'Diane Castellanos', title: 'Chief Risk Officer, AI Council chair' },
  cco: { name: 'Gwen Albright', title: 'Chief Compliance Officer' },
  cdo: { name: 'Marcus Bell', title: 'Chief Data Officer' },
  privacy: { name: 'Samuel Okafor', title: 'Privacy Counsel' },
  ciso: { name: 'Lauren Pike', title: 'Chief Information Security Officer' },
  claims: { name: 'Rafael Ortiz', title: 'VP Claims Operations' },
  siu: { name: 'Nadia Sorensen', title: 'Head of Special Investigations' },
  actuary: { name: 'Kenji Watanabe', title: 'Chief Actuary' },
  audit: { name: 'Victor Mensah', title: 'Director, Internal Audit' },
  dataGov: { name: 'Elena Ruiz', title: 'Data Governance Lead' },
  eng: { name: 'Priya Natarajan', title: 'Lead Data Engineer' },
};

// Risk tiering. Score = 2 x impact + autonomy + exposure + sensitivity (each 1-5, max 25).
// Floor rule: a consequential consumer decision with no human review is Tier 1 whatever the score.
const TIER_RULES = [
  { tier: 1, name: 'Tier 1 (High)', min: 19, controls: 'All 24 controls; AI Council approval; independent validation; annual re-assessment' },
  { tier: 2, name: 'Tier 2 (Elevated)', min: 14, controls: '17 controls; Governance Lead approval; validation by a second-line reviewer; annual re-assessment' },
  { tier: 3, name: 'Tier 3 (Moderate)', min: 9, controls: '10 controls; system owner attests; review every 2 years' },
  { tier: 4, name: 'Tier 4 (Low)', min: 0, controls: '5 controls; register and follow the acceptable-use policy' },
];
const scoreOf = (s) => 2 * s.impact + s.autonomy + s.exposure + s.sensitivity;
function tierOf(s) {
  if (s.prohibited) return 0;
  const base = TIER_RULES.find((r) => scoreOf(s) >= r.min).tier;
  return s.consequentialNoHuman ? 1 : base;
}
const tierName = (t) => (t === 0 ? 'Prohibited' : TIER_RULES.find((r) => r.tier === t).name);

const SYSTEMS = [
  { id: 'TL-AI-01', name: 'ClaimsPilot AI (FNOL triage and fast-track)', short: 'ClaimsPilot', owner: 'Rafael Ortiz', source: 'In-house + hosted LLM', purpose: 'Classifies new claims, routes them, and fast-track pays glass, towing and rental claims up to $2,500', decision: 'Claim routing; payment on fast-track claims', data: 'Claimant PII, policy, loss description, photos', impact: 4, autonomy: 4, exposure: 5, sensitivity: 4, consequentialNoHuman: true, status: 'Production', reviewed: '2026-07-14', found: 'Intake' },
  { id: 'TL-AI-02', name: 'SentinelRisk Fraud Scoring', short: 'SentinelRisk', owner: 'Nadia Sorensen', source: 'Vendor (SentinelRisk Inc.)', purpose: 'Scores every claim for fraud likelihood; scores above 0.82 are referred to SIU', decision: 'SIU referral (investigator decides)', data: 'Claim, claimant history, address, device and network signals', impact: 5, autonomy: 2, exposure: 5, sensitivity: 4, status: 'Production (conditional)', reviewed: '2026-09-22', found: 'Intake' },
  { id: 'TL-AI-03', name: 'RateSense Renewal Pricing Model', short: 'RateSense', owner: 'Kenji Watanabe', source: 'In-house (gradient-boosted model)', purpose: 'Recommends renewal rate adjustments within filed rating plans', decision: 'Renewal premium (actuary approves the plan; model sets the factor)', data: 'Policy, vehicle, telematics opt-in, claims, credit-based insurance score', impact: 5, autonomy: 3, exposure: 5, sensitivity: 4, status: 'Assessment in progress', reviewed: '2026-09-30', found: 'Intake' },
  { id: 'TL-AI-04', name: 'PolicyLens Coverage Copilot', short: 'PolicyLens', owner: 'Rafael Ortiz', source: 'In-house RAG on hosted LLM', purpose: 'Answers coverage questions for agents and service reps, citing the policy form', decision: 'None directly; a person answers the customer', data: 'Policy forms, endorsements, policy record', impact: 3, autonomy: 2, exposure: 4, sensitivity: 3, status: 'Production', reviewed: '2026-06-30', found: 'Intake' },
  { id: 'TL-AI-05', name: 'Lumina Document Intelligence', short: 'Lumina', owner: 'Rafael Ortiz', source: 'Vendor (Lumina Labs)', purpose: 'Extracts fields from claim documents, estimates and medical bills', decision: 'Populates the claim file; adjuster confirms', data: 'Medical bills (PHI), repair estimates, IDs', impact: 3, autonomy: 3, exposure: 4, sensitivity: 5, status: 'Production', reviewed: '2026-05-19', found: 'Intake' },
  { id: 'TL-AI-06', name: 'VoxSight Call Analytics', short: 'VoxSight', owner: 'Contact Center Director', source: 'Vendor (VoxSight)', purpose: 'Transcribes service calls and scores agent quality and customer sentiment', decision: 'Inputs to agent coaching and performance reviews', data: 'Call audio, transcripts, employee IDs', impact: 3, autonomy: 2, exposure: 3, sensitivity: 4, status: 'Production (registered late)', reviewed: '2026-08-27', found: 'Shadow-AI scan' },
  { id: 'TL-AI-07', name: 'PulseNotify Message Drafting', short: 'PulseNotify', owner: 'Customer Communications Manager', source: 'Vendor feature (GenAI)', purpose: 'Drafts claim-status texts and emails from templates', decision: 'Message content; a person approves each template', data: 'Claim status, first name, contact details', impact: 2, autonomy: 3, exposure: 4, sensitivity: 3, status: 'Production', reviewed: '2026-04-08', found: 'Intake' },
  { id: 'TL-AI-08', name: 'LedgerOne Loss-Reserve Forecast', short: 'Reserve Forecast', owner: 'Kenji Watanabe', source: 'In-house (time-series model)', purpose: 'Forecasts IBNR reserves as one input to the actuarial reserve review', decision: 'Input only; the Chief Actuary sets reserves', data: 'De-identified LedgerOne marts', impact: 4, autonomy: 1, exposure: 2, sensitivity: 2, status: 'Production', reviewed: '2026-03-12', found: 'Intake' },
  { id: 'TL-AI-09', name: 'DeskAssist Employee GenAI', short: 'DeskAssist', owner: 'Lauren Pike', source: 'Enterprise LLM tenant', purpose: 'General writing and summarizing assistant for employees', decision: 'None', data: 'Internal documents (no claimant PII by policy)', impact: 1, autonomy: 1, exposure: 3, sensitivity: 3, status: 'Production', reviewed: '2026-02-26', found: 'Intake' },
  { id: 'TL-AI-10', name: 'CodeAssist Developer Assistant', short: 'CodeAssist', owner: 'Tom Becker', source: 'Vendor coding assistant', purpose: 'Code completion and review suggestions for engineers', decision: 'None; code review and tests gate every change', data: 'Source code (no production data)', impact: 1, autonomy: 1, exposure: 2, sensitivity: 2, status: 'Production', reviewed: '2026-02-26', found: 'Intake' },
  { id: 'TL-AI-11', name: 'Browser AI note-taker (unapproved)', short: 'Note-taker', owner: 'None (individual adjusters)', source: 'Free consumer service', purpose: 'Recorded and summarized adjuster meetings', decision: 'None', data: 'Meeting audio including claimant PII', impact: 2, autonomy: 1, exposure: 2, sensitivity: 5, prohibited: true, status: 'Blocked 2026-09-11', reviewed: '2026-09-11', found: 'Shadow-AI scan' },
].map((s) => ({ ...s, score: scoreOf(s), tier: tierOf(s) }));

const tierCount = (t) => SYSTEMS.filter((s) => s.tier === t).length;
const shadowCount = SYSTEMS.filter((s) => s.found === 'Shadow-AI scan').length;

// SentinelRisk fairness test: 12 months of scored claims, groups inferred with BIFSG
// (aggregate testing only; never attached to an individual claim). Rates are SIU referral %.
const FAIR = {
  window: 'Oct 2025 to Sep 2026', threshold: 1.25, reference: 'White',
  groups: [
    { g: 'White', n: 31500, before: 2.6, after: 2.8 },
    { g: 'Black', n: 8900, before: 4.1, after: 3.3 },
    { g: 'Hispanic', n: 10200, before: 3.6, after: 3.2 },
    { g: 'Asian', n: 3400, before: 2.4, after: 2.6 },
    { g: 'Other / unknown', n: 4400, before: 3.0, after: 2.9 },
  ],
  precisionBefore: 31.0, precisionAfter: 29.6, fraudFoundBefore: 14.2, fraudFoundAfter: 13.7,
  removed: 'territory_claim_density', capped: 'prior_claims_at_address',
};
const refRate = (k) => FAIR.groups.find((x) => x.g === FAIR.reference)[k];
FAIR.groups.forEach((x) => {
  x.refBefore = Math.round((x.n * x.before) / 100); x.refAfter = Math.round((x.n * x.after) / 100);
  x.ratioBefore = +(x.before / refRate('before')).toFixed(2); x.ratioAfter = +(x.after / refRate('after')).toFixed(2);
});
FAIR.total = FAIR.groups.reduce((a, x) => a + x.n, 0);
FAIR.flaggedBefore = FAIR.groups.filter((x) => x.ratioBefore > FAIR.threshold).map((x) => x.g);
FAIR.flaggedAfter = FAIR.groups.filter((x) => x.ratioAfter > FAIR.threshold).map((x) => x.g);

// ClaimsPilot (model card and monitoring).
const CP = {
  holdout: 6000, accuracy: 93.8, severeMisroute: 0.4, severeMisrouteLimit: 0.5, stpShare: 31, stpCap: 2500,
  overrideBand: [3, 12], firstContactBefore: 4.2, firstContactAfter: 0.6,
  months: ['Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep'],
  override: [5.9, 6.2, 6.4, 6.1, 7.3, 6.8],
  psi: [0.04, 0.05, 0.06, 0.05, 0.11, 0.08],
  psiAmber: 0.10, psiRed: 0.25,
  classes: [['Fast-track (pay)', 31, 96.9], ['Standard adjuster', 47, 93.1], ['Complex / injury', 17, 91.4], ['SIU review', 5, 88.2]],
};

const PROGRAM = {
  quarters: ['Q4 2025', 'Q1 2026', 'Q2 2026', 'Q3 2026'],
  intakeDays: [38, 31, 22, 14], intakeTarget: 15,
  trainingPct: 96, findings: { high: 2, medium: 7, low: 11 },
  incidents: 3,
};

const INCIDENTS = [
  ['AI-INC-2026-004', '2026-06-17', 'PolicyLens', 'Sev 3', 'Cited a superseded endorsement form (HO-17 2019 edition) to a service rep', 'Rep caught it before answering; retrieval index now filters by form effective date; regression test added', '0 customers affected'],
  ['AI-INC-2026-007', '2026-08-04', 'ClaimsPilot', 'Sev 2', 'Hail event shifted inputs (PSI 0.11); severe misroutes reached 0.9% for 2 days, above the 0.5% red line', 'Automatic fallback to human triage for hail claims; 37 fast-tracked claims re-reviewed; 3 claimants contacted with supplemental payments', '3 claimants, $4,180 supplemented'],
  ['AI-INC-2026-009', '2026-09-11', 'Note-taker (shadow)', 'Sev 2', 'Unapproved browser note-taker uploaded adjuster meeting audio to a consumer service', 'Blocked at web proxy; vendor deletion confirmation obtained; Privacy Counsel assessed notification duty (none triggered); adjusters retrained', '41 meetings, no SSNs or bank data'],
];

module.exports = { ORG, PEOPLE, TIER_RULES, SYSTEMS, tierName, tierCount, shadowCount, scoreOf, FAIR, CP, PROGRAM, INCIDENTS };
