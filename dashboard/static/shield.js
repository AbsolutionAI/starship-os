/* Shield — multi-node telemetry from remote agents */

async function renderShieldView(area) {
  showLoading(area);
  const data = await api('/api/shield/stats');
  if (!data || data.status === 'no_data') {
    showNoData(area, 'Shield', 'No telemetry from remote agents yet. Deploy staragent on endpoints.');
    return;
  }

  const agg = data.aggregate || {};
  const nodes = data.nodes || [];
  const online = nodes.filter(n => n.tables && n.tables.status);

  area.innerHTML = `
    <div class="view-header">
      <h2><span>Shield</span> · Fleet Security Telemetry</h2>
      <span class="muted mono" style="font-size:11px">${escapeHtml(data.timestamp || '')}</span>
    </div>

    <div class="health-grid">
      <div class="health-card glass ${agg.cpu_avg > 80 ? 'bad' : agg.cpu_avg > 60 ? 'warn' : 'good'}">
        <div class="label">Avg CPU</div>
        <div class="value">${agg.cpu_avg || 0}%</div>
      </div>
      <div class="health-card glass ${agg.memory_percent_avg > 80 ? 'bad' : agg.memory_percent_avg > 60 ? 'warn' : 'good'}">
        <div class="label">Avg Memory</div>
        <div class="value">${agg.memory_percent_avg || 0}%</div>
      </div>
      <div class="health-card glass ${agg.disk_percent_avg > 80 ? 'bad' : agg.disk_percent_avg > 60 ? 'warn' : 'good'}">
        <div class="label">Avg Disk</div>
        <div class="value">${agg.disk_percent_avg || 0}%</div>
      </div>
      <div class="health-card glass ${online.length > 0 ? 'good' : 'warn'}">
        <div class="label">Nodes Online</div>
        <div class="value">${online.length}/${data.total_nodes}</div>
      </div>
      <div class="health-card glass good">
        <div class="label">Peak CPU</div>
        <div class="value">${agg.cpu_max || 0}%</div>
      </div>
    </div>

    <div class="section glass">
      <div class="panel-title">Endpoints (${nodes.length})</div>
      <div style="padding:0 14px 14px">
        ${nodes.length ? `<table>
          <tr><th>Hostname</th><th>CPU</th><th>Memory</th><th>Disk</th><th>Network</th><th>Last Seen</th></tr>
          ${nodes.map(n => {
            const s = (n.tables && n.tables.status) || {};
            const cpu = typeof s.cpu === 'number' ? s.cpu.toFixed(1) + '%' : '—';
            const mem = typeof s.memory_used === 'number' && typeof s.memory_total === 'number'
              ? ((s.memory_used / s.memory_total) * 100).toFixed(1) + '%' : '—';
            const disk = typeof s.disk_used === 'number' && typeof s.disk_total === 'number'
              ? ((s.disk_used / s.disk_total) * 100).toFixed(1) + '%' : '—';
            const net = s.rx_bytes != null || s.tx_bytes != null
              ? '↓' + formatBytes(s.rx_bytes || 0) + ' ↑' + formatBytes(s.tx_bytes || 0) : '—';
            return `<tr>
              <td><strong>${escapeHtml(n.hostname)}</strong></td>
              <td><span class="badge ${parseFloat(cpu) > 80 ? 'danger' : parseFloat(cpu) > 60 ? 'warn' : ''}">${cpu}</span></td>
              <td>${mem}</td>
              <td>${disk}</td>
              <td class="mono" style="font-size:10px">${net}</td>
              <td class="muted mono" style="font-size:10px">${escapeHtml(n.last_seen || '')}</td>
            </tr>`;
          }).join('')}
        </table>` : '<div class="empty-state" style="padding:16px"><p>No endpoints reporting</p></div>'}
      </div>
    </div>

    <div class="section glass">
      <div class="panel-title">Per-Node Detail</div>
      <div style="padding:0 14px 14px">
        ${online.length ? online.map(n => {
          const s = n.tables.status || {};
          const cpu = typeof s.cpu === 'number' ? s.cpu.toFixed(1) : '—';
          const memUsed = formatBytes(s.memory_used || 0);
          const memTotal = formatBytes(s.memory_total || 0);
          const diskUsed = formatBytes(s.disk_used || 0);
          const diskTotal = formatBytes(s.disk_total || 0);
          return `<div class="plant-card glass" style="margin-bottom:8px">
            <div class="plant-name">${escapeHtml(n.hostname)}</div>
            <div class="plant-meta">
              <span>CPU: ${cpu}%</span>
              <span>RAM: ${memUsed} / ${memTotal}</span>
              <span>Disk: ${diskUsed} / ${diskTotal}</span>
              <span>RX: ${formatBytes(s.rx_bytes || 0)}</span>
              <span>TX: ${formatBytes(s.tx_bytes || 0)}</span>
            </div>
            <div class="plant-meta" style="margin-top:4px">
              <span class="badge">${Object.keys(n.tables).length} table(s)</span>
              <span class="muted mono" style="font-size:10px">${escapeHtml(n.last_seen || '')}</span>
            </div>
          </div>`;
        }).join('') : '<div class="empty-state" style="padding:16px"><p>No nodes reporting</p></div>'}
      </div>
    </div>
  `;
}
