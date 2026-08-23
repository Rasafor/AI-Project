/*
  Single source of truth for the Family Tree App knowledge base.
  Every page (index.html and 01-07) reads from this object at runtime.
  If a number or fact needs to change, it changes here once.

  IMPORTANT: this is declared with `const` at the top level of a classic
  <script> tag (no ES modules, per the portability requirement — file://
  URLs block type="module" fetches). `const` at top level does NOT attach
  to `window`, so other scripts must reference the bare identifier
  `BLUEPRINT`, not `window.BLUEPRINT`.
*/
const BLUEPRINT = {

  meta: {
    title: "Family Tree App",
    tagline: "System architecture and build plan for an app that creates a family tree at least 10 generations deep.",
    generated: "2026-08-06"
  },

  idea: "Build an app that can be used to create a family tree with 10 generations deep at a minimum.",

  ideaFraming: "Two phrases in that sentence drive every decision in this design: “app…used to create” means a human builds the tree by hand across more than one sitting, and “10 generations deep at a minimum” is the requirement that outranks everything else — a tree that looks fine at 3 generations and breaks at 10 hasn't done its job.",

  // Ordered list of knowledge-base sections. Drives the Command Center tiles,
  // the shared nav, breadcrumbs, and previous/next links on every page.
  sections: [
    {
      id: "idea",
      page: "01-the-idea.html",
      nav: "The Idea",
      title: "The Idea",
      blurb: "The one-paragraph brief this whole design is built from.",
      illustration: "idea-pipeline"
    },
    {
      id: "components",
      page: "02-components.html",
      nav: "Components",
      title: "Components",
      blurb: "The real, idea-specific pieces this app needs — nothing padded in.",
      illustration: "layer-diagram"
    },
    {
      id: "diagram",
      page: "03-how-it-fits-together.html",
      nav: "How It Fits Together",
      title: "How It Fits Together",
      blurb: "The architecture diagram: components and the data moving between them.",
      illustration: "node-graph"
    },
    {
      id: "dataflow",
      page: "04-data-flow.html",
      nav: "Data Flow",
      title: "Data Flow",
      blurb: "A numbered walkthrough of what happens, step by step, when someone builds the tree.",
      illustration: "flow-ribbon"
    },
    {
      id: "buildorder",
      page: "05-build-order.html",
      nav: "Build Order",
      title: "Build Order",
      blurb: "The four phases, in order, and what each one has to prove before moving on.",
      illustration: "phase-bars"
    },
    {
      id: "assumptions",
      page: "06-assumptions.html",
      nav: "Assumptions",
      title: "Assumptions",
      blurb: "What this design assumes, the impact if any assumption is wrong, and the one open question.",
      illustration: "fork-branches"
    },
    {
      id: "coverage",
      page: "07-coverage.html",
      nav: "What This Doesn't Cover",
      title: "What This Design Does Not Cover",
      blurb: "An honest list of what's covered now versus deliberately deferred.",
      illustration: "coverage-grid"
    }
  ],

  // The 4 real components. Nothing here that the idea didn't ask for.
  components: [
    {
      id: "ui",
      name: "Tree Builder & Viewer UI",
      layer: "interface",
      sentence: "The screen where a person adds relatives, fills in names and dates, and looks at the tree they've built so far.",
      why: "“app…used to create” — a human directly builds and views it, so something has to be the thing they touch."
    },
    {
      id: "engine",
      name: "Genealogy Engine",
      layer: "logic",
      sentence: "Keeps the family structure correct — who is whose parent, child, or spouse, and how many generations separate any two people — and rejects nonsense before it's saved.",
      why: "“create a family tree” + “10 generations deep” — this is the component that structurally guarantees there's no hidden ceiling. It's an open-ended relationship chain, not a form with exactly 10 pre-printed slots.",
      guarantor: true,
      guarantorRole: "Guarantees depth can exist — the data structure has no hardcoded generation limit."
    },
    {
      id: "render",
      name: "Tree Rendering Engine",
      layer: "logic",
      sentence: "Draws the tree on screen so it's usable at real depth — pan, zoom, and collapse branches instead of 10 generations becoming an unreadable wall of boxes.",
      why: "“10 generations deep” — the other half of the guarantee: the Genealogy Engine proves the depth can exist, this proves a person can actually see and use it.",
      guarantor: true,
      guarantorRole: "Guarantees depth is usable — the tree stays navigable once it's actually 10+ generations deep."
    },
    {
      id: "store",
      name: "Local Persistent Store",
      layer: "data",
      sentence: "Saves the tree to the device so it's still there next time the app opens — nobody wants to rebuild ten generations from scratch.",
      why: "“create” implies ongoing work across more than one sitting — state that outlives a session needs somewhere to live."
    }
  ],

  // Nodes/edges shared by the mermaid flowchart AND the inline-SVG mini node graph.
  graph: {
    nodes: [
      { id: "user", label: "Person building the tree", kind: "entry" },
      { id: "ui", label: "Tree Builder & Viewer UI", kind: "service" },
      { id: "engine", label: "Genealogy Engine", kind: "service" },
      { id: "render", label: "Tree Rendering Engine", kind: "service" },
      { id: "store", label: "Local Persistent Store", kind: "data" }
    ],
    edges: [
      { from: "user", to: "ui", label: "adds a person / defines a relationship" },
      { from: "ui", to: "engine", label: "new person or relationship record" },
      { from: "engine", to: "store", label: "validated update, generation numbers recalculated" },
      { from: "store", to: "engine", label: "saved tree graph, on app open" },
      { from: "engine", to: "render", label: "current graph or requested branch" },
      { from: "render", to: "ui", label: "tree view, navigable past 10 generations" },
      { from: "ui", to: "render", label: "pan, zoom, expand, collapse" }
    ]
  },

  flowchartMermaid:
`flowchart TD
    User(["Person building the tree"]) -->|"adds a person or defines a relationship"| UI["Tree Builder and Viewer UI"]
    UI -->|"new person or relationship record"| Engine["Genealogy Engine - relationship graph and validation"]
    Engine -->|"validated update, generation numbers recalculated"| Store[("Local Persistent Store")]
    Store -->|"saved tree graph, on app open"| Engine
    Engine -->|"current graph or requested branch"| Render["Tree Rendering Engine"]
    Render -->|"tree view, navigable past 10 generations"| UI
    UI -->|"pan, zoom, expand, collapse"| Render`,

  flowchartInterpretation: "A person's actions flow through the UI into the Genealogy Engine, the only component allowed to decide the family structure is valid — it then hands the confirmed structure to storage so it survives closing the app, and to the renderer so it can actually be seen, even ten generations deep.",

  sequenceMermaid:
`sequenceDiagram
    participant User as Person building the tree
    participant UI as Tree Builder and Viewer UI
    participant Engine as Genealogy Engine
    participant Store as Local Persistent Store
    participant Render as Tree Rendering Engine

    UI->>Store: does a saved tree exist
    Store-->>Engine: saved tree graph, if any
    User->>UI: add person or define relationship
    UI->>Engine: new person or relationship record
    Engine->>Engine: validate structure and recalc generation numbers
    Engine->>Store: write validated update
    Engine->>Render: current graph or requested branch
    Render-->>UI: tree view, navigable past 10 generations
    User->>Render: pan, zoom, expand, collapse`,

  sequenceInterpretation: "Nothing reaches storage or the screen until the Genealogy Engine has validated it — that ordering is what keeps a corrupted tree from ever getting saved or shown.",

  ganttMermaid:
`gantt
    title Build Order - relative sequence, not calendar dates
    dateFormat  YYYY-MM-DD
    axisFormat  Day %j
    section Phase 1 - Foundation
    Genealogy Engine and Local Store   :a1, 2024-01-01, 3d
    section Phase 2 - Builder
    Tree Builder UI                    :a2, after a1, 2d
    section Phase 3 - Make or break
    Tree Rendering Engine at depth     :crit, a3, after a2, 4d
    section Phase 4 - Hardening
    Validation and edge cases          :a4, after a3, 2d`,

  ganttInterpretation: "The bar lengths show relative order and effort, not calendar dates — there is no real deadline data in the idea, so none is invented here. Phase 3 is marked critical because it's the phase that proves the one requirement the idea actually named.",

  dataFlowSteps: [
    { n: 1, text: "The app opens; the UI asks the Local Persistent Store whether a tree already exists on this device.", touches: ["ui", "store"] },
    { n: 2, text: "If one does, the Store hands the saved graph to the Genealogy Engine, which loads it into memory.", touches: ["store", "engine"] },
    { n: 3, text: "The person adds someone new, or links two existing people as parent/child or spouses, through the UI.", touches: ["ui"] },
    { n: 4, text: "The UI passes that record to the Genealogy Engine, which checks it's structurally sound — no loops, no duplicate people — and recalculates generation numbers.", touches: ["ui", "engine"] },
    { n: 5, text: "The Genealogy Engine writes the validated change to the Local Persistent Store, so it survives closing the app.", touches: ["engine", "store"] },
    { n: 6, text: "The Tree Rendering Engine asks the Genealogy Engine for the current graph — or just the branch in view — and lays it out so every generation, including the 10th and beyond, stays reachable.", touches: ["engine", "render"] },
    { n: 7, text: "The person pans, zooms, or expands/collapses a branch; the Rendering Engine re-queries only the relevant slice, so performance doesn't degrade as the tree gets deeper.", touches: ["ui", "render"] }
  ],

  dataFlowNote: "There's no AI model in this architecture, so the usual “colour-coded by which steps the model touches” treatment doesn't apply here — the ribbon below is colour-coded by which component each step touches instead.",

  buildPhases: [
    {
      n: 1,
      name: "Genealogy Engine + Local Store",
      focus: "The relationship graph and its persistence, with no hardcoded generation limit.",
      proves: "The data underneath can actually hold 10+ generations and survive an app restart — before any screen exists to look at it.",
      critical: false
    },
    {
      n: 2,
      name: "Tree Builder UI",
      focus: "Forms and controls to add people and define parent/child/spouse relationships.",
      proves: "Someone with no technical background can build a tree by hand, not just by loading test data.",
      critical: false
    },
    {
      n: 3,
      name: "Tree Rendering Engine at depth",
      focus: "Layout, pan, zoom, and collapse for a real 10+ generation tree.",
      proves: "The one requirement the idea actually named holds up on screen, not just in storage. Most likely phase to fail quietly if rushed.",
      critical: true
    },
    {
      n: 4,
      name: "Validation & edge cases",
      focus: "The Genealogy Engine catching bad input — cycles, duplicate people, orphaned branches — before it corrupts hours of someone's work.",
      proves: "The app is safe to keep using, not just usable once.",
      critical: false
    }
  ],

  assumptions: [
    {
      text: "Single person, single device — no login, no sharing, no sync.",
      impact: "If a family needs to co-edit one shared tree, this requires adding a backend, authentication, and a shared cloud database — a materially different system."
    },
    {
      text: "“10 generations deep at a minimum” means no fixed ceiling, not “exactly 10 and no more.”",
      impact: "If the real requirement is “cap at 10,” the Genealogy Engine could be simpler — a fixed-size structure instead of an open-ended graph."
    },
    {
      text: "“Family tree” includes spouses, not just a straight ancestor line.",
      impact: "If only direct lineage matters (no marriages), the relationship model simplifies to a single parent-child chain."
    },
    {
      text: "“App” means a browser-based app, since the idea doesn't name a platform.",
      impact: "If a native desktop or mobile app is intended instead, the UI and rendering technology change, but the Genealogy Engine and data model stay the same."
    }
  ],

  openQuestion: {
    question: "Does more than one family member need to see or edit this tree?",
    branchA: {
      label: "No — single user, single device",
      detail: "The design above as-is: local UI, local engine, local storage. No backend, no login."
    },
    branchB: {
      label: "Yes — shared / multi-device",
      detail: "Requires adding an authentication layer, a backend API, and moving the Local Persistent Store to a shared cloud database so multiple people's edits merge into one tree — a materially bigger system."
    }
  },

  // Covered = what this design already provides. Deferred = named honestly, not built.
  coverage: [
    { area: "Single-person tree creation", status: "covered", note: "The Tree Builder UI." },
    { area: "Arbitrary-depth relationship storage", status: "covered", note: "The Genealogy Engine's open-ended graph." },
    { area: "Deep-tree navigation (10+ generations)", status: "covered", note: "The Tree Rendering Engine's pan/zoom/collapse." },
    { area: "Persistence across sessions", status: "covered", note: "The Local Persistent Store." },
    { area: "Multi-user collaboration", status: "deferred", note: "One person, one tree, one device." },
    { area: "GEDCOM import / export", status: "deferred", note: "The standard genealogy file format — not mentioned in the idea." },
    { area: "Matching against external historical records", status: "deferred", note: "Census data, archives, other genealogy sites." },
    { area: "Concurrent-edit conflict resolution", status: "deferred", note: "Follows directly from the single-user assumption." },
    { area: "Mobile-native offline sync", status: "deferred", note: "Beyond the device's own local storage." }
  ],

  // AI Ask panel config
  ask: {
    models: [
      { id: "claude-opus-5", label: "Claude Opus 5 (default)", supportsEffort: true },
      { id: "claude-sonnet-5", label: "Claude Sonnet 5", supportsEffort: true },
      { id: "claude-haiku-4-5", label: "Claude Haiku 4.5", supportsEffort: false }
    ],
    apiUrl: "https://api.anthropic.com/v1/messages",
    anthropicVersion: "2023-06-01"
  }
};
