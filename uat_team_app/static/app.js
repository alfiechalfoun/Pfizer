// Shared frontend code. Every page talks to the same Python API and SQLite database.
const $ = (id) => document.getElementById(id);
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[char]));

let reports = [];
let activity = [];
let selectedId = null;

async function api(path, data) {
  const options = data === undefined ? {} : {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  };
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed');
  return result;
}

async function refresh() {
  try {
    const data = await api('/api/reports');
    reports = data.reports;
    activity = data.activity;
    render();
  } catch (error) {
    alert('Unable to reach the shared server: ' + error.message);
  }
}

function statusBadge(status) {
  const style = status === 'Approved' || status === 'Resolved' ? 'approved' :
    status.includes('duplicate') ? 'duplicate' : status === 'Dismissed' ? 'dismissed' : '';
  return `<span class="pill ${style}">${escapeHTML(status)}</span>`;
}

function reportCard(report) {
  return `<article class="report">
    <div class="row"><strong>#${report.id} · ${escapeHTML(report.area)}</strong>${statusBadge(report.status)}</div>
    <p>${escapeHTML(report.message)}</p>
    <div class="row"><small class="muted">${escapeHTML(report.tester)} · ${escapeHTML(report.created)}</small>
      <span class="pill">${escapeHTML(report.type)} · ${escapeHTML(report.priority)}</span></div>
    ${document.body.dataset.role === 'tester' ? '' :
      `<div class="actions"><button class="secondary" data-select="${report.id}">Open ticket</button></div>`}
  </article>`;
}

function render() {
  const role = document.body.dataset.role;
  if (role === 'tester') renderTester();
  if (role === 'manager') renderManager();
  if (role === 'developer') renderDeveloper();
}

function renderTester() {
  const name = $('tester-filter').value.trim().toLowerCase();
  const shown = name ? reports.filter((r) => r.tester.toLowerCase().includes(name)) : reports;
  $('tester-list').innerHTML = shown.length ? shown.map(reportCard).join('') : '<p class="hint">No reports found.</p>';
}

function renderManager() {
  const states = [
    ['Total reports', reports.length],
    ['Awaiting review', reports.filter((r) => ['Needs review', 'Possible duplicate'].includes(r.status)).length],
    ['Possible duplicates', reports.filter((r) => r.status === 'Possible duplicate').length],
    ['Approved', reports.filter((r) => ['Approved', 'In progress', 'Resolved'].includes(r.status)).length]
  ];
  $('stats').innerHTML = states.map(([label, number]) =>
    `<div class="stat"><strong>${number}</strong><span>${label}</span></div>`).join('');

  const filter = $('manager-filter').value;
  const shown = reports.filter((r) => filter === 'all' || r.status === filter);
  $('manager-list').innerHTML = shown.length ? shown.map(reportCard).join('') : '<p class="hint">No matching reports.</p>';
  $('activity').innerHTML = activity.length ? activity.slice(0, 12).map((entry) =>
    `<p class="hint">#${entry.report_id} · ${escapeHTML(entry.action)} · ${escapeHTML(entry.at)}</p>`).join('') : '<p class="hint">No activity yet.</p>';

  const r = reports.find((report) => report.id === selectedId);
  if (!r) return;

  $('manager-detail').innerHTML = `
    <h3>#${r.id}: ${escapeHTML(r.area)}</h3>
    <p><strong>Reported by:</strong> ${escapeHTML(r.tester)}</p>
    <p>${escapeHTML(r.message)}</p>
    <p><strong>Expected:</strong> ${escapeHTML(r.expected || 'Not provided')}</p>
    ${r.duplicate_of ? `<div class="alert">Possible duplicate of report #${r.duplicate_of}. Please verify before dismissing.</div>` : ''}
    <label for="edit-type">Classification</label>
    <select id="edit-type">${['Bug','Question','Improvement','Needs classification'].map((x) =>
      `<option ${r.type === x ? 'selected' : ''}>${x}</option>`).join('')}</select>
    <label for="edit-priority">Priority</label>
    <select id="edit-priority">${['High','Medium','Low'].map((x) =>
      `<option ${r.priority === x ? 'selected' : ''}>${x}</option>`).join('')}</select>
    <label for="edit-notes">Manager notes</label><textarea id="edit-notes">${escapeHTML(r.notes)}</textarea>
    <label for="edit-ticket">Editable development ticket</label><textarea id="edit-ticket" class="ticket">${escapeHTML(r.ticket)}</textarea>
    <div class="actions">
      <button data-manager-action="Approved">Approve for developer</button>
      <button class="secondary" data-manager-action="Needs review">Save review</button>
      <button class="danger" data-manager-action="Dismissed">Dismiss</button>
    </div>`;
}

function renderDeveloper() {
  const shown = reports.filter((r) => ['Approved', 'In progress', 'Resolved'].includes(r.status));
  $('developer-list').innerHTML = shown.length ? shown.map(reportCard).join('') :
    '<p class="hint">No approved tickets yet. The manager must approve a report first.</p>';
  const r = shown.find((report) => report.id === selectedId);
  if (!r) return;
  $('developer-detail').innerHTML = `
    <h3>#${r.id}: ${escapeHTML(r.area)}</h3>
    <div class="row">${statusBadge(r.status)}<span class="pill">${escapeHTML(r.priority)} priority</span></div>
    <pre style="white-space:pre-wrap;overflow-wrap:anywhere">${escapeHTML(r.ticket)}</pre>
    ${r.notes ? `<div class="alert"><strong>Manager notes:</strong> ${escapeHTML(r.notes)}</div>` : ''}
    <label for="dev-status">Progress</label>
    <select id="dev-status">${['Approved','In progress','Resolved'].map((x) =>
      `<option ${r.status === x ? 'selected' : ''}>${x}</option>`).join('')}</select>
    <label for="dev-notes">Developer notes</label>
    <textarea id="dev-notes" placeholder="What has been done?">${escapeHTML(r.developer_notes)}</textarea>
    <div class="actions"><button id="save-development">Save progress</button></div>`;
}

// Tester submits a new report; the server classifies and stores it.
$('feedback-form')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const result = await api('/api/reports', {
      tester: $('tester').value,
      area: $('area').value,
      message: $('message').value,
      expected: $('expected').value
    });
    $('form-result').textContent = `Report #${result.id} submitted (${result.status}).`;
    $('feedback-form').reset();
    await refresh();
  } catch (error) {
    $('form-result').textContent = error.message;
  }
});

$('tester-filter')?.addEventListener('input', renderTester);
$('manager-filter')?.addEventListener('change', renderManager);
$('refresh')?.addEventListener('click', refresh);

// Both queues use delegation so newly rendered buttons work automatically.
document.addEventListener('click', async (event) => {
  const selectButton = event.target.closest('[data-select]');
  if (selectButton) {
    selectedId = Number(selectButton.dataset.select);
    render();
    return;
  }

  const managerButton = event.target.closest('[data-manager-action]');
  if (managerButton) {
    const status = managerButton.dataset.managerAction;
    try {
      await api(`/api/reports/${selectedId}`, {
        action: 'review',
        status,
        type: $('edit-type').value,
        priority: $('edit-priority').value,
        notes: $('edit-notes').value,
        ticket: $('edit-ticket').value
      });
      $('manager-result').textContent = `Report #${selectedId} updated.`;
      await refresh();
    } catch (error) {
      $('manager-result').textContent = error.message;
    }
  }

  if (event.target.id === 'save-development') {
    try {
      await api(`/api/reports/${selectedId}`, {
        action: 'developer',
        status: $('dev-status').value,
        developer_notes: $('dev-notes').value
      });
      $('developer-result').textContent = `Ticket #${selectedId} saved.`;
      await refresh();
    } catch (error) {
      $('developer-result').textContent = error.message;
    }
  }
});

refresh();
// Refresh shared changes every 15 seconds; click Refresh for an immediate update.
setInterval(refresh, 15000);
