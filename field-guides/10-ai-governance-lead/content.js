'use strict';
// Week 10 deep dive: AI Governance Lead. Built by field-guides/kit/build.js.
// Numbers live in model.js and controls.js; prose in sections.js, docs-a.js, docs-b.js, faq.js.
const P = require('../kit/parts');
const { ORG, PEOPLE, SYSTEMS } = require('./model');
const CONTROLS_COUNT = require('./controls').CONTROLS.length;
const { sections } = require('./sections');
const { docsA } = require('./docs-a');
const { docsB } = require('./docs-b');
const { faq } = require('./faq');

module.exports = {
  meta: {
    week: 10, discipline: 'AI Governance Lead', title: 'AI Governance Lead Field Guide', file: 'AIGovernanceLead_FieldGuide.html',
    date: ORG.date, buildNumber: 'AGL-20261003-01', version: '1.0.0',
    studentId: 'regina.asafor@gmail.com', projectId: '36a39c2b-9cd5-4034-9582-1800a9453431',
    author: PEOPLE.lead.name, authorTitle: PEOPLE.lead.title,
    description: `Colaberry AI Governance Lead Field Guide: inventory, risk tiering, controls, fairness testing, oversight, vendors and monitoring for AI Solution Architects, with nine complete documents for ${ORG.name}'s TrustLine program.`,
  },
  example: { industry: 'Insurance (personal auto and homeowners)', organization: ORG.name, initiative: 'TrustLine: Enterprise AI Governance Program', short: 'TrustLine', docPrefix: 'TL-AG' },
  people: { prepared: PEOPLE.lead, reviewed: PEOPLE.cco, approved: PEOPLE.cro },
  hero: {
    lede: `The 20% of AI governance an AI Solution Architect needs to direct, evaluate and approve AI-generated policies, assessments and controls, applied end to end to one realistic program: <strong>${ORG.name}'s TrustLine</strong>, which brings ${SYSTEMS.length} AI systems under one inventory, one tiering rule and one council.`,
    chips: [`${SYSTEMS.length} AI systems`, `${CONTROLS_COUNT} controls`, '1 fairness test, 2 groups fixed'],
  },
  start: `
<p class="lede">AI will draft your charters, policies, risk assessments and model cards in minutes. Your job as an AI Solution Architect is to <strong>direct</strong> that work with a precise brief, <strong>evaluate</strong> what comes back against a known standard, and <strong>approve</strong> only what would satisfy an examiner, an auditor and a customer who was harmed. This guide is the 20% of AI governance that makes those three verbs possible.</p>
${P.table(['Part', 'What it gives you', 'Use it when'], [
    ['The discipline (chapters 1 to 10)', 'The concepts behind every governance decision, one screen each', 'You need to understand or explain a decision'],
    ['Judgment', 'Good vs bad, KPIs and the review lens', 'You are approving or rejecting a draft'],
    ['The worked example', 'Meridian Mutual\'s TrustLine program, figures consistent throughout', 'You want to see the concepts applied'],
    ['Nine documents', 'Complete, designed deliverables with HTML, PDF and CSV downloads', 'You need the benchmark for what "done" looks like'],
  ])}
${P.callout('info', 'Search and Ask', 'Use the search box (press <span class="kbd">/</span>) to jump to any topic, control or system. Use <strong>Ask the guide</strong> to ask a question in plain English; it answers only from this page and names the section it used.')}
<h3>The three verbs</h3>
${P.table(['Verb', 'What you do', 'Evidence you look for'], [
    ['Direct', 'Give AI the system, the decision it influences, the people affected, the data, the tier and the controls that apply', 'A brief that names the tier and the control IDs'],
    ['Evaluate', 'Check the draft against the review lens', 'Named owners, testable statements, dated evidence, a failure path'],
    ['Approve', 'Sign only what you would defend to a regulator', 'A decision record with conditions, owners and due dates'],
  ])}`,
  sections,
  documents: [...docsA, ...docsB],
  glossary: [
    ['AI system', 'Anything that produces predictions, classifications, recommendations, scores or generated content from data, including AI features in vendor products.'],
    ['AI inventory', 'The register of every AI system with owner, purpose, tier and status.'],
    ['AI Council', 'The executive body that approves, conditions, pauses or prohibits Tier 1 AI systems.'],
    ['Adverse outcome', 'A result that harms the person it is about: a referral, a denial, a higher price, a delay.'],
    ['Automation bias', 'The tendency of people to accept a system\'s output without checking it.'],
    ['BIFSG', 'Bayesian Improved First name and Surname Geocoding: a method to infer race and ethnicity in aggregate for fairness testing.'],
    ['Decision log', 'An append-only record of each AI-influenced decision: inputs, version, output and the human action.'],
    ['Drift', 'A change in a system\'s inputs or outcomes after it was approved.'],
    ['Fail-closed', 'A gate that treats missing evidence as "no" rather than "assume fine".'],
    ['Fairness threshold', 'The ratio of a group\'s adverse-outcome rate to the reference group\'s above which a finding is raised (1.25 at Meridian).'],
    ['Floor rule', 'A rule that sets a minimum tier regardless of score, such as consequential consumer decisions with no human review.'],
    ['Gate', 'A lifecycle point where evidence is checked before a system moves on (G0 to G5).'],
    ['Human-in-the-loop', 'A person approves every output before it takes effect.'],
    ['Human-on-the-loop', 'Outputs take effect, and a person monitors and can reverse them.'],
    ['Intake', 'The required registration step before any AI system is bought, built or switched on.'],
    ['Kill switch', 'A tested way to stop an AI system and fall back to a manual process.'],
    ['Material change', 'A change to model, prompt, vendor version or data source that could change outcomes; it re-enters intake.'],
    ['Model card', 'A short document stating a model\'s intended use, limits, performance and oversight.'],
    ['NAIC AI bulletin', 'The NAIC Model Bulletin on the Use of AI Systems by Insurers, adopted by many US states.'],
    ['NIST AI RMF', 'NIST AI Risk Management Framework 1.0, organized as GOVERN, MAP, MEASURE and MANAGE.'],
    ['ISO/IEC 42001', 'International, certifiable standard for an AI management system.'],
    ['Override rate', 'The share of AI outputs a person changes; a test of whether oversight is real.'],
    ['Prompt injection', 'Instructions hidden in input content that try to steer a generative AI system.'],
    ['Proxy', 'An input that stands in for a protected characteristic, such as ZIP code for race.'],
    ['PSI', 'Population Stability Index: a measure of how much an input distribution has shifted.'],
    ['Risk tier', 'The level of scrutiny a system gets, set by a scoring rule (Tier 1 to 4, or prohibited).'],
    ['Shadow AI', 'AI in use without registration or approval.'],
    ['Three lines of defense', 'Owners manage risk, a second line sets and checks the rules, Internal Audit assures.'],
  ],
  faq,
  ask: {
    suggestions: ['How is the risk tier calculated?', 'What counts as an AI system?', 'How do you test for unfair discrimination without collecting race?', 'Who can switch off an AI system?', 'What must a vendor AI contract include?', 'Can I paste claim data into a chatbot?', 'What happened in the hail-event incident?', 'What should I check before approving an AI-drafted governance document?'],
    placeholder: 'e.g. How is the risk tier calculated?',
    searchPlaceholder: 'Search topics, documents, controls, systems...',
    noMatchHint: 'Try a control id (TL-C-20), a system (SentinelRisk) or a concept (tiering, drift, shadow AI).',
    notCovered: 'AI inventory and intake, risk tiering, frameworks and regulation, lifecycle gates, fairness testing, human oversight, vendor AI, monitoring and incidents, generative AI, or any of the nine documents',
  },
  checks: {
    search: [
      { q: 'shadow AI', expect: ['inventory', 'doc-inventory'] },
      { q: 'BIFSG', expect: ['fairness', 'doc-impact'] },
      { q: 'kill switch', expect: ['doc-charter', 'doc-monitoring', 'doc-model-card'] },
      { q: 'TL-C-20', expect: 'doc-controls' },
      { q: 'prompt injection', expect: 'genai' },
      { q: 'hail', expect: ['monitoring', 'doc-monitoring', 'doc-model-card'] },
      { q: 'audit rights', expect: ['vendors', 'doc-vendor'] },
    ],
    ask: [
      { q: 'how do we score how risky a system is', expect: 'tiering' },
      { q: 'is a vendor CRM lead score an AI system?', expect: 'inventory' },
      { q: 'how can we check fairness if we do not collect race', expect: 'fairness' },
      { q: 'who is allowed to stop an AI system', expect: 'doc-charter' },
      { q: 'what clauses should an AI vendor contract have', expect: 'vendors' },
      { q: 'can employees paste claimant data into ChatGPT', expect: 'doc-policy' },
      { q: 'what did fixing the fraud model cost us', expect: 'doc-impact' },
      { q: 'how do I know the human reviewers are not rubber stamping', expect: 'oversight' },
    ],
    offTopic: 'What is the best recipe for sourdough bread?',
  },
};
