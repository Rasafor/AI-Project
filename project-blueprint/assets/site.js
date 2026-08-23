/* Family Tree App knowledge base — shared rendering, nav, search, diagrams, illustrations, Ask panel.
   Classic script, no ES modules (file:// blocks module fetches). Reads the bare `BLUEPRINT`
   identifier from assets/blueprint.js, loaded just before this file on every page. */

(function () {
  'use strict';

  // ---------------------------------------------------------------------
  // Utilities
  // ---------------------------------------------------------------------

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  var escapeXml = escapeHtml;

  function truncate(s, n) {
    s = String(s);
    return s.length > n ? s.slice(0, n - 1) + '…' : s;
  }

  function currentSectionId() {
    return document.body.getAttribute('data-section') || '';
  }

  function findSection(id) {
    return BLUEPRINT.sections.filter(function (s) { return s.id === id; })[0];
  }

  function sectionPage(id) {
    var s = findSection(id);
    return s ? s.page : 'index.html';
  }

  // ---------------------------------------------------------------------
  // Theme
  // ---------------------------------------------------------------------

  function initTheme() {
    var KEY = 'ft_theme';
    var saved = localStorage.getItem(KEY);
    if (saved === 'dark' || saved === 'light') {
      document.documentElement.setAttribute('data-theme', saved);
    }
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var current = document.documentElement.getAttribute('data-theme') ||
        (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      var next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem(KEY, next);
      runMermaid();
      initCharts();
    });
  }

  // ---------------------------------------------------------------------
  // Chrome: breadcrumbs, prev/next, scroll progress, back-to-top, print
  // ---------------------------------------------------------------------

  function initBreadcrumbs() {
    var el = document.getElementById('breadcrumbs');
    if (!el) return;
    var sec = findSection(currentSectionId());
    if (!sec) { el.style.display = 'none'; return; }
    el.innerHTML = '<a href="index.html">Command Center</a>' +
      '<span class="sep">/</span><span class="current">' + escapeHtml(sec.title) + '</span>';
  }

  function initFooterNav() {
    var el = document.getElementById('footer-nav');
    if (!el) return;
    var sections = BLUEPRINT.sections;
    var idx = -1;
    for (var i = 0; i < sections.length; i++) { if (sections[i].id === currentSectionId()) { idx = i; break; } }
    if (idx === -1) return;
    var prev = sections[idx - 1];
    var next = sections[idx + 1];
    var html = '';
    html += prev
      ? '<a class="prev" href="' + prev.page + '"><div class="dir">&larr; Previous</div>' + escapeHtml(prev.title) + '</a>'
      : '<a class="prev" href="index.html"><div class="dir">&larr; Back</div>Command Center</a>';
    html += next
      ? '<a class="next" href="' + next.page + '"><div class="dir">Next &rarr;</div>' + escapeHtml(next.title) + '</a>'
      : '<a class="next" href="index.html"><div class="dir">Done &rarr;</div>Back to Command Center</a>';
    el.innerHTML = html;
  }

  function initScrollFx() {
    var bar = document.getElementById('scroll-progress');
    var backBtn = document.getElementById('back-to-top');
    function onScroll() {
      var h = document.documentElement;
      var scrolled = h.scrollTop;
      var height = h.scrollHeight - h.clientHeight;
      var pct = height > 0 ? (scrolled / height) * 100 : 0;
      if (bar) bar.style.width = pct + '%';
      if (backBtn) backBtn.classList.toggle('show', scrolled > 400);
    }
    document.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    if (backBtn) {
      backBtn.addEventListener('click', function () {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    }
  }

  function initPrint() {
    var btn = document.getElementById('print-btn');
    if (btn) btn.addEventListener('click', function () { window.print(); });
  }

  // ---------------------------------------------------------------------
  // Counts (computed once, used by tiles and kv-stats — never hardcoded twice)
  // ---------------------------------------------------------------------

  function computeCount(id) {
    switch (id) {
      case 'idea': return BLUEPRINT.idea.split(/\s+/).length + ' words';
      case 'components': return BLUEPRINT.components.length + ' components';
      case 'diagram': return BLUEPRINT.graph.nodes.length + ' nodes, ' + BLUEPRINT.graph.edges.length + ' connections';
      case 'dataflow': return BLUEPRINT.dataFlowSteps.length + ' steps';
      case 'buildorder': return BLUEPRINT.buildPhases.length + ' phases';
      case 'assumptions': return BLUEPRINT.assumptions.length + ' assumptions';
      case 'coverage': return BLUEPRINT.coverage.filter(function (c) { return c.status === 'deferred'; }).length + ' deferred';
      default: return '';
    }
  }

  // ---------------------------------------------------------------------
  // Search index — built once over every BLUEPRINT field
  // ---------------------------------------------------------------------

  var STOPWORDS = ['the', 'a', 'an', 'of', 'to', 'and', 'or', 'in', 'on', 'for', 'is', 'are',
    'it', 'this', 'that', 'with', 'as', 'by', 'at', 'be', 'from', 'how', 'what', 'does', 'do', 'so'];

  function tokenize(s) {
    return (String(s).toLowerCase().match(/[a-z0-9']+/g) || []);
  }

  function stem(w) {
    return w.length > 4 ? w.replace(/(ing|edly|ations|ation|ed|es|s)$/, '') : w;
  }

  var SEARCH_INDEX = [];

  function buildSearchIndex() {
    var idx = [];
    function push(sectionId, title, text) {
      if (!text) return;
      var section = findSection(sectionId);
      if (!section) return;
      idx.push({
        sectionId: sectionId,
        page: section.page,
        sectionTitle: section.title,
        title: title,
        text: text,
        lower: String(text).toLowerCase(),
        tokens: tokenize(text),
        titleTokens: tokenize(title)
      });
    }

    push('idea', 'The Idea', BLUEPRINT.idea);
    push('idea', 'Idea Framing', BLUEPRINT.ideaFraming);

    BLUEPRINT.components.forEach(function (c) {
      push('components', c.name, c.sentence + ' ' + c.why);
    });

    push('diagram', 'Architecture Diagram', BLUEPRINT.flowchartInterpretation);
    push('diagram', 'Data Flow Diagram', BLUEPRINT.sequenceInterpretation);

    BLUEPRINT.dataFlowSteps.forEach(function (s) {
      push('dataflow', 'Step ' + s.n, s.text);
    });

    BLUEPRINT.buildPhases.forEach(function (p) {
      push('buildorder', 'Phase ' + p.n + ': ' + p.name, p.focus + ' ' + p.proves);
    });

    BLUEPRINT.assumptions.forEach(function (a, i) {
      push('assumptions', 'Assumption ' + (i + 1), a.text + ' ' + a.impact);
    });
    push('assumptions', 'Open Question', BLUEPRINT.openQuestion.question + ' ' +
      BLUEPRINT.openQuestion.branchA.label + ': ' + BLUEPRINT.openQuestion.branchA.detail + ' ' +
      BLUEPRINT.openQuestion.branchB.label + ': ' + BLUEPRINT.openQuestion.branchB.detail);

    BLUEPRINT.coverage.forEach(function (c) {
      push('coverage', c.area, c.note + ' (' + c.status + ')');
    });

    SEARCH_INDEX = idx;
  }

  function scoreEntry(queryTokens, entry) {
    var score = 0;
    queryTokens.forEach(function (qt) {
      if (STOPWORDS.indexOf(qt) !== -1) return;
      var hits = 0;
      entry.tokens.forEach(function (t) { if (t === qt) hits++; });
      if (hits === 0) {
        var qs = stem(qt);
        entry.tokens.forEach(function (t) { if (stem(t) === qs) hits++; });
      }
      score += hits;
      if (entry.titleTokens.indexOf(qt) !== -1) score += 3;
    });
    if (queryTokens.length > 1) {
      var phrase = queryTokens.filter(function (t) { return STOPWORDS.indexOf(t) === -1; }).join(' ');
      if (phrase && entry.lower.indexOf(phrase) !== -1) score += 5;
    }
    return score;
  }

  function highlight(text, tokens) {
    var escaped = escapeHtml(text);
    var valid = tokens.filter(function (t) { return t.length > 1 && STOPWORDS.indexOf(t) === -1; });
    if (!valid.length) return escaped;
    var pattern = valid.map(function (t) { return t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }).join('|');
    var re = new RegExp('(' + pattern + ')', 'ig');
    return escaped.replace(re, '<mark>$1</mark>');
  }

  function snippetFor(entry, queryTokens) {
    var text = entry.text;
    var idx = -1;
    for (var i = 0; i < queryTokens.length && idx === -1; i++) {
      idx = entry.lower.indexOf(queryTokens[i]);
    }
    var start = idx === -1 ? 0 : Math.max(0, idx - 40);
    var snippet = text.slice(start, start + 140);
    if (start > 0) snippet = '…' + snippet;
    if (start + 140 < text.length) snippet += '…';
    return highlight(snippet, queryTokens);
  }

  function runSearch(query) {
    var qTokens = tokenize(query);
    if (!qTokens.length) return [];
    var results = SEARCH_INDEX.map(function (entry) {
      return { entry: entry, score: scoreEntry(qTokens, entry) };
    }).filter(function (r) { return r.score > 0; });
    results.sort(function (a, b) { return b.score - a.score; });
    return results.slice(0, 8).map(function (r) {
      return {
        page: r.entry.page,
        sectionTitle: r.entry.sectionTitle,
        title: r.entry.title,
        snippet: snippetFor(r.entry, qTokens)
      };
    });
  }

  function filterCurrentPage(query) {
    var items = document.querySelectorAll('[data-search-text]');
    if (!items.length) return;
    var q = query.trim().toLowerCase();
    items.forEach(function (elm) {
      if (!q) { elm.classList.remove('search-hidden'); return; }
      var hay = elm.getAttribute('data-search-text').toLowerCase();
      elm.classList.toggle('search-hidden', hay.indexOf(q) === -1);
    });
  }

  function initSearch() {
    buildSearchIndex();
    var input = document.getElementById('site-search');
    var results = document.getElementById('search-results');
    if (!input || !results) return;
    var currentPage = sectionPage(currentSectionId());

    input.addEventListener('input', function () {
      var q = input.value.trim();
      filterCurrentPage(q);
      if (!q) { results.classList.remove('open'); results.innerHTML = ''; return; }
      var matches = runSearch(q);
      var other = matches.filter(function (m) { return m.page !== currentPage; });
      if (!other.length) {
        results.innerHTML = '<div class="search-empty">No matches elsewhere in the blueprint.</div>';
      } else {
        results.innerHTML = other.map(function (m) {
          return '<a href="' + m.page + '"><div class="sr-section">' + escapeHtml(m.sectionTitle) +
            ' &middot; ' + escapeHtml(m.title) + '</div><div class="sr-snippet">' + m.snippet + '</div></a>';
        }).join('');
      }
      results.classList.add('open');
    });

    document.addEventListener('click', function (e) {
      if (!results.contains(e.target) && e.target !== input) results.classList.remove('open');
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { results.classList.remove('open'); input.blur(); }
    });
  }

  // ---------------------------------------------------------------------
  // Mermaid diagrams
  // ---------------------------------------------------------------------

  function mermaidThemeName() {
    var t = document.documentElement.getAttribute('data-theme');
    if (t) return t === 'dark' ? 'dark' : 'default';
    return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'default';
  }

  function runMermaid() {
    if (typeof mermaid === 'undefined') return;
    try {
      mermaid.initialize({
        startOnLoad: false,
        theme: mermaidThemeName(),
        securityLevel: 'loose',
        fontFamily: 'Segoe UI, system-ui, sans-serif'
      });
      var nodes = document.querySelectorAll('.mermaid[data-mermaid-source]');
      nodes.forEach(function (elm) {
        var key = elm.getAttribute('data-mermaid-source');
        elm.removeAttribute('data-processed');
        elm.textContent = BLUEPRINT[key] || '';
      });
      if (!nodes.length) return;
      if (typeof mermaid.run === 'function') {
        mermaid.run({ querySelector: '.mermaid[data-mermaid-source]' });
      } else if (typeof mermaid.init === 'function') {
        mermaid.init(undefined, '.mermaid[data-mermaid-source]');
      }
    } catch (e) {
      console.error('Mermaid render failed', e);
    }
  }

  function initDiagrams() {
    document.querySelectorAll('[data-interp]').forEach(function (elm) {
      var key = elm.getAttribute('data-interp');
      if (BLUEPRINT[key]) elm.textContent = BLUEPRINT[key];
    });
    runMermaid();
  }

  // ---------------------------------------------------------------------
  // Chart.js — only where there's real, counted data (coverage covered/deferred)
  // ---------------------------------------------------------------------

  var _coverageChart = null;

  function initCharts() {
    var canvas = document.getElementById('coverage-chart');
    if (!canvas || typeof Chart === 'undefined') return;
    var covered = BLUEPRINT.coverage.filter(function (c) { return c.status === 'covered'; }).length;
    var deferred = BLUEPRINT.coverage.length - covered;
    var styles = getComputedStyle(document.documentElement);
    if (_coverageChart) { _coverageChart.destroy(); }
    _coverageChart = new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels: ['Covered (' + covered + ')', 'Deferred (' + deferred + ')'],
        datasets: [{
          data: [covered, deferred],
          backgroundColor: [styles.getPropertyValue('--good').trim(), styles.getPropertyValue('--warn').trim()],
          borderWidth: 0
        }]
      },
      options: {
        cutout: '62%',
        plugins: {
          legend: { position: 'bottom', labels: { color: styles.getPropertyValue('--text').trim() } }
        }
      }
    });
  }

  // ---------------------------------------------------------------------
  // Inline SVG illustrations — generated from BLUEPRINT, theme-aware via CSS vars
  // ---------------------------------------------------------------------

  function svgWrap(viewBox, inner) {
    return '<svg viewBox="' + viewBox + '" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">' + inner + '</svg>';
  }

  function svgLines(text, maxChars) {
    var words = String(text).split(' ');
    var lines = [];
    var cur = '';
    words.forEach(function (w) {
      if ((cur + ' ' + w).trim().length > maxChars) {
        if (cur) lines.push(cur.trim());
        cur = w;
      } else {
        cur = (cur + ' ' + w).trim();
      }
    });
    if (cur) lines.push(cur);
    return lines;
  }

  function svgText(x, y, text, maxChars, fontSize, styleExtra) {
    var lines = svgLines(text, maxChars);
    var out = '<text x="' + x + '" y="' + y + '" text-anchor="middle" font-size="' + fontSize +
      '" style="fill:var(--text);' + (styleExtra || '') + '">';
    lines.forEach(function (line, i) {
      out += '<tspan x="' + x + '" dy="' + (i === 0 ? 0 : fontSize + 2) + '">' + escapeXml(line) + '</tspan>';
    });
    out += '</text>';
    return out;
  }

  function ideaPipelineSVG() {
    var defs = '<defs><marker id="arrowIdea" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" style="fill:var(--muted)"/></marker></defs>';
    var out = '';
    out += '<rect x="10" y="60" width="120" height="80" rx="8" style="fill:var(--card);stroke:var(--border)"/>';
    out += svgText(70, 90, 'One-paragraph idea', 16, 10, '');
    out += svgText(70, 110, '10 generations deep, minimum', 18, 8.5, 'fill:var(--muted)');
    out += '<path d="M130,100 L172,100" marker-end="url(#arrowIdea)" style="fill:none;stroke:var(--muted);stroke-width:1.5"/>';
    out += '<rect x="172" y="55" width="140" height="90" rx="8" style="fill:var(--info-bg);stroke:var(--info)"/>';
    out += svgText(242, 85, 'UI, Genealogy Engine, Renderer, Store', 20, 8.5, 'fill:var(--text)');
    out += svgText(242, 115, '4 components, one loop', 20, 8.5, 'fill:var(--muted)');
    out += '<path d="M312,100 L354,100" marker-end="url(#arrowIdea)" style="fill:none;stroke:var(--muted);stroke-width:1.5"/>';
    out += '<rect x="354" y="55" width="126" height="90" rx="8" style="fill:var(--good-bg);stroke:var(--good)"/>';
    out += svgText(417, 88, 'A tree, 10+ generations deep', 16, 9, 'fill:var(--good);font-weight:700');
    out += svgText(417, 118, 'pannable and zoomable', 18, 8, 'fill:var(--muted)');
    return svgWrap('0 0 496 200', defs + out);
  }

  function layerDiagramSVG() {
    var layers = ['interface', 'logic', 'data'];
    var layerLabel = { interface: 'Interface', logic: 'Logic', data: 'Data' };
    var rowY = { interface: 26, logic: 106, data: 186 };
    var out = '';
    layers.forEach(function (layer) {
      var comps = BLUEPRINT.components.filter(function (c) { return c.layer === layer; });
      out += '<text x="4" y="' + (rowY[layer] - 8) + '" font-size="11" style="fill:var(--muted)">' + layerLabel[layer] + '</text>';
      var x = 4;
      comps.forEach(function (c) {
        var w = 150;
        out += '<rect x="' + x + '" y="' + rowY[layer] + '" width="' + w + '" height="48" rx="8" style="fill:var(--card);stroke:var(--border)"/>';
        out += svgText(x + w / 2, rowY[layer] + 24, c.name, 20, 10, '');
        if (c.guarantor) {
          out += '<text x="' + (x + w - 8) + '" y="' + (rowY[layer] + 16) + '" text-anchor="end" font-size="11" style="fill:var(--warn)">★</text>';
        }
        x += w + 14;
      });
    });
    return svgWrap('0 0 486 240', out);
  }

  function nodeGraphSVG() {
    var pos = {
      user: { x: 220, y: 22 },
      ui: { x: 220, y: 84 },
      engine: { x: 220, y: 146 },
      store: { x: 82, y: 208 },
      render: { x: 358, y: 208 }
    };
    var shapes = { user: 'stadium', ui: 'rect', engine: 'rect', render: 'rect', store: 'cyl' };
    var defs = '<defs><marker id="arrowNG" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" style="fill:var(--accent)"/></marker></defs>';
    var edges = '';
    BLUEPRINT.graph.edges.forEach(function (e, i) {
      var a = pos[e.from], b = pos[e.to];
      var dx = (b.x - a.x) * 0.15 * (i % 2 === 0 ? 1 : -1);
      var dy = (b.y - a.y) * 0.15 * (i % 2 === 0 ? -1 : 1);
      var midx = (a.x + b.x) / 2 + dx;
      var midy = (a.y + b.y) / 2 + dy;
      edges += '<path d="M' + a.x + ',' + a.y + ' Q' + midx + ',' + midy + ' ' + b.x + ',' + b.y +
        '" style="fill:none;stroke:var(--muted);stroke-width:1.4" marker-end="url(#arrowNG)" />';
    });
    var nodes = '';
    BLUEPRINT.graph.nodes.forEach(function (n) {
      var p = pos[n.id];
      var label = truncate(n.label, 20);
      if (shapes[n.id] === 'cyl') {
        nodes += '<g><ellipse cx="' + p.x + '" cy="' + (p.y - 13) + '" rx="48" ry="9" style="fill:var(--card);stroke:var(--border)"/>' +
          '<rect x="' + (p.x - 48) + '" y="' + (p.y - 13) + '" width="96" height="26" style="fill:var(--card);stroke:var(--border)"/>' +
          '<ellipse cx="' + p.x + '" cy="' + (p.y + 13) + '" rx="48" ry="9" style="fill:var(--card);stroke:var(--border)"/>' +
          svgText(p.x, p.y + 4, label, 18, 9.5, '') + '</g>';
      } else if (shapes[n.id] === 'stadium') {
        nodes += '<g><rect x="' + (p.x - 62) + '" y="' + (p.y - 14) + '" width="124" height="28" rx="14" style="fill:var(--accent)"/>' +
          svgText(p.x, p.y + 4, label, 20, 9.5, 'fill:var(--accent-ink);font-weight:700') + '</g>';
      } else {
        nodes += '<g><rect x="' + (p.x - 60) + '" y="' + (p.y - 17) + '" width="120" height="34" rx="6" style="fill:var(--card);stroke:var(--border)"/>' +
          svgText(p.x, p.y + 4, label, 18, 9.5, '') + '</g>';
      }
    });
    return svgWrap('0 0 440 248', defs + edges + nodes);
  }

  function flowRibbonSVG() {
    var colorFor = { ui: 'var(--accent)', engine: 'var(--info)', render: 'var(--warn)', store: 'var(--neutral)' };
    var steps = BLUEPRINT.dataFlowSteps;
    var perRow = 4;
    var out = '';
    steps.forEach(function (s, i) {
      var row = Math.floor(i / perRow);
      var col = i % perRow;
      var cx = 50 + col * 100;
      var cy = 40 + row * 90;
      var color = colorFor[s.touches[0]] || 'var(--accent)';
      out += '<circle cx="' + cx + '" cy="' + cy + '" r="21" style="fill:' + color + '"/>';
      out += '<text x="' + cx + '" y="' + (cy + 4) + '" text-anchor="middle" font-size="12" style="fill:var(--accent-ink);font-weight:700">' + s.n + '</text>';
      if (col < perRow - 1 && i < steps.length - 1) {
        out += '<line x1="' + (cx + 23) + '" y1="' + cy + '" x2="' + (cx + 77) + '" y2="' + cy + '" style="stroke:var(--border);stroke-width:2"/>';
      }
    });
    var rows = Math.ceil(steps.length / perRow);
    return svgWrap('0 0 420 ' + (36 + rows * 90), out);
  }

  function phaseBarsSVG() {
    var phases = BLUEPRINT.buildPhases;
    var relDays = [3, 2, 4, 2];
    var maxDay = Math.max.apply(null, relDays);
    var out = '';
    phases.forEach(function (p, i) {
      var y = 22 + i * 54;
      var w = (relDays[i] / maxDay) * 320;
      var color = p.critical ? 'var(--warn)' : 'var(--accent)';
      out += '<text x="0" y="' + (y - 6) + '" font-size="11" style="fill:var(--text)">' + (i + 1) + '. ' +
        escapeXml(p.name) + (p.critical ? '  ★' : '') + '</text>';
      out += '<rect x="0" y="' + y + '" width="' + w + '" height="22" rx="5" style="fill:' + color + '"/>';
    });
    return svgWrap('0 0 360 ' + (22 + phases.length * 54), out);
  }

  function coverageGridSVG() {
    var items = BLUEPRINT.coverage;
    var cols = 3;
    var cellW = 128, cellH = 56, gap = 8;
    var out = '';
    items.forEach(function (it, i) {
      var col = i % cols, row = Math.floor(i / cols);
      var x = col * (cellW + gap), y = row * (cellH + gap);
      var color = it.status === 'covered' ? 'var(--good)' : 'var(--warn)';
      var bg = it.status === 'covered' ? 'var(--good-bg)' : 'var(--warn-bg)';
      out += '<rect x="' + x + '" y="' + y + '" width="' + cellW + '" height="' + cellH + '" rx="8" style="fill:' + bg + ';stroke:' + color + '"/>';
      out += svgText(x + cellW / 2, y + 24, truncate(it.area, 24), 20, 9.5, '');
      out += '<text x="' + (x + cellW / 2) + '" y="' + (y + 44) + '" text-anchor="middle" font-size="8.5" style="fill:' + color + ';font-weight:700">' + it.status.toUpperCase() + '</text>';
    });
    var rows = Math.ceil(items.length / cols);
    return svgWrap('0 0 ' + (cols * (cellW + gap)) + ' ' + (rows * (cellH + gap)), out);
  }

  function forkBranchesSVG() {
    var q = BLUEPRINT.openQuestion;
    var out = '';
    out += '<rect x="70" y="8" width="260" height="46" rx="8" style="fill:var(--info-bg);stroke:var(--info)"/>';
    out += svgText(200, 28, q.question, 36, 9.5, '');
    out += '<path d="M160,54 L92,98" style="fill:none;stroke:var(--muted);stroke-width:1.5"/>';
    out += '<path d="M240,54 L308,98" style="fill:none;stroke:var(--muted);stroke-width:1.5"/>';
    out += '<rect x="8" y="98" width="184" height="98" rx="8" style="fill:var(--good-bg);stroke:var(--good)"/>';
    out += svgText(100, 118, q.branchA.label, 24, 10, 'fill:var(--good);font-weight:700');
    out += svgText(100, 138, q.branchA.detail, 30, 8.2, '');
    out += '<rect x="208" y="98" width="184" height="98" rx="8" style="fill:var(--warn-bg);stroke:var(--warn)"/>';
    out += svgText(300, 118, q.branchB.label, 22, 10, 'fill:var(--warn);font-weight:700');
    out += svgText(300, 138, q.branchB.detail, 30, 8.2, '');
    return svgWrap('0 0 400 205', out);
  }

  var ILLUSTRATIONS = {
    'idea-pipeline': ideaPipelineSVG,
    'layer-diagram': layerDiagramSVG,
    'node-graph': nodeGraphSVG,
    'flow-ribbon': flowRibbonSVG,
    'phase-bars': phaseBarsSVG,
    'fork-branches': forkBranchesSVG,
    'coverage-grid': coverageGridSVG
  };

  function renderIllustration(key) {
    var fn = ILLUSTRATIONS[key];
    return fn ? fn() : '';
  }

  function initIllustrations() {
    document.querySelectorAll('[data-illustration]').forEach(function (elm) {
      elm.innerHTML = renderIllustration(elm.getAttribute('data-illustration'));
    });
  }

  // ---------------------------------------------------------------------
  // Per-page data-driven tables — every one reads BLUEPRINT, nothing hardcoded
  // ---------------------------------------------------------------------

  function initComponentsTable() {
    var mount = document.getElementById('components-table');
    if (!mount) return;
    mount.innerHTML = BLUEPRINT.components.map(function (c) {
      var searchText = c.name + ' ' + c.sentence + ' ' + c.why;
      return '<tr data-search-text="' + escapeHtml(searchText) + '">' +
        '<td><strong>' + escapeHtml(c.name) + '</strong>' +
        (c.guarantor ? '<div><span class="badge warn">depth guarantor</span></div>' : '') + '</td>' +
        '<td>' + escapeHtml(c.sentence) + (c.guarantorRole ? '<div class="muted" style="margin-top:0.3rem;font-size:0.82rem">' + escapeHtml(c.guarantorRole) + '</div>' : '') + '</td>' +
        '<td>' + escapeHtml(c.why) + '</td>' +
        '</tr>';
    }).join('');
  }

  function initDataFlowList() {
    var mount = document.getElementById('dataflow-steps');
    if (!mount) return;
    mount.innerHTML = BLUEPRINT.dataFlowSteps.map(function (s) {
      return '<li data-search-text="' + escapeHtml(s.text) + '"><span class="step-num">' + s.n + '</span><span>' + escapeHtml(s.text) + '</span></li>';
    }).join('');
    var note = document.getElementById('dataflow-note');
    if (note) note.textContent = BLUEPRINT.dataFlowNote;
  }

  function initBuildPhases() {
    var mount = document.getElementById('build-phases-table');
    if (!mount) return;
    mount.innerHTML = BLUEPRINT.buildPhases.map(function (p) {
      var searchText = p.name + ' ' + p.focus + ' ' + p.proves;
      return '<tr data-search-text="' + escapeHtml(searchText) + '">' +
        '<td><strong>Phase ' + p.n + '</strong><br>' + escapeHtml(p.name) +
        (p.critical ? '<div style="margin-top:0.3rem"><span class="badge warn">make or break</span></div>' : '') + '</td>' +
        '<td>' + escapeHtml(p.focus) + '</td>' +
        '<td>' + escapeHtml(p.proves) + '</td>' +
        '</tr>';
    }).join('');
  }

  function initAssumptions() {
    var mount = document.getElementById('assumptions-table');
    if (mount) {
      mount.innerHTML = BLUEPRINT.assumptions.map(function (a, i) {
        var searchText = a.text + ' ' + a.impact;
        return '<tr data-search-text="' + escapeHtml(searchText) + '">' +
          '<td><strong>' + (i + 1) + '.</strong> ' + escapeHtml(a.text) + '</td>' +
          '<td>' + escapeHtml(a.impact) + '</td>' +
          '</tr>';
      }).join('');
    }
    var q = document.getElementById('open-question');
    if (q) {
      var oq = BLUEPRINT.openQuestion;
      q.setAttribute('data-search-text', oq.question + ' ' + oq.branchA.detail + ' ' + oq.branchB.detail);
      q.innerHTML =
        '<h3 style="margin-top:0">' + escapeHtml(oq.question) + '</h3>' +
        '<div class="kv-list">' +
        '<div class="kv-item"><div class="kv-label">' + escapeHtml(oq.branchA.label) + '</div><div style="margin-top:0.3rem;font-size:0.9rem">' + escapeHtml(oq.branchA.detail) + '</div></div>' +
        '<div class="kv-item"><div class="kv-label">' + escapeHtml(oq.branchB.label) + '</div><div style="margin-top:0.3rem;font-size:0.9rem">' + escapeHtml(oq.branchB.detail) + '</div></div>' +
        '</div>';
    }
  }

  function initCoverage() {
    var mount = document.getElementById('coverage-table');
    if (!mount) return;
    mount.innerHTML = BLUEPRINT.coverage.map(function (c) {
      var badge = c.status === 'covered' ? 'good' : 'warn';
      var searchText = c.area + ' ' + c.note + ' ' + c.status;
      return '<tr data-search-text="' + escapeHtml(searchText) + '">' +
        '<td>' + escapeHtml(c.area) + '</td>' +
        '<td><span class="badge ' + badge + '">' + c.status + '</span></td>' +
        '<td>' + escapeHtml(c.note) + '</td>' +
        '</tr>';
    }).join('');
  }

  // ---------------------------------------------------------------------
  // Command Center tiles
  // ---------------------------------------------------------------------

  function initCommandCenter() {
    var grid = document.getElementById('tile-grid');
    if (!grid) return;
    grid.innerHTML = BLUEPRINT.sections.map(function (s) {
      return '<a class="tile" href="' + s.page + '">' +
        '<div class="tile-preview">' + renderIllustration(s.illustration) + '</div>' +
        '<h3>' + escapeHtml(s.title) + '</h3>' +
        '<p>' + escapeHtml(s.blurb) + '</p>' +
        '<span class="tile-count">' + escapeHtml(computeCount(s.id)) + '</span>' +
        '</a>';
    }).join('');
  }

  // ---------------------------------------------------------------------
  // Fullscreen expand + zoom for every diagram/chart/illustration
  // ---------------------------------------------------------------------

  function initModal() {
    var backdrop = document.getElementById('diagram-modal');
    if (!backdrop) return null;
    var viewport = backdrop.querySelector('.modal-viewport');
    var inner = backdrop.querySelector('.modal-zoom-inner');
    var titleEl = backdrop.querySelector('.modal-title');
    var scale = 1, panX = 0, panY = 0, dragging = false, startX, startY;

    function applyTransform() {
      inner.style.transform = 'translate(' + panX + 'px,' + panY + 'px) scale(' + scale + ')';
    }
    function open(sourceEl, title, alreadyDetached) {
      inner.innerHTML = '';
      var node = alreadyDetached ? sourceEl : sourceEl.cloneNode(true);
      if (node.removeAttribute) node.removeAttribute('id');
      inner.appendChild(node);
      scale = 1; panX = 0; panY = 0;
      applyTransform();
      if (titleEl) titleEl.textContent = title || '';
      backdrop.classList.add('open');
      document.addEventListener('keydown', onKey);
    }
    function close() {
      backdrop.classList.remove('open');
      document.removeEventListener('keydown', onKey);
    }
    function onKey(e) { if (e.key === 'Escape') close(); }

    var zoomInBtn = backdrop.querySelector('.zoom-in');
    var zoomOutBtn = backdrop.querySelector('.zoom-out');
    var zoomResetBtn = backdrop.querySelector('.zoom-reset');
    var closeBtn = backdrop.querySelector('.modal-close');
    if (zoomInBtn) zoomInBtn.addEventListener('click', function () { scale = Math.min(scale * 1.25, 6); applyTransform(); });
    if (zoomOutBtn) zoomOutBtn.addEventListener('click', function () { scale = Math.max(scale / 1.25, 0.2); applyTransform(); });
    if (zoomResetBtn) zoomResetBtn.addEventListener('click', function () { scale = 1; panX = 0; panY = 0; applyTransform(); });
    if (closeBtn) closeBtn.addEventListener('click', close);
    backdrop.addEventListener('click', function (e) { if (e.target === backdrop) close(); });

    viewport.addEventListener('mousedown', function (e) {
      dragging = true; startX = e.clientX - panX; startY = e.clientY - panY;
      viewport.classList.add('grabbing');
    });
    window.addEventListener('mouseup', function () { dragging = false; viewport.classList.remove('grabbing'); });
    window.addEventListener('mousemove', function (e) {
      if (!dragging) return;
      panX = e.clientX - startX; panY = e.clientY - startY;
      applyTransform();
    });
    viewport.addEventListener('wheel', function (e) {
      e.preventDefault();
      var delta = e.deltaY < 0 ? 1.1 : 0.9;
      scale = Math.min(6, Math.max(0.2, scale * delta));
      applyTransform();
    }, { passive: false });

    return { open: open, close: close };
  }

  function wireExpandButtons(modal) {
    document.querySelectorAll('.expand-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var block = btn.closest('[data-figure]');
        if (!block) return;
        var target = block.querySelector('svg, canvas');
        if (!target) return;
        var title = block.getAttribute('data-figure-title') || '';
        if (target.tagName.toLowerCase() === 'canvas') {
          var img = document.createElement('img');
          img.src = target.toDataURL('image/png');
          img.style.maxWidth = 'none';
          modal.open(img, title, true);
        } else {
          modal.open(target, title, false);
        }
      });
    });
  }

  // ---------------------------------------------------------------------
  // AI Ask panel — Search mode (offline) + Claude mode (needs key)
  // ---------------------------------------------------------------------

  function computeSectionSubset(sectionId) {
    var map = {
      idea: ['idea', 'ideaFraming'],
      components: ['components'],
      diagram: ['graph', 'flowchartMermaid', 'flowchartInterpretation', 'sequenceMermaid', 'sequenceInterpretation'],
      dataflow: ['dataFlowSteps', 'dataFlowNote'],
      buildorder: ['buildPhases', 'ganttMermaid', 'ganttInterpretation'],
      assumptions: ['assumptions', 'openQuestion'],
      coverage: ['coverage']
    };
    var keys = map[sectionId] || [];
    var subset = { idea: BLUEPRINT.idea };
    keys.forEach(function (k) { subset[k] = BLUEPRINT[k]; });
    return subset;
  }

  function askClaude(question, apiKey, modelId, scope, sectionId) {
    var modelCfg = BLUEPRINT.ask.models.filter(function (m) { return m.id === modelId; })[0] || BLUEPRINT.ask.models[0];
    var subset = scope === 'section' ? computeSectionSubset(sectionId) : BLUEPRINT;
    var system = 'You are answering questions about a system architecture blueprint for a family tree app ' +
      'that must support at least 10 generations deep. Answer only using the JSON data below. If the answer ' +
      'is not covered by this data, say so plainly and suggest the reader check the "What This Design Does ' +
      'Not Cover" section. Data:\n' + JSON.stringify(subset);
    var body = { model: modelCfg.id, max_tokens: 16000, system: system, messages: [{ role: 'user', content: question }] };
    if (modelCfg.supportsEffort) body.output_config = { effort: 'low' };

    return fetch(BLUEPRINT.ask.apiUrl, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': BLUEPRINT.ask.anthropicVersion,
        'anthropic-dangerous-direct-browser-access': 'true'
      },
      body: JSON.stringify(body)
    }).catch(function () {
      throw new Error('Could not reach Anthropic (network issue). You can fall back to Search mode.');
    }).then(function (res) {
      return res.json().catch(function () {
        throw new Error('Got an unreadable response from Anthropic. You can fall back to Search mode.');
      }).then(function (data) {
        if (!res.ok) {
          var apiMsg = (data && data.error && data.error.message) || ('Request failed with status ' + res.status);
          if (res.status === 401) throw new Error('That API key was rejected: ' + apiMsg + '. You can fall back to Search mode.');
          if (res.status === 429) throw new Error('Rate limited by Anthropic: ' + apiMsg + '. Wait a moment, or fall back to Search mode.');
          throw new Error('Anthropic returned an error: ' + apiMsg + '. You can fall back to Search mode.');
        }
        if (data.stop_reason === 'refusal') {
          throw new Error('Claude declined to answer that one. Try rephrasing, or fall back to Search mode.');
        }
        var blocks = Array.isArray(data.content) ? data.content : [];
        var text = blocks.filter(function (b) { return b.type === 'text'; }).map(function (b) { return b.text; }).join('\n\n');
        if (!text) throw new Error('No answer text came back. You can fall back to Search mode.');
        return text;
      });
    });
  }

  function initAsk() {
    var mount = document.getElementById('ask-panel');
    if (!mount) return;
    var sectionId = currentSectionId();
    var isHome = !sectionId;

    mount.innerHTML =
      '<h3 style="margin-top:0">Ask the Blueprint</h3>' +
      '<div class="ask-modes">' +
      '<button type="button" class="ask-mode-btn active" data-mode="search">Search &middot; no key</button>' +
      '<button type="button" class="ask-mode-btn" data-mode="claude">Claude &middot; needs key</button>' +
      '</div>' +
      '<div id="ask-search-mode">' +
      '<textarea class="ask-textarea" id="ask-search-q" placeholder="Ask something about this blueprint..."></textarea>' +
      '<button class="ask-submit" id="ask-search-go" type="button">Search</button>' +
      '<p class="ask-hint">Answers come from the same offline index as the nav search. No API key, no network, no model — works with the internet off.</p>' +
      '</div>' +
      '<div id="ask-claude-mode" style="display:none">' +
      '<div class="ask-row"><input type="password" id="ask-key" placeholder="Paste your Anthropic API key"></div>' +
      '<div class="ask-row"><select id="ask-model">' +
      BLUEPRINT.ask.models.map(function (m) { return '<option value="' + m.id + '">' + escapeHtml(m.label) + '</option>'; }).join('') +
      '</select></div>' +
      '<div class="ask-row"><select id="ask-scope">' +
      (isHome ? '' : '<option value="section">This section</option>') +
      '<option value="all">Whole blueprint</option>' +
      '</select></div>' +
      '<textarea class="ask-textarea" id="ask-claude-q" placeholder="Ask something about this blueprint..."></textarea>' +
      '<button class="ask-submit" id="ask-claude-go" type="button">Ask Claude</button>' +
      '<p class="ask-hint">Your key is saved only in this browser (localStorage) and sent only to Anthropic. Answers are grounded only in this blueprint’s data.</p>' +
      '</div>' +
      '<div class="ask-results" id="ask-results"></div>';

    var savedKey = localStorage.getItem('ft_anthropic_key');
    var keyInput = mount.querySelector('#ask-key');
    if (savedKey && keyInput) keyInput.value = savedKey;

    mount.querySelectorAll('.ask-mode-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        mount.querySelectorAll('.ask-mode-btn').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        var mode = btn.getAttribute('data-mode');
        mount.querySelector('#ask-search-mode').style.display = mode === 'search' ? 'block' : 'none';
        mount.querySelector('#ask-claude-mode').style.display = mode === 'claude' ? 'block' : 'none';
        mount.querySelector('#ask-results').innerHTML = '';
      });
    });

    mount.querySelector('#ask-search-go').addEventListener('click', function () {
      var q = mount.querySelector('#ask-search-q').value.trim();
      var box = mount.querySelector('#ask-results');
      if (!q) { box.innerHTML = ''; return; }
      var matches = runSearch(q);
      if (!matches.length) {
        box.innerHTML = '<div class="ask-error">No matches. That gap might itself be the answer — check ' +
          '<a href="' + sectionPage('coverage') + '">What This Design Does Not Cover</a>.</div>';
        return;
      }
      box.innerHTML = matches.map(function (m) {
        return '<div class="ask-card"><div class="ask-card-section">' + escapeHtml(m.sectionTitle) + ' &middot; ' +
          escapeHtml(m.title) + '</div><div>' + m.snippet + '</div><a href="' + m.page + '">Open section &rarr;</a></div>';
      }).join('');
    });

    mount.querySelector('#ask-claude-go').addEventListener('click', function () {
      var q = mount.querySelector('#ask-claude-q').value.trim();
      var key = mount.querySelector('#ask-key').value.trim();
      var modelId = mount.querySelector('#ask-model').value;
      var scope = mount.querySelector('#ask-scope').value;
      var box = mount.querySelector('#ask-results');
      if (!q) return;
      if (!key) { box.innerHTML = '<div class="ask-error">Paste your Anthropic API key above first, or switch to Search mode.</div>'; return; }
      localStorage.setItem('ft_anthropic_key', key);
      var goBtn = mount.querySelector('#ask-claude-go');
      goBtn.disabled = true;
      goBtn.textContent = 'Asking...';
      box.innerHTML = '<div class="ask-hint">Waiting on Claude...</div>';
      askClaude(q, key, modelId, scope, sectionId)
        .then(function (answer) {
          box.innerHTML = '<div class="ask-card"><div class="ask-answer">' + escapeHtml(answer) + '</div></div>';
        })
        .catch(function (err) {
          box.innerHTML = '<div class="ask-error">' + escapeHtml(err.message) + '</div>';
        })
        .then(function () {
          goBtn.disabled = false;
          goBtn.textContent = 'Ask Claude';
        });
    });
  }

  // ---------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------

  document.addEventListener('DOMContentLoaded', function () {
    initTheme();
    initScrollFx();
    initPrint();
    initBreadcrumbs();
    initFooterNav();
    initCommandCenter();
    initComponentsTable();
    initDataFlowList();
    initBuildPhases();
    initAssumptions();
    initCoverage();
    initIllustrations();
    initDiagrams();
    initCharts();
    var modal = initModal();
    if (modal) wireExpandButtons(modal);
    initSearch();
    initAsk();
  });
})();
