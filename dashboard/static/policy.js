/* Policy — osquery pack configurations */

async function renderPolicyView(area) {
  showLoading(area);
  const res = await api('/api/policy');
  const packs = (res && res.packs) || {};

  if (!Object.keys(packs).length) {
    showNoData(area, 'Policy', 'No osquery policy packs found. Define packs in config/osquery/.');
    return;
  }

  area.innerHTML = `
    <div class="view-header">
      <h2><span>Policy</span> · osquery Monitoring Queries</h2>
      <span class="muted">${res.total_packs || Object.keys(packs).length} pack(s) · ${escapeHtml(res.timestamp || '')}</span>
    </div>
    ${Object.entries(packs).map(([key, pack]) => `
      <div class="section glass" style="margin-bottom:12px">
        <div class="panel-title" style="display:flex;align-items:center;gap:8px">
          <span>${escapeHtml(pack.name)}</span>
          <span class="badge" style="font-size:10px">${pack.total} queries</span>
          <span class="muted" style="font-size:11px;font-weight:normal">${escapeHtml(pack.description)}</span>
        </div>
        <div style="padding:0 14px 14px">
          ${pack.queries.map(q => `
            <details style="margin-bottom:6px;border:1px solid var(--color-glass-edge);border-radius:6px;overflow:hidden">
              <summary style="padding:8px 10px;cursor:pointer;font-size:12px;background:var(--color-glass);display:flex;align-items:center;gap:8px">
                <span style="flex:1"><strong>${escapeHtml(q.name)}</strong></span>
                <span class="badge" style="font-size:9px">every ${q.interval}s</span>
              </summary>
              <div style="padding:8px 10px;border-top:1px solid var(--color-glass-edge)">
                <div class="muted" style="font-size:11px;margin-bottom:6px">${escapeHtml(q.description || '')}</div>
                <pre class="mono" style="margin:0;font-size:10px;line-height:1.5;background:var(--color-glass);padding:8px;border-radius:4px;overflow-x:auto;white-space:pre-wrap">${escapeHtml(q.sql)}</pre>
              </div>
            </details>
          `).join('')}
        </div>
      </div>
    `).join('')}
  `;
}
