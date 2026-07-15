/* ── Agents View ───────────────────────────────────────────────────────── */

async function renderAgentView(area, data) {
  showLoading(area);
  const result = await api('/api/agents');
  if (!result || !result.agents) { showError(area, 'Failed to load agents'); return; }
  S.agents = result.agents;

  const statusIcon = { online: '🟢', busy: '🟡', offline: '🔴' };

  area.innerHTML = `
    <div class="section-title">Agents (${S.agents.length})</div>
    <div class="agent-list">
      ${S.agents.map(a => `
        <div class="agent-card" data-agent="${escapeHtml(a.name)}">
          <div class="agent-status-indicator">
            <span class="status-dot ${a.status === 'online' ? 'green' : a.status === 'busy' ? 'yellow' : 'red'}"></span>
          </div>
          <div class="agent-info">
            <div class="agent-name">${escapeHtml(a.name)}</div>
            <div class="agent-meta">${escapeHtml(a.model)} &middot; ${durationStr(a.uptime)} uptime &middot; v${escapeHtml(a.version)}</div>
          </div>
          <div class="agent-actions">
            <button class="btn btn-sm btn-outline chat-agent" data-agent="${escapeHtml(a.name)}">Chat</button>
            <button class="btn btn-sm btn-outline view-agent" data-agent="${escapeHtml(a.name)}">Details</button>
          </div>
        </div>
      `).join('')}
    </div>
  `;

  area.querySelectorAll('.chat-agent').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      renderView('chat', { agent: btn.dataset.agent });
    });
  });

  area.querySelectorAll('.agent-card, .view-agent').forEach(el => {
    el.addEventListener('click', () => {
      const agentName = el.dataset.agent || el.closest('.agent-card')?.dataset.agent;
      if (agentName) showAgentDetail(agentName);
    });
  });
}

async function showAgentDetail(name) {
  const result = await api(`/api/agent/${encodeURIComponent(name)}`);
  if (!result || !result.agent) { showToast('Failed to load agent details', 3000, 'error'); return; }
  const a = result.agent;
  const activity = result.recent_activity || [];

  setRightPanel(`
    <div class="detail-section">
      <div class="detail-section-title">Agent Info</div>
      <div class="detail-field"><span class="field-label">Name</span><span class="field-value">${escapeHtml(a.name)}</span></div>
      <div class="detail-field"><span class="field-label">Status</span><span class="field-value" style="color:${a.status === 'online' ? '#00e676' : a.status === 'busy' ? '#ffd600' : '#ff5252'}">${capitalize(a.status)}</span></div>
      <div class="detail-field"><span class="field-label">Model</span><span class="field-value">${escapeHtml(a.model)}</span></div>
      <div class="detail-field"><span class="field-label">Version</span><span class="field-value">${escapeHtml(a.version)}</span></div>
      <div class="detail-field"><span class="field-label">Uptime</span><span class="field-value">${durationStr(a.uptime)}</span></div>
      <div class="detail-field"><span class="field-label">Last Active</span><span class="field-value">${formatDate(a.last_active)}</span></div>
    </div>
    <div class="detail-section">
      <div class="detail-section-title">Capabilities</div>
      <div>${(a.capabilities || []).map(c => `<span class="detail-capability">${escapeHtml(c)}</span>`).join('')}</div>
    </div>
    <div class="detail-section">
      <div class="detail-section-title">Skills</div>
      <div>${(a.skills || []).map(s => `<span class="detail-capability">${escapeHtml(s)}</span>`).join('')}</div>
    </div>
    <div class="detail-section">
      <div class="detail-section-title">Configuration</div>
      ${Object.entries(a.config || {}).map(([k, v]) =>
        `<div class="detail-field"><span class="field-label">${escapeHtml(k)}</span><span class="field-value">${escapeHtml(String(v))}</span></div>`
      ).join('')}
    </div>
    <div class="detail-section">
      <div class="detail-section-title">Recent Activity</div>
      ${activity.length ? activity.slice(0, 10).map(e =>
        `<div class="log-entry"><span class="log-time">${formatTime(e.timestamp)}</span> <span class="log-msg">${escapeHtml(e.message || e.type)}</span></div>`
      ).join('') : '<div style="color:#666;font-size:12px">No recent activity</div>'}
    </div>
    <div style="margin-top:16px">
      <button class="btn btn-primary chat-from-detail" data-agent="${escapeHtml(a.name)}" style="width:100%">Chat with ${escapeHtml(a.name)}</button>
    </div>
  `);

  document.querySelector('.chat-from-detail')?.addEventListener('click', () => {
    renderView('chat', { agent: name });
  });
}
