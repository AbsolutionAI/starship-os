/* ── Panel Views: Policy, Memory, Skills, Shield, Telemetry, Accounts ──── */

// ── Policy View ──────────────────────────────────────────────────────────

async function renderPolicyView(area) {
  showLoading(area);
  const result = await api('/api/policy');
  if (!result || !result.policy) { showError(area, 'Failed to load policy'); return; }
  const policy = result.policy;

  area.innerHTML = `
    <div class="section-title">Policy Management</div>
    <p style="font-size:12px;color:#888;margin-bottom:16px">
      Three-tier policy: System (read-only) &rarr; Service &rarr; User (overridable).
      Changes to user policy take effect immediately.
    </p>

    <div id="policy-check-area" style="margin-bottom:20px">
      <div style="display:flex;gap:8px">
        <input type="text" id="policy-check-input" placeholder="Enter a command to check against policy..." style="flex:1;background:#25264a;border:1px solid #3d3f6b;border-radius:6px;padding:8px 12px;color:#fff">
        <button class="btn btn-primary" id="policy-check-btn">Check</button>
      </div>
      <div id="policy-check-result" style="margin-top:8px"></div>
    </div>

    ${['system', 'service', 'user'].map(level => `
      <div class="policy-level">
        <div class="policy-level-title">
          <span class="policy-badge ${level}">${capitalize(level)}</span> Policy
        </div>
        ${Object.entries(policy[level] || {}).map(([key, value]) => `
          <div class="policy-item">
            <span class="policy-key">${escapeHtml(key)}</span>:
            <span class="${typeof value === 'boolean' ? 'policy-bool' : typeof value === 'string' ? 'policy-value' : Array.isArray(value) ? 'policy-value' : 'policy-value'}">
              ${escapeHtml(Array.isArray(value) ? '[' + value.join(', ') + ']' : String(value))}
            </span>
          </div>
        `).join('')}
      </div>
    `).join('')}

    <div class="section-title">User Policy Editor</div>
    <div id="user-policy-editor">
      <div style="margin-bottom:12px">
        <label style="display:flex;align-items:center;gap:8px;font-size:13px;color:#ccc">
          <input type="checkbox" id="policy-override" ${policy.user?.override_policy ? 'checked' : ''}>
          Override system/service policy
        </label>
      </div>
      <div style="margin-bottom:12px">
        <div style="font-size:12px;color:#888;margin-bottom:6px">Custom Rules (JSON)</div>
        <textarea id="policy-rules-editor" style="width:100%;background:#13142a;border:1px solid #3d3f6b;border-radius:6px;padding:10px;color:#fff;font-family:monospace;font-size:12px;min-height:120px">${escapeHtml(JSON.stringify(policy.user?.custom_rules || [], null, 2))}</textarea>
      </div>
      <button class="btn btn-primary" id="policy-save-btn">Save Policy</button>
    </div>
  `;

  document.getElementById('policy-check-btn').addEventListener('click', async () => {
    const input = document.getElementById('policy-check-input');
    const resultDiv = document.getElementById('policy-check-result');
    const cmd = input.value.trim();
    if (!cmd) { resultDiv.innerHTML = '<span style="color:#888;font-size:12px">Enter a command to check</span>'; return; }
    const res = await api('/api/policy/check', { method: 'POST', body: { command: cmd } });
    if (res) {
      resultDiv.innerHTML = `<span style="color:${res.blocked ? '#ff5252' : '#00e676'};font-size:13px;font-weight:600">
        ${res.blocked ? '&#10060; BLOCKED' : '&#10004; ALLOWED'}
      </span>
      ${res.reasons?.length ? '<div style="font-size:12px;color:#888;margin-top:4px">' + res.reasons.map(r => escapeHtml(r)).join('<br>') + '</div>' : ''}`;
    }
  });

  document.getElementById('policy-save-btn').addEventListener('click', async () => {
    try {
      const rules = JSON.parse(document.getElementById('policy-rules-editor').value);
      const override = document.getElementById('policy-override').checked;
      const res = await api('/api/policy', {
        method: 'POST',
        body: { rules, override_policy: override },
      });
      if (res) showToast('Policy saved', 2000, 'success');
    } catch (e) {
      showToast('Invalid JSON in rules', 3000, 'error');
    }
  });
}

// ── Memory View ──────────────────────────────────────────────────────────

async function renderMemoryView(area) {
  showLoading(area);
  const result = await api('/api/memory');
  if (!result || !result.types) { showError(area, 'Failed to load memory'); return; }
  S.memory = result.types;
  let currentType = 'all';

  area.innerHTML = `
    <div class="section-title">Memory Browser</div>
    <p style="font-size:12px;color:#888;margin-bottom:16px">Browse all 7 memory types. Search across stores or view by type.</p>
    <div class="memory-search">
      <input type="text" id="memory-search-input" placeholder="Search memory..." style="flex:1;background:#25264a;border:1px solid #3d3f6b;border-radius:6px;padding:8px 12px;color:#fff">
      <button class="btn btn-primary" id="memory-search-btn">Search</button>
    </div>
    <div class="memory-tabs" id="memory-tabs">
      <button class="memory-tab active" data-type="all">All <span class="mem-count">${result.types.reduce((s, t) => s + t.count, 0)}</span></button>
      ${result.types.map(t => `
        <button class="memory-tab" data-type="${escapeHtml(t.type)}">${capitalize(t.type)} <span class="mem-count">${t.count}</span></button>
      `).join('')}
    </div>
    <div id="memory-results"></div>
  `;

  async function loadMemory(type) {
    const resultsDiv = document.getElementById('memory-results');
    currentType = type;
    resultsDiv.innerHTML = '<div class="loading">Loading...</div>';
    let results;
    if (type === 'all') {
      const allResults = [];
      for (const mt of S.memory) {
        const r = await api('/api/memory/search', { method: 'POST', body: { type: mt.type } });
        if (r?.results) allResults.push(...r.results);
      }
      results = { results: allResults, total: allResults.length };
    } else {
      results = await api('/api/memory/search', { method: 'POST', body: { type } });
    }
    if (!results || !results.results) {
      resultsDiv.innerHTML = '<div class="empty-state"><div class="empty-text">No results</div></div>';
      return;
    }
    resultsDiv.innerHTML = results.results.map(r =>
      `<div class="memory-result">
        <span class="mem-type-badge">${escapeHtml(r.type)}</span>
        <div class="mem-content">${escapeHtml(r.content)}</div>
        <div class="mem-confidence">Confidence: ${(r.confidence * 100).toFixed(0)}% &middot; ${formatDate(r.created)}</div>
      </div>`
    ).join('') || '<div class="empty-state"><div class="empty-text">No results</div></div>';
  }

  document.getElementById('memory-tabs').addEventListener('click', (e) => {
    const tab = e.target.closest('.memory-tab');
    if (!tab) return;
    document.querySelectorAll('.memory-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    loadMemory(tab.dataset.type);
  });

  document.getElementById('memory-search-btn').addEventListener('click', async () => {
    const query = document.getElementById('memory-search-input').value.trim();
    if (!query) { loadMemory(currentType); return; }
    const resultsDiv = document.getElementById('memory-results');
    resultsDiv.innerHTML = '<div class="loading">Searching...</div>';
    const results = await api('/api/memory/search', { method: 'POST', body: { query } });
    if (results?.results) {
      resultsDiv.innerHTML = results.results.map(r =>
        `<div class="memory-result">
          <span class="mem-type-badge">${escapeHtml(r.type)}</span>
          <div class="mem-content">${escapeHtml(r.content)}</div>
          <div class="mem-confidence">Confidence: ${(r.confidence * 100).toFixed(0)}%</div>
        </div>`
      ).join('') || '<div class="empty-state"><div class="empty-text">No matching memory entries</div></div>';
    }
  });

  // Load initial
  loadMemory('all');
}

// ── Skills View ──────────────────────────────────────────────────────────

async function renderSkillsView(area) {
  showLoading(area);
  const result = await api('/api/skills');
  if (!result || !result.skills) { showError(area, 'Failed to load skills'); return; }

  area.innerHTML = `
    <div class="section-title">Available Skills (${result.skills.length})</div>
    <div class="section-title" style="font-size:12px;color:#888;font-weight:400;margin-top:-8px;margin-bottom:16px">Skills are capabilities agents can invoke during task execution.</div>
    ${result.skills.map(s => `
      <div class="skill-card">
        <div class="skill-name">${escapeHtml(s.name)}</div>
        <div class="skill-desc">${escapeHtml(s.description)}</div>
        <div class="skill-meta">
          <span class="skill-version">v${escapeHtml(s.version)}</span>
          <span class="skill-agents">${escapeHtml((s.agents || []).join(', '))}</span>
        </div>
      </div>
    `).join('')}
  `;
}

// ── Shield View ──────────────────────────────────────────────────────────

async function renderShieldView(area) {
  showLoading(area);
  const statsResult = await api('/api/shield/stats');
  if (!statsResult || !statsResult.stats) { showError(area, 'Failed to load shield stats'); return; }
  const stats = statsResult.stats;

  area.innerHTML = `
    <div class="section-title">Droid Shield &mdash; Secret Scanner</div>
    <div class="shield-stats">
      <div class="shield-stat-card"><div class="stat-value">${(stats.total_scans || 0).toLocaleString()}</div><div class="stat-label">Total Scans</div></div>
      <div class="shield-stat-card"><div class="stat-value" style="color:#ff5252">${stats.secrets_found || 0}</div><div class="stat-label">Secrets Found</div></div>
      <div class="shield-stat-card"><div class="stat-value" style="color:#ffd600">${stats.false_positives || 0}</div><div class="stat-label">False Positives</div></div>
      <div class="shield-stat-card"><div class="stat-value">${Object.keys(stats.types_found || {}).length}</div><div class="stat-label">Secret Types</div></div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px">
      <div class="card">
        <div class="card-title">Secret Types Found</div>
        ${Object.entries(stats.types_found || {}).map(([k, v]) =>
          `<div class="detail-field"><span class="field-label">${escapeHtml(k)}</span><span class="field-value">${v}</span></div>`
        ).join('')}
      </div>
      <div class="card">
        <div class="card-title">By Severity</div>
        ${Object.entries(stats.scans_by_severity || {}).map(([k, v]) =>
          `<div class="detail-field"><span class="field-label" style="color:${k === 'critical' ? '#ff5252' : k === 'high' ? '#ff9100' : k === 'medium' ? '#ffd600' : '#69db7c'}">${capitalize(k)}</span><span class="field-value">${v}</span></div>`
        ).join('')}
      </div>
    </div>

    <div class="section-title">Manual Scan</div>
    <div class="shield-scan-area">
      <textarea id="shield-scan-text" placeholder="Paste text to scan for secrets, API keys, tokens, passwords..."></textarea>
      <div style="display:flex;gap:8px">
        <button class="btn btn-primary" id="shield-scan-btn">Scan Text</button>
      </div>
      <div id="shield-scan-results" style="margin-top:12px"></div>
    </div>
  `;

  document.getElementById('shield-scan-btn').addEventListener('click', async () => {
    const text = document.getElementById('shield-scan-text').value;
    if (!text.trim()) { showToast('Enter text to scan', 2000, 'warning'); return; }
    const resultsDiv = document.getElementById('shield-scan-results');
    resultsDiv.innerHTML = '<div class="loading">Scanning...</div>';
    const result = await api('/api/shield/scan', { method: 'POST', body: { text } });
    if (result) {
      if (result.found) {
        resultsDiv.innerHTML = '<div style="color:#ff5252;font-weight:600;margin-bottom:8px">&#9888; Secrets detected!</div>' +
          result.results.map(r =>
            `<div class="shield-result-item">
              <span><span class="result-severity ${r.severity}">${capitalize(r.severity)}</span> <span class="result-type">${escapeHtml(r.type)}</span></span>
              <span class="result-sample">${escapeHtml(r.sample)}</span>
            </div>`
          ).join('');
      } else {
        resultsDiv.innerHTML = '<div style="color:#00e676;font-weight:600">&#10004; No secrets found</div>';
      }
    }
  });
}

// ── Telemetry View ───────────────────────────────────────────────────────

async function renderTelemetryView(area) {
  showLoading(area);
  const [statsResult, recentResult] = await Promise.all([
    api('/api/telemetry/stats'),
    api('/api/telemetry/recent?limit=100'),
  ]);

  const stats = statsResult?.stats;
  const events = recentResult?.events || [];

  area.innerHTML = `
    <div class="section-title">Telemetry</div>
    <div class="dashboard-grid" style="grid-template-columns:repeat(auto-fill,minmax(160px,1fr))">
      <div class="card"><div class="card-title">Total Events</div><div class="card-value">${stats?.total_events || 0}</div></div>
      <div class="card"><div class="card-title">Event Types</div><div class="card-value">${Object.keys(stats?.by_type || {}).length}</div></div>
      <div class="card"><div class="card-title">Active Agents</div><div class="card-value">${Object.keys(stats?.by_agent || {}).length}</div></div>
      <div class="card"><div class="card-title">Time Range</div><div class="card-value" style="font-size:16px">${stats?.time_range_hours || 0}h</div></div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px">
      <div class="card">
        <div class="card-title">By Type</div>
        ${Object.entries(stats?.by_type || {}).map(([k, v]) =>
          `<div class="detail-field"><span class="field-label">${escapeHtml(k)}</span><span class="field-value">${v}</span></div>`
        ).join('')}
      </div>
      <div class="card">
        <div class="card-title">By Agent</div>
        ${Object.entries(stats?.by_agent || {}).map(([k, v]) =>
          `<div class="detail-field"><span class="field-label">${escapeHtml(k)}</span><span class="field-value">${v}</span></div>`
        ).join('')}
      </div>
    </div>

    <div class="section-title">Event Log</div>
    <div class="telemetry-filter">
      <select id="telem-type-filter">
        <option value="">All Types</option>
        ${[...new Set(events.map(e => e.type))].map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join('')}
      </select>
      <select id="telem-agent-filter">
        <option value="">All Agents</option>
        ${[...new Set(events.map(e => e.agent))].map(a => `<option value="${escapeHtml(a)}">${escapeHtml(a)}</option>`).join('')}
      </select>
    </div>
    <div id="telem-event-list" class="scroll-list" style="max-height:500px">
      ${events.map(e => `
        <div class="telemetry-event" data-type="${escapeHtml(e.type)}" data-agent="${escapeHtml(e.agent)}">
          <span class="evt-type">${escapeHtml(e.type)}</span>
          <span class="evt-msg">${escapeHtml(e.message)}</span>
          <span class="evt-agent">${escapeHtml(e.agent)}</span>
          <span class="evt-time">${formatTime(e.timestamp)}</span>
        </div>
      `).join('')}
    </div>
  `;

  function filterEvents() {
    const typeFilter = document.getElementById('telem-type-filter')?.value || '';
    const agentFilter = document.getElementById('telem-agent-filter')?.value || '';
    document.querySelectorAll('#telem-event-list .telemetry-event').forEach(el => {
      const typeMatch = !typeFilter || el.dataset.type === typeFilter;
      const agentMatch = !agentFilter || el.dataset.agent === agentFilter;
      el.style.display = typeMatch && agentMatch ? 'flex' : 'none';
    });
  }

  document.getElementById('telem-type-filter')?.addEventListener('change', filterEvents);
  document.getElementById('telem-agent-filter')?.addEventListener('change', filterEvents);
}

// ── Accounts View ────────────────────────────────────────────────────────

async function renderAccountsView(area) {
  showLoading(area);
  const result = await api('/api/accounts');
  if (!result || !result.accounts) { showError(area, 'Failed to load accounts'); return; }

  area.innerHTML = `
    <div class="section-title">Service Accounts (${result.accounts.length})</div>
    <p style="font-size:12px;color:#888;margin-bottom:16px">Manage service accounts and their permissions.</p>

    <div class="section-title" style="font-size:13px;margin-bottom:8px">Create New Account</div>
    <div class="account-form">
      <input type="text" id="acct-name" placeholder="Account name" style="flex:1;min-width:150px">
      <select id="acct-role" style="min-width:120px">
        <option value="ci/cd">CI/CD</option>
        <option value="deployment">Deployment</option>
        <option value="audit">Audit</option>
        <option value="monitoring">Monitoring</option>
        <option value="custom">Custom</option>
      </select>
      <button class="btn btn-primary" id="acct-create-btn">Create</button>
    </div>

    <div class="section-title" style="font-size:13px">Existing Accounts</div>
    <div id="account-list">
      ${result.accounts.map(a => `
        <div class="account-card">
          <span class="acct-name">${escapeHtml(a.name)}</span>
          <span class="acct-role">${escapeHtml(a.role)}</span>
          <span class="acct-status ${a.status}">${capitalize(a.status)}</span>
          <span style="font-size:11px;color:#888">${a.last_used ? `Last used: ${formatDate(a.last_used)}` : 'Never used'}</span>
          ${a.status === 'active' ? `<button class="btn btn-sm btn-danger revoke-acct" data-id="${escapeHtml(a.id)}">Revoke</button>` : ''}
        </div>
      `).join('')}
    </div>
  `;

  document.getElementById('acct-create-btn').addEventListener('click', async () => {
    const name = document.getElementById('acct-name').value.trim();
    const role = document.getElementById('acct-role').value;
    if (!name) { showToast('Enter an account name', 2000, 'warning'); return; }
    const res = await api('/api/accounts', { method: 'POST', body: { name, role } });
    if (res) {
      showToast(`Account '${name}' created`, 2000, 'success');
      renderAccountsView(area);
    }
  });

  area.querySelectorAll('.revoke-acct').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.id;
      const confirmed = await showConfirmDialog('Revoke this service account?');
      if (!confirmed) return;
      const res = await api('/api/accounts/revoke', { method: 'POST', body: { id } });
      if (res) {
        showToast('Account revoked', 2000, 'success');
        renderAccountsView(area);
      }
    });
  });
}

// ── Org Chart View ──────────────────────────────────────────────────────

async function renderOrgChartView(area) {
  showLoading(area);
  const res = await api('/api/orgchart');
  if (!res) { showError(area, 'Failed to load org data'); return; }

  const org = res.org || [];
  const goals = res.goals || [];

  area.innerHTML = `
    <div class="health-grid">
      <div class="health-card good">
        <div class="label">Agents</div>
        <div class="value">${org.length}</div>
      </div>
      <div class="health-card good">
        <div class="label">Active Goals</div>
        <div class="value">${goals.filter(g => g.status === 'active').length}</div>
      </div>
      <div class="health-card good">
        <div class="label">Completed Goals</div>
        <div class="value">${goals.filter(g => g.status === 'completed').length}</div>
      </div>
    </div>

    <div class="card">
      <h3>&#9632; Agent Hierarchy (Paperclip-inspired)</h3>
      <p style="margin-bottom:12px;">Each agent reports its status, capabilities, and assigned goals. Click an agent to inspect.</p>
      <div id="org-tree" style="display:flex;flex-direction:column;gap:8px;"></div>
    </div>

    <div class="card">
      <h3>&#9733; Goal Alignment</h3>
      <p style="margin-bottom:12px;">Goals are assigned to agents with milestones and progress tracking. Paperclip-style heartbeat scheduling.</p>
      <div id="goal-list"></div>
    </div>
  `;

  // Render org tree
  const tree = document.getElementById('org-tree');
  tree.innerHTML = org.map((node, i) => `
    <div class="agent-item" style="background:rgba(139,123,214,0.04);border-radius:8px;">
      <span class="status-dot ${node.status === 'online' ? 'green' : node.status === 'busy' ? 'yellow' : 'red'}"></span>
      <div style="flex:1;">
        <div class="name">${escapeHtml(node.name)}</div>
        <div class="model">${escapeHtml(node.model || 'unknown')} &middot; ${(node.capabilities || []).slice(0, 3).join(', ')}</div>
      </div>
      <span style="font-size:11px;color:rgba(255,255,255,0.3)">${node.status}</span>
    </div>
  `).join('');

  // Render goals
  const goalList = document.getElementById('goal-list');
  if (!goals.length) {
    goalList.innerHTML = '<p style="color:rgba(255,255,255,0.4);font-size:13px;">No goals defined. Create one to start tracking.</p>';
    return;
  }
  goalList.innerHTML = goals.map(g => `
    <div class="card" style="margin-bottom:8px;padding:14px 18px;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;">
        <div>
          <h3>${escapeHtml(g.title)}</h3>
          <p>${escapeHtml(g.description)}</p>
        </div>
        <span style="font-size:12px;padding:2px 10px;border-radius:10px;background:${g.status === 'active' ? 'rgba(0,230,118,0.15)' : 'rgba(255,255,255,0.06)'};color:${g.status === 'active' ? '#00e676' : 'rgba(255,255,255,0.4)'};">${g.status}</span>
      </div>
      <div style="display:flex;align-items:center;gap:12px;margin-top:10px;">
        <div style="flex:1;height:6px;background:rgba(255,255,255,0.06);border-radius:3px;overflow:hidden;">
          <div style="width:${g.progress}%;height:100%;background:linear-gradient(90deg,#8b7bd6,#6c5bbf);border-radius:3px;"></div>
        </div>
        <span style="font-size:12px;font-weight:600;color:#c4b5f5">${g.progress}%</span>
        <span style="font-size:11px;color:rgba(255,255,255,0.3)">owner: ${escapeHtml(g.owner)}</span>
      </div>
      <div style="margin-top:8px;">
        ${(g.milestones || []).map(m => `
          <div style="display:flex;align-items:center;gap:8px;margin:3px 0;font-size:12px;color:${m.done ? '#00e676' : 'rgba(255,255,255,0.4)'}">
            <span>${m.done ? '&#10003;' : '&#9679;'}</span> ${escapeHtml(m.title)}
          </div>
        `).join('')}
      </div>
    </div>
  `).join('');
}
