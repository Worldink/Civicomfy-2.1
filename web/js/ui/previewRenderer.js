/**
 * Download tab preview: version selector, image gallery, description, file info.
 * "View on Civitai" moved here. EA and already-installed checks shown inline.
 */
const PH = `/extensions/Civicomfy/images/placeholder.jpeg`;
const _IMG_BASE = "https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7QA";

export function renderDownloadPreview(ui, data) {
  if (!ui.downloadPreviewArea) return;
  ui.ensureFontAwesome();

  const mid = data.model_id;
  const vid = data.version_id;
  const name = data.model_name || 'Untitled';
  const creator = data.creator_username || 'Unknown';
  const mtype = data.model_type || 'N/A';
  const vname = data.version_name || 'N/A';
  const bm = data.base_model || 'N/A';
  const stats = data.stats || {};
  const desc = data.description_html || '';
  const vdesc = data.version_description_html || '';
  const fi = data.file_info || {};
  const files = data.files || [];
  const allVersions = data.all_versions || [];
  const images = data.images || [];
  const trainedWords = data.trained_words || [];
  const isEA = data.is_early_access === true;
  const eaDeadline = data.early_access_deadline;
  // Check installed from in-memory library scan (instant, no backend call)
  const alreadyDl = ui.isVersionInstalled(mid, vid) || data.already_downloaded === true;

  // Store current preview IDs for status poll to detect completed downloads
  ui._previewModelId = mid;
  ui._previewVersionId = vid;

  const civLink = mid ? `https://civitai.com/models/${mid}${vid ? '?modelVersionId=' + vid : ''}` : '#';

  // --- Version selector ---
  let versionOptions = allVersions.map(v => {
    const sel = v.id == vid ? 'selected' : '';
    const ea = v.is_early_access ? ' [EA]' : '';
    return `<option value="${v.id}" ${sel}>${v.name}${v.baseModel ? ' — ' + v.baseModel : ''}${ea}</option>`;
  }).join('');

  // --- Image gallery ---
  let galleryHTML = '';
  if (images.length > 0) {
    galleryHTML = `<div class="civitai-preview-gallery">
      ${images.slice(0, 6).map((img, i) => {
        const nsfwLvl = img.nsfwLevel || 0;
        const shouldBlur = ui.settings?.hideMatureInSearch && nsfwLvl >= (ui.settings?.nsfwBlurMinLevel ?? 4);
        const blurClass = shouldBlur ? ' blurred' : '';
        const overlay = shouldBlur ? '<div class="civitai-nsfw-overlay">R</div>' : '';
        if (img.type === 'video') {
          return `<div class="civitai-gallery-item${blurClass}" data-nsfw-level="${nsfwLvl}">
            <video class="civitai-hover-video" src="${img.url}" muted loop playsinline preload="metadata"></video>
            ${overlay}</div>`;
        }
        const url = img.url.includes('/width=') ? img.url : `${img.url}/width=400`;
        return `<div class="civitai-gallery-item${blurClass}" data-nsfw-level="${nsfwLvl}">
          <img src="${url}" loading="lazy" onerror="this.style.display='none';">
          ${overlay}</div>`;
      }).join('')}
    </div>`;
  }

  // --- Status banner ---
  let statusBanner = '';
  if (isEA) {
    statusBanner = `<div class="civitai-ea-banner"><i class="fas fa-lock"></i> Early Access${eaDeadline ? ' — releases ' + new Date(eaDeadline).toLocaleDateString() : ''}</div>`;
  } else if (alreadyDl) {
    statusBanner = `<div class="civitai-installed-banner"><i class="fas fa-check-circle"></i> Already installed</div>`;
  }

  // --- File selector ---
  let fileSelect = '';
  if (files.length > 1) {
    fileSelect = `<div class="civitai-form-group" style="margin-top:10px;">
      <label>File variant</label>
      <select id="civitai-file-select" class="civitai-select">
        <option value="">Auto (primary)</option>
        ${files.map(f => {
          const sz = typeof f.size_kb === 'number' ? ui.formatBytes(f.size_kb * 1024) : '?';
          return `<option value="${f.id || ''}" ${!f.downloadable ? 'disabled' : ''}>${f.name || '?'} — ${f.format || ''} ${sz}</option>`;
        }).join('')}
      </select>
    </div>`;
  }

  // --- Trained words ---
  let twHTML = '';
  if (trainedWords.length) {
    twHTML = `<div class="civitai-trained-words"><strong>Trigger words:</strong> ${trainedWords.map(w => `<code>${w}</code>`).join(' ')}</div>`;
  }

  const html = `
    ${statusBanner}
    <div class="civitai-preview-header">
      <div class="civitai-preview-title-row">
        <h3>${name}</h3>
        <a href="${civLink}" target="_blank" rel="noopener" class="civitai-button small" title="View on Civitai">
          <i class="fas fa-external-link-alt"></i> Civitai
        </a>
      </div>
      <div class="civitai-preview-meta">
        <span><i class="fas fa-user"></i> ${creator}</span>
        <span class="civitai-type-pill">${mtype}</span>
        <span><i class="fas fa-download"></i> ${(stats.downloads||0).toLocaleString()}</span>
        <span><i class="fas fa-thumbs-up"></i> ${(stats.likes||0).toLocaleString()}</span>
      </div>
    </div>

    <div class="civitai-preview-version-row">
      <label>Version:</label>
      <select id="civitai-version-select" class="civitai-select">${versionOptions}</select>
      <span class="base-model-badge">${bm}</span>
    </div>

    ${galleryHTML}
    ${twHTML}

    <div class="civitai-preview-file-info">
      <span><strong>${fi.name || 'N/A'}</strong></span>
      <span>${ui.formatBytes((fi.size_kb||0)*1024)}</span>
      <span>${fi.format || ''}</span>
      <span>${fi.precision || ''}</span>
      <span>${fi.model_size || ''}</span>
    </div>
    ${fileSelect}

    ${desc ? `<details class="civitai-preview-desc"><summary>Description</summary><div class="model-description-content">${desc}</div></details>` : ''}
    ${vdesc ? `<details class="civitai-preview-desc"><summary>Version Notes</summary><div class="model-description-content">${vdesc}</div></details>` : ''}
  `;

  ui.downloadPreviewArea.innerHTML = html;

  // Update hidden version ID field
  const hiddenVid = ui.modal.querySelector('#civitai-model-version-id');
  if (hiddenVid) hiddenVid.value = vid || '';

  // Version selector change -> reload preview
  const vsel = ui.downloadPreviewArea.querySelector('#civitai-version-select');
  if (vsel) {
    vsel.addEventListener('change', () => {
      if (hiddenVid) hiddenVid.value = vsel.value;
      ui.fetchAndDisplayDownloadPreview();
    });
  }

  // Hover video
  ui.downloadPreviewArea.querySelectorAll('.civitai-hover-video').forEach(v => {
    const p = v.closest('.civitai-gallery-item');
    if (p) {
      p.addEventListener('mouseenter', () => { try { v.play(); } catch(_){} });
      p.addEventListener('mouseleave', () => { try { v.pause(); v.currentTime = 0; } catch(_){} });
    }
  });

  // Blur toggle
  ui.downloadPreviewArea.querySelectorAll('.civitai-gallery-item.blurred').forEach(el => {
    el.style.cursor = 'pointer';
    el.addEventListener('click', () => {
      el.classList.toggle('blurred');
      const ov = el.querySelector('.civitai-nsfw-overlay');
      if (ov) ov.style.display = el.classList.contains('blurred') ? '' : 'none';
    });
  });

  // Download button state
  if (ui.downloadSubmitButton) {
    if (isEA) {
      ui.downloadSubmitButton.disabled = true;
      ui.downloadSubmitButton.className = 'civitai-button civitai-download-btn civitai-btn-ea';
      ui.downloadSubmitButton.innerHTML = '<i class="fas fa-lock"></i> Early Access — Not Available';
    } else if (alreadyDl) {
      ui.downloadSubmitButton.disabled = true;
      ui.downloadSubmitButton.className = 'civitai-button civitai-download-btn civitai-btn-installed';
      ui.downloadSubmitButton.innerHTML = '<i class="fas fa-check"></i> Already Installed';
    } else {
      ui.downloadSubmitButton.disabled = false;
      ui.downloadSubmitButton.className = 'civitai-button primary civitai-download-btn';
      ui.downloadSubmitButton.innerHTML = '<i class="fas fa-download"></i> Download';
    }
  }
}
