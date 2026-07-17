/* Skills — agent skill and capability registry */

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

  area.innerHTML = `
    <div class="view-header">
      <h2><span>Skills</span> · Agent Capability Registry</h2>
      <span class="muted">${agentNames.length} agent(s) · ${allSkills.length} skill(s) · ${escapeHtml(res.timestamp || '')}</span>
    </div>
    <div class="section glass" style="margin-bottom:12px">
      <div class="panel-title">By Skill</div>
      <div style="padding:0 14px 14px">
        ${allSkills.length ? allSkills.map(skill => `
          <div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--color-glass-edge)">
            <span style="flex:1;font-size:13px"><strong>${escapeHtml(skill)}</strong></span>
            <div style="display:flex;gap:4px;flex-wrap:wrap">
              ${bySkill[skill].map(agentName => `
                <span class="badge">${escapeHtml(agentName)}</span>
              `).join('')}
            </div>
          </div>
        `).join('') : '<div class="muted" style="padding:8px">No skills defined</div>'}
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
  `;
}
