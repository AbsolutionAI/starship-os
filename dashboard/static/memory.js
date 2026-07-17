/* Memory — agent conversation history */

async function renderMemoryView(area) {
  showLoading(area);
  const res = await api('/api/memory');
  const agents = (res && res.agents) || {};
  const total = res ? res.total_entries : 0;

  const agentNames = Object.keys(agents);

  if (!agentNames.length) {
    showNoData(area, 'Memory', 'No conversation history yet. Start a conversation with an agent via Officer Check-In.');
    return;
  }

  area.innerHTML = `
    <div class="view-header">
      <h2><span>Memory</span> · Agent Conversation History</h2>
      <span class="muted">${total} entr${total === 1 ? 'y' : 'ies'} · ${escapeHtml(res.timestamp || '')}</span>
    </div>
    ${agentNames.map(agent => {
      const entries = agents[agent] || [];
      return `
        <div class="section glass" style="margin-bottom:12px">
          <div class="panel-title" style="display:flex;align-items:center;gap:8px">
            <span>${escapeHtml(agent)}</span>
            <span class="badge" style="font-size:10px">${entries.length}</span>
          </div>
          <div style="padding:0 14px 14px">
            ${entries.length ? entries.map(e => `
              <div style="padding:8px 10px;margin-bottom:6px;border:1px solid var(--color-glass-edge);border-radius:6px;background:var(--color-glass)">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
                  <span class="badge" style="font-size:9px">${escapeHtml(e.role || 'message')}</span>
                  <span class="mono muted" style="font-size:10px">${escapeHtml((e.timestamp || '').substring(11, 19))}</span>
                  ${e.command ? `<code class="mono" style="font-size:10px;background:rgba(0,0,0,0.2);padding:2px 6px;border-radius:3px">${escapeHtml(e.command)}</code>` : ''}
                </div>
                <div class="mono" style="font-size:11px;line-height:1.5;white-space:pre-wrap;word-break:break-word">${escapeHtml(e.summary || '')}</div>
              </div>
            `).join('') : '<div class="muted" style="padding:8px">No entries</div>'}
          </div>
        </div>
      `;
    }).join('')}
  `;
}
