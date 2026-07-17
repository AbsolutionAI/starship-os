/* Telemetry Log — per-node telemetry snapshots */

async function renderTelemetryView(area) {
  showLoading(area);
  const res = await api('/api/telemetry/recent');
  const nodes = (res && res.nodes) || [];

  if (!nodes.length) {
    showNoData(area, 'Telemetry Log', 'No endpoints have reported telemetry yet. Deploy StarAgent on remote machines.');
    return;
  }

  const now = Date.now();

  area.innerHTML = `
    <div class="view-header">
      <h2><span>Telemetry Log</span> · Node Telemetry</h2>
      <span class="muted">${nodes.length} node(s) · ${escapeHtml(res.timestamp || '')}</span>
    </div>
    <div class="section glass" style="padding:0 0 8px">
      <table>
        <tr>
          <th>Hostname</th>
          <th>CPU</th>
          <th>Memory</th>
          <th>Disk</th>
          <th>↓ RX</th>
          <th>↑ TX</th>
          <th>Tables</th>
          <th>Last Seen</th>
        </tr>
        ${nodes.map(n => {
          const age = n.last_seen ? Math.round((now - new Date(n.last_seen).getTime()) / 1000) : 999;
          const stale = age > 60;
          const cpu = typeof n.cpu === 'number' ? n.cpu.toFixed(1) + '%' : '—';
          const mem = typeof n.memory_percent === 'number' ? n.memory_percent.toFixed(1) + '%' : '—';
          const disk = typeof n.disk_percent === 'number' ? n.disk_percent.toFixed(1) + '%' : '—';
          const tables = (n.tables && n.tables.length) ? n.tables.join(', ') : '—';
          const ageStr = age < 10 ? 'just now' : age < 60 ? age + 's ago' : Math.floor(age / 60) + 'm ago';
          return `<tr style="${stale ? 'opacity:0.6' : ''}">
            <td><strong>${escapeHtml(n.hostname)}</strong> ${stale ? '<span class="badge" style="background:#e06c75">stale</span>' : ''}</td>
            <td><span class="badge ${parseFloat(cpu) > 80 ? 'danger' : parseFloat(cpu) > 60 ? 'warn' : ''}">${cpu}</span></td>
            <td>${mem}</td>
            <td>${disk}</td>
            <td class="mono" style="font-size:11px">${formatBytes(n.rx_bytes || 0)}</td>
            <td class="mono" style="font-size:11px">${formatBytes(n.tx_bytes || 0)}</td>
            <td class="mono" style="font-size:10px">${escapeHtml(tables)}</td>
            <td class="mono muted" style="font-size:10px">${ageStr}</td>
          </tr>`;
        }).join('')}
      </table>
    </div>
  `;
}
