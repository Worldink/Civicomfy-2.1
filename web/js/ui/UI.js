import { Feedback } from "./feedback.js";
import { setupEventListeners } from "./handlers/eventListeners.js";
import { handleDownloadSubmit, fetchAndDisplayDownloadPreview, debounceFetchDownloadPreview } from "./handlers/downloadHandler.js";
import { handleSearchSubmit } from "./handlers/searchHandler.js";
import { handleSettingsSave, loadAndApplySettings, loadSettingsFromCookie, saveSettingsToCookie, applySettings, getDefaultSettings, loadGlobalRootSetting, handleSetGlobalRoot, handleClearGlobalRoot, checkCivitaiStatus } from "./handlers/settingsHandler.js";
import { startStatusUpdates, stopStatusUpdates, updateStatus, handleCancelDownload, handleRetryDownload, handleOpenPath, handleClearHistory } from "./handlers/statusHandler.js";
import { handleLibraryScan, handleDeleteModel, executeDeleteModel, isVersionInstalled } from "./handlers/libraryHandler.js";
import { renderSearchResults } from "./searchRenderer.js";
import { renderDownloadList } from "./statusRenderer.js";
import { renderDownloadPreview } from "./previewRenderer.js";
import { renderLibrary } from "./libraryRenderer.js";
import { modalTemplate } from "./templates.js";
import { CivitaiDownloaderAPI } from "../api/civitai.js";

export class CivitaiDownloaderUI {
  constructor() {
    this.modal = null;
    this.tabs = {};
    this.tabContents = {};
    this.activeTab = 'search';
    this.modelTypes = {};
    this.statusInterval = null;
    this.statusData = { queue: [], active: [], history: [] };
    this.baseModels = [];
    this.searchPagination = { currentPage: 1, totalPages: 1, limit: 20 };
    this.settings = this.getDefaultSettings();
    this._previewDebounce = null;
    this._lastPreviewReq = 0;
    this._libraryModels = null;
    this._installedVersions = new Set(); // "modelId:versionId" strings for instant lookup
    this._completedIds = new Set(); // track already-processed completed download IDs
    this._confirmAction = null;
    this._pendingDelete = null;

    this.updateStatus();
    this._build();
    this._cache();
    this.setupEventListeners();
    this.feedback = new Feedback(this.modal.querySelector('#civitai-toast'));
    this.ensureFontAwesome();
  }

  _build() {
    this.modal = document.createElement('div');
    this.modal.className = 'civitai-downloader-modal';
    this.modal.id = 'civitai-downloader-modal';
    this.modal.innerHTML = modalTemplate(this.settings);
  }

  _cache() {
    const q = s => this.modal.querySelector(s);
    this.closeButton = q('#civitai-close-modal');
    this.tabContainer = q('.civitai-downloader-tabs');

    // Download
    this.downloadForm = q('#civitai-download-form');
    this.downloadPreviewArea = q('#civitai-download-preview-area');
    this.modelUrlInput = q('#civitai-model-url');
    this.downloadModelTypeSelect = q('#civitai-model-type');
    this.createModelTypeButton = q('#civitai-create-model-type');
    this.subfolderInput = q('#civitai-subfolder');
    this.customFilenameInput = q('#civitai-custom-filename');
    this.downloadSubmitButton = q('#civitai-download-submit');

    // Search
    this.searchForm = q('#civitai-search-form');
    this.searchQueryInput = q('#civitai-search-query');
    this.searchTypeSelect = q('#civitai-search-type');
    this.searchBaseModelSelect = q('#civitai-search-base-model');
    this.searchSortSelect = q('#civitai-search-sort');
    this.searchSubmitButton = q('#civitai-search-submit');
    this.searchResultsContainer = q('#civitai-search-results');
    this.searchPaginationContainer = q('#civitai-search-pagination');

    // Status
    this.statusContent = q('#civitai-status-content');
    this.activeListContainer = q('#civitai-active-list');
    this.queuedListContainer = q('#civitai-queued-list');
    this.historyListContainer = q('#civitai-history-list');
    this.statusIndicator = q('#civitai-status-indicator');
    this.activeCountSpan = q('#civitai-active-count');

    // Library
    this.libraryScanButton = q('#civitai-library-scan');
    this.librarySearchInput = q('#civitai-library-search');
    this.libraryListContainer = q('#civitai-library-list');

    // Settings
    this.settingsForm = q('#civitai-settings-form');
    this.settingsApiKeyInput = q('#civitai-settings-api-key');
    this.settingsGlobalRootInput = q('#civitai-settings-global-root');
    this.settingsSetGlobalRootButton = q('#civitai-settings-set-global-root');
    this.settingsClearGlobalRootButton = q('#civitai-settings-clear-global-root');
    this.settingsDefaultTypeSelect = q('#civitai-settings-default-type');
    this.settingsAutoOpenCheckbox = q('#civitai-settings-auto-open-status');
    this.settingsHideMatureCheckbox = q('#civitai-settings-hide-mature');
    this.settingsNsfwThresholdInput = q('#civitai-settings-nsfw-threshold');

    // Confirm modal
    this.confirmModal = q('#civitai-confirm-clear-modal');
    this.confirmText = q('#civitai-confirm-text');
    this.confirmYesButton = q('#civitai-confirm-yes');
    this.confirmNoButton = q('#civitai-confirm-no');

    // Tabs
    this.tabs = {};
    this.modal.querySelectorAll('.civitai-downloader-tab').forEach(t => { this.tabs[t.dataset.tab] = t; });
    this.tabContents = {};
    this.modal.querySelectorAll('.civitai-downloader-tab-content').forEach(c => {
      const n = c.id.replace('civitai-tab-', '');
      if (n) this.tabContents[n] = c;
    });
  }

  async initializeUI() {
    await this.populateModelTypes();
    await this.populateBaseModels();
    await this.loadAndApplySettings();
    await this.loadGlobalRootSetting();
  }

  async populateModelTypes() {
    try {
      const t = await CivitaiDownloaderAPI.getModelTypes();
      if (!t || typeof t !== 'object') throw 0;
      this.modelTypes = t;
      const sorted = Object.entries(t).sort((a, b) => a[1].localeCompare(b[1]));
      this.downloadModelTypeSelect.innerHTML = '';
      this.searchTypeSelect.innerHTML = '<option value="any">Any Type</option>';
      this.settingsDefaultTypeSelect.innerHTML = '';
      sorted.forEach(([k, v]) => {
        const o = document.createElement('option');
        o.value = k; o.textContent = v;
        this.downloadModelTypeSelect.appendChild(o.cloneNode(true));
        this.settingsDefaultTypeSelect.appendChild(o.cloneNode(true));
        this.searchTypeSelect.appendChild(o.cloneNode(true));
      });
    } catch (_) {
      this.downloadModelTypeSelect.innerHTML = '<option value="checkpoints">Checkpoints</option>';
      this.modelTypes = { checkpoints: "Checkpoints" };
    }
  }

  async populateBaseModels() {
    try {
      const r = await CivitaiDownloaderAPI.getBaseModels();
      if (!r?.base_models) throw 0;
      this.baseModels = r.base_models;
      const sel = this.searchBaseModelSelect;
      while (sel.options.length > 1) sel.remove(1);
      this.baseModels.forEach(bm => {
        const o = document.createElement('option');
        o.value = bm; o.textContent = bm;
        sel.appendChild(o);
      });
    } catch (_) {}
  }

  switchTab(id) {
    if (this.activeTab === id || !this.tabs[id]) return;
    this.tabs[this.activeTab]?.classList.remove('active');
    this.tabContents[this.activeTab]?.classList.remove('active');
    this.tabs[id].classList.add('active');
    this.tabContents[id].classList.add('active');
    this.tabContents[id].scrollTop = 0;
    this.activeTab = id;
    if (id === 'status') this.updateStatus();
    else if (id === 'settings') { this.applySettings(); this.checkCivitaiStatus(); }
    else if (id === 'library' && this._libraryModels) {
      this.renderLibrary(this._libraryModels, this.libraryListContainer, this.librarySearchInput?.value || '');
    }
    else if (id === 'download' && Object.keys(this.modelTypes).length)
      this.downloadModelTypeSelect.value = this.downloadModelTypeSelect.value || this.settings.defaultModelType;
  }

  openModal() {
    this.modal?.classList.add('open');
    document.body.style.setProperty('overflow', 'hidden', 'important');
    this.startStatusUpdates();
    // Auto-scan library in background on every open (fast, non-blocking)
    this.handleLibraryScan(true);
  }

  closeModal() {
    this.modal?.classList.remove('open');
    document.body.style.removeProperty('overflow');
    this.stopStatusUpdates();

    // Reset ONLY search + download (library and status persist)
    if (this.searchResultsContainer) this.searchResultsContainer.innerHTML = '';
    if (this.searchPaginationContainer) this.searchPaginationContainer.innerHTML = '';
    if (this.searchQueryInput) this.searchQueryInput.value = '';
    if (this.searchTypeSelect) this.searchTypeSelect.value = 'any';
    if (this.searchBaseModelSelect) this.searchBaseModelSelect.value = 'any';
    if (this.searchSortSelect) this.searchSortSelect.value = 'Relevancy';
    this.searchPagination.currentPage = 1;

    if (this.downloadPreviewArea) this.downloadPreviewArea.innerHTML = `<div class="civitai-empty-state"><i class="fas fa-cloud-download-alt" style="font-size:2.5em;opacity:.3;"></i><p>Search for a model and click the download button, or paste a Civitai URL below.</p></div>`;
    if (this.modelUrlInput) this.modelUrlInput.value = '';
    if (this.customFilenameInput) this.customFilenameInput.value = '';
    if (this.subfolderInput) this.subfolderInput.value = '';
    const hiddenVid = this.modal?.querySelector('#civitai-model-version-id');
    if (hiddenVid) hiddenVid.value = '';
    this._previewModelId = null;
    this._previewVersionId = null;
    if (this.downloadSubmitButton) {
      this.downloadSubmitButton.disabled = false;
      this.downloadSubmitButton.className = 'civitai-button primary civitai-download-btn';
      this.downloadSubmitButton.innerHTML = '<i class="fas fa-download"></i> Download';
    }

    if (this.activeTab !== 'search') this.switchTab('search');
  }

  formatBytes(b, d = 2) {
    if (b == null || isNaN(b)) return 'N/A';
    if (b === 0) return '0 B';
    const k = 1024, s = ['B','KB','MB','GB','TB'];
    const i = Math.floor(Math.log(Math.abs(b)) / Math.log(k));
    return parseFloat((b / Math.pow(k, i)).toFixed(d)) + ' ' + s[i];
  }
  formatSpeed(b) { return (!isFinite(b) || b <= 0) ? '' : this.formatBytes(b) + '/s'; }
  showToast(m, t = 'info', d = 3000) { this.feedback?.show(m, t, d); }
  ensureFontAwesome() { this.feedback?.ensureFontAwesome(); }

  inferFolderFromCivitaiType(ct) {
    if (!ct) return null;
    const t = ct.trim().toLowerCase();
    const keys = Object.keys(this.modelTypes || {});
    if (!keys.length) return null;
    if (keys.includes(t)) return t;
    if (keys.includes(t + 's')) return t + 's';
    const map = { checkpoint:['checkpoints'], lora:['loras'], locon:['loras'], lycoris:['loras'], vae:['vae'], textualinversion:['embeddings'], embedding:['embeddings'], hypernetwork:['hypernetworks'], controlnet:['controlnet'], unet:['unet'], upscaler:['upscale_models'], motionmodule:['motion_models'] };
    for (const c of (map[t] || [])) if (keys.includes(c)) return c;
    return keys.find(k => k.includes(t)) || null;
  }

  async autoSelectModelTypeFromCivitai(ct) {
    const f = this.inferFolderFromCivitaiType(ct);
    if (f && this.downloadModelTypeSelect.value !== f) this.downloadModelTypeSelect.value = f;
  }

  renderSearchPagination(meta) {
    const c = this.searchPaginationContainer;
    if (!c) return;
    if (!meta || meta.totalPages <= 1) { c.innerHTML = ''; this.searchPagination = { ...this.searchPagination, ...meta }; return; }
    this.searchPagination = { ...this.searchPagination, ...meta };
    const { currentPage: cp, totalPages: tp, totalItems: ti } = this.searchPagination;
    const btn = (t, p, dis, cur) => {
      const b = document.createElement('button');
      b.className = `civitai-button small civitai-page-button${cur ? ' primary active' : ''}`;
      b.dataset.page = p; b.disabled = !!dis; b.innerHTML = t; b.type = 'button'; return b;
    };
    const f = document.createDocumentFragment();
    f.appendChild(btn('&laquo;', cp - 1, cp === 1));
    let s = Math.max(1, cp - 2), e = Math.min(tp, cp + 2);
    if (s > 1) f.appendChild(btn('1', 1));
    if (s > 2) { const sp = document.createElement('span'); sp.textContent = '…'; f.appendChild(sp); }
    for (let i = s; i <= e; i++) f.appendChild(btn(String(i), i, false, i === cp));
    if (e < tp - 1) { const sp = document.createElement('span'); sp.textContent = '…'; f.appendChild(sp); }
    if (e < tp) f.appendChild(btn(String(tp), tp));
    f.appendChild(btn('&raquo;', cp + 1, cp === tp));
    const info = document.createElement('div');
    info.className = 'civitai-pagination-info';
    info.textContent = `Page ${cp}/${tp} (${ti.toLocaleString()})`;
    f.appendChild(info);
    c.innerHTML = ''; c.appendChild(f);
  }

  // Delegated
  setupEventListeners = () => setupEventListeners(this);
  getDefaultSettings = () => getDefaultSettings();
  loadAndApplySettings = () => loadAndApplySettings(this);
  loadSettingsFromCookie = () => loadSettingsFromCookie(this);
  saveSettingsToCookie = () => saveSettingsToCookie(this);
  applySettings = () => applySettings(this);
  handleSettingsSave = () => handleSettingsSave(this);
  loadGlobalRootSetting = () => loadGlobalRootSetting(this);
  handleSetGlobalRoot = () => handleSetGlobalRoot(this);
  handleClearGlobalRoot = () => handleClearGlobalRoot(this);
  checkCivitaiStatus = () => checkCivitaiStatus(this);
  handleDownloadSubmit = () => handleDownloadSubmit(this);
  handleSearchSubmit = () => handleSearchSubmit(this);
  fetchAndDisplayDownloadPreview = () => fetchAndDisplayDownloadPreview(this);
  debounceFetchDownloadPreview = (d) => debounceFetchDownloadPreview(this, d);
  startStatusUpdates = () => startStatusUpdates(this);
  stopStatusUpdates = () => stopStatusUpdates(this);
  updateStatus = () => updateStatus(this);
  handleCancelDownload = (id) => handleCancelDownload(this, id);
  handleRetryDownload = (id, b) => handleRetryDownload(this, id, b);
  handleOpenPath = (id, b) => handleOpenPath(this, id, b);
  handleClearHistory = () => handleClearHistory(this);
  handleLibraryScan = (silent) => handleLibraryScan(this, silent);
  handleDeleteModel = (p, n) => handleDeleteModel(this, p, n);
  executeDeleteModel = () => executeDeleteModel(this);
  isVersionInstalled = (mid, vid) => isVersionInstalled(this, mid, vid);
  renderDownloadList = (i, c, m) => renderDownloadList(this, i, c, m);
  renderSearchResults = (i) => renderSearchResults(this, i);
  renderDownloadPreview = (d) => renderDownloadPreview(this, d);
  renderLibrary = (m, c, f) => renderLibrary(this, m, c, f);
}
