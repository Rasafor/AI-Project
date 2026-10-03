(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var root = document.documentElement;
  var escH = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  // Guide-specific wording comes from #guide-config, written by field-guides/kit/build.js.
  var CFG = JSON.parse($('#guide-config').textContent);

  // Logo: one embedded copy (header), reused by every document cover.
  var LOGO = $('#cb-logo').getAttribute('src');
  $$('img[data-logo]').forEach(function (i) { i.setAttribute('src', LOGO); });

  // Theme (per-viewer convenience only).
  try { var saved = localStorage.getItem(CFG.themeKey); if (saved) root.setAttribute('data-theme', saved); } catch (e) { /* storage unavailable: use system theme */ }
  $('#theme-btn').addEventListener('click', function () {
    var cur = root.getAttribute('data-theme') || (window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    var next = cur === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem(CFG.themeKey, next); } catch (e) { /* not persisted */ }
  });

  // Mobile nav.
  var side = $('#side'), menu = $('#menu-btn');
  menu.addEventListener('click', function () { var o = side.classList.toggle('open'); menu.setAttribute('aria-expanded', String(o)); });
  side.addEventListener('click', function (e) { if (e.target.tagName === 'A') { side.classList.remove('open'); menu.setAttribute('aria-expanded', 'false'); } });

  // Active nav item.
  var navLinks = {};
  $$('nav.side a').forEach(function (a) { navLinks[a.dataset.nav] = a; });
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (ents) {
      ents.forEach(function (en) {
        if (en.isIntersecting && navLinks[en.target.id]) {
          $$('nav.side a.active').forEach(function (a) { a.classList.remove('active'); });
          navLinks[en.target.id].classList.add('active');
        }
      });
    }, { rootMargin: '-80px 0px -70% 0px' });
    $$('section.sec').forEach(function (s) { io.observe(s); });
  }

  function go(id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    history.replaceState(null, '', '#' + id);
    var box = el.closest('section') === el ? el : el;
    box.classList.remove('flash'); void box.offsetWidth; box.classList.add('flash');
  }

  // ---------- Index: one chunk per section and per h2/h3 inside it ----------
  var STOP = {};
  'a an the and or of to in on for is are be by with as at it its this that what which how do does i we you our your from can should when why who into than then there their them they was were will would not no if my me us about has have had any all each per vs'.split(' ').forEach(function (w) { STOP[w] = 1; });
  function stem(w) {
    if (w.length > 4 && /ies$/.test(w)) return w.slice(0, -3) + 'y';
    if (w.length > 5 && /ing$/.test(w)) return w.slice(0, -3);
    if (w.length > 4 && /ed$/.test(w) && !/eed$/.test(w)) return w.slice(0, -2);
    if (w.length > 3 && /s$/.test(w) && !/ss$/.test(w)) return w.slice(0, -1);
    return w;
  }
  function tok(s) {
    var out = [];
    (String(s).toLowerCase().match(/[a-z0-9_]+(?:-[a-z0-9_]+)*/g) || []).forEach(function (w) {
      if (w.indexOf('-') > 0) { if (/d/.test(w)) out.push(w); w.split('-').forEach(function (p) { out.push(p); }); } else out.push(w);
    });
    return out.filter(function (w) { return !STOP[w]; }).map(stem);
  }

  var chunks = [];
  $$('section.sec').forEach(function (sec) {
    var cur = { id: sec.id, head: sec.dataset.title, text: '' };
    chunks.push(cur);
    $$('h2,h3,p,li,tr,figcaption,pre,.callout,.tile', sec).forEach(function (el) {
      if (!el.classList.contains('callout') && el.closest('.callout')) return;
      if (!el.classList.contains('tile') && el.closest('.tile')) return;
      if (/^H[23]$/.test(el.tagName) && !el.classList.contains('sec-title')) {
        if (!el.id) el.id = sec.id + '-h' + chunks.length;
        cur = { id: el.id, head: sec.dataset.title + ' › ' + el.textContent.trim(), text: '' };
        chunks.push(cur);
      } else if (!el.classList.contains('sec-title')) {
        var t = el.tagName === 'TR' ? Array.prototype.map.call(el.cells, function (td) { return td.textContent.trim(); }).join(' | ') : el.textContent;
        cur.text += ' ' + t.replace(/\s+/g, ' ').trim() + (/^(TR|LI)$/.test(el.tagName) ? '.' : '');
      }
    });
  });
  var df = {};
  chunks.forEach(function (c) {
    c.tf = {};
    tok(c.text).forEach(function (t) { c.tf[t] = (c.tf[t] || 0) + 1; });
    tok(c.head).forEach(function (t) { c.tf[t] = (c.tf[t] || 0) + 3; });
    c.len = 0; for (var k in c.tf) { c.len += c.tf[k]; df[k] = (df[k] || 0) + 1; }
  });
  var N = chunks.length, avg = chunks.reduce(function (a, c) { return a + c.len; }, 0) / N;
  function idf(t) { var d = df[t] || 0; return Math.log(1 + (N - d + 0.5) / (d + 0.5)); }
  function search(q) {
    var qt = uniq(tok(q));
    if (!qt.length) return [];
    return chunks.map(function (c) {
      var s = 0, hit = 0;
      qt.forEach(function (t) { var f = c.tf[t]; if (!f) return; hit++; s += idf(t) * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * c.len / avg)); });
      // Exact multi-word phrase in the chunk outranks the same words scattered apart.
      var phrase = qt.length > 1 && (c.head + ' ' + c.text).toLowerCase().indexOf(String(q).toLowerCase().trim()) >= 0;
      return { c: c, s: s * (0.5 + 0.5 * hit / qt.length) * (phrase ? 1.6 : 1) };
    }).filter(function (x) { return x.s > 0; }).sort(function (a, b) { return b.s - a.s; });
  }
  function uniq(a) { var o = {}, r = []; a.forEach(function (x) { if (!o[x]) { o[x] = 1; r.push(x); } }); return r; }
  function snippet(text, q, n) {
    n = n || 170;
    var qt = uniq(tok(q)), low = text.toLowerCase(), pos = -1;
    qt.forEach(function (t) { var i = low.indexOf(t); if (i >= 0 && (pos < 0 || i < pos)) pos = i; });
    var start = Math.max(0, pos - 50), s = text.slice(start, start + n).trim();
    s = (start > 0 ? '... ' : '') + s + (start + n < text.length ? ' ...' : '');
    return highlight(s, qt);
  }
  function highlight(s, qt) {
    var h = escH(s);
    qt.filter(function (t) { return t.length > 1; }).forEach(function (t) {
      h = h.replace(new RegExp('\\b(' + t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '[a-z0-9_]*)', 'gi'), '<mark>$1</mark>');
    });
    return h;
  }

  // ---------- Search box ----------
  var q = $('#q'), qres = $('#qres'), sel = -1, timer;
  function renderResults() {
    var v = q.value.trim();
    if (v.length < 2) { qres.classList.remove('open'); qres.innerHTML = ''; return; }
    var r = search(v).slice(0, 8);
    sel = -1;
    qres.innerHTML = r.length ? r.map(function (x, i) {
      return '<a class="qr" href="#' + x.c.id + '" data-i="' + i + '" data-id="' + x.c.id + '" role="option"><b>' + escH(x.c.head) + '</b><span>' + snippet(x.c.text, v) + '</span></a>';
    }).join('') : '<div class="qr"><b>No matches</b><span>' + escH(CFG.noMatchHint) + '</span></div>';
    qres.classList.add('open');
  }
  q.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(renderResults, 110); });
  q.addEventListener('focus', renderResults);
  q.addEventListener('keydown', function (e) {
    var items = $$('.qr[data-id]', qres);
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!items.length) return;
      sel = (sel + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      items.forEach(function (it, i) { it.classList.toggle('sel', i === sel); });
    } else if (e.key === 'Enter') {
      e.preventDefault();
      var t = items[Math.max(0, sel)];
      if (t) { qres.classList.remove('open'); go(t.dataset.id); }
    } else if (e.key === 'Escape') { qres.classList.remove('open'); q.blur(); }
  });
  qres.addEventListener('click', function (e) {
    var a = e.target.closest('.qr[data-id]'); if (!a) return;
    e.preventDefault(); qres.classList.remove('open'); go(a.dataset.id);
  });
  document.addEventListener('click', function (e) { if (!e.target.closest('.search')) qres.classList.remove('open'); });
  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && !/INPUT|TEXTAREA/.test(document.activeElement.tagName)) { e.preventDefault(); q.focus(); }
    if (e.key === 'Escape' && ask.classList.contains('open')) closeAsk();
  });

  // ---------- Ask the guide (offline, grounded in this page) ----------
  var FAQ = JSON.parse($('#faq-data').textContent);
  FAQ.forEach(function (f) { f.toks = uniq(tok(f.q + ' ' + (f.k || ''))); });
  var ask = $('#ask'), log = $('#ask-log'), askIn = $('#ask-in');
  function openAsk() { ask.classList.add('open'); ask.setAttribute('aria-hidden', 'false'); setTimeout(function () { askIn.focus(); }, 50); }
  function closeAsk() { ask.classList.remove('open'); ask.setAttribute('aria-hidden', 'true'); }
  $$('[data-ask-open]').forEach(function (b) { b.addEventListener('click', openAsk); });
  $('#ask-close').addEventListener('click', closeAsk);
  var sugs = CFG.suggestions;
  $('#sugs').innerHTML = sugs.map(function (s) { return '<button class="sug" type="button">' + escH(s) + '</button>'; }).join('');
  $('#sugs').addEventListener('click', function (e) { if (e.target.classList.contains('sug')) answer(e.target.textContent); });
  $('#ask-form').addEventListener('submit', function (e) { e.preventDefault(); var v = askIn.value.trim(); if (v) { answer(v); askIn.value = ''; } });

  function chunkById(id) { for (var i = 0; i < chunks.length; i++) if (chunks[i].id === id) return chunks[i]; return null; }
  function bestSentences(text, qt, max) {
    var sents = text.split(/(?<=[.?!])\s+/).filter(function (s) { return s.length > 25; });
    var scored = sents.map(function (s, i) {
      var st = tok(s), sc = 0; qt.forEach(function (t) { if (st.indexOf(t) >= 0) sc += idf(t); });
      return { s: s, i: i, sc: sc };
    }).filter(function (x) { return x.sc > 0; });
    // An exact identifier in the question (e.g. DQ-UNI-03) narrows the answer to sentences that contain it.
    var ids = qt.filter(function (t) { return t.indexOf('-') > 0 && /\d/.test(t); });
    var exact = scored.filter(function (x) { return ids.some(function (t) { return tok(x.s).indexOf(t) >= 0; }); });
    if (exact.length) scored = exact;
    scored = scored.sort(function (a, b) { return b.sc - a.sc; }).slice(0, max);
    return scored.sort(function (a, b) { return a.i - b.i; }).map(function (x) { return x.s; });
  }
  function answer(question) {
    var qt = uniq(tok(question));
    var qIdf = qt.reduce(function (a, t) { return a + idf(t); }, 0) || 1;
    var bestF = null, bestFS = 0;
    FAQ.forEach(function (f) {
      var s = 0; qt.forEach(function (t) { if (f.toks.indexOf(t) >= 0) s += idf(t); });
      s = s / qIdf;
      if (s > bestFS) { bestFS = s; bestF = f; }
    });
    var hits = search(question);
    var html;
    if (bestF && bestFS >= 0.5) {
      var c = chunkById(bestF.ref) || { head: bestF.ref };
      var rel = hits.filter(function (h) { return h.c.id !== bestF.ref; }).slice(0, 2);
      html = '<div class="abub"><div>' + bestF.a + '</div><div class="src">Source: <a href="#' + bestF.ref + '" data-go="' + bestF.ref + '">' + escH(c.head) + '</a></div>' +
        (rel.length ? '<div class="rel">Related: ' + rel.map(function (h) { return '<a href="#' + h.c.id + '" data-go="' + h.c.id + '">' + escH(h.c.head) + '</a>'; }).join(' &middot; ') + '</div>' : '') + '</div>';
    } else if (hits.length && hits[0].s >= 2.2) {
      var top = hits[0].c, sents = bestSentences(top.text, qt, 3);
      if (!sents.length) sents = [top.text.slice(0, 300) + '...'];
      html = '<div class="abub"><div>' + sents.map(function (s) { return highlight(s, qt); }).join(' ') + '</div><div class="src">From: <a href="#' + top.id + '" data-go="' + top.id + '">' + escH(top.head) + '</a></div>' +
        (hits.length > 1 ? '<div class="rel">Also see: ' + hits.slice(1, 3).map(function (h) { return '<a href="#' + h.c.id + '" data-go="' + h.c.id + '">' + escH(h.c.head) + '</a>'; }).join(' &middot; ') + '</div>' : '') + '</div>';
    } else {
      html = '<div class="abub none"><div>This guide does not cover that, so there is no grounded answer to give. Try asking about ' + escH(CFG.notCovered) + '.</div></div>';
    }
    var d = document.createElement('div');
    d.innerHTML = '<div class="qbub">' + escH(question) + '</div>' + html;
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
  }
  log.addEventListener('click', function (e) {
    var a = e.target.closest('a[data-go]'); if (!a) return;
    e.preventDefault(); if (window.innerWidth < 980) closeAsk(); go(a.dataset.go);
  });

  // ---------- Downloads: HTML, PDF (print), CSV, SQL ----------
  var DATA = JSON.parse($('#doc-data').textContent);
  var DOC_CSS = $('#doc-css').textContent;
  function standalone(id) {
    var art = document.getElementById('art-' + id).cloneNode(true);
    $$('img[data-logo]', art).forEach(function (i) { i.setAttribute('src', LOGO); });
    return '<!doctype html>\n<html lang="en" data-theme="light"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' +
      '<title>' + escH(art.dataset.title) + ' | ' + escH(CFG.short) + '</title>' +
      '<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;600;700&family=Roboto+Mono:wght@400;600&display=swap" rel="stylesheet">' +
      '<style>' + DOC_CSS + '\nhtml,body{margin:0;background:var(--surface2)}body{padding:24px 16px}.doc{max-width:1060px;margin:0 auto}@media print{body{padding:0}}</style></head><body>' +
      art.outerHTML + '</body></html>';
  }
  function save(name, content, type) {
    var blob = new Blob([content], { type: type });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
  }
  function csvText(head, rows) {
    var cell = function (v) { v = v == null ? '' : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    return '﻿' + [head].concat(rows).map(function (r) { return r.map(cell).join(','); }).join('\r\n');
  }
  function printDoc(id) {
    var f = document.createElement('iframe');
    f.setAttribute('aria-hidden', 'true');
    f.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0';
    document.body.appendChild(f);
    f.onload = function () {
      var w = f.contentWindow;
      var ready = w.document.fonts && w.document.fonts.ready ? w.document.fonts.ready : Promise.resolve();
      Promise.race([ready, new Promise(function (r) { setTimeout(r, 1500); })]).then(function () {
        w.focus(); w.print();
        setTimeout(function () { f.remove(); }, 2000);
      });
    };
    f.srcdoc = standalone(id);
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-act]'); if (!b) return;
    var id = b.dataset.doc, d = DATA[id];
    if (b.dataset.act === 'html') save(d.file + '.html', standalone(id), 'text/html;charset=utf-8');
    else if (b.dataset.act === 'pdf') printDoc(id);
    else if (b.dataset.act === 'csv') { var c = d.csv[+b.dataset.i]; save(c.name, csvText(c.head, c.rows), 'text/csv;charset=utf-8'); }
    else if (b.dataset.act === 'sql') save(d.sql.name, d.sql.text, 'application/sql;charset=utf-8');
  });

  if (location.hash.length > 1) setTimeout(function () { var el = document.getElementById(location.hash.slice(1)); if (el) el.scrollIntoView(); }, 50);
})();
