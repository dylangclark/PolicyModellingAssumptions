const palette = ['#155b75', '#8a4f16', '#5b4c9a', '#26734d', '#9a3658', '#4e6672'];
let registry = null;

const number = new Intl.NumberFormat('en-CA', { maximumFractionDigits: 3 });
const dateFormat = new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: 'short', day: 'numeric' });

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
}
function safeUrl(value) {
  if (!value) return null;
  try {
    const parsed = new URL(String(value), window.location.href);
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
}
function sourceLink(url, label) {
  const safe = safeUrl(url);
  return safe
    ? `<a href="${escapeHtml(safe)}">${escapeHtml(label)}</a>`
    : escapeHtml(label);
}
function formatDate(value) {
  if (!value) return '—';
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(parsed.valueOf()) ? value : dateFormat.format(parsed);
}
function formatValue(record) {
  if (record.value !== null && record.value !== undefined) return `${number.format(record.value)} ${record.unit_canonical}`;
  if (record.range_low !== null && record.range_high !== null) return `${number.format(record.range_low)}–${number.format(record.range_high)} ${record.unit_canonical}`;
  return '—';
}
function badge(status) {
  const kind = status === 'success' ? 'success' : status === 'failed' ? 'danger' : 'warning';
  return `<span class="badge ${kind}">${escapeHtml(status || 'not run')}</span>`;
}

function renderSummary() {
  const summary = registry.summary;
  const items = [
    ['Configured variables', summary.configured_variable_count],
    ['Enabled sources', summary.enabled_source_count],
    ['Required sources', summary.required_source_count],
    ['Public records', summary.current_record_count],
    ['Variables with public data', summary.variable_count],
    ['Historical versions', summary.history_record_count],
    ['Source documents', summary.document_count],
  ];
  document.getElementById('summary-cards').innerHTML = items.map(([label, value]) =>
    `<div class="card"><span class="value">${number.format(value)}</span><span class="label">${label}</span></div>`
  ).join('');
  document.getElementById('generated-at').textContent = `Generated ${formatDate(summary.generated_at)}`;
}

function renderSources() {
  const rows = registry.sources.map(source => {
    const run = source.latest_run;
    return `<tr>
      <td>${sourceLink(source.source_url, source.name)}</td>
      <td>${escapeHtml(source.publisher)}</td>
      <td>${source.enabled ? '<span class="badge success">enabled</span>' : '<span class="badge">staged</span>'}</td>
      <td>${source.required ? '<span class="badge warning">required</span>' : '<span class="badge">optional</span>'}</td>
      <td>${source.publish_enabled ? '<span class="badge success">enabled</span>' : '<span class="badge warning">licence gate</span>'}</td>
      <td>${run ? formatDate(run.started_at) : '—'}</td>
      <td>${run ? badge(run.status) : '<span class="badge">not run</span>'}</td>
    </tr>`;
  });
  document.getElementById('source-table').innerHTML = rows.join('');
}

function populateFilters() {
  const variablesWithData = new Set(registry.records.map(row => row.variable_id));
  const variableSelect = document.getElementById('variable-filter');
  const variables = registry.variables.slice().sort((a,b) => `${a.class_name} ${a.name}`.localeCompare(`${b.class_name} ${b.name}`));
  variableSelect.innerHTML = variables.map(variable =>
    `<option value="${escapeHtml(variable.variable_id)}" ${variablesWithData.has(variable.variable_id) ? '' : 'data-empty="true"'}>${escapeHtml(variable.class_name)} — ${escapeHtml(variable.name)}${variablesWithData.has(variable.variable_id) ? '' : ' (no public data)'}</option>`
  ).join('');
  const firstWithData = variables.find(variable => variablesWithData.has(variable.variable_id));
  if (firstWithData) variableSelect.value = firstWithData.variable_id;

  const sourceSelect = document.getElementById('source-filter');
  const sourceIds = [...new Set(registry.records.map(row => row.source_id))].sort();
  const sources = registry.sources.filter(source => sourceIds.includes(source.source_id));
  sourceSelect.innerHTML += sources.map(source => `<option value="${escapeHtml(source.source_id)}">${escapeHtml(source.name)}</option>`).join('');
}

function filteredRecords() {
  const variable = document.getElementById('variable-filter').value;
  const source = document.getElementById('source-filter').value;
  const search = document.getElementById('record-search').value.trim().toLowerCase();
  return registry.records.filter(row => {
    if (row.variable_id !== variable) return false;
    if (source && row.source_id !== source) return false;
    if (!search) return true;
    return [row.reference_period_start, row.source_name, row.record_kind, row.scenario_original, row.scenario_family, row.statistic_type, ...(row.quality_flags || [])]
      .join(' ').toLowerCase().includes(search);
  });
}

function renderTable(rows) {
  const ordered = rows.slice().sort((a,b) => b.reference_period_start.localeCompare(a.reference_period_start)).slice(0, 500);
  document.getElementById('record-table').innerHTML = ordered.map(row => `<tr>
    <td>${formatDate(row.reference_period_start)}</td>
    <td>${escapeHtml(row.variable_name)}</td>
    <td>${escapeHtml(formatValue(row))}</td>
    <td>${sourceLink(row.source_url, row.source_name)}</td>
    <td>${escapeHtml(row.record_kind)}</td>
    <td>${formatDate(row.vintage_date || row.publication_date)}</td>
    <td>${escapeHtml((row.quality_flags || []).join(', ') || '—')}</td>
  </tr>`).join('');
}

function renderChart(rows) {
  const variableId = document.getElementById('variable-filter').value;
  const variable = registry.variables.find(item => item.variable_id === variableId);
  document.getElementById('chart-title').textContent = variable ? variable.name : 'Selected variable';
  document.getElementById('chart-subtitle').textContent = variable ? `${variable.description} Unit: ${variable.canonical_unit}.` : '';
  const svg = document.getElementById('series-chart');
  const empty = document.getElementById('chart-empty');
  const numeric = rows.filter(row => Number.isFinite(Number(row.value)));
  if (!numeric.length) {
    svg.innerHTML = '';
    svg.hidden = true;
    empty.hidden = false;
    document.getElementById('chart-legend').innerHTML = '';
    return;
  }
  svg.hidden = false;
  empty.hidden = true;
  const groups = new Map();
  numeric.forEach(row => {
    const key = `${row.source_name} · ${row.source_series_id}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  });
  groups.forEach(values => values.sort((a,b) => a.reference_period_start.localeCompare(b.reference_period_start)));
  const all = [...groups.values()].flat();
  const times = all.map(row => new Date(`${row.reference_period_start}T00:00:00Z`).valueOf());
  const values = all.map(row => Number(row.value));
  let minX = Math.min(...times), maxX = Math.max(...times), minY = Math.min(...values), maxY = Math.max(...values);
  if (minX === maxX) { minX -= 86400000; maxX += 86400000; }
  if (minY === maxY) { minY -= Math.abs(minY || 1) * .05; maxY += Math.abs(maxY || 1) * .05; }
  const yPadding = (maxY - minY) * .08;
  minY -= yPadding; maxY += yPadding;
  const width = 1000, height = 420, left = 82, right = 22, top = 25, bottom = 58;
  const plotW = width - left - right, plotH = height - top - bottom;
  const x = value => left + (value - minX) / (maxX - minX) * plotW;
  const y = value => top + (maxY - value) / (maxY - minY) * plotH;
  let markup = '';
  for (let i = 0; i <= 5; i++) {
    const yy = top + i * plotH / 5;
    const label = maxY - i * (maxY - minY) / 5;
    markup += `<line class="chart-grid" x1="${left}" y1="${yy}" x2="${width-right}" y2="${yy}"></line>`;
    markup += `<text class="chart-label" x="${left-10}" y="${yy+4}" text-anchor="end">${escapeHtml(number.format(label))}</text>`;
  }
  for (let i = 0; i <= 4; i++) {
    const xx = left + i * plotW / 4;
    const instant = new Date(minX + i * (maxX - minX) / 4);
    markup += `<line class="chart-grid" x1="${xx}" y1="${top}" x2="${xx}" y2="${height-bottom}"></line>`;
    markup += `<text class="chart-label" x="${xx}" y="${height-bottom+25}" text-anchor="middle">${instant.getUTCFullYear()}</text>`;
  }
  markup += `<line class="chart-axis" x1="${left}" y1="${height-bottom}" x2="${width-right}" y2="${height-bottom}"></line>`;
  markup += `<line class="chart-axis" x1="${left}" y1="${top}" x2="${left}" y2="${height-bottom}"></line>`;
  const legend = [];
  [...groups.entries()].forEach(([name, valuesForSource], index) => {
    const colour = palette[index % palette.length];
    const points = valuesForSource.map(row => `${x(new Date(`${row.reference_period_start}T00:00:00Z`).valueOf())},${y(Number(row.value))}`).join(' ');
    markup += `<polyline class="chart-line" stroke="${colour}" points="${points}"></polyline>`;
    valuesForSource.forEach(row => {
      const cx = x(new Date(`${row.reference_period_start}T00:00:00Z`).valueOf());
      const cy = y(Number(row.value));
      markup += `<circle class="chart-point" fill="${colour}" cx="${cx}" cy="${cy}" r="3"><title>${escapeHtml(name)} — ${escapeHtml(row.reference_period_start)}: ${escapeHtml(formatValue(row))}</title></circle>`;
    });
    legend.push(`<span><i style="background:${colour}"></i>${escapeHtml(name)}</span>`);
  });
  svg.innerHTML = markup;
  document.getElementById('chart-legend').innerHTML = legend.join('');
}

function renderExplorer() {
  const rows = filteredRecords();
  renderChart(rows);
  renderTable(rows);
}

async function start() {
  try {
    const response = await fetch('data/registry.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    registry = await response.json();
    renderSummary();
    renderSources();
    populateFilters();
    renderExplorer();
    const publicCount = registry.summary.current_record_count;
    document.getElementById('status-banner').textContent = publicCount
      ? `${number.format(publicCount)} public records loaded. Internal-only sources remain behind publication gates.`
      : 'The registry is configured, but no public records have been collected in this build.';
    ['variable-filter', 'source-filter', 'record-search'].forEach(id => document.getElementById(id).addEventListener(id === 'record-search' ? 'input' : 'change', renderExplorer));
  } catch (error) {
    const banner = document.getElementById('status-banner');
    banner.classList.add('error');
    banner.textContent = `Registry data could not be loaded: ${error.message}`;
  }
}
start();
