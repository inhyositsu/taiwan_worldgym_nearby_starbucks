#!/usr/bin/env node
// Simple zero-dependency viewer for results.json.
// Usage: node server.js   then open http://localhost:5173

const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 5173;
const ROOT = __dirname;
const RESULTS_FILE = path.join(ROOT, 'results.json');

const HTML = `<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>WG × Starbucks 500m</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, "Noto Sans TC", sans-serif; display: flex; height: 100vh; }
  #side { width: 420px; overflow-y: auto; border-right: 1px solid #ddd; }
  #map { flex: 1; }
  header { padding: 12px 14px; background: #111; color: #fff; position: sticky; top: 0; z-index: 10; }
  header h1 { margin: 0 0 4px; font-size: 15px; }
  header .meta { font-size: 12px; opacity: .75; }
  header label { font-size: 12px; display: flex; align-items: center; gap: 6px; margin-top: 6px; cursor: pointer; }
  .item { padding: 10px 14px; border-bottom: 1px solid #eee; cursor: pointer; }
  .item:hover { background: #f7f7f7; }
  .item.active { background: #fff7d6; }
  .item.nomatch { opacity: .4; }
  .item .name { font-weight: 600; font-size: 14px; }
  .item .addr { font-size: 12px; color: #666; margin-top: 2px; }
  .item .sb { font-size: 12px; color: #008f4a; margin-top: 4px; }
  .item .sb .dist { background: #008f4a; color: #fff; padding: 1px 6px; border-radius: 10px; margin-right: 6px; font-weight: 600; }
  .item .none { font-size: 12px; color: #c00; margin-top: 4px; }
  .badge { display: inline-block; background: #333; color: #fff; padding: 1px 6px; border-radius: 3px; font-size: 11px; margin-right: 4px; vertical-align: middle; }
</style>
</head>
<body>
<div id="side">
  <header>
    <h1>World Gym × Starbucks 500m 內</h1>
    <div class="meta" id="stat">載入中…</div>
    <label><input type="checkbox" id="onlyhit" checked> 只顯示 500m 內有星巴克</label>
    <label><input type="checkbox" id="sortdist"> 依距離排序（否則由北到南）</label>
  </header>
  <div id="list"></div>
</div>
<div id="map"></div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const map = L.map('map').setView([23.7, 121], 8);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap', maxZoom: 19
}).addTo(map);

const wgIcon = L.divIcon({ html:'<div style="background:#d61919;color:#fff;padding:2px 6px;border-radius:3px;font-size:11px;font-weight:700;white-space:nowrap">WG</div>', className:'', iconSize:[0,0] });
const sbIcon = L.divIcon({ html:'<div style="background:#008f4a;color:#fff;padding:2px 6px;border-radius:3px;font-size:11px;font-weight:700;white-space:nowrap">☕</div>', className:'', iconSize:[0,0] });

let allMarkers = [];
let activeLayer = null;

function clearLayer() {
  if (activeLayer) { map.removeLayer(activeLayer); activeLayer = null; }
}

function focusBranch(b) {
  clearLayer();
  if (b.lat == null) return;
  const g = L.featureGroup();
  L.marker([b.lat, b.lng], { icon: wgIcon }).bindPopup('<b>' + b.name + '</b><br>' + (b.address || '')).addTo(g);
  L.circle([b.lat, b.lng], { radius: 500, color: '#d61919', weight: 1, fillOpacity: 0.08 }).addTo(g);
  for (const sb of b.starbucks) {
    L.marker([sb.lat, sb.lng], { icon: sbIcon }).bindPopup('<b>' + sb.name + '</b><br>' + sb.address + '<br>距離 ' + sb.distance_m + ' m').addTo(g);
    L.polyline([[b.lat,b.lng],[sb.lat,sb.lng]], { color: '#008f4a', weight: 2, dashArray: '4 4' }).addTo(g);
  }
  g.addTo(map);
  activeLayer = g;
  map.fitBounds(g.getBounds().pad(0.3));
}

function render(data) {
  const onlyHit = document.getElementById('onlyhit').checked;
  const sortDist = document.getElementById('sortdist').checked;

  let rows = data.filter(r => r.lat != null);
  if (onlyHit) rows = rows.filter(r => r.starbucks.length > 0);
  rows.sort(sortDist
    ? (a,b) => (a.nearest_distance_m ?? 1e9) - (b.nearest_distance_m ?? 1e9)
    : (a,b) => b.lat - a.lat);

  const list = document.getElementById('list');
  list.innerHTML = '';
  rows.forEach((r, i) => {
    const el = document.createElement('div');
    el.className = 'item' + (r.starbucks.length === 0 ? ' nomatch' : '');
    const sbHtml = r.starbucks.length > 0
      ? '<div class="sb"><span class="dist">' + r.starbucks[0].distance_m + ' m</span>' + r.starbucks[0].name + (r.starbucks.length > 1 ? ' <span class="badge">+' + (r.starbucks.length-1) + '</span>' : '') + '</div>'
      : '<div class="none">500m 內無星巴克</div>';
    el.innerHTML =
      '<div class="name"><span class="badge">#' + (i+1) + '</span>' + r.name + '</div>' +
      '<div class="addr">' + (r.address || '(無地址)') + (r.geocoded ? ' <span class="badge">geocoded</span>' : '') + '</div>' +
      sbHtml;
    el.onclick = () => {
      document.querySelectorAll('.item.active').forEach(x => x.classList.remove('active'));
      el.classList.add('active');
      focusBranch(r);
    };
    list.appendChild(el);
  });

  const total = data.length;
  const hits = data.filter(r => r.starbucks.length > 0).length;
  document.getElementById('stat').textContent =
    '顯示 ' + rows.length + ' / 共 ' + total + ' 間；500m 內有星巴克 ' + hits + ' 間';
}

fetch('/results.json').then(r => r.json()).then(data => {
  window._data = data;
  render(data);
  // overview markers of all WG
  const bounds = L.latLngBounds();
  for (const b of data) {
    if (b.lat == null) continue;
    bounds.extend([b.lat, b.lng]);
  }
  if (bounds.isValid()) map.fitBounds(bounds.pad(0.1));
});

document.getElementById('onlyhit').onchange = () => render(window._data);
document.getElementById('sortdist').onchange = () => render(window._data);
</script>
</body>
</html>`;

const server = http.createServer((req, res) => {
  if (req.url === '/' || req.url === '/index.html') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    return res.end(HTML);
  }
  if (req.url === '/results.json') {
    fs.readFile(RESULTS_FILE, (err, buf) => {
      if (err) { res.writeHead(500); return res.end('cannot read results.json'); }
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(buf);
    });
    return;
  }
  res.writeHead(404);
  res.end('not found');
});

server.listen(PORT, () => {
  console.log(`➜  Open  http://localhost:${PORT}`);
});
