/* Incidents — live from agent failures, stale endpoints, system pressure */

async function renderIncidentsView(area) {
  showLoading(area);
  const res = await api('/api/incidents');
  const list = (res && res.incidents) || [];
  const total = res ? res.total : 0;
  S.incidents = list;

  const bySource = {};
  list.forEach(i => {
    const s = i.source || 'other';
    if (!bySource[s]) bySource[s] = [];
    bySource[s].push(i);
  });

  const sourceLabels = { agent: 'Agents', telemetry: 'Endpoints', system: 'Hub System' };
  const severityOrder = { critical: 0, high: 1, warn: 2, info: 3 };

  if (!list.length) {
    area.innerHTML = `
      <div class="view-header">
        <h2><span>Incidents</span></h2>
        <span class="muted">All clear</span>
      </div>
      <div class="section glass">
        <div class="empty-state" style="padding:24px">
          <div class="icon" style="font-size:28px">✓</div>
          <h3>No active incidents</h3>
          <p>All agents online, all systems nominal.</p>
        </div>
      </div>
    `;
    return;
  }

  const severityIcon = { critical: '🔴', high: '🟠', warn: '🟡', info: '🔵' };

  list.sort((a, b) => (severityOrder[a.severity] || 9) - (severityOrder[b.severity] || 9));

  area.innerHTML = `
    <div class="view-header">
      <h2><span>Incidents</span></h2>
      <span class="muted">${total} open</span>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;margin-bottom:16px">
      ${Object.entries(bySource).map(([src, items]) => `
        <div class="health-card glass ${items.some(i => i.severity === 'critical') ? 'bad' : items.some(i => i.severity === 'high') ? 'warn' : 'good'}">
          <div class="label">${sourceLabels[src] || src}</div>
          <div class="value">${items.length}</div>
          <div style="font-size:11px;display:flex;gap:4px;flex-wrap:wrap;margin-top:4px">
            ${['critical','high','warn','info'].filter(s => items.some(i => i.severity === s)).map(s =>
              `<span style="font-size:10px">${severityIcon[s]||''} ${items.filter(i => i.severity === s).length} ${s}</span>`
            ).join('')}
          </div>
        </div>
      `).join('')}
    </div>
    <div class="section glass" style="padding:0 0 8px">
      <table>
        <tr><th>Severity</th><th>Title</th><th>Source</th><th>Status</th><th>Time</th></tr>
        ${list.map(i => `<tr>
          <td><span class="badge ${i.severity === 'critical' ? 'danger' : i.severity === 'high' ? 'warn' : ''}">${escapeHtml(i.severity || '—')}</span></td>
          <td><strong>${escapeHtml(i.title || '')}</strong><br><span class="muted" style="font-size:11px">${escapeHtml(i.summary || '')}</span></td>
          <td class="muted" style="font-size:11px">${escapeHtml(i.source || '')}</td>
          <td><span class="badge">${escapeHtml(i.status || '')}</span></td>
          <td class="mono muted" style="font-size:10px">${escapeHtml((i.timestamp || '').substring(11, 19))}</td>
        </tr>`).join('')}
      </table>
    </div>
  `;
}
