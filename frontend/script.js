const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];

function badge(text) {
  const t = String(text || 'UNKNOWN');
  const c = t.toLowerCase().replace(/\s+/g, '-');
  return `<span class="badge ${c}">${t}</span>`;
}

function money(v) {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(v || 0));
}

function num(v, digits = 0) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  return Number(v).toLocaleString('en-IN', { maximumFractionDigits: digits });
}

function svgLineChart(points, labels, options = {}) {
  const width = 860, height = 260, pad = { l: 42, r: 14, t: 18, b: 30 };
  const iw = width - pad.l - pad.r, ih = height - pad.t - pad.b;
  const vals = points.map(Number);
  const max = Math.max(1, ...vals), min = Math.min(0, ...vals), span = Math.max(1, max - min);
  const x = i => pad.l + (vals.length <= 1 ? 0 : (i / (vals.length - 1)) * iw);
  const y = v => pad.t + (max - v) / span * ih;
  const d = vals.map((v, i) => `${i ? 'L' : 'M'} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');
  const area = `${d} L ${x(vals.length - 1).toFixed(1)} ${pad.t + ih} L ${x(0).toFixed(1)} ${pad.t + ih} Z`;
  const yTicks = [0, .25, .5, .75, 1].map(p => {
    const v = min + (max - min) * p;
    return `<g><line x1="${pad.l}" y1="${y(v)}" x2="${width-pad.r}" y2="${y(v)}" stroke="#e5ecef"/><text x="${pad.l-8}" y="${y(v)+4}" text-anchor="end" fill="#7b8a92" font-size="10">${num(v,0)}</text></g>`;
  }).join('');
  const xLabels = labels.map((lab, i) => i % Math.max(1, Math.ceil(labels.length / 6)) === 0 ? `<text x="${x(i)}" y="${height-8}" text-anchor="middle" fill="#7b8a92" font-size="10">${lab}</text>` : '').join('');
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Consumption chart">
    ${yTicks}
    <path d="${area}" fill="#e9f4f6" opacity=".95"></path>
    <path d="${d}" fill="none" stroke="#0d6b78" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
    ${vals.map((v,i) => i % Math.max(1, Math.ceil(vals.length / 12)) === 0 ? `<circle cx="${x(i)}" cy="${y(v)}" r="3.3" fill="#0d6b78"></circle>` : '').join('')}
    ${xLabels}
  </svg>`;
}

function svgBars(items, maxValue) {
  const width = 860, rowH = 38, height = Math.max(120, items.length * rowH + 32);
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Bar chart">${items.map((item, i) => {
    const y = 10 + i*rowH, w = Math.max(4, (Number(item.value)/Math.max(1,maxValue))*560);
    return `<g><text x="0" y="${y+15}" font-size="11" fill="#41545d">${item.label}</text><rect x="180" y="${y+4}" width="570" height="12" rx="6" fill="#eef2f4"/><rect x="180" y="${y+4}" width="${w}" height="12" rx="6" fill="#1a8a9a"/><text x="770" y="${y+15}" font-size="11" fill="#10212b">${item.display ?? num(item.value)}</text></g>`;
  }).join('')}</svg>`;
}

async function api(url, options) {
  const res = await fetch(url, options);
  const contentType = res.headers.get('content-type') || '';
  const raw = await res.text();
  let data;
  try {
    data = contentType.includes('application/json') ? JSON.parse(raw) : JSON.parse(raw);
  } catch {
    throw new Error(`${res.status} ${res.statusText}: Server returned non-JSON content.`);
  }
  if (!res.ok) throw new Error(data.message || 'Request failed');
  return data;
}

function setActiveNav() {
  const p = location.pathname;
  $$('.nav-link').forEach(a => a.classList.remove('active'));
  const map = {
    '/': 'dashboard', '/inventory.html': 'inventory', '/alerts.html': 'alerts',
    '/prediction.html': 'prediction', '/supply-chain.html': 'supply-chain', '/procurement.html': 'procurement', '/settings.html': 'settings'
  };
  const key = map[p] || 'dashboard';
  const el = $(`[data-nav="${key}"]`); if (el) el.classList.add('active');
}

function shell(pageTitle, subtitle='Healthcare Supply Chain Intelligence') {
  return `<div class="app-shell">
    <aside class="sidebar">
      <a class="brand" href="/">
        <div class="brand-mark">MS</div>
        <div><div class="brand-title">MedSupplyAI</div><div class="brand-subtitle">Intelligence Platform</div></div>
      </a>
      <div class="nav-section">Operations</div>
      <a class="nav-link" data-nav="dashboard" href="/"><span class="nav-icon">◉</span>Dashboard</a>
      <a class="nav-link" data-nav="inventory" href="/inventory.html"><span class="nav-icon">▣</span>Inventory</a>
      <a class="nav-link" data-nav="alerts" href="/alerts.html"><span class="nav-icon">⚠</span>Alerts</a>
      <a class="nav-link" data-nav="prediction" href="/prediction.html"><span class="nav-icon">◒</span>AI Forecast</a>
      <a class="nav-link" data-nav="supply-chain" href="/supply-chain.html"><span class="nav-icon">◇</span>Supply Chain</a>
      <a class="nav-link" data-nav="procurement" href="/procurement.html"><span class="nav-icon">▤</span>Procurement</a>
      <div class="nav-section">Administration</div>
      <a class="nav-link" data-nav="settings" href="/settings.html"><span class="nav-icon">⚙</span>Settings</a>
      <div class="sidebar-footer">Prototype • Data-aware • Decision support</div>
    </aside>
    <main class="main">
      <header class="topbar">
        <div class="topbar-left"><h1>${pageTitle}</h1><div class="crumb">${subtitle}</div></div>
        <div class="topbar-actions"><input class="search" id="globalSearch" placeholder="Search medicines, batches…"><button class="icon-btn" title="Alerts" onclick="location.href='/alerts.html'">🔔</button><div class="avatar">A</div></div>
      </header>
      <section class="content" id="appContent"></section>
    </main>
  </div>`;
}

function renderPage(title, subtitle, content) {
  document.body.innerHTML = shell(title, subtitle);
  $('#appContent').innerHTML = content;
  setActiveNav();
}

async function dashboardPage() {
  renderPage('Supply Chain Overview', 'Real-time operational visibility and predictive inventory intelligence', '<div class="empty">Loading dashboard…</div>');
  try {
    const d = await api('/api/dashboard');
    const top = d.top_risks || [];
    const consumption = d.consumption_30d || [];
    const labels = consumption.map(x => x.date.slice(5));
    const values = consumption.map(x => x.usage);
    const riskItems = top.map(x => ({ label: x.medicine_name, value: x.risk_score, display: `${x.risk_score}/100` }));
    $('#appContent').innerHTML = `
      <div class="page-head"><div><h2>Operational overview</h2><p>${new Date().toLocaleDateString('en-IN', {weekday:'long', day:'numeric', month:'long', year:'numeric'})}</p></div><div class="actions"><a class="btn" href="/inventory.html">View inventory</a><a class="btn primary" href="/prediction.html">Open AI forecast</a></div></div>
      <div class="kpi-grid">
        <div class="kpi-card"><div class="label">Active SKUs</div><div class="value">${num(d.total_items)}</div><div class="meta">Items under management</div></div>
        <div class="kpi-card"><div class="label">Units on hand</div><div class="value">${num(d.total_units)}</div><div class="meta">Across tracked inventory</div></div>
        <div class="kpi-card"><div class="label">Low stock</div><div class="value">${num(d.low_stock)}</div><div class="meta">At or below minimum level</div></div>
        <div class="kpi-card"><div class="label">Projected stockouts</div><div class="value">${num(d.projected_stockouts)}</div><div class="meta">Within supplier lead time</div></div>
        <div class="kpi-card"><div class="label">Inventory value</div><div class="value">${money(d.inventory_value)}</div><div class="meta">Current book value estimate</div></div>
      </div>
      <div class="grid-2">
        <div class="panel"><div class="panel-head"><h3>30-day consumption trend</h3><span>Recorded usage</span></div><div class="chart">${values.length ? svgLineChart(values, labels) : '<div class="empty">No consumption data yet.</div>'}</div></div>
        <div class="panel"><div class="panel-head"><h3>Highest current supply risk</h3><span>Rule-based index</span></div><div class="chart">${riskItems.length ? svgBars(riskItems, 100) : '<div class="empty">No risk items.</div>'}</div></div>
      </div>
      <div class="insight"><div class="eyebrow">AI / Decision Support Insight</div><h3>${top[0] ? `${top[0].medicine_name} requires attention` : 'System is monitoring current inventory'}</h3><p>${top[0] ? (top[0].risk_reasons?.join('. ') || 'The item has elevated supply risk based on stock, lead time, expiry and criticality.') + '.' : 'No high-priority condition was detected from the current dataset.'}</p></div>
      <div class="grid-2">
        <div class="panel"><div class="panel-head"><h3>Risk register</h3><span>Top items</span></div><div class="risk-list">${top.map(x => `<div class="risk-row"><div><div class="name">${x.medicine_name}</div><div class="small">${num(x.quantity)} units • ${x.stock_days == null ? 'No forecast' : `${num(x.stock_days,1)} days cover`}</div></div>${badge(x.risk)}</div>`).join('') || '<div class="empty">No risk items.</div>'}</div></div>
        <div class="panel"><div class="panel-head"><h3>System signals</h3><span>Current</span></div><div class="small-grid">
          <div class="metric"><div class="label">Expiry ≤30d</div><div class="value">${num(d.expiring_soon)}</div></div>
          <div class="metric"><div class="label">Critical items</div><div class="value">${num(d.critical_items)}</div></div>
          <div class="metric"><div class="label">Alerts</div><div class="value">${num(d.alert_count)}</div></div>
          <div class="metric"><div class="label">Data mode</div><div class="value" style="font-size:13px">Hybrid</div></div>
        </div><div class="notice" style="margin-top:12px">Numbers marked DEMO are synthetic demonstration data. Replace them with verified product, batch and hospital transaction data before real operational use.</div></div>
      </div>`;
  } catch (e) { $('#appContent').innerHTML = `<div class="panel"><div class="empty">${e.message}</div></div>`; }
}

async function inventoryPage() {
  renderPage('Inventory Control', 'Stock balances, expiry, reorder parameters and traceability', '<div class="panel"><div class="empty">Loading inventory…</div></div>');
  const items = await api('/api/inventory');
  $('#appContent').innerHTML = `
    <div class="page-head"><div><h2>Inventory control</h2><p>Operational stock plus calculated supply indicators.</p></div><div class="actions"><button class="btn primary" id="addBtn">+ Add medicine</button></div></div>
    <div class="panel"><div class="panel-head"><h3>Inventory register</h3><span>${items.length} records</span></div><div class="table-wrap"><table><thead><tr><th>Medicine</th><th>Stock</th><th>Daily usage</th><th>Stock days</th><th>Reorder point</th><th>Expiry</th><th>Risk</th><th>Data</th><th></th></tr></thead><tbody>${items.map(x => `<tr><td><strong>${x.medicine_name}</strong><div class="muted">${x.category} · ${x.criticality}</div></td><td>${num(x.quantity)} / ${num(x.minimum_stock)}</td><td>${num(x.daily_usage,2)}/day</td><td>${x.stock_days == null ? '—' : num(x.stock_days,1)}</td><td>${num(x.reorder_point)}</td><td>${x.expiry_date}<div class="muted">${x.days_to_expiry < 0 ? 'Expired' : `${num(x.days_to_expiry)} days`}</div></td><td>${badge(x.risk)}</td><td>${badge(x.data_status || 'DEMO')}</td><td><button class="btn small" onclick="viewTrace(${x.id})">Trace</button></td></tr>`).join('')}</tbody></table></div></div>
    <div class="panel" style="margin-top:16px"><div class="panel-head"><h3>Feasible inventory parameters</h3><span>Model assumptions</span></div><div class="notice">Reorder point = forecast demand during supplier lead time + safety stock. Safety stock uses the greater of the configured minimum/elective reserve and a 95% service-level statistical buffer from historical variability. These are decision-support assumptions, not universal clinical rules.</div></div>
    <div class="modal" id="traceModal"><div class="modal-card"><div class="modal-head"><h3>Traceability</h3><button class="icon-btn" onclick="$('#traceModal').classList.remove('show')">×</button></div><div id="traceBody"><div class="empty">Loading…</div></div></div></div>
    <div class="modal" id="addModal"><div class="modal-card"><div class="modal-head"><h3>Add inventory item</h3><button class="icon-btn" onclick="$('#addModal').classList.remove('show')">×</button></div><form id="addForm"><div class="form-grid">
      <div class="field"><label>Medicine name *</label><input name="medicine_name" required></div><div class="field"><label>Category *</label><input name="category" required></div>
      <div class="field"><label>Quantity *</label><input name="quantity" type="number" min="0" required></div><div class="field"><label>Minimum stock *</label><input name="minimum_stock" type="number" min="0" value="20" required></div>
      <div class="field"><label>Maximum stock *</label><input name="maximum_stock" type="number" min="0" value="100" required></div><div class="field"><label>Expiry date *</label><input name="expiry_date" type="date" required></div>
      <div class="field"><label>Supplier</label><input name="supplier"></div><div class="field"><label>Supplier lead time (days)</label><input name="supplier_lead_days" type="number" min="0" value="5"></div>
      <div class="field"><label>Unit price (₹)</label><input name="unit_price" type="number" min="0" step="0.01" value="0"></div><div class="field"><label>Criticality</label><select name="criticality"><option>Routine</option><option>Essential</option><option>Critical</option></select></div>
      <div class="field"><label>Generic name</label><input name="generic_name"></div><div class="field"><label>Brand name</label><input name="brand_name"></div>
      <div class="field"><label>Strength</label><input name="strength" placeholder="e.g. 500 mg"></div><div class="field"><label>Dosage form</label><input name="dosage_form" placeholder="Tablet / Injection"></div>
      <div class="field span-2"><label>Storage instruction (verified label text)</label><input name="storage_instruction" placeholder="Enter only from a verified product source."></div>
      <div class="field"><label>Manufacturer</label><input name="manufacturer"></div><div class="field"><label>Manufacturing site</label><input name="manufacturing_site"></div>
      <div class="field"><label>Product identifier / GTIN</label><input name="gtin"></div><div class="field"><label>Source URL</label><input name="source_url"></div>
      <div class="field"><label>Data status</label><select name="data_status"><option>USER ENTERED</option><option>VERIFIED</option><option>DEMO</option></select></div><div class="field"><label>Source name</label><input name="source_name"></div>
      <div class="span-2 actions"><button class="btn" type="button" onclick="$('#addModal').classList.remove('show')">Cancel</button><button class="btn primary" type="submit">Save item</button></div>
    </div></form></div></div>`;
  $('#addBtn').onclick = () => $('#addModal').classList.add('show');
  $('#addForm').onsubmit = async e => { e.preventDefault(); const fd = new FormData(e.target); const obj = Object.fromEntries(fd.entries()); obj.quantity=+obj.quantity; obj.minimum_stock=+obj.minimum_stock; obj.maximum_stock=+obj.maximum_stock; obj.supplier_lead_days=+obj.supplier_lead_days; obj.unit_price=+obj.unit_price; try { await api('/api/inventory',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)}); location.reload(); } catch(err){ alert(err.message); } };
}

async function viewTrace(id) {
  $('#traceModal').classList.add('show');
  try {
    const d = await api(`/api/traceability/${id}`);
    const m = d.medicine;
    $('#traceBody').innerHTML = `<div class="small-grid"><div class="metric"><div class="label">Medicine</div><div class="value" style="font-size:14px">${m.medicine_name}</div></div><div class="metric"><div class="label">Data status</div><div class="value" style="font-size:14px">${m.data_status || '—'}</div></div><div class="metric"><div class="label">Manufacturer</div><div class="value" style="font-size:14px">${m.manufacturer || 'Not recorded'}</div></div><div class="metric"><div class="label">GTIN</div><div class="value" style="font-size:14px">${m.gtin || 'Not recorded'}</div></div></div><div class="notice" style="margin:14px 0">Origin/manufacturer fields are shown only when a verified source has supplied them. The demo batch records do not invent origin facts.</div><h4>Batches</h4>${d.batches.length ? d.batches.map(b => `<div class="panel" style="box-shadow:none;margin-bottom:10px"><div class="small-grid"><div class="metric"><div class="label">Batch</div><div class="value" style="font-size:13px">${b.batch_number}</div></div><div class="metric"><div class="label">Current qty</div><div class="value">${num(b.quantity_current)}</div></div><div class="metric"><div class="label">Expiry</div><div class="value" style="font-size:14px">${b.expiry_date}</div></div><div class="metric"><div class="label">Quality</div><div class="value" style="font-size:13px">${b.quality_status}</div></div></div><div class="muted" style="margin-top:9px">Supplier: ${b.supplier_name || 'Not recorded'} · Location: ${b.location_name || 'Not recorded'} · Origin: ${b.origin_country || 'Not recorded'}</div></div>`).join('') : '<div class="empty">No batches recorded.</div>'}<h4>Event timeline</h4><div class="timeline">${d.events.length ? d.events.map(e => `<div class="timeline-item"><div class="t">${e.event_type.replaceAll('_',' ')}</div><div class="d">${e.event_time || ''} · ${e.location_name || 'Location not recorded'}</div><div class="muted">${e.notes || ''}</div></div>`).join('') : '<div class="empty">No traceability events.</div>'}</div>`;
  } catch(e) { $('#traceBody').innerHTML = `<div class="empty">${e.message}</div>`; }
}

async function alertsPage() {
  renderPage('Alerts & Exceptions', 'Exceptions requiring operational review', '<div class="panel"><div class="empty">Loading alerts…</div></div>');
  const alerts = await api('/api/alerts');
  $('#appContent').innerHTML = `<div class="page-head"><div><h2>Exception management</h2><p>${alerts.length} current signal${alerts.length===1?'':'s'}.</p></div><div class="actions"><button class="btn" onclick="location.reload()">Refresh</button></div></div><div class="grid-2"><div class="panel"><div class="panel-head"><h3>Active alerts</h3><span>Prioritized by severity</span></div><div class="risk-list">${alerts.map(a => `<div class="risk-row"><div><div class="name">${a.type} · ${a.medicine_name}</div><div class="small">${a.message}</div><div class="muted" style="margin-top:4px">${a.recommendation}</div></div>${badge(a.severity)}</div>`).join('') || '<div class="empty">No active alerts.</div>'}</div></div><div class="panel"><div class="panel-head"><h3>Alert logic</h3><span>Transparent rules</span></div><div class="notice">Alerts are generated from stock thresholds, projected stockout timing, expiry windows and unusual consumption patterns. They are operational decision-support signals, not clinical judgments.</div><div class="risk-list" style="margin-top:12px"><div class="risk-row"><div><div class="name">Low stock</div><div class="small">On-hand quantity ≤ configured minimum.</div></div>${badge('HIGH')}</div><div class="risk-row"><div><div class="name">Projected stockout</div><div class="small">Projected stock duration ≤ supplier lead time.</div></div>${badge('CRITICAL')}</div><div class="risk-row"><div><div class="name">Expiry</div><div class="small">Expiry is within 30 days or has passed.</div></div>${badge('HIGH')}</div><div class="risk-row"><div><div class="name">Abnormal usage</div><div class="small">Recent average substantially exceeds baseline.</div></div>${badge('MEDIUM')}</div></div></div></div>`;
}

async function predictionPage() {
  renderPage('AI Forecasting', 'Demand forecasting, stock cover and procurement intelligence', '<div class="panel"><div class="empty">Loading model outputs…</div></div>');
  const rows = await api('/api/predictions');
  $('#appContent').innerHTML = `<div class="page-head"><div><h2>Forecasting workspace</h2><p>Random Forest demand forecasting over the available consumption history.</p></div><div class="actions"><button class="btn" onclick="location.reload()">Re-run analysis</button></div></div><div class="grid-2"><div class="panel"><div class="panel-head"><h3>Model profile</h3><span>Transparent parameters</span></div><div class="small-grid"><div class="metric"><div class="label">Model</div><div class="value" style="font-size:13px">Random Forest</div></div><div class="metric"><div class="label">Trees</div><div class="value">160</div></div><div class="metric"><div class="label">Service level</div><div class="value">95%</div></div><div class="metric"><div class="label">Horizon</div><div class="value">30d</div></div></div><div class="notice" style="margin-top:12px">Forecast outputs are AI-derived from consumption history. Demo history is synthetic unless marked otherwise in the inventory source fields.</div></div><div class="panel"><div class="panel-head"><h3>Highest demand-rate items</h3><span>Predicted units/day</span></div><div class="chart">${svgBars(rows.slice().sort((a,b)=>b.daily_usage-a.daily_usage).slice(0,6).map(x=>({label:x.medicine_name,value:x.daily_usage,display:`${num(x.daily_usage,2)}/day`})), Math.max(1,...rows.map(x=>x.daily_usage)))}</div></div></div><div class="panel" style="margin-top:16px"><div class="panel-head"><h3>Forecast register</h3><span>Click a row for details</span></div><div class="table-wrap"><table><thead><tr><th>Medicine</th><th>Daily usage</th><th>7-day</th><th>30-day</th><th>Stock days</th><th>Lead time</th><th>Reorder point</th><th>Recommended order</th><th>Risk</th></tr></thead><tbody>${rows.map(x=>`<tr onclick="showForecast(${x.id})" style="cursor:pointer"><td><strong>${x.medicine_name}</strong><div class="muted">${x.forecast.model}</div></td><td>${num(x.daily_usage,2)}</td><td>${num(x.forecast.predicted_7_days)}</td><td>${num(x.forecast.predicted_30_days)}</td><td>${x.stock_days==null?'—':num(x.stock_days,1)}</td><td>${num(x.supplier_lead_days)}d</td><td>${num(x.reorder_point)}</td><td>${num(x.recommended_order)}</td><td>${badge(x.risk)}</td></tr>`).join('')}</tbody></table></div></div><div class="modal" id="forecastModal"><div class="modal-card"><div class="modal-head"><h3>Forecast detail</h3><button class="icon-btn" onclick="$('#forecastModal').classList.remove('show')">×</button></div><div id="forecastBody"></div></div></div>`;
  window.__forecastRows = rows;
}

function showForecast(id) {
  const x = window.__forecastRows.find(r => r.id === id); if (!x) return;
  $('#forecastModal').classList.add('show');
  const labels = Array.from({length:30},(_,i)=>`+${i+1}`);
  $('#forecastBody').innerHTML = `<div class="small-grid"><div class="metric"><div class="label">Medicine</div><div class="value" style="font-size:15px">${x.medicine_name}</div></div><div class="metric"><div class="label">Daily usage</div><div class="value">${num(x.daily_usage,2)}</div></div><div class="metric"><div class="label">Stock days</div><div class="value">${x.stock_days==null?'—':num(x.stock_days,1)}</div></div><div class="metric"><div class="label">Reorder point</div><div class="value">${num(x.reorder_point)}</div></div></div><div class="panel" style="margin-top:14px;box-shadow:none"><div class="panel-head"><h3>30-day forecast series</h3><span>units/day</span></div><div class="chart">${svgLineChart(x.forecast.forecast_series, labels)}</div></div><div class="notice">Risk: ${x.risk}. ${x.risk_reasons?.join('. ') || 'No specific rule trigger recorded.'}.</div>`;
}

async function procurementPage() {
  renderPage('Procurement Control', 'Recommendation queue and purchase-order workflow', '<div class="panel"><div class="empty">Loading recommendations…</div></div>');
  try {
    const [recommendations, orders] = await Promise.all([api('/api/procurement/recommendations'), api('/api/procurement')]);
    $('#appContent').innerHTML = `<div class="page-head"><div><h2>Procurement workspace</h2><p>Recommendations are generated from forecast demand, lead time, safety stock and current inventory.</p></div><div class="actions"><button class="btn" onclick="location.reload()">Refresh</button></div></div><div class="panel"><div class="panel-head"><h3>Recommended orders</h3><span>${recommendations.length} items</span></div><div class="table-wrap"><table><thead><tr><th>Medicine</th><th>Current</th><th>Daily usage</th><th>Lead time</th><th>Reorder point</th><th>Recommended</th><th>Risk</th><th>Action</th></tr></thead><tbody>${recommendations.map(x=>`<tr><td><strong>${x.medicine_name}</strong><div class="muted">${x.supplier || 'Supplier not recorded'}</div></td><td>${num(x.quantity)}</td><td>${num(x.daily_usage,2)}</td><td>${num(x.supplier_lead_days)}d</td><td>${num(x.reorder_point)}</td><td><strong>${num(x.recommended_order)}</strong><div class="muted">Net after open orders: ${num(x.outstanding_order || 0)}</div></td><td>${badge(x.risk)}</td><td><button class="btn small primary" onclick="createPO(${x.id},${x.recommended_order})">Place order</button></td></tr>`).join('') || '<tr><td colspan="8"><div class="empty">No uncovered procurement recommendations at current settings.</div></td></tr>'}</tbody></table></div></div><div class="panel" style="margin-top:16px"><div class="panel-head"><h3>Purchase orders</h3><span>${orders.length} records</span></div><div class="table-wrap"><table><thead><tr><th>Order</th><th>Supplier</th><th>Created</th><th>Expected</th><th>Status</th><th>Priority</th><th>Value</th></tr></thead><tbody>${orders.map(o=>`<tr><td><strong>${o.order_number}</strong></td><td>${o.supplier_name || 'Not assigned'}</td><td>${o.created_at?.replace('T',' ').slice(0,16) || '—'}</td><td>${o.expected_delivery || '—'}</td><td>${badge(o.status)}</td><td>${badge(o.priority)}</td><td>${money(o.total_value)}</td></tr>`).join('') || '<tr><td colspan="7"><div class="empty">No purchase orders yet.</div></td></tr>'}</tbody></table></div></div>`;
  } catch (e) {
    $('#appContent').innerHTML = `<div class="panel"><div class="empty"><strong>Procurement data could not load.</strong><br><span class="muted">${e.message}</span><div style="margin-top:12px"><button class="btn" onclick="procurementPage()">Retry</button> <a class="btn" href="/api/health" target="_blank">Check API health</a></div></div></div>`;
  }
}

async function createPO(inventoryId, qty) {
  if (!confirm(`Place a purchase order for ${qty} units?`)) return;
  try {
    const r = await api('/api/procurement',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({inventory_id:inventoryId,quantity:qty,priority:'HIGH'})});
    alert(`Order ${r.order_number} placed.`);
    await procurementPage();
  } catch(e) { alert(e.message); }
}

async function supplyChainPage() {
  renderPage('Supply Chain Traceability', 'Batch genealogy, storage locations and supply-chain events', '<div class="panel"><div class="empty">Loading batches…</div></div>');
  try {
    const results = await Promise.allSettled([api('/api/batches'), api('/api/storage'), api('/api/suppliers')]);
    const [batchResult, storageResult, supplierResult] = results;
    const batches = batchResult.status === 'fulfilled' ? batchResult.value : [];
    const storage = storageResult.status === 'fulfilled' ? storageResult.value : {locations: [], temperature_logs: []};
    const suppliers = supplierResult.status === 'fulfilled' ? supplierResult.value : [];

    const failures = [];
    if (batchResult.status === 'rejected') failures.push(`Batch register: ${batchResult.reason.message}`);
    if (storageResult.status === 'rejected') failures.push(`Storage monitoring: ${storageResult.reason.message}`);
    if (supplierResult.status === 'rejected') failures.push(`Suppliers: ${supplierResult.reason.message}`);
    const warning = failures.length ? `<div class="notice warning" style="margin-bottom:16px"><strong>Some supply-chain data is unavailable.</strong><br>${failures.join('<br>')}</div>` : '';
    $('#appContent').innerHTML = warning + `<div class="page-head"><div><h2>Traceability & storage</h2><p>Track what arrived, where it is stored, and what information is actually verified.</p></div></div><div class="grid-3"><div class="panel"><div class="panel-head"><h3>Storage locations</h3><span>${storage.locations.length}</span></div>${storage.locations.map(l=>`<div class="risk-row"><div><div class="name">${l.location_name}</div><div class="small">${l.location_code} · ${l.location_type}</div></div>${l.monitoring_enabled ? badge('MONITORED') : badge('MANUAL')}</div>`).join('')}</div><div class="panel"><div class="panel-head"><h3>Suppliers</h3><span>${suppliers.length}</span></div>${suppliers.map(s=>`<div class="risk-row"><div><div class="name">${s.supplier_name}</div><div class="small">Lead time ${s.lead_time_days} days</div></div>${badge(s.data_status || 'DEMO')}</div>`).join('')}</div><div class="panel"><div class="panel-head"><h3>Data provenance</h3><span>Policy</span></div><div class="notice">Verified product/label data should be distinguished from hospital-entered and synthetic demonstration data. Origin is never inferred from a supplier name.</div></div></div><div class="panel" style="margin-top:16px"><div class="panel-head"><h3>Batch register</h3><span>FEFO view</span></div><div class="table-wrap"><table><thead><tr><th>Medicine</th><th>Batch</th><th>Current</th><th>Expiry</th><th>Supplier</th><th>Storage</th><th>Origin</th><th>Status</th></tr></thead><tbody>${batches.map(b=>`<tr><td><strong>${b.medicine_name || (b.batch_id ? 'Inventory #'+b.inventory_id : '—')}</strong></td><td>${b.batch_number}</td><td>${num(b.quantity_current)}</td><td>${b.expiry_date}</td><td>${b.supplier_name || 'Not recorded'}</td><td>${b.location_name || 'Not recorded'}</td><td>${b.origin_country || 'Not recorded'}</td><td>${badge(b.data_status || 'DEMO')}</td></tr>`).join('')}</tbody></table></div></div><div class="grid-2" style="margin-top:16px"><div class="panel"><div class="panel-head"><h3>Storage monitoring</h3><span>Recent logs</span></div>${storage.temperature_logs.length?`<div class="table-wrap"><table style="min-width:0"><thead><tr><th>Time</th><th>Location</th><th>Temp</th><th>Humidity</th><th>Status</th></tr></thead><tbody>${storage.temperature_logs.map(t=>`<tr><td>${t.logged_at}</td><td>${t.location_name}</td><td>${t.temperature_c ?? '—'} °C</td><td>${t.humidity_rh ?? '—'}%</td><td>${t.status || '—'}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">No sensor logs yet. The schema is ready for IoT/sensor ingestion.</div>'}</div><div class="panel"><div class="panel-head"><h3>FEFO principle</h3><span>Operational rule</span></div><div class="notice">When multiple batches of the same product are available, the batch with the earliest expiry should normally be prioritized for issue/distribution, subject to quality status and organizational procedure.</div></div></div>`;
  } catch (e) {
    $('#appContent').innerHTML = `<div class="panel"><div class="empty"><strong>Supply chain data could not load.</strong><br><span class="muted">${e.message}</span><div style="margin-top:12px"><button class="btn" onclick="supplyChainPage()">Retry</button> <a class="btn" href="/api/health" target="_blank">Check API health</a></div></div></div>`;
  }
}

function settingsPage() {
  renderPage('System & Data Policy', 'Prototype controls and provenance settings', `<div class="page-head"><div><h2>System configuration</h2><p>These controls document how MedSupplyAI treats data and predictions.</p></div></div><div class="grid-2"><div class="panel"><div class="panel-head"><h3>Model assumptions</h3><span>Current</span></div><div class="risk-list"><div class="risk-row"><div><div class="name">Forecast algorithm</div><div class="small">Random Forest Regression</div></div>${badge('AI-DERIVED')}</div><div class="risk-row"><div><div class="name">Forecast horizon</div><div class="small">30 days</div></div>${badge('CONFIGURED')}</div><div class="risk-row"><div><div class="name">Reorder policy</div><div class="small">Order-up-to maximum when at/below reorder point</div></div>${badge('RULE')}</div><div class="risk-row"><div><div class="name">Service level assumption</div><div class="small">95% z-value = 1.645 for safety-stock estimate</div></div>${badge('ASSUMPTION')}</div></div></div><div class="panel"><div class="panel-head"><h3>Data provenance</h3><span>Required discipline</span></div><div class="notice">Use VERIFIED only when a traceable external document or authorized operational record supports the field. Use DEMO for synthetic data. Use USER ENTERED for operator-provided values. Use AI-DERIVED for model outputs.</div><div class="notice" style="margin-top:12px">This prototype is not a certified pharmaceutical inventory, quality-management or clinical system. It is an engineering decision-support demonstration.</div></div></div><div class="panel" style="margin-top:16px"><div class="panel-head"><h3>Real-data integration roadmap</h3><span>Recommended next stage</span></div><ol><li>Import verified product metadata and label fields from a documented public source.</li><li>Capture batch/lot, expiry and manufacturer information from authorized records or product packaging.</li><li>Ingest actual receipts/issues from a hospital information or warehouse management system.</li><li>Add barcode/2D-code scanning for GTIN + batch + expiry where applicable.</li><li>Add sensor ingestion for monitored storage locations.</li><li>Replace demo consumption history with validated historical operational data and evaluate forecasting accuracy.</li></ol></div>`);
}

document.addEventListener('DOMContentLoaded', async () => {
  try {
    if (location.pathname === '/' || location.pathname === '/index.html') await dashboardPage();
    else if (location.pathname === '/inventory.html') await inventoryPage();
    else if (location.pathname === '/alerts.html') await alertsPage();
    else if (location.pathname === '/prediction.html') await predictionPage();
    else if (location.pathname === '/supply-chain.html') await supplyChainPage();
    else if (location.pathname === '/procurement.html') await procurementPage();
    else if (location.pathname === '/settings.html') settingsPage();
  } catch (e) {
    if ($('#appContent')) $('#appContent').innerHTML = `<div class="panel"><div class="empty">${e.message}<br><span class="muted">Check that the Flask backend and MySQL are running.</span></div></div>`;
  }
});
