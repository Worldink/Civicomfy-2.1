import { CivitaiDownloaderAPI } from "../../api/civitai.js";

/**
 * Build the installed versions lookup Set from library models.
 * Keys are "modelId:versionId" strings for O(1) lookup.
 */
function _buildInstalledSet(ui) {
  const s = new Set();
  if (ui._libraryModels) {
    for (const m of ui._libraryModels) {
      if (m.civitai_model_id && m.civitai_version_id) {
        s.add(`${m.civitai_model_id}:${m.civitai_version_id}`);
      }
    }
  }
  ui._installedVersions = s;
}

/**
 * Check if a model version is installed (instant, from memory).
 */
export function isVersionInstalled(ui, modelId, versionId) {
  if (!modelId || !versionId) return false;
  return ui._installedVersions.has(`${modelId}:${versionId}`);
}

/**
 * Scan models folder. Called:
 * - Automatically on openModal (silent=true: no toast, no UI flicker)
 * - Manually via Scan button (silent=false: toast + re-render)
 */
export async function handleLibraryScan(ui, silent = false) {
  const btn = ui.libraryScanButton;
  const c = ui.libraryListContainer;

  if (!silent) {
    if (btn) btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Scanning...';
    if (c) c.innerHTML = '<p><i class="fas fa-spinner fa-spin"></i> Scanning...</p>';
    ui.ensureFontAwesome();
  }

  try {
    const r = await CivitaiDownloaderAPI.scanModels();
    if (r?.success && Array.isArray(r.models)) {
      ui._libraryModels = r.models;
      _buildInstalledSet(ui);

      // Only update Library UI if tab is visible or manual scan
      if (!silent || ui.activeTab === 'library') {
        ui.renderLibrary(r.models, c, ui.librarySearchInput?.value || '');
      }
      if (!silent) {
        ui.showToast(`Found ${r.count} model(s).`, 'success');
      }
    } else if (!silent) {
      if (c) c.innerHTML = `<p style="color:#ff6b6b;">${r?.error || 'Scan failed.'}</p>`;
    }
  } catch (e) {
    if (!silent) {
      if (c) c.innerHTML = `<p style="color:#ff6b6b;">${e.message}</p>`;
    }
  } finally {
    if (btn) btn.innerHTML = '<i class="fas fa-sync-alt"></i> Scan';
  }
}

export async function handleDeleteModel(ui, absPath, name) {
  ui._pendingDelete = { path: absPath, name };
  if (ui.confirmText) ui.confirmText.textContent = `Delete "${name}" and all associated files? This cannot be undone.`;
  ui._confirmAction = 'delete_model';
  ui.confirmModal.style.display = 'flex';
}

export async function executeDeleteModel(ui) {
  const d = ui._pendingDelete;
  if (!d) return;
  ui.confirmYesButton.disabled = true;
  ui.confirmYesButton.textContent = 'Deleting...';
  try {
    const r = await CivitaiDownloaderAPI.deleteModel(d.path);
    if (r.success) {
      ui.showToast(r.message || 'Deleted.', 'success');
      ui.confirmModal.style.display = 'none';
      // Remove from cache and rebuild installed set
      if (ui._libraryModels) {
        ui._libraryModels = ui._libraryModels.filter(m => m.abs_path !== d.path);
        _buildInstalledSet(ui);
        ui.renderLibrary(ui._libraryModels, ui.libraryListContainer, ui.librarySearchInput?.value || '');
      }
    } else {
      ui.showToast(`Failed: ${r.error || 'Unknown'}`, 'error');
    }
  } catch (e) {
    ui.showToast(`Failed: ${e.message}`, 'error');
  } finally {
    ui.confirmYesButton.disabled = false;
    ui.confirmYesButton.textContent = 'Confirm';
    ui._pendingDelete = null;
    ui._confirmAction = null;
  }
}
