/* Skills — agent skill registry with library links, vetting, security scores */

async function renderSkillsView(area) {
  showLoading(area);
  const res = await api('/api/skills');
  const agents = (res && res.agents) || {};
  const bySkill = (res && res.by_skill) || {};
  const agentNames = Object.keys(agents);

  if (!agentNames.length) {
    showNoData(area, 'Skills', 'No agent skill data. Define skills in agent YAML configs.');
    return;
  }

  const allSkills = Object.keys(bySkill).sort();
  const catColors = {
    security: '#FF3355', network: '#FF8C00', system: '#D4A843',
    operations: '#00CC88', development: '#00D4FF', quality: '#8899AA',
    ai: '#D4A843', design: '#CC88FF', uncategorized: '#555555',
  };

  function scoreBadge(score) {
    if (!score && score !== 0) return '<span class="badge">—</span>';
    const pct = parseInt(score);
    const cls = pct >= 85 ? '' : pct >= 70 ? 'warn' : 'danger';
    return `<span class="badge ${cls}" style="min-width:32px;text-align:center">${pct}</span>`;
  }

  function vetBtn(skill) {
    return `<button class="btn btn-secondary" style="padding:4px 10px;font-size:10px" onclick="vetSkill('${escapeHtml(skill)}', this)">Vet by Proxy</button>`;
  }

  area.innerHTML = `
    <div class="view-header">
      <h2><span>Skills</span> · Agent Capability Registry</h2>
      <span class="muted">${agentNames.length} agent(s) · ${allSkills.length} skill(s)</span>
    </div>
    <div class="section glass" style="margin-bottom:12px">
      <div class="panel-title">By Skill</div>
      <div style="padding:0 14px 14px">
        <div style="display:grid;gap:4px">
          ${allSkills.length ? allSkills.map(skill => {
            const s = bySkill[skill];
            const libUrl = s.library_url;
            const cat = s.category || 'uncategorized';
            const catColor = catColors[cat] || '#555';
            return `<div style="display:flex;align-items:center;gap:8px;padding:8px 6px;border-bottom:1px solid var(--color-glass-edge);flex-wrap:wrap">
              <span style="flex:1;min-width:120px;font-size:13px">
                <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${catColor};margin-right:6px"></span>
                <strong>${escapeHtml(skill)}</strong>
                <span class="muted" style="font-size:10px;margin-left:4px">${escapeHtml(cat)}</span>
              </span>
              <span style="display:flex;gap:4px;flex-wrap:wrap;align-items:center">
                ${(s.agents || []).map(a => `<span class="chip" style="font-size:10px">${escapeHtml(a)}</span>`).join('')}
              </span>
              <span style="display:flex;gap:4px;align-items:center">
                ${scoreBadge(s.security_score)}
                ${libUrl ? `<a href="${escapeHtml(libUrl)}" target="_blank" class="btn btn-secondary" style="padding:3px 8px;font-size:10px;text-decoration:none">Library</a>` : ''}
                ${vetBtn(skill)}
              </span>
            </div>`;
          }).join('') : '<div class="muted" style="padding:8px">No skills defined</div>'}
        </div>
      </div>
    </div>
    <div class="section glass" style="margin-bottom:12px">
      <div class="panel-title">By Agent</div>
      <div style="padding:0 14px 14px">
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px">
          ${agentNames.map(name => {
            const a = agents[name];
            const skills = (a.skills || []);
            const caps = (a.capabilities || []);
            return `<div class="plant-card glass">
              <div class="plant-name">${escapeHtml(name)}</div>
              <div class="plant-meta" style="font-size:11px;color:var(--color-text-muted)">
                ${escapeHtml(a.role || '')} · ${escapeHtml(a.model || '')}
              </div>
              ${skills.length ? `<div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:4px">
                ${skills.map(s => `<span class="chip">${escapeHtml(s)}</span>`).join('')}
              </div>` : ''}
              ${caps.length ? `<div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:4px">
                ${caps.map(c => `<span class="chip" style="background:var(--color-glass)">${escapeHtml(c)}</span>`).join('')}
              </div>` : ''}
            </div>`;
          }).join('')}
        </div>
      </div>
    </div>
    <div id="skill-vet-result"></div>
  `;
  loadMarketplace(area);
}

/* ─── Marketplace / Skill Libraries ──────────────────────────── */

async function loadMarketplace(area) {
  const res = await api('/api/skills/marketplace');
  const sources = (res && res.sources) || [];
  const protocol = res ? res.protocol : '';

  if (!sources.length) return;

  area.innerHTML += `
    <div class="section glass" style="margin-top:12px">
      <div class="panel-title">Skill Libraries</div>
      <div style="padding:0 14px 14px">
        <div style="font-size:12px;color:var(--color-text-muted);margin-bottom:10px;line-height:1.5">
          Browse and pull skills from community libraries using the
          <code class="mono" style="font-size:11px">SKILL.md</code> protocol.
          ${escapeHtml(protocol || '')}
        </div>

        <div style="display:flex;gap:8px;margin-bottom:12px">
          <input id="skill-search-input" type="text" placeholder="Search for a skill..." autocomplete="off"
            style="flex:1;padding:8px 12px;border-radius:6px;border:1px solid var(--color-glass-edge);background:var(--color-glass);color:var(--color-text);font-size:13px;outline:none"
            onkeydown="if(event.key==='Enter') searchMarketplace()">
          <button class="btn btn-secondary" style="padding:6px 14px;font-size:11px" onclick="searchMarketplace()">Search</button>
        </div>

        <div id="marketplace-results" style="margin-bottom:12px"></div>

        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:8px">
          ${sources.map(s => `
            <div class="plant-card glass" style="padding:10px;cursor:pointer" onclick="browseSource('${escapeHtml(s.id)}')">
              <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
                <span style="font-size:14px">📦</span>
                <strong style="font-size:12px">${escapeHtml(s.label)}</strong>
              </div>
              <div style="font-size:10px;color:var(--color-text-dim);margin-bottom:2px">${escapeHtml(s.id)}</div>
              <div style="font-size:10px;color:var(--color-text-muted)">${escapeHtml(s.description)}</div>
              <div style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap">
                <span class="badge" style="font-size:8px">${escapeHtml(s.protocol)}</span>
                <a href="${escapeHtml(s.url)}" target="_blank" class="badge" style="font-size:8px;text-decoration:none;cursor:pointer">GitHub →</a>
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    </div>
  `;
}

async function searchMarketplace() {
  const q = document.getElementById('skill-search-input')?.value.trim();
  if (!q) return;
  const el = document.getElementById('marketplace-results');
  if (!el) return;
  el.innerHTML = '<div class="muted" style="padding:8px;text-align:center">Searching...</div>';
  const res = await api(`/api/skills/marketplace?q=${encodeURIComponent(q)}`);
  const skills = (res && res.skills) || [];
  if (!skills.length) {
    el.innerHTML = '<div class="muted" style="padding:12px;text-align:center">No skills found for that query. Try a different search term.</div>';
    return;
  }
  el.innerHTML = `
    <div style="font-size:11px;color:var(--color-text-muted);margin-bottom:6px">Found ${skills.length} skill(s) for "${escapeHtml(q)}"</div>
    <div style="display:grid;gap:4px">
      ${skills.map(s => `
        <div style="display:flex;align-items:center;gap:8px;padding:6px 8px;border:1px solid var(--color-glass-edge);border-radius:4px">
          <span style="flex:1;font-size:12px"><strong>${escapeHtml(s.name)}</strong></span>
          <span class="badge" style="font-size:9px">${escapeHtml(s.label)}</span>
          <a href="${escapeHtml(s.url)}" target="_blank" class="btn btn-secondary" style="padding:3px 8px;font-size:9px;text-decoration:none">View</a>
          <button class="btn btn-secondary" style="padding:3px 8px;font-size:9px" onclick="showToast('Skill pull coming soon — use marketplace.py CLI for now', 3000)">Pull</button>
        </div>
      `).join('')}
    </div>
  `;
}

async function browseSource(sourceId) {
  const el = document.getElementById('marketplace-results');
  if (!el) return;
  el.innerHTML = '<div class="muted" style="padding:8px;text-align:center">Loading...</div>';
  const res = await api(`/api/skills/marketplace?source=${encodeURIComponent(sourceId)}`);
  const skills = (res && res.skills) || [];
  if (!skills.length) {
    el.innerHTML = '<div class="muted" style="padding:12px;text-align:center">No skills available from this source.</div>';
    return;
  }
  el.innerHTML = `
    <div style="font-size:11px;color:var(--color-text-muted);margin-bottom:6px">${skills.length} skill(s) available</div>
    <div style="display:grid;gap:4px;max-height:300px;overflow-y:auto">
      ${skills.map(s => `
        <div style="display:flex;align-items:center;gap:8px;padding:6px 8px;border:1px solid var(--color-glass-edge);border-radius:4px">
          <span style="flex:1;font-size:12px"><strong>${escapeHtml(s.name)}</strong></span>
          <span class="badge" style="font-size:9px">${escapeHtml(s.label)}</span>
          <a href="${escapeHtml(s.url)}" target="_blank" class="btn btn-secondary" style="padding:3px 8px;font-size:9px;text-decoration:none">View</a>
          <button class="btn btn-secondary" style="padding:3px 8px;font-size:9px" onclick="showToast('Skill pull coming soon — use marketplace.py CLI for now', 3000)">Pull</button>
        </div>
      `).join('')}
    </div>
  `;
}


async function vetSkill(skill, btn) {
  if (!skill) return;
  btn.disabled = true;
  btn.textContent = 'Vetting...';
  const res = await api(`/api/skills/vet/${encodeURIComponent(skill)}`, { method: 'POST' });
  btn.disabled = false;
  btn.textContent = 'Vet by Proxy';
  if (!res) {
    showToast('Vet request failed', 3000, 'error');
    return;
  }
  const el = document.getElementById('skill-vet-result');
  if (!el) return;
  const catColors = { security: '#FF3355', network: '#FF8C00', system: '#D4A843', operations: '#00CC88', development: '#00D4FF', ai: '#D4A843' };
  el.innerHTML = `
    <div class="section glass" style="margin-top:8px">
      <div class="panel-title">Vet Results: ${escapeHtml(skill)}</div>
      <div style="padding:0 14px 14px">
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px">
          <div><span class="badge">Score: ${res.security_score}/100</span></div>
          <div><span class="badge" style="background:${catColors[res.category] || '#555'}">${escapeHtml(res.category)}</span></div>
          <div><span class="badge">${escapeHtml(res.vet_status)}</span></div>
          <div><span class="badge ${res.recommendation === 'approved' ? '' : 'warn'}">${escapeHtml(res.recommendation)}</span></div>
          <div class="mono muted" style="font-size:10px">Review: ${res.review_id}</div>
        </div>
        ${res.concerns && res.concerns.length ? `
          <div style="font-size:12px;color:var(--color-text-dim);margin-bottom:6px">Concerns:</div>
          <ul style="margin:0;padding-left:16px;font-size:12px">
            ${res.concerns.map(c => `<li style="color:var(--color-text-dim);margin-bottom:2px">${escapeHtml(c)}</li>`).join('')}
          </ul>
        ` : '<div style="color:var(--color-success);font-size:12px">No concerns identified</div>'}
        ${res.library_url ? `<div style="margin-top:8px"><a href="${escapeHtml(res.library_url)}" target="_blank" class="btn btn-secondary" style="padding:6px 14px;font-size:11px;text-decoration:none">View Library →</a></div>` : ''}
      </div>
    </div>
  `;
  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
