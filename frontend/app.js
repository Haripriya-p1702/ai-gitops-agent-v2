/* ── Config ─────────────────────────────────────────────────────────────────── */
const WS_URL = 'ws://localhost:8000/ws';
const API_URL = 'http://localhost:8000';

/* ── State ──────────────────────────────────────────────────────────────────── */
let stats = { prs: new Set(), issues: 0, fixes: 0, files: 0 };
let ws;

/* ── WebSocket ──────────────────────────────────────────────────────────────── */
function connectWS() {
    const badge = document.getElementById('ws-status');
    badge.className = 'ws-badge ws-connecting';
    badge.innerHTML = '<span class="ws-dot"></span> Connecting...';

    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        badge.className = 'ws-badge ws-connected';
        badge.innerHTML = '<span class="ws-dot"></span> Connected';
    };

    ws.onclose = () => {
        badge.className = 'ws-badge ws-error';
        badge.innerHTML = '<span class="ws-dot"></span> Disconnected';
        setTimeout(connectWS, 3000);   // auto-reconnect
    };

    ws.onerror = () => {
        badge.className = 'ws-badge ws-error';
        badge.innerHTML = '<span class="ws-dot"></span> Error';
    };

    ws.onmessage = (e) => {
        try {
            const event = JSON.parse(e.data);
            handleEvent(event);
        } catch (_) { }
    };
}

/* ── Event Handler ──────────────────────────────────────────────────────────── */
function handleEvent(event) {
    console.log('[DASHBOARD] 📬 Raw Event:', event);

    // Initial state from backend
    if (event.type === 'init') {
        console.log('[DASHBOARD] 🚀 Initializing state:', event);
        if (event.stats) {
            stats.issues = event.stats.issues_detected || 0;
            stats.files = event.stats.files_analyzed || 0;
            stats.fixes = event.stats.prs_created || 0;
            updateStat('stat-issues', stats.issues);
            updateStat('stat-files', stats.files);
            updateStat('stat-fixes', stats.fixes);
            updateStat('stat-prs', event.stats.repos_watched || 1);
        }
        if (event.events) {
            const feed = document.getElementById('event-feed');
            feed.innerHTML = ''; // clear for fresh start
            event.events.forEach(e => addEventToFeed(e));
        }
        return;
    }

    // Backend wraps live events in { type: 'event', data: { ... } }
    let data = event;
    while (data && data.type === 'event' && data.data) {
        data = data.data;
    }

    console.log('[DASHBOARD] 📄 Processing Data:', data);
    addEventToFeed(data);

    switch (data.type) {
        case 'push_detected':
        case 'pr_received':
            stats.prs.add(`${data.repo}#${data.pr_number || 'demo'}`);
            updateStat('stat-prs', stats.prs.size);
            break;

        case 'issue_detected':
        case 'analysis_complete':
            const issues = data.analysis || data.issues || data.analyses || [];
            const issueCount = data.issues_count || issues.length || 0;
            stats.issues += issueCount;
            updateStat('stat-issues', stats.issues);
            stats.files += 1;
            updateStat('stat-files', stats.files);
            renderAnalyses([data]);
            break;

        case 'fix_generated':
            // Update the results display with the fix/diff
            renderAnalyses([data]);
            // Auto-expand the newest card
            setTimeout(() => {
                const firstCard = document.querySelector('.result-card-header');
                if (firstCard && !firstCard.nextElementSibling.classList.contains('open')) {
                    toggleCard(firstCard);
                }
            }, 500);
            break;

        case 'pr_created':
        case 'fix_pr_created':
            stats.fixes++;
            updateStat('stat-fixes', stats.fixes);
            if (data.pr_url || data.fix_pr_url) showToast(data.pr_url || data.fix_pr_url);
            break;
    }
}

/* ── Feed ───────────────────────────────────────────────────────────────────── */
function addEventToFeed(event) {
    const feed = document.getElementById('event-feed');

    // remove empty state
    const empty = feed.querySelector('.empty-state');
    if (empty) empty.remove();

    const ts = new Date(event.timestamp || Date.now());
    const timeStr = ts.toLocaleTimeString();

    const div = document.createElement('div');
    div.className = `event-item type-${event.type}`;
    div.innerHTML = `
    <span class="event-msg">${escapeHtml(event.message || event.type)}</span>
    <span class="event-time">${timeStr}</span>
  `;
    feed.prepend(div);

    // cap feed at 100 items
    while (feed.children.length > 100) feed.removeChild(feed.lastChild);
}

/* ── Results ─────────────────────────────────────────────────────────────────── */
function renderAnalyses(analyses) {
    const list = document.getElementById('results-list');

    // remove empty state
    const empty = list.querySelector('.empty-state');
    if (empty) empty.remove();

    const count = document.getElementById('results-count');
    const total = list.querySelectorAll('.result-card').length + analyses.length;
    count.textContent = `${total} file${total !== 1 ? 's' : ''}`;

    analyses.forEach(a => {
        const card = buildResultCard(a);
        list.prepend(card);
    });
}

function buildResultCard(a) {
    const sev = (a.severity || 'none').toLowerCase();
    const issues = a.analysis || a.issues || [];
    const hasIssues = issues.length > 0;
    const fname = a.filename || a.file || 'unknown';

    const div = document.createElement('div');
    div.className = 'result-card';

    const issuesHtml = issues.map(i =>
        `<div class="issue-item">${escapeHtml(i.description || i)}</div>`
    ).join('');

    const fixes = a.fixes_applied || [];
    const fixListHtml = fixes.length > 0
        ? `<div class="fixes-applied-list">
             <strong>Fixes applied:</strong>
             <ul>${fixes.map(f => `<li>${escapeHtml(f)}</li>`).join('')}</ul>
           </div>`
        : '';

    const fixHtml = (a.changes_explanation || a.fix_description || a.description)
        ? `<div class="fix-explanation">
             ${fixListHtml}
             <div class="explanation-text">${escapeHtml(a.changes_explanation || a.fix_description || a.description)}</div>
           </div>`
        : '';

    const diffHtml = a.diff
        ? `<div class="diff-container">${formatDiff(a.diff)}</div>`
        : '';

    div.innerHTML = `
    <div class="result-card-header" onclick="toggleCard(this)">
      <div class="result-filename">
        ${fileIcon(fname)}
        <div class="filename-stack">
          <span class="repo-name">${escapeHtml(a.repo || 'unknown/repo')}</span>
          <span class="file-path">${escapeHtml(fname)}</span>
        </div>
      </div>
      <div class="result-right">
        <span class="severity-badge sev-${sev}">${sev}</span>
        <span class="chevron">▼</span>
      </div>
    </div>
    <div class="result-body">
      <div class="result-summary">${escapeHtml(a.summary || (hasIssues ? 'Issues found.' : 'No issues found.'))}</div>
      ${hasIssues && issues.length ? `<div class="issues-list">${issuesHtml}</div>` : ''}
      ${fixHtml}
      ${diffHtml}
    </div>
  `;
    return div;
}

function formatDiff(diff) {
    if (!diff) return '<div class="diff-info">No diff available</div>';
    console.log('[DIFF DEBUG] Length:', diff.length, 'Data:', diff.substring(0, 50));

    // Normalize newlines and split
    const lines = diff.replace(/\r/g, '').split('\n');

    return lines.map(line => {
        const cleanLine = line; // maybe trim? but diffs need leading spaces
        let cls = '';
        if (cleanLine.startsWith('+') && !cleanLine.startsWith('+++')) cls = 'diff-add';
        else if (cleanLine.startsWith('-') && !cleanLine.startsWith('---')) cls = 'diff-remove';
        else if (cleanLine.startsWith('@@')) cls = 'diff-meta';
        else if (cleanLine.startsWith('---') || cleanLine.startsWith('+++')) cls = 'diff-info';

        return `<span class="diff-line ${cls}">${escapeHtml(cleanLine)}</span>`;
    }).join('');
}

function toggleCard(header) {
    const body = header.nextElementSibling;
    const chevron = header.querySelector('.chevron');
    body.classList.toggle('open');
    chevron.classList.toggle('open');
}

/* ── Toast ───────────────────────────────────────────────────────────────────── */
function showToast(url) {
    const toast = document.getElementById('fix-toast');
    const link = document.getElementById('toast-link');
    link.href = url;
    link.textContent = url;
    toast.classList.remove('hidden');
    setTimeout(hideToast, 8000);
}
function hideToast() {
    document.getElementById('fix-toast').classList.add('hidden');
}

/* ── Helpers ─────────────────────────────────────────────────────────────────── */
function updateStat(id, val) {
    const el = document.getElementById(id);
    el.textContent = val;
    el.classList.add('bump');
    setTimeout(() => el.classList.remove('bump'), 400);
}

function clearFeed() {
    const feed = document.getElementById('event-feed');
    feed.innerHTML = `<div class="empty-state">
    <div class="empty-icon">🤖</div>
    <p>Feed cleared — waiting for events...</p>
  </div>`;
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function fileIcon(filename) {
    if (!filename) return '📄';
    const f = filename.toLowerCase();
    if (f.includes('dockerfile')) return '🐳';
    if (f.endsWith('.tf')) return '🟣';
    if (f.includes('workflow') || f.includes('.github')) return '⚡';
    if (f.endsWith('.yaml') || f.endsWith('.yml')) return '☸️';
    return '📄';
}

/* ── Demo Trigger ────────────────────────────────────────────────────────────── */
async function triggerDemo() {
    const btn = document.getElementById('demo-btn');
    btn.disabled = true;
    btn.textContent = '⏳ Running...';
    try {
        const res = await fetch(`${API_URL}/api/demo/trigger`, { method: 'POST' });
        if (!res.ok) throw new Error(await res.text());
    } catch (err) {
        alert('Could not reach backend: ' + err.message +
            '\n\nMake sure the backend is running on port 8000.');
    } finally {
        setTimeout(() => {
            btn.disabled = false;
            btn.textContent = '▶ Run Demo';
        }, 5000);
    }
}

/* ── Init ────────────────────────────────────────────────────────────────────── */
connectWS();
