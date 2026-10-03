'use strict';
// Building blocks for field-guide content. Every helper returns an HTML string
// styled by doc.css / guide.css, so a weekly content.js never writes CSS.
// Cell and body arguments are trusted, authored HTML; use esc() for raw text.

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const TONES = { berry: 'k-berry', leaf: 'k-leaf', cherry: 'k-cherry', muted: 'k-muted' };
const tone = (t) => TONES[t || 'berry'] || 'k-berry';
const num = (v) => (Math.round(v * 100) / 100).toLocaleString('en-US');

function table(head, rows, cls = '') {
  const th = head.map((h) => `<th>${h}</th>`).join('');
  const tb = rows.map((r) => `<tr>${r.map((c) => `<td>${c == null ? '' : c}</td>`).join('')}</tr>`).join('');
  return `<div class="tbl-wrap"><table class="${cls}"><thead><tr>${th}</tr></thead><tbody>${tb}</tbody></table></div>`;
}

// kind: info | tip | warn
const callout = (kind, title, body) => `<div class="callout ${kind}"><div class="callout-t">${title}</div><div>${body}</div></div>`;

// tiles([{ v: '66%', l: 'Loss ratio', s: 'TTM', tone: 'good' | 'warn' }])
const tiles = (items) => `<div class="tiles">${items.map((t) => `<div class="tile ${t.tone || ''}"><div class="tile-v">${t.v}</div><div class="tile-l">${t.l}</div>${t.s ? `<div class="tile-s">${t.s}</div>` : ''}</div>`).join('')}</div>`;

const fig = (svg, caption) => `<figure class="fig">${svg}${caption ? `<figcaption>${caption}</figcaption>` : ''}</figure>`;
const chartRow = (...svgs) => `<div class="chart-row">${svgs.join('')}</div>`;
const pre = (text) => `<pre class="code">${esc(text)}</pre>`;
const list = (items, ordered) => `<${ordered ? 'ol' : 'ul'}>${items.map((i) => `<li>${i}</li>`).join('')}</${ordered ? 'ol' : 'ul'}>`;

function svgOpen(w, h, label, cls = 'chart') {
  return `<svg class="dg ${cls}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg"><title>${esc(label)}</title>`;
}

// Horizontal bar chart. data: [{ label, value, tone }]; unit is appended to values.
function barChart({ title, data, unit = '', max }) {
  const W = 560, left = 170, right = 70, rowH = 34, top = 28;
  const H = top + data.length * rowH + 10;
  const m = max || Math.max(...data.map((d) => d.value)) || 1;
  const span = W - left - right;
  let s = svgOpen(W, H, title) + `<text x="0" y="16" class="c-title">${esc(title)}</text>`;
  for (let i = 1; i <= 4; i++) { const x = left + (span * i) / 4; s += `<line x1="${x}" y1="${top}" x2="${x}" y2="${H - 10}" class="c-grid"/>`; }
  data.forEach((d, i) => {
    const y = top + i * rowH, w = Math.max(2, (span * d.value) / m);
    s += `<g class="c-hover"><title>${esc(d.label)}: ${num(d.value)}${esc(unit)}</title><rect x="0" y="${y}" width="${W}" height="${rowH}" class="c-hit"/>` +
      `<text x="${left - 10}" y="${y + 21}" class="c-lbl" text-anchor="end">${esc(d.label)}</text>` +
      `<rect x="${left}" y="${y + 7}" width="${w.toFixed(1)}" height="20" rx="4" class="${tone(d.tone)}"/>` +
      `<text x="${(left + w + 6).toFixed(1)}" y="${y + 21}" class="c-val">${num(d.value)}${esc(unit)}</text></g>`;
  });
  return s + '</svg>';
}

// Line chart over categorical x labels, optional horizontal target line.
function lineChart({ title, labels, values, unit = '', target, min, max }) {
  const W = 560, H = 240, l = 48, r = 16, t = 32, b = 34;
  const lo = min != null ? min : Math.min(...values, target != null ? target : Infinity);
  const hi = max != null ? max : Math.max(...values, target != null ? target : -Infinity);
  const pad = (hi - lo) * 0.1 || 1, y0 = lo - pad, y1 = hi + pad;
  const X = (i) => l + (labels.length === 1 ? 0 : ((W - l - r) * i) / (labels.length - 1));
  const Y = (v) => t + (H - t - b) * (1 - (v - y0) / (y1 - y0));
  let s = svgOpen(W, H, title) + `<text x="0" y="16" class="c-title">${esc(title)}</text>`;
  for (let i = 0; i <= 4; i++) { const v = y0 + ((y1 - y0) * i) / 4, y = Y(v); s += `<line x1="${l}" y1="${y.toFixed(1)}" x2="${W - r}" y2="${y.toFixed(1)}" class="c-grid"/><text x="${l - 6}" y="${(y + 4).toFixed(1)}" class="c-tick" text-anchor="end">${num(v)}</text>`; }
  labels.forEach((lab, i) => { s += `<text x="${X(i).toFixed(1)}" y="${H - 12}" class="c-tick" text-anchor="middle">${esc(lab)}</text>`; });
  if (target != null) s += `<line x1="${l}" y1="${Y(target).toFixed(1)}" x2="${W - r}" y2="${Y(target).toFixed(1)}" class="c-target"><title>Target ${num(target)}${esc(unit)}</title></line>`;
  s += `<polyline points="${values.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(' ')}" class="c-line"/>`;
  values.forEach((v, i) => { s += `<circle cx="${X(i).toFixed(1)}" cy="${Y(v).toFixed(1)}" r="4" class="c-dot"><title>${esc(labels[i])}: ${num(v)}${esc(unit)}</title></circle>`; });
  return s + '</svg>';
}

// Donut with a legend. data: [{ label, value, tone }]; center: big label in the hole.
function donut({ title, data, center, unit = '' }) {
  const W = 560, H = 230, cx = 115, cy = 125, R = 82, r = 52;
  const total = data.reduce((a, d) => a + d.value, 0) || 1;
  let a0 = -Math.PI / 2, s = svgOpen(W, H, title) + `<text x="0" y="16" class="c-title">${esc(title)}</text>`;
  data.forEach((d, i) => {
    const a1 = a0 + (2 * Math.PI * d.value) / total, large = a1 - a0 > Math.PI ? 1 : 0;
    const p = (ang, rad) => `${(cx + rad * Math.cos(ang)).toFixed(2)},${(cy + rad * Math.sin(ang)).toFixed(2)}`;
    const path = data.length === 1
      ? `M${cx - R},${cy} a${R},${R} 0 1 0 ${2 * R},0 a${R},${R} 0 1 0 ${-2 * R},0 M${cx - r},${cy} a${r},${r} 0 1 1 ${2 * r},0 a${r},${r} 0 1 1 ${-2 * r},0`
      : `M${p(a0, R)} A${R},${R} 0 ${large} 1 ${p(a1, R)} L${p(a1, r)} A${r},${r} 0 ${large} 0 ${p(a0, r)} Z`;
    const pct = Math.round((100 * d.value) / total);
    s += `<g class="c-hover"><title>${esc(d.label)}: ${num(d.value)}${esc(unit)} (${pct}%)</title><path d="${path}" class="${tone(d.tone)} c-seg"/>` +
      `<rect x="250" y="${48 + i * 30}" width="12" height="12" rx="2" class="${tone(d.tone)}"/><text x="270" y="${59 + i * 30}" class="c-lbl">${esc(d.label)}</text>` +
      `<text x="${W - 10}" y="${59 + i * 30}" class="c-val" text-anchor="end">${num(d.value)}${esc(unit)} (${pct}%)</text></g>`;
    a0 = a1;
  });
  if (center) s += `<text x="${cx}" y="${cy + 7}" class="c-big" text-anchor="middle">${esc(center)}</text>`;
  return s + '</svg>';
}

// Box-and-arrow diagram. nodes: [{ id, x, y, w, h, t, s, kind }] where kind is a
// .n-* class suffix (std, src, gate, out, warn, muted, fact, hot, warm, cold).
// edges: [{ from, to, label, warn, side: 'auto' | 'v' | 'h' }]
function flow({ title, width, height, nodes, edges = [] }) {
  const byId = Object.fromEntries(nodes.map((n) => [n.id, { w: 160, h: 56, kind: 'std', ...n }]));
  let s = svgOpen(width, height, title, 'flow') +
    '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="d-arrowhead"/></marker></defs>';
  edges.forEach((e) => {
    const a = byId[e.from], b = byId[e.to];
    if (!a || !b) throw new Error(`flow "${title}": edge ${e.from} -> ${e.to} names a missing node`);
    const dx = b.x + b.w / 2 - (a.x + a.w / 2), dy = b.y + b.h / 2 - (a.y + a.h / 2);
    const vertical = e.side === 'v' || (e.side !== 'h' && Math.abs(dy) > Math.abs(dx));
    let x1, y1, x2, y2;
    if (vertical) { x1 = a.x + a.w / 2; x2 = b.x + b.w / 2; y1 = dy > 0 ? a.y + a.h : a.y; y2 = dy > 0 ? b.y : b.y + b.h; }
    else { y1 = a.y + a.h / 2; y2 = b.y + b.h / 2; x1 = dx > 0 ? a.x + a.w : a.x; x2 = dx > 0 ? b.x : b.x + b.w; }
    const d = vertical ? `M${x1},${y1} C${x1},${(y1 + y2) / 2} ${x2},${(y1 + y2) / 2} ${x2},${y2}` : `M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}`;
    s += `<path d="${d}" class="d-flow${e.warn ? ' warnline' : ''}" marker-end="url(#ah)"/>`;
    if (e.label) s += `<text x="${(x1 + x2) / 2 + (vertical ? 6 : 0)}" y="${(y1 + y2) / 2 - (vertical ? 0 : 6)}" class="d-elbl" text-anchor="${vertical ? 'start' : 'middle'}">${esc(e.label)}</text>`;
  });
  Object.values(byId).forEach((n) => {
    const fact = n.kind === 'fact', cx = n.x + n.w / 2;
    s += `<g><title>${esc(n.t)}${n.s ? ': ' + esc(n.s) : ''}</title><rect x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" rx="8" class="n-${n.kind}"/>` +
      `<text x="${cx}" y="${n.y + (n.s ? n.h / 2 - 3 : n.h / 2 + 5)}" class="n-t${fact ? ' n-t-fact' : ''}" text-anchor="middle">${esc(n.t)}</text>` +
      (n.s ? `<text x="${cx}" y="${n.y + n.h / 2 + 14}" class="n-s${fact ? ' n-s-fact' : ''}" text-anchor="middle">${esc(n.s)}</text>` : '') + '</g>';
  });
  return s + '</svg>';
}

module.exports = { esc, table, callout, tiles, fig, chartRow, pre, list, barChart, lineChart, donut, flow };
