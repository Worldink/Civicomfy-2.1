import { CivitaiDownloaderAPI } from "../../api/civitai.js";

export function startStatusUpdates(ui) {
  if (!ui.statusInterval) {
    ui.updateStatus();
    ui.statusInterval = setInterval(() => ui.updateStatus(), 2500);
  }
}

export function stopStatusUpdates(ui) {
  if (ui.statusInterval) {
    clearInterval(ui.statusInterval);
    ui.statusInterval = null;
  }
}

export async function updateStatus(ui) {
  if (!ui.modal?.classList.contains('open')) return;
  try {
    const d = await CivitaiDownloaderAPI.getStatus();
    if (!d?.active || !d?.queue || !d?.history) return;

    // Build set of currently downloading/queued versions
    const dlSet = new Set();
    for (const item of [...d.active, ...d.queue]) {
      if (item.civitai_model_id && item.civitai_version_id &&
          !['completed', 'failed', 'cancelled'].includes(item.status)) {
        dlSet.add(`${item.civitai_model_id}:${item.civitai_version_id}`);
      }
    }
    ui._downloadingVersions = dlSet;

    // Detect newly completed downloads → update installed set
    const prevCompleted = ui._completedIds || new Set();
    const newCompleted = new Set();
    for (const item of d.history) {
      if (item.status === 'completed' && item.civitai_model_id && item.civitai_version_id) {
        const key = `${item.civitai_model_id}:${item.civitai_version_id}`;
        newCompleted.add(item.id);
        if (!prevCompleted.has(item.id)) {
          ui._installedVersions.add(key);
        }
      }
    }
    for (const item of d.active) {
      if (item.status === 'completed' && item.civitai_model_id && item.civitai_version_id) {
        ui._installedVersions.add(`${item.civitai_model_id}:${item.civitai_version_id}`);
      }
    }
    ui._completedIds = newCompleted;

    // If Download tab open → update button to match current state
    if (ui.activeTab === 'download' && ui._previewModelId && ui._previewVersionId) {
      const key = `${ui._previewModelId}:${ui._previewVersionId}`;
      const btn = ui.downloadSubmitButton;
      if (btn) {
        if (ui._installedVersions.has(key)) {
          if (!btn.classList.contains('civitai-btn-installed')) {
            btn.disabled = true;
            btn.className = 'civitai-button civitai-download-btn civitai-btn-installed';
            btn.innerHTML = '<i class="fas fa-check"></i> Already Installed';
          }
        } else if (dlSet.has(key)) {
          if (!btn.innerHTML.includes('Downloading')) {
            btn.disabled = true;
            btn.className = 'civitai-button civitai-download-btn';
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Downloading...';
          }
        }
      }
    }

    ui.statusData = d;
    const cnt = d.active.length + d.queue.length;
    if (ui.activeCountSpan) ui.activeCountSpan.textContent = cnt;
    if (ui.statusIndicator) ui.statusIndicator.style.display = cnt > 0 ? 'inline' : 'none';
    if (ui.activeTab === 'status') {
      ui.renderDownloadList(d.active, ui.activeListContainer, 'No active downloads.');
      ui.renderDownloadList(d.queue, ui.queuedListContainer, 'Queue empty.');
      ui.renderDownloadList(d.history, ui.historyListContainer, 'No history.');
    }
  } catch (e) {
    if (ui.activeTab === 'status' && ui.activeListContainer) {
      ui.activeListContainer.innerHTML = `<p style="color:#ff6b6b;">${e.message}</p>`;
    }
  }
}

export async function handleCancelDownload(ui, id) {
  const btn = ui.modal.querySelector(`.civitai-cancel-button[data-id="${id}"]`);
  if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; }
  try {
    const r = await CivitaiDownloaderAPI.cancelDownload(id);
    ui.showToast(r.message || 'Cancelled.', 'info');
    ui.updateStatus();
  } catch (e) {
    ui.showToast(`Cancel failed: ${e.message}`, 'error');
    if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-times"></i>'; }
  }
}

export async function handleRetryDownload(ui, id, btn) {
  btn.disabled = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
  try {
    const r = await CivitaiDownloaderAPI.retryDownload(id);
    if (r.success) {
      ui.showToast('Retry queued.', 'success');
      if (ui.settings.autoOpenStatusTab) ui.switchTab('status');
      else ui.updateStatus();
    } else {
      ui.showToast(`Retry failed: ${r.error}`, 'error');
      btn.disabled = false; btn.innerHTML = '<i class="fas fa-redo"></i>';
    }
  } catch (e) {
    ui.showToast(`Retry failed: ${e.message}`, 'error');
    btn.disabled = false; btn.innerHTML = '<i class="fas fa-redo"></i>';
  }
}

export async function handleOpenPath(ui, id, btn) {
  const orig = btn.innerHTML;
  btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
  try {
    const r = await CivitaiDownloaderAPI.openPath(id);
    if (r.success) ui.showToast('Opened.', 'success');
    else ui.showToast(`Failed: ${r.error}`, 'error');
  } catch (e) {
    ui.showToast(`Failed: ${e.message}`, 'error');
  } finally {
    btn.disabled = false; btn.innerHTML = orig;
  }
}

export async function handleClearHistory(ui) {
  ui.confirmYesButton.disabled = true;
  ui.confirmYesButton.textContent = 'Clearing...';
  try {
    const r = await CivitaiDownloaderAPI.clearHistory();
    if (r.success) {
      ui.showToast('History cleared.', 'success');
      ui.statusData.history = [];
      ui.renderDownloadList([], ui.historyListContainer, 'No history.');
      ui.confirmModal.style.display = 'none';
    } else {
      ui.showToast(`Failed: ${r.error}`, 'error');
    }
  } catch (e) {
    ui.showToast(`Failed: ${e.message}`, 'error');
  } finally {
    ui.confirmYesButton.disabled = false;
    ui.confirmYesButton.textContent = 'Confirm';
  }
}
