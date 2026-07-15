/* ── Incidents View ─────────────────────────────────────────────────────── */

async function renderIncidentsView(area) {
  showLoading(area);
  const result = await api('/api/incidents');
  const runbooksResult = await api('/api/runbooks');
  if (!result || !result.incidents) { showError(area, 'Failed to load incidents'); return; }
  S.incidents = result.incidents;
  const runbooks = runbooksResult?.runbooks || [];

  const severityColors = { critical: '#ff5252', high: '#ff9100', medium: '#ffd600', low: '#69db7c' };

  const openIncidents = S.incidents.filter(i => i.status !== 'resolved');
  const resolvedIncidents = S.incidents.filter(i => i.status === 'resolved');

  area.innerHTML = `
    <div class="section-title">Active Incidents (${openIncidents.length})</div>
    <div id="incident-list">
      ${openIncidents.length ? openIncidents.map(i => `
        <div class="incident-card severity-${i.severity}" data-id="${escapeHtml(i.id)}">
          <div class="incident-header">
            <span class="incident-id">${escapeHtml(i.id)}</span>
            <span class="severity-badge ${i.severity}">${capitalize(i.severity)}</span>
            <span class="status-badge ${i.status}">${i.status === 'in_progress' ? 'In Progress' : capitalize(i.status)}</span>
            <span style="font-size:11px;color:#888;margin-left:auto">${formatDate(i.updated)}</span>
          </div>
          <div class="incident-title">${escapeHtml(i.title)}</div>
          <div style="font-size:12px;color:#888;margin-top:4px">${escapeHtml(i.description)}</div>
          <div style="display:flex;gap:8px;margin-top:8px">
            ${i.status !== 'resolved' ? `<button class="btn btn-sm btn-danger resolve-incident" data-id="${escapeHtml(i.id)}">Resolve</button>` : ''}
          </div>
        </div>
      `).join('') : '<div class="empty-state"><div class="empty-text">No active incidents</div></div>'}
    </div>

    ${resolvedIncidents.length ? `
      <div class="section-title" style="margin-top:24px">Resolved (${resolvedIncidents.length})</div>
      ${resolvedIncidents.map(i => `
        <div class="incident-card severity-${i.severity}" data-id="${escapeHtml(i.id)}" style="opacity:0.6">
          <div class="incident-header">
            <span class="incident-id">${escapeHtml(i.id)}</span>
            <span class="severity-badge ${i.severity}">${capitalize(i.severity)}</span>
            <span class="status-badge resolved">Resolved</span>
          </div>
          <div class="incident-title">${escapeHtml(i.title)}</div>
        </div>
      `).join('')}
    ` : ''}

    ${runbooks.length ? `
      <div class="section-title" style="margin-top:24px">Runbooks</div>
      ${runbooks.map(rb => `
        <div class="runbook-card">
          <div class="runbook-title">${escapeHtml(rb.name)}</div>
          <div class="runbook-desc">${escapeHtml(rb.description)}</div>
          ${(rb.steps || []).map(s => `
            <div class="runbook-step step-${s.status}">
              <div class="step-num">${s.order}</div>
              <div class="step-info">
                <div class="step-title">${escapeHtml(s.title)}</div>
                <div class="step-desc">${escapeHtml(s.description)}</div>
              </div>
            </div>
          `).join('')}
        </div>
      `).join('')}
    ` : ''}
  `;

  area.querySelectorAll('.resolve-incident').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const id = btn.dataset.id;
      const confirmed = await showConfirmDialog(`Resolve incident ${id}?`);
      if (!confirmed) return;
      const result = await api('/api/incidents/resolve', { method: 'POST', body: { id } });
      if (result) {
        showToast(`Incident ${id} resolved`, 3000, 'success');
        renderIncidentsView(area);
        renderSidebar();
      }
    });
  });
}
