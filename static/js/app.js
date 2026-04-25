/* ── State ─────────────────────────────────────────────────────────────── */
const state = {
  accounts: [],
  senders: [],
  currentFilter: 'active',
};

/* ── API helpers ────────────────────────────────────────────────────────── */
async function api(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== null) opts.body = JSON.stringify(body);
  const res = await fetch(`/api${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

/* ── Toast notifications ─────────────────────────────────────────────── */
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3500);
}

/* ── Navigation ──────────────────────────────────────────────────────── */
function navigate(viewId) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(`view-${viewId}`).classList.add('active');
  document.querySelector(`[data-view="${viewId}"]`).classList.add('active');
  if (viewId === 'senders') renderSenders();
  if (viewId === 'accounts') renderAccounts();
}

/* ── Accounts view ───────────────────────────────────────────────────── */
async function loadAccounts() {
  try {
    state.accounts = await api('GET', '/accounts');
  } catch (e) {
    showToast(e.message, 'error');
  }
}

function renderAccounts() {
  const list = document.getElementById('account-list');
  if (!state.accounts.length) {
    list.innerHTML = `<div class="empty-state">
      <div class="empty-icon">📭</div>
      <p>No accounts yet.<br>Add one below to get started.</p>
    </div>`;
    return;
  }
  list.innerHTML = state.accounts.map(acc => `
    <div class="account-item">
      <span class="account-icon">${acc.provider === 'fastmail' ? '⚡' : '📧'}</span>
      <div class="account-info">
        <div class="account-name">${esc(acc.name)}</div>
        <div class="account-email">${esc(acc.email)}</div>
        <div class="account-email" style="font-size:0.7rem;margin-top:2px">
          ${acc.provider.toUpperCase()}${acc.last_scan ? ` · Last scan: ${fmtDate(acc.last_scan)}` : ''}
        </div>
      </div>
      <div class="account-actions">
        <button class="btn btn-ghost btn-sm" onclick="scanAccount(${acc.id})" title="Scan inbox">
          🔍
        </button>
        <button class="btn btn-ghost btn-sm" onclick="deleteAccount(${acc.id})" title="Remove account">
          🗑️
        </button>
      </div>
    </div>
  `).join('');
}

async function scanAccount(id) {
  showToast('Scanning… this may take a moment.');
  try {
    const res = await api('POST', `/scan/${id}`);
    await loadAccounts();
    await loadSenders();
    renderAccounts();
    showToast(res.message, 'success');
  } catch (e) {
    showToast(e.message, 'error');
  }
}

async function deleteAccount(id) {
  if (!confirm('Remove this account and all its data?')) return;
  try {
    await api('DELETE', `/accounts/${id}`);
    state.accounts = state.accounts.filter(a => a.id !== id);
    state.senders = state.senders.filter(s => s.account_id !== id);
    renderAccounts();
    renderSenders();
    showToast('Account removed.', 'success');
  } catch (e) {
    showToast(e.message, 'error');
  }
}

/* ── Add-account forms ───────────────────────────────────────────────── */
function selectTab(tab) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
  document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
  document.getElementById(`form-${tab}`).classList.remove('hidden');
}

async function addIMAPAccount(e) {
  e.preventDefault();
  const btn = e.target.querySelector('[type=submit]');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Connecting…';
  try {
    const account = await api('POST', '/accounts/imap', {
      name: e.target.name.value.trim(),
      email: e.target.email.value.trim(),
      imap_host: e.target.imap_host.value.trim(),
      imap_port: parseInt(e.target.imap_port.value, 10),
      imap_username: e.target.imap_username.value.trim(),
      password: e.target.password.value,
    });
    state.accounts.push(account);
    renderAccounts();
    e.target.reset();
    showToast('Account added successfully!', 'success');
    navigate('accounts');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Connect & Save';
  }
}

async function addFastmailAccount(e) {
  e.preventDefault();
  const btn = e.target.querySelector('[type=submit]');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Connecting…';
  try {
    const account = await api('POST', '/accounts/fastmail', {
      name: e.target.name.value.trim(),
      email: e.target.email.value.trim(),
      api_token: e.target.api_token.value.trim(),
    });
    state.accounts.push(account);
    renderAccounts();
    e.target.reset();
    showToast('Fastmail account added!', 'success');
    navigate('accounts');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Connect & Save';
  }
}

/* ── Senders view ────────────────────────────────────────────────────── */
async function loadSenders() {
  try {
    state.senders = await api('GET', '/senders');
  } catch (e) {
    showToast(e.message, 'error');
  }
}

function setFilter(filter) {
  state.currentFilter = filter;
  document.querySelectorAll('.filter-chip').forEach(c => {
    c.classList.toggle('active', c.dataset.filter === filter);
  });
  renderSenders();
}

function renderSenders() {
  const container = document.getElementById('sender-list');
  let list = state.senders;

  if (state.currentFilter !== 'all') {
    list = list.filter(s => s.status === state.currentFilter);
  }

  if (!list.length) {
    const hint = state.senders.length
      ? 'No senders in this category.'
      : 'No senders found yet. Add an account and run a scan.';
    container.innerHTML = `<div class="empty-state">
      <div class="empty-icon">🎉</div>
      <p>${hint}</p>
    </div>`;
    return;
  }

  container.innerHTML = list.map(s => {
    const initials = (s.display_name || s.email).substring(0, 2).toUpperCase();
    const canUnsub = s.status === 'active' && (s.unsubscribe_link || s.unsubscribe_mailto);
    const unsubBtn = canUnsub
      ? `<button class="btn btn-danger btn-sm" onclick="unsubscribe(${s.id})">Unsubscribe</button>`
      : s.status === 'unsubscribed'
        ? `<span class="badge badge-success">Done ✓</span>`
        : `<span class="badge badge-muted">No link</span>`;
    return `
      <div class="sender-card">
        <div class="sender-avatar">${esc(initials)}</div>
        <div class="sender-info">
          <div class="sender-name">${esc(s.display_name || s.email)}</div>
          <div class="sender-email">${esc(s.email)}</div>
          <div class="sender-meta">${s.email_count} email${s.email_count !== 1 ? 's' : ''} · ${s.last_seen ? fmtDate(s.last_seen) : ''}</div>
        </div>
        <div class="sender-actions">${unsubBtn}</div>
      </div>`;
  }).join('');
}

async function unsubscribe(senderId) {
  try {
    const attempt = await api('POST', `/senders/${senderId}/unsubscribe`);
    if (attempt.status === 'success') {
      const sender = state.senders.find(s => s.id === senderId);
      if (sender) sender.status = 'unsubscribed';
      renderSenders();
      showToast('Unsubscribed successfully!', 'success');
    } else {
      showToast('Unsubscribe request failed. Try manually.', 'error');
    }
  } catch (e) {
    showToast(e.message, 'error');
  }
}

/* ── Utility ─────────────────────────────────────────────────────────── */
function esc(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fmtDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

/* ── Bootstrap ───────────────────────────────────────────────────────── */
(async () => {
  await Promise.all([loadAccounts(), loadSenders()]);
  navigate('senders');
})();
