import { CivitaiDownloaderAPI } from "../../api/civitai.js";

export function setupEventListeners(ui) {
  ui.closeButton.addEventListener('click', () => ui.closeModal());
  // Modal closes only via X button (no click-outside dismiss)

  // Tabs
  ui.tabContainer.addEventListener('click', e => {
    if (e.target.matches('.civitai-downloader-tab')) ui.switchTab(e.target.dataset.tab);
  });

  // Forms
  ui.downloadForm.addEventListener('submit', e => { e.preventDefault(); ui.handleDownloadSubmit(); });
  ui.searchForm.addEventListener('submit', e => {
    e.preventDefault();
    if (!ui.searchQueryInput.value.trim() && ui.searchTypeSelect.value === 'any' && ui.searchBaseModelSelect.value === 'any') {
      ui.showToast("Enter query or filter.", "error"); return;
    }
    ui.searchPagination.currentPage = 1;
    ui.handleSearchSubmit();
  });
  ui.settingsForm.addEventListener('submit', e => { e.preventDefault(); ui.handleSettingsSave(); });

  // Create model type folder
  ui.createModelTypeButton.addEventListener('click', async () => {
    const name = prompt('New model type folder name:');
    if (!name) return;
    try {
      const r = await CivitaiDownloaderAPI.createModelType(name);
      if (r?.success) { await ui.populateModelTypes(); ui.downloadModelTypeSelect.value = r.name; ui.showToast(`Created: ${r.name}`, 'success'); }
      else ui.showToast(r?.error || 'Failed', 'error');
    } catch (e) { ui.showToast(e.message, 'error'); }
  });

  // Download preview
  ui.modelUrlInput.addEventListener('input', () => ui.debounceFetchDownloadPreview());
  ui.modelUrlInput.addEventListener('paste', () => ui.debounceFetchDownloadPreview(100));

  // Settings buttons
  ui.settingsSetGlobalRootButton?.addEventListener('click', () => ui.handleSetGlobalRoot());
  ui.settingsClearGlobalRootButton?.addEventListener('click', () => ui.handleClearGlobalRoot());
  ui.modal.querySelector('#civitai-refresh-status')?.addEventListener('click', () => ui.checkCivitaiStatus());

  // --- Blur toggle helper ---
  function toggleBlur(e) {
    const tc = e.target.closest('.civitai-thumbnail-container, .civitai-gallery-item');
    if (!tc) return false;
    const lvl = Number(tc.dataset.nsfwLevel ?? 0);
    if (!(ui.settings?.hideMatureInSearch && lvl >= (ui.settings?.nsfwBlurMinLevel ?? 4))) return false;
    tc.classList.toggle('blurred');
    const ov = tc.querySelector('.civitai-nsfw-overlay');
    if (ov) ov.style.display = tc.classList.contains('blurred') ? '' : 'none';
    return true;
  }

  // --- Status tab ---
  ui.statusContent.addEventListener('click', e => {
    if (toggleBlur(e)) return;
    const btn = e.target.closest('button');
    if (!btn) return;
    const id = btn.dataset.id;
    if (id) {
      if (btn.classList.contains('civitai-cancel-button')) ui.handleCancelDownload(id);
      else if (btn.classList.contains('civitai-retry-button')) ui.handleRetryDownload(id, btn);
      else if (btn.classList.contains('civitai-openpath-button')) ui.handleOpenPath(id, btn);
    } else if (btn.id === 'civitai-clear-history-button') {
      ui._confirmAction = 'clear_history';
      if (ui.confirmText) ui.confirmText.textContent = 'Clear download history?';
      ui.confirmModal.style.display = 'flex';
    }
  });

  // --- Search results: single download button → sends to Download tab ---
  ui.searchResultsContainer.addEventListener('click', e => {
    if (toggleBlur(e)) return;
    const dlBtn = e.target.closest('.civitai-search-download-button');
    if (dlBtn) {
      e.preventDefault();
      const mid = dlBtn.dataset.modelId;
      const mtype = dlBtn.dataset.modelType;
      if (!mid) { ui.showToast("Missing data.", "error"); return; }

      const typeKey = Object.keys(ui.modelTypes).find(
        k => ui.modelTypes[k]?.toLowerCase() === mtype?.toLowerCase()
      ) || ui.settings.defaultModelType;

      ui.modelUrlInput.value = mid;
      // Clear version - will auto-select latest
      const hiddenVid = ui.modal.querySelector('#civitai-model-version-id');
      if (hiddenVid) hiddenVid.value = '';
      ui.customFilenameInput.value = '';
      if (ui.subfolderInput) ui.subfolderInput.value = '';
      ui.downloadModelTypeSelect.value = typeKey;
      ui.switchTab('download');
      ui.fetchAndDisplayDownloadPreview();
      return;
    }
  });

  // Pagination
  ui.searchPaginationContainer.addEventListener('click', e => {
    const btn = e.target.closest('.civitai-page-button');
    if (btn && !btn.disabled) {
      const pg = parseInt(btn.dataset.page, 10);
      if (pg && pg !== ui.searchPagination.currentPage) {
        ui.searchPagination.currentPage = pg;
        ui.handleSearchSubmit();
      }
    }
  });

  // --- Library ---
  ui.libraryScanButton?.addEventListener('click', () => ui.handleLibraryScan(false));
  ui.librarySearchInput?.addEventListener('input', () => {
    if (ui._libraryModels) ui.renderLibrary(ui._libraryModels, ui.libraryListContainer, ui.librarySearchInput.value);
  });
  ui.libraryListContainer?.addEventListener('click', e => {
    const del = e.target.closest('.civitai-delete-model-button');
    if (del) ui.handleDeleteModel(del.dataset.absPath, del.dataset.name || 'this model');
  });

  // --- Confirm modal ---
  ui.confirmYesButton.addEventListener('click', () => {
    if (ui._confirmAction === 'clear_history') ui.handleClearHistory();
    else if (ui._confirmAction === 'delete_model') ui.executeDeleteModel();
  });
  ui.confirmNoButton.addEventListener('click', () => { ui.confirmModal.style.display = 'none'; });
  ui.confirmModal.addEventListener('click', e => { if (e.target === ui.confirmModal) ui.confirmModal.style.display = 'none'; });
}
