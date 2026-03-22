import { CivitaiDownloaderAPI } from "../../api/civitai.js";

export function debounceFetchDownloadPreview(ui, delay = 500) {
  clearTimeout(ui._previewDebounce);
  ui._previewDebounce = setTimeout(() => fetchAndDisplayDownloadPreview(ui), delay);
}

export async function fetchAndDisplayDownloadPreview(ui) {
  const url = ui.modelUrlInput.value.trim();
  const vid = ui.modal.querySelector('#civitai-model-version-id')?.value?.trim();

  if (!url) {
    ui.downloadPreviewArea.innerHTML = `<div class="civitai-empty-state"><i class="fas fa-cloud-download-alt" style="font-size:2.5em;opacity:.3;"></i><p>Paste a Civitai URL or select from Search.</p></div>`;
    if (ui.downloadSubmitButton) { ui.downloadSubmitButton.disabled = false; ui.downloadSubmitButton.innerHTML = '<i class="fas fa-download"></i> Download'; }
    return;
  }

  // Ghost fix: track request ID
  const reqId = Date.now();
  ui._lastPreviewReq = reqId;

  ui.downloadPreviewArea.innerHTML = '<p class="civitai-loading"><i class="fas fa-spinner fa-spin"></i> Loading model details...</p>';
  ui.ensureFontAwesome();

  // Disable download button while loading (prevents clicking before EA check)
  if (ui.downloadSubmitButton) {
    ui.downloadSubmitButton.disabled = true;
    ui.downloadSubmitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
  }

  try {
    const r = await CivitaiDownloaderAPI.getModelDetails({
      model_url_or_id: url,
      model_version_id: vid ? parseInt(vid, 10) : null,
      api_key: ui.settings.apiKey,
    });
    if (ui._lastPreviewReq !== reqId) return; // Stale
    if (r?.success) {
      ui.renderDownloadPreview(r);
      if (r.model_type) await ui.autoSelectModelTypeFromCivitai(r.model_type);
    } else {
      ui.downloadPreviewArea.innerHTML = `<p style="color:#ff6b6b;">${r?.error || 'Failed.'}</p>`;
      _resetBtn(ui);
    }
  } catch (e) {
    if (ui._lastPreviewReq !== reqId) return;
    ui.downloadPreviewArea.innerHTML = `<p style="color:#ff6b6b;">${e.details || e.message}</p>`;
    _resetBtn(ui);
  }
}

export async function handleDownloadSubmit(ui) {
  ui.downloadSubmitButton.disabled = true;
  ui.downloadSubmitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting...';

  const url = ui.modelUrlInput.value.trim();
  if (!url) { ui.showToast("URL required.", "error"); _resetBtn(ui); return; }

  const params = {
    model_url_or_id: url,
    model_type: ui.downloadModelTypeSelect.value,
    model_version_id: ui.modal.querySelector('#civitai-model-version-id')?.value || null,
    custom_filename: ui.customFilenameInput.value.trim(),
    subfolder: ui.subfolderInput?.value?.trim() || '',
    api_key: ui.settings.apiKey,
  };
  if (params.model_version_id) params.model_version_id = parseInt(params.model_version_id, 10);

  const fileSelect = ui.modal.querySelector('#civitai-file-select');
  if (fileSelect?.value) { const fid = parseInt(fileSelect.value, 10); if (!isNaN(fid)) params.file_id = fid; }

  try {
    const r = await CivitaiDownloaderAPI.downloadModel(params);
    if (r.status === 'queued') {
      ui.showToast(`Queued: ${r.details?.filename || 'Model'}`, 'success');
      if (ui.settings.autoOpenStatusTab) ui.switchTab('status');
      else ui.updateStatus();
    } else if (r.status === 'blocked') {
      ui.showToast(r.message || 'Early Access.', 'error', 5000);
    } else if (r.status === 'already_installed') {
      ui.showToast(r.message || 'Already installed.', 'info', 4000);
    } else {
      ui.showToast(`${r.status}: ${r.message || ''}`, 'info');
    }
  } catch (e) {
    ui.showToast(`Failed: ${e.details || e.message}`, 'error', 6000);
  } finally {
    _resetBtn(ui);
  }
}

function _resetBtn(ui) {
  if (ui.downloadSubmitButton) {
    ui.downloadSubmitButton.disabled = false;
    ui.downloadSubmitButton.className = 'civitai-button primary civitai-download-btn';
    ui.downloadSubmitButton.innerHTML = '<i class="fas fa-download"></i> Download';
  }
}
