/**
 * CampusCloud — app.js
 * Client-side Cloud Controller: handles all UI state, API calls,
 * file management, upload progress, and notifications.
 */

'use strict';

// ═══════════════════════════════════════════════════════════════════════════════
// State
// ═══════════════════════════════════════════════════════════════════════════════
const state = {
  currentView: 'dashboard',
  files: [],
  filteredFiles: [],
  selectedFile: null,
  deleteTarget: null,
  hdfsOnline: false,
};

// ═══════════════════════════════════════════════════════════════════════════════
// API
// ═══════════════════════════════════════════════════════════════════════════════
const API = {
  BASE: '/api',

  async get(path) {
    const resp = await fetch(`${this.BASE}${path}`);
    return resp.json();
  },

  async delete(path) {
    const resp = await fetch(`${this.BASE}${path}`, { method: 'DELETE' });
    return resp.json();
  },

  async uploadFile(file, onProgress) {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append('file', file);

      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${this.BASE}/files`);

      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 90)); // 90% for upload, 10% for HDFS
        }
      });

      xhr.addEventListener('load', () => {
        try {
          const data = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) {
            onProgress(100);
            resolve(data);
          } else {
            reject(new Error(data.message || 'Upload failed'));
          }
        } catch {
          reject(new Error('Invalid server response'));
        }
      });

      xhr.addEventListener('error', () => reject(new Error('Network error during upload')));
      xhr.addEventListener('abort', () => reject(new Error('Upload cancelled')));

      xhr.send(form);
    });
  },
};

// ═══════════════════════════════════════════════════════════════════════════════
// View Management
// ═══════════════════════════════════════════════════════════════════════════════
function showView(viewName) {
  // Hide all views
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  // Show target
  const view = document.getElementById(`view-${viewName}`);
  if (view) view.classList.add('active');

  const nav = document.getElementById(`nav-${viewName}`);
  if (nav) nav.classList.add('active');

  // Update page title
  const titles = { dashboard: 'Dashboard', files: 'My Files', upload: 'Upload File' };
  document.getElementById('page-title').textContent = titles[viewName] || viewName;

  state.currentView = viewName;

  // Load data for views
  if (viewName === 'dashboard') loadDashboard();
  if (viewName === 'files') loadFiles();
}

function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
}

// ═══════════════════════════════════════════════════════════════════════════════
// HDFS Health Check
// ═══════════════════════════════════════════════════════════════════════════════
async function checkHealth() {
  const dot = document.getElementById('status-dot');
  const text = document.getElementById('hdfs-status-text');
  const dashStatus = document.getElementById('dash-hdfs-status');

  dot.className = 'status-dot checking';
  text.textContent = 'Checking…';

  try {
    const data = await API.get('/health');
    state.hdfsOnline = data.hdfs?.hdfs_reachable === true;

    if (state.hdfsOnline) {
      dot.className = 'status-dot online';
      text.textContent = 'Online';
      if (dashStatus) dashStatus.textContent = 'Online';
      if (dashStatus) dashStatus.style.color = 'var(--green)';
    } else {
      dot.className = 'status-dot offline';
      text.textContent = 'Offline';
      if (dashStatus) dashStatus.textContent = 'Offline';
      if (dashStatus) dashStatus.style.color = 'var(--red)';
    }
  } catch {
    dot.className = 'status-dot offline';
    text.textContent = 'Unreachable';
    if (dashStatus) dashStatus.textContent = 'Error';
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Dashboard
// ═══════════════════════════════════════════════════════════════════════════════
async function loadDashboard() {
  await Promise.all([checkHealth(), loadStorageStats(), loadRecentFiles()]);
}

async function loadStorageStats() {
  try {
    const data = await API.get('/storage');
    const s = data.storage;

    document.getElementById('dash-file-count').textContent = s.file_count ?? '—';
    document.getElementById('dash-storage-used').textContent = formatBytes(s.total_bytes ?? 0);
    document.getElementById('files-count').textContent = s.file_count ?? '0';
  } catch {
    document.getElementById('dash-file-count').textContent = '—';
    document.getElementById('dash-storage-used').textContent = '—';
  }
}

async function loadRecentFiles() {
  const loading = document.getElementById('dash-loading');
  const empty   = document.getElementById('dash-empty');
  const table   = document.getElementById('dash-files-table');
  const tbody   = document.getElementById('dash-files-tbody');

  loading.classList.remove('hidden');
  empty.classList.add('hidden');
  table.classList.add('hidden');

  try {
    const data = await API.get('/files');
    state.files = data.files || [];

    loading.classList.add('hidden');

    if (state.files.length === 0) {
      empty.classList.remove('hidden');
      return;
    }

    // Show last 5 files
    const recent = state.files.slice(0, 5);
    tbody.innerHTML = recent.map(f => renderFileRow(f, 'dash')).join('');
    table.classList.remove('hidden');

    document.getElementById('files-count').textContent = state.files.length;
  } catch {
    loading.classList.add('hidden');
    empty.classList.remove('hidden');
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Files View
// ═══════════════════════════════════════════════════════════════════════════════
async function loadFiles() {
  const loading = document.getElementById('files-loading');
  const empty   = document.getElementById('files-empty');
  const table   = document.getElementById('all-files-table');
  const tbody   = document.getElementById('all-files-tbody');

  loading.classList.remove('hidden');
  empty.classList.add('hidden');
  table.classList.add('hidden');

  try {
    const data = await API.get('/files');
    state.files = data.files || [];
    state.filteredFiles = [...state.files];

    loading.classList.add('hidden');

    if (state.files.length === 0) {
      empty.classList.remove('hidden');
      return;
    }

    tbody.innerHTML = state.filteredFiles.map(f => renderFileRow(f, 'all')).join('');
    table.classList.remove('hidden');

    document.getElementById('files-count').textContent = state.files.length;
  } catch (err) {
    loading.classList.add('hidden');
    empty.classList.remove('hidden');
    showToast('Failed to load files: ' + err.message, 'error');
  }
}

function filterFiles() {
  const q = document.getElementById('search-input').value.toLowerCase();
  state.filteredFiles = state.files.filter(f =>
    f.original_name.toLowerCase().includes(q)
  );
  const tbody = document.getElementById('all-files-tbody');
  const table = document.getElementById('all-files-table');
  const empty = document.getElementById('files-empty');

  if (state.filteredFiles.length === 0) {
    table.classList.add('hidden');
    empty.classList.remove('hidden');
  } else {
    empty.classList.add('hidden');
    table.classList.remove('hidden');
    tbody.innerHTML = state.filteredFiles.map(f => renderFileRow(f, 'all')).join('');
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// File Row Rendering
// ═══════════════════════════════════════════════════════════════════════════════
function renderFileRow(file, context) {
  const ext = file.original_name.split('.').pop().substring(0, 4).toUpperCase();
  const color = extColor(ext);
  const hash = file.sha256 ? file.sha256.substring(0, 12) + '…' : '—';
  const date = formatDate(file.uploaded_at);

  const hashCol = context === 'all'
    ? `<td class="file-hash">${hash}</td>`
    : '';

  return `
    <tr>
      <td>
        <div class="file-name-cell">
          <div class="file-type-icon" style="background:${color.bg};color:${color.fg}">${ext || 'BIN'}</div>
          <span class="file-name-text" title="${escHtml(file.original_name)}">${escHtml(file.original_name)}</span>
        </div>
      </td>
      <td class="file-size">${formatBytes(file.size_bytes)}</td>
      ${hashCol}
      <td class="file-date">${date}</td>
      <td>
        <div class="table-actions">
          <button class="btn-icon-outline" onclick="downloadFile('${file.id}')" title="Download from HDFS">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
          </button>
          <button class="btn-icon-outline danger" onclick="openDeleteModal('${file.id}', '${escAttr(file.original_name)}')" title="Delete from HDFS">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/>
              <path d="M10 11v6M14 11v6"/>
            </svg>
          </button>
        </div>
      </td>
    </tr>`;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Upload
// ═══════════════════════════════════════════════════════════════════════════════
function fileSelected(event) {
  const file = event.target.files[0];
  if (file) setSelectedFile(file);
}

function setSelectedFile(file) {
  state.selectedFile = file;

  const ext = file.name.split('.').pop().substring(0, 4).toUpperCase();
  const color = extColor(ext);

  const preview = document.getElementById('file-preview');
  const icon    = document.getElementById('preview-icon');

  icon.textContent = ext || 'BIN';
  icon.style.background = color.bg;
  icon.style.color = color.fg;

  document.getElementById('preview-name').textContent = file.name;
  document.getElementById('preview-size').textContent = formatBytes(file.size);

  preview.classList.remove('hidden');
  document.getElementById('drop-zone').classList.add('hidden');
  document.getElementById('upload-btn').disabled = false;
}

function removeFile() {
  state.selectedFile = null;
  document.getElementById('file-input').value = '';
  document.getElementById('file-preview').classList.add('hidden');
  document.getElementById('drop-zone').classList.remove('hidden');
  document.getElementById('upload-btn').disabled = true;
  document.getElementById('upload-progress').classList.add('hidden');
}

function dragOver(event) {
  event.preventDefault();
  document.getElementById('drop-zone').classList.add('dragging');
}

function dragLeave(event) {
  document.getElementById('drop-zone').classList.remove('dragging');
}

function dropFile(event) {
  event.preventDefault();
  document.getElementById('drop-zone').classList.remove('dragging');
  const file = event.dataTransfer.files[0];
  if (file) setSelectedFile(file);
}

async function uploadFile() {
  if (!state.selectedFile) return;

  const btn      = document.getElementById('upload-btn');
  const progress = document.getElementById('upload-progress');
  const fill     = document.getElementById('progress-fill');
  const pct      = document.getElementById('progress-pct');
  const stage    = document.getElementById('progress-stage');
  const filename = document.getElementById('progress-filename');

  // Show progress
  btn.disabled = true;
  document.getElementById('file-preview').classList.add('hidden');
  progress.classList.remove('hidden');
  filename.textContent = state.selectedFile.name;
  stage.textContent = 'Uploading to CampusCloud…';

  try {
    const result = await API.uploadFile(state.selectedFile, (pctValue) => {
      fill.style.width = `${pctValue}%`;
      pct.textContent  = `${pctValue}%`;
      if (pctValue >= 90) {
        stage.textContent = 'Writing to HDFS DataNode…';
      }
    });

    stage.textContent = 'Stored in HDFS ✓';

    showToast(`"${result.file.original_name}" uploaded to HDFS successfully.`, 'success');

    // Reset after short delay
    setTimeout(() => {
      removeFile();
      progress.classList.add('hidden');
      btn.disabled = false;
      showView('files');
    }, 1200);

  } catch (err) {
    progress.classList.add('hidden');
    document.getElementById('file-preview').classList.remove('hidden');
    btn.disabled = false;
    showToast('Upload failed: ' + err.message, 'error');
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Download
// ═══════════════════════════════════════════════════════════════════════════════
function downloadFile(fileId) {
  showToast('Retrieving from HDFS…', 'info');
  // Browser-native download via hidden anchor
  const a = document.createElement('a');
  a.href = `/api/files/${fileId}/download`;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Delete
// ═══════════════════════════════════════════════════════════════════════════════
function openDeleteModal(fileId, filename) {
  state.deleteTarget = fileId;
  document.getElementById('delete-filename').textContent = filename;
  document.getElementById('delete-modal').classList.remove('hidden');
}

function closeDeleteModal() {
  state.deleteTarget = null;
  document.getElementById('delete-modal').classList.add('hidden');
}

async function confirmDelete() {
  if (!state.deleteTarget) return;

  const btn = document.getElementById('confirm-delete-btn');
  btn.textContent = 'Deleting…';
  btn.disabled = true;

  try {
    const data = await API.delete(`/files/${state.deleteTarget}`);
    closeDeleteModal();

    if (data.status === 'ok') {
      showToast(`"${data.file.name}" deleted from HDFS.`, 'success');
      // Refresh current view
      if (state.currentView === 'files') loadFiles();
      else loadDashboard();
    } else {
      showToast(data.message || 'Delete failed.', 'error');
    }
  } catch (err) {
    showToast('Delete failed: ' + err.message, 'error');
    closeDeleteModal();
  } finally {
    btn.textContent = 'Delete from HDFS';
    btn.disabled = false;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Toasts
// ═══════════════════════════════════════════════════════════════════════════════
function showToast(message, type = 'info') {
  const icons = {
    success: `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`,
    error:   `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
    info:    `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
  };

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `${icons[type] || icons.info}<span>${escHtml(message)}</span>`;

  const container = document.getElementById('toast-container');
  container.appendChild(toast);

  // Auto-dismiss
  setTimeout(() => {
    toast.classList.add('out');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Utilities
// ═══════════════════════════════════════════════════════════════════════════════
function formatBytes(bytes) {
  if (bytes === 0 || bytes == null) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function formatDate(ts) {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return d.toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escAttr(str) {
  return String(str).replace(/'/g, "\\'").replace(/"/g, '\\"');
}

function extColor(ext) {
  const map = {
    PDF: { bg: 'rgba(239,68,68,0.15)',   fg: '#ef4444' },
    DOC: { bg: 'rgba(59,130,246,0.15)',  fg: '#60a5fa' },
    DOCX:{ bg: 'rgba(59,130,246,0.15)',  fg: '#60a5fa' },
    XLS: { bg: 'rgba(34,197,94,0.15)',   fg: '#4ade80' },
    XLSX:{ bg: 'rgba(34,197,94,0.15)',   fg: '#4ade80' },
    PNG: { bg: 'rgba(168,85,247,0.15)',  fg: '#c084fc' },
    JPG: { bg: 'rgba(168,85,247,0.15)',  fg: '#c084fc' },
    JPEG:{ bg: 'rgba(168,85,247,0.15)',  fg: '#c084fc' },
    GIF: { bg: 'rgba(168,85,247,0.15)',  fg: '#c084fc' },
    MP4: { bg: 'rgba(245,158,11,0.15)',  fg: '#fbbf24' },
    MOV: { bg: 'rgba(245,158,11,0.15)',  fg: '#fbbf24' },
    MP3: { bg: 'rgba(20,184,166,0.15)',  fg: '#2dd4bf' },
    WAV: { bg: 'rgba(20,184,166,0.15)',  fg: '#2dd4bf' },
    ZIP: { bg: 'rgba(234,179,8,0.15)',   fg: '#facc15' },
    TAR: { bg: 'rgba(234,179,8,0.15)',   fg: '#facc15' },
    TXT: { bg: 'rgba(148,163,184,0.15)', fg: '#94a3b8' },
    PY:  { bg: 'rgba(99,102,241,0.15)',  fg: '#818cf8' },
    JS:  { bg: 'rgba(234,179,8,0.15)',   fg: '#fde047' },
    HTML:{ bg: 'rgba(249,115,22,0.15)',  fg: '#fb923c' },
    CSV: { bg: 'rgba(34,197,94,0.12)',   fg: '#86efac' },
  };
  return map[ext] || { bg: 'rgba(148,163,184,0.12)', fg: '#94a3b8' };
}

// ═══════════════════════════════════════════════════════════════════════════════
// Close modal on overlay click
// ═══════════════════════════════════════════════════════════════════════════════
document.getElementById('delete-modal').addEventListener('click', function(e) {
  if (e.target === this) closeDeleteModal();
});

// Close sidebar on mobile when clicking outside
document.addEventListener('click', (e) => {
  const sidebar = document.getElementById('sidebar');
  const toggle  = document.getElementById('menu-toggle');
  if (
    sidebar.classList.contains('open') &&
    !sidebar.contains(e.target) &&
    !toggle.contains(e.target)
  ) {
    sidebar.classList.remove('open');
  }
});

// ═══════════════════════════════════════════════════════════════════════════════
// Init
// ═══════════════════════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
  showView('dashboard');
  // Periodic health check every 30 seconds
  setInterval(checkHealth, 30000);
});
