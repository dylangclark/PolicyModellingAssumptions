const numberFormat = new Intl.NumberFormat('en-CA');
const dateTimeFormat = new Intl.DateTimeFormat('en-CA', {
  year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short'
});
let pipelineData = { summary: null, sources: [], runs: [] };

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[character]));
}

function parseDate(value) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? null : parsed;
}

function formatDateTime(value) {
  const parsed = parseDate(value);
  return parsed ? dateTimeFormat.format(parsed) : '—';
}

function formatDuration(startedAt, finishedAt) {
  const start = parseDate(startedAt);
  const finish = parseDate(finishedAt);
  if (!start || !finish) return '—';
  const seconds = Math.max(0, Math.round((finish - start) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

function ageInDays(value) {
  const parsed = parseDate(value);
  if (!parsed) return null;
  return Math.max(0, (Date.now() - parsed.valueOf()) / 86400000);
}

function formatAge(value) {
  const days = ageInDays(value);
  if (days === null) return 'never';
  if (days < 1) return `${Math.max(0, Math.round(days * 24))}h ago`;
  return `${Math.floor(days)}d ago`;
}

function badge(label, kind = '') {
  return `<span class="badge ${kind}">${escapeHtml(label)}</span>`;
}

function sourceAssessment(source) {
  if (!source.enabled) return { label: 'staged', kind: '', attention: false };
  if (!source.latest_run) return { label: 'not run', kind: 'danger', attention: true };
  if (source.latest_run.status !== 'success') return { label: source.latest_run.status, kind: 'danger', attention: true };
  const age = ageInDays(source.latest_run.finished_at || source.latest_run.started_at);
  if (age !== null && source.collection_stale_after_days && age > source.collection_stale_after_days) {
    return { label: 'collection stale', kind: 'warning', attention: true };
  }
  return { label: 'healthy', kind: 'success', attention: false };
}

function renderSummary() {
  const summary = pipelineData.summary;
  const enabled = pipelineData.sources.filter(source => source.enabled);
  const healthy = enabled.filter(source => !sourceAssessment(source).attention).length;
  const failedRuns = pipelineData.runs.filter(run => run.status === 'failed').length;
  const latestRun = pipelineData.runs.slice().sort((a, b) => String(b.finished_at || b.started_at).localeCompare(String(a.finished_at || a.started_at)))[0];
  const cards = [
    ['Release status', summary.failed_sources?.length ? 'Attention' : 'Ready', summary.failed_sources?.length ? 'danger' : 'success'],
    ['Healthy enabled sources', `${healthy}/${enabled.length}`, healthy === enabled.length ? 'success' : 'warning'],
    ['Latest successful run', formatAge(summary.latest_successful_run), ''],
    ['Public records', numberFormat.format(summary.current_record_count || 0), ''],
    ['Variables with data', numberFormat.format(summary.variable_count || 0), ''],
    ['Failed runs retained', numberFormat.format(failedRuns), failedRuns ? 'warning' : 'success'],
    ['Most recent source run', latestRun ? formatAge(latestRun.finished_at || latestRun.started_at) : 'never', '']
  ];
  document.getElementById('pipeline-summary-cards').innerHTML = cards.map(([label, value, state]) =>
    `<div class="card metric-card ${state}"><span class="value">${escapeHtml(value)}</span><span class="label">${escapeHtml(label)}</span></div>`
  ).join('');
  document.getElementById('pipeline-generated-at').textContent = `Public release generated ${formatDateTime(summary.generated_at)}`;

  const banner = document.getElementById('pipeline-banner');
  if (summary.failed_sources?.length) {
    banner.classList.add('error');
    banner.textContent = `Current release reports failed sources: ${summary.failed_sources.join(', ')}.`;
  } else {
    banner.textContent = `All ${summary.required_source_count} required sources passed the published release gate. Latest successful collection: ${formatDateTime(summary.latest_successful_run)}.`;
  }
}

function renderSources() {
  const filter = document.getElementById('source-status-filter').value;
  const rows = pipelineData.sources.filter(source => {
    const assessment = sourceAssessment(source);
    if (filter === 'enabled') return source.enabled;
    if (filter === 'attention') return assessment.attention || (source.enabled && !source.publish_enabled);
    return true;
  }).map(source => {
    const run = source.latest_run;
    const assessment = sourceAssessment(source);
    const role = source.required ? badge('required', 'warning') : source.enabled ? badge('optional') : badge('staged');
    const freshness = run ? `${formatAge(run.finished_at || run.started_at)} / ${source.collection_stale_after_days || '—'}d limit` : 'No run';
    const publication = source.publish_enabled ? badge('public', 'success') : source.enabled ? badge('licence gate', 'warning') : badge('not active');
    const recordSummary = run ? `${numberFormat.format(run.records_seen || 0)} seen<br><span class="muted">${numberFormat.format(run.records_inserted || 0)} new · ${numberFormat.format(run.records_revised || 0)} revised</span>` : '—';
    return `<tr class="${assessment.attention ? 'attention-row' : ''}">
      <td><a href="${escapeHtml(source.source_url || '#')}" target="_blank" rel="noopener">${escapeHtml(source.name)}</a><br><span class="muted">${escapeHtml(source.publisher)}</span></td>
      <td>${role}</td>
      <td>${run ? formatDateTime(run.finished_at || run.started_at) : '—'}</td>
      <td>${run ? formatDuration(run.started_at, run.finished_at) : '—'}</td>
      <td>${recordSummary}</td>
      <td>${escapeHtml(freshness)}</td>
      <td>${publication}</td>
      <td>${badge(assessment.label, assessment.kind)}</td>
    </tr>`;
  });
  document.getElementById('pipeline-source-table').innerHTML = rows.join('') || '<tr><td colspan="8">No sources match this filter.</td></tr>';
}

function populateRunFilter() {
  const select = document.getElementById('run-source-filter');
  const sourcesById = new Map(pipelineData.sources.map(source => [source.source_id, source.name]));
  const sourceIds = [...new Set(pipelineData.runs.map(run => run.source_id))].sort((a, b) => (sourcesById.get(a) || a).localeCompare(sourcesById.get(b) || b));
  select.innerHTML = '<option value="">All sources</option>' + sourceIds.map(sourceId =>
    `<option value="${escapeHtml(sourceId)}">${escapeHtml(sourcesById.get(sourceId) || sourceId)}</option>`
  ).join('');
}

function filteredRuns() {
  const sourceId = document.getElementById('run-source-filter').value;
  return pipelineData.runs.filter(run => !sourceId || run.source_id === sourceId)
    .slice().sort((a, b) => String(b.started_at).localeCompare(String(a.started_at)));
}

function renderRuns() {
  const runs = filteredRuns();
  const sourcesById = new Map(pipelineData.sources.map(source => [source.source_id, source.name]));
  const recent = runs.slice(0, 40).reverse();
  document.getElementById('run-strip').innerHTML = recent.map(run => {
    const kind = run.status === 'success' ? 'success' : run.status === 'failed' ? 'danger' : 'warning';
    const title = `${sourcesById.get(run.source_id) || run.source_id}: ${run.status}, ${formatDateTime(run.started_at)}`;
    return `<span class="run-block ${kind}" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}"></span>`;
  }).join('') || '<span class="muted">No runs available.</span>';

  document.getElementById('run-history-table').innerHTML = runs.slice(0, 100).map(run => {
    const kind = run.status === 'success' ? 'success' : run.status === 'failed' ? 'danger' : 'warning';
    const message = run.error || (run.warnings?.length ? run.warnings.join('; ') : '—');
    return `<tr>
      <td>${formatDateTime(run.started_at)}</td>
      <td>${escapeHtml(sourcesById.get(run.source_id) || run.source_id)}</td>
      <td>${badge(run.status, kind)}</td>
      <td>${formatDuration(run.started_at, run.finished_at)}</td>
      <td>${numberFormat.format(run.records_seen || 0)}</td>
      <td>${numberFormat.format(run.records_inserted || 0)}</td>
      <td>${numberFormat.format(run.records_revised || 0)}</td>
      <td>${numberFormat.format(run.records_rejected || 0)}</td>
      <td class="message-cell">${escapeHtml(message)}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="9">No runs available.</td></tr>';
}

async function loadJson(path) {
  const response = await fetch(path, { cache: 'no-store' });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

async function start() {
  try {
    const [summary, sources, runs] = await Promise.all([
      loadJson('data/summary.json'), loadJson('data/sources.json'), loadJson('data/runs.json')
    ]);
    pipelineData = { summary, sources, runs };
    renderSummary();
    populateRunFilter();
    renderSources();
    renderRuns();
    document.getElementById('source-status-filter').addEventListener('change', renderSources);
    document.getElementById('run-source-filter').addEventListener('change', renderRuns);
  } catch (error) {
    const banner = document.getElementById('pipeline-banner');
    banner.classList.add('error');
    banner.textContent = `Pipeline data could not be loaded: ${error.message}`;
  }
}

start();
