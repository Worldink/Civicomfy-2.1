import { setCookie, getCookie } from "../../utils/cookies.js";
import { CivitaiDownloaderAPI } from "../../api/civitai.js";

const COOKIE = 'civitaiSettings_v2';

export function getDefaultSettings() {
  return {
    apiKey: '', numConnections: 1, defaultModelType: 'checkpoints',
    autoOpenStatusTab: true, searchResultLimit: 20,
    hideMatureInSearch: true, nsfwBlurMinLevel: 4,
  };
}

export function loadAndApplySettings(ui) {
  ui.settings = loadSettingsFromCookie(ui);
  applySettings(ui);
}

export function loadSettingsFromCookie(ui) {
  const def = getDefaultSettings();
  const raw = getCookie(COOKIE);
  if (raw) {
    try { return { ...def, ...JSON.parse(raw) }; } catch (_) {}
  }
  return def;
}

export function saveSettingsToCookie(ui) {
  try {
    setCookie(COOKIE, JSON.stringify(ui.settings), 365);
    ui.showToast('Settings saved!', 'success');
  } catch (_) {
    ui.showToast('Error saving settings', 'error');
  }
}

export function applySettings(ui) {
  const s = ui.settings;
  if (ui.settingsApiKeyInput) ui.settingsApiKeyInput.value = s.apiKey || '';
  if (ui.settingsDefaultTypeSelect) {
    ui.settingsDefaultTypeSelect.value = s.defaultModelType || 'checkpoints';
  }
  if (ui.settingsAutoOpenCheckbox) ui.settingsAutoOpenCheckbox.checked = s.autoOpenStatusTab;
  if (ui.settingsHideMatureCheckbox) ui.settingsHideMatureCheckbox.checked = s.hideMatureInSearch;
  if (ui.settingsNsfwThresholdInput) ui.settingsNsfwThresholdInput.value = s.nsfwBlurMinLevel ?? 4;
  if (ui.downloadModelTypeSelect && Object.keys(ui.modelTypes).length > 0) {
    ui.downloadModelTypeSelect.value = s.defaultModelType || 'checkpoints';
  }
  ui.searchPagination.limit = s.searchResultLimit || 20;
}

export async function loadGlobalRootSetting(ui) {
  if (!ui.settingsGlobalRootInput) return;
  try {
    const r = await CivitaiDownloaderAPI.getGlobalRoot();
    ui.settingsGlobalRootInput.value = r?.global_root || '';
  } catch (_) {}
}

export async function handleSetGlobalRoot(ui) {
  const p = ui.settingsGlobalRootInput?.value.trim();
  if (!p) { ui.showToast("Enter a path.", "error"); return; }
  try {
    const r = await CivitaiDownloaderAPI.setGlobalRoot(p);
    ui.settingsGlobalRootInput.value = r?.global_root || p;
    ui.showToast("Global root set.", "success");
  } catch (e) {
    ui.showToast(e.details || e.message || "Failed.", "error", 5000);
  }
}

export async function handleClearGlobalRoot(ui) {
  try {
    await CivitaiDownloaderAPI.clearGlobalRoot();
    if (ui.settingsGlobalRootInput) ui.settingsGlobalRootInput.value = '';
    ui.showToast("Global root cleared.", "success");
  } catch (e) {
    ui.showToast(e.details || "Failed.", "error");
  }
}

export function handleSettingsSave(ui) {
  ui.settings.apiKey = ui.settingsApiKeyInput.value.trim();
  ui.settings.defaultModelType = ui.settingsDefaultTypeSelect.value;
  ui.settings.autoOpenStatusTab = ui.settingsAutoOpenCheckbox.checked;
  ui.settings.hideMatureInSearch = ui.settingsHideMatureCheckbox.checked;
  const nv = Number(ui.settingsNsfwThresholdInput.value);
  ui.settings.nsfwBlurMinLevel = Number.isFinite(nv) && nv >= 0 ? Math.min(128, Math.round(nv)) : 4;
  saveSettingsToCookie(ui);
  applySettings(ui);
}

export async function checkCivitaiStatus(ui) {
  const setDot = (id, status) => {
    const dot = ui.modal.querySelector(`#civitai-dot-${id}`);
    if (dot) { dot.className = `civitai-dot ${status}`; }
  };
  const setMsg = (id, msg) => {
    const el = ui.modal.querySelector(`#civitai-msg-${id}`);
    if (el) el.textContent = msg;
  };

  // Set all to checking
  ['statuspage', 'api', 'search'].forEach(id => {
    setDot(id, 'unknown');
    setMsg(id, 'Checking...');
  });

  try {
    const r = await CivitaiDownloaderAPI.checkCivitaiStatus();
    if (r) {
      const map = { status_page: 'statuspage', api: 'api', search: 'search' };
      for (const [key, domId] of Object.entries(map)) {
        const svc = r[key];
        if (svc) {
          setDot(domId, svc.status || 'unknown');
          setMsg(domId, svc.message || svc.status || '?');
        }
      }
    }
  } catch (e) {
    ['statuspage', 'api', 'search'].forEach(id => {
      setDot(id, 'error');
      setMsg(id, 'Check failed');
    });
  }
}
