'use strict';
// TrustLine control set. `reach` = the lowest-risk tier the control still applies to
// (4 = every tier, 1 = Tier 1 only). Counts per tier are asserted below so the
// numbers quoted in TIER_RULES (model.js) can never drift from this list.
const { TIER_RULES } = require('./model');

const C = (n, domain, control, reach, gate, nist, iso, naic, evidence, owner, freq) =>
  ({ id: `TL-C-${String(n).padStart(2, '0')}`, domain, control, reach, gate, nist, iso, naic, evidence, owner, freq });

const CONTROLS = [
  C(1, 'Inventory', 'Registered in the AI inventory with a named business owner before first use', 4, 'G0', 'GOVERN', '8 Operation', 'Written AIS program', 'Inventory record', 'System owner', 'Before use; on change'),
  C(2, 'People', 'Every user has acknowledged the Responsible AI Policy', 4, 'G0', 'GOVERN', '7 Support', 'Governance and accountability', 'LMS completion report', 'HR / Governance Lead', 'Annual'),
  C(3, 'Data', 'Restricted data (SSN, bank, health) only enters systems approved for it', 4, 'G1', 'MAP', '8 Operation', 'Risk management and internal controls', 'DLP rule and system configuration', 'CISO', 'Continuous'),
  C(4, 'Security', 'Single sign-on, access logging and a passed security review', 4, 'G1', 'MANAGE', '8 Operation', 'Third-party AI systems', 'Security review ticket', 'CISO', 'Before use; annual'),
  C(5, 'Risk', 'Risk tier assigned and recorded with score and rationale', 4, 'G0', 'MAP', '6 Planning', 'Risk management and internal controls', 'Tiering worksheet', 'Governance Lead', 'Before use; on change'),
  C(6, 'Purpose', 'Intended use, users and out-of-scope uses documented', 3, 'G1', 'MAP', '8 Operation', 'Documentation for regulators', 'Model card or system sheet', 'System owner', 'Before use; on change'),
  C(7, 'Oversight', 'Human oversight defined: who can override, how, and within what time', 3, 'G1', 'MANAGE', '8 Operation', 'Governance and accountability', 'Oversight design and procedure', 'Business owner', 'Before use'),
  C(8, 'Change', 'Material changes (model, prompt, vendor version, data source) re-enter intake', 3, 'G4', 'MANAGE', '8 Operation', 'Risk management and internal controls', 'Change tickets linked to inventory', 'System owner', 'Every change'),
  C(9, 'Incidents', 'Incident reporting path known to users and tested', 3, 'G4', 'MANAGE', '10 Improvement', 'Risk management and internal controls', 'Tabletop record', 'Governance Lead', 'Annual'),
  C(10, 'Review', 'Periodic re-assessment on the tier schedule', 3, 'G4', 'MEASURE', '9 Performance evaluation', 'Written AIS program', 'Re-assessment record', 'Governance Lead', 'Tier 1-2 annual; Tier 3 every 2 years'),
  C(11, 'Validation', 'Pre-deployment validation against written acceptance criteria by a second-line reviewer', 2, 'G2', 'MEASURE', '9 Performance evaluation', 'Risk management and internal controls', 'Validation report', 'Model Risk', 'Before use; on material change'),
  C(12, 'Monitoring', 'Performance metrics with green/amber/red thresholds and a named responder', 2, 'G4', 'MEASURE', '9 Performance evaluation', 'Risk management and internal controls', 'Monitoring dashboard and runbook', 'System owner', 'Continuous'),
  C(13, 'Explainability', 'Outputs carry reasons a person can act on (reason codes, cited sources)', 2, 'G2', 'MEASURE', '8 Operation', 'Risk management and internal controls', 'Sample of outputs with reasons', 'System owner', 'Before use; quarterly sample'),
  C(14, 'Transparency', 'Notice to consumers or employees where AI materially contributes to a decision about them', 2, 'G3', 'GOVERN', '7 Support', 'Governance and accountability', 'Approved notice text and placement', 'Compliance', 'Before use'),
  C(15, 'Data', 'Training and retrieval data lineage and provenance documented', 2, 'G1', 'MAP', '8 Operation', 'Documentation for regulators', 'Lineage map and data sheet', 'Data Governance Lead', 'Before use; on change'),
  C(16, 'Vendor', 'Contract gives audit rights, change notice, data-use limits and test data access', 2, 'G1', 'GOVERN', '8 Operation', 'Third-party AI systems', 'Executed contract clauses', 'Procurement / Legal', 'Before signature; renewal'),
  C(17, 'GenAI', 'Prompt-injection and harmful-output testing; grounded answers cite sources', 2, 'G2', 'MEASURE', '8 Operation', 'Risk management and internal controls', 'Red-team test log', 'System owner', 'Before use; on change'),
  C(18, 'Approval', 'AI Council approval before production and after any material change', 1, 'G3', 'GOVERN', '5 Leadership', 'Governance and accountability', 'Council minutes and decision record', 'AI Council chair', 'Before use; on change'),
  C(19, 'Validation', 'Independent validation by a team that did not build it, including a benchmark or challenger', 1, 'G2', 'MEASURE', '9 Performance evaluation', 'Risk management and internal controls', 'Independent validation report', 'Model Risk', 'Before use; annual'),
  C(20, 'Fairness', 'Unfair-discrimination testing across protected classes (inferred, aggregate) against a 1.25 ratio threshold, with remediation', 1, 'G2', 'MEASURE', '8 Operation', 'Risk management and internal controls', 'Fairness test report', 'Governance Lead', 'Before use; quarterly'),
  C(21, 'Logging', 'Every AI-influenced decision logged (inputs, version, output, human action) in a tamper-evident store for 7 years', 1, 'G3', 'MANAGE', '9 Performance evaluation', 'Documentation for regulators', 'Decision log sample and hash-chain check', 'System owner', 'Continuous'),
  C(22, 'Fallback', 'Kill switch and manual fallback process, tested', 1, 'G3', 'MANAGE', '8 Operation', 'Risk management and internal controls', 'Fallback test record', 'Business owner', 'Quarterly'),
  C(23, 'Monitoring', 'Drift and outcome monitoring that triggers automatic fallback at the red line', 1, 'G4', 'MANAGE', '9 Performance evaluation', 'Risk management and internal controls', 'Alert configuration and test', 'System owner', 'Continuous'),
  C(24, 'Assurance', 'Internal Audit review of the control set (third line)', 1, 'G4', 'GOVERN', '9 Performance evaluation', 'Governance and accountability', 'Audit report', 'Internal Audit', 'Annual'),
];

const controlsFor = (tier) => CONTROLS.filter((c) => c.reach >= tier);
const EXPECTED = { 1: 24, 2: 17, 3: 10, 4: 5 };
for (const t of [1, 2, 3, 4]) {
  if (controlsFor(t).length !== EXPECTED[t]) throw new Error(`controls.js: Tier ${t} has ${controlsFor(t).length} controls, TIER_RULES says ${EXPECTED[t]}`);
  if (!TIER_RULES.find((r) => r.tier === t).controls.startsWith(EXPECTED[t] === 24 ? 'All 24' : String(EXPECTED[t]))) throw new Error(`controls.js: TIER_RULES text for Tier ${t} disagrees`);
}

const GATES = [
  ['G0', 'Intake and tiering', 'Is this AI, who owns it, and how risky is it?', 'Inventory record, tiering worksheet'],
  ['G1', 'Design review', 'Is the purpose legitimate, the data allowed and the oversight real?', 'System sheet, data approval, oversight design, vendor clauses'],
  ['G2', 'Validation', 'Does it work, fairly and safely, against criteria written before testing?', 'Validation report, fairness report, red-team log'],
  ['G3', 'Go-live approval', 'Is everything in place to run it and stop it?', 'Council decision, notices, logging, fallback test'],
  ['G4', 'Operate and monitor', 'Is it still doing what was approved?', 'Monitoring, change tickets, incidents, re-assessments'],
  ['G5', 'Retire', 'Is it switched off cleanly, with records kept?', 'Decommission record, data disposal certificate'],
];

module.exports = { CONTROLS, controlsFor, GATES };
