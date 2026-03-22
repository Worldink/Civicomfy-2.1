/**
 * Search results: one card per model, single "Download" button.
 * Version selection happens in Download tab.
 */
const PH = `/extensions/Civicomfy/images/placeholder.jpeg`;
const ABBR = {checkpoint:"CK",lora:"L",locon:"LC",lycoris:"LY",vae:"V",textualinversion:"E",embedding:"E",hypernetwork:"HN",controlnet:"CN",upscaler:"UP",motionmodule:"MM",unet:"UN",other:"?"};

function _ab(t) { return ABBR[(t||"").toLowerCase()] || (t||"?").slice(0,2).toUpperCase(); }

function _thumb(url, type, name, mtype) {
  if (url && type === "video")
    return `<video class="civitai-thumb-media civitai-hover-video" src="${url}" muted loop playsinline preload="metadata"></video>`;
  if (url)
    return `<img src="${url}" alt="${name}" class="civitai-thumb-media" loading="lazy"
      onerror="this.style.display='none';this.nextElementSibling.style.display='flex';">
      <div class="civitai-thumb-fallback" style="display:none;">${_ab(mtype)}</div>`;
  return `<div class="civitai-thumb-fallback">${_ab(mtype)}</div>`;
}

export function renderSearchResults(ui, items) {
  ui.feedback?.ensureFontAwesome();
  const c = ui.searchResultsContainer;
  if (!items?.length) { c.innerHTML = '<p>No results.</p>'; return; }

  const frag = document.createDocumentFragment();

  items.forEach(hit => {
    const mid = hit.id;
    if (!mid) return;
    const name = hit.name || "Untitled";
    const creator = hit.user?.username || "Unknown";
    const type = hit.type || "other";
    const stats = hit.metrics || {};
    const tags = (hit.tags?.map(t => t.name) || []).slice(0, 4);
    const thumbUrl = hit.thumbnailUrl;
    const thumbType = hit.thumbnailType || "image";
    const nsfwLvl = Number(hit.thumbnailNsfwLevel ?? 0);
    const shouldBlur = ui.settings?.hideMatureInSearch && nsfwLvl >= (ui.settings?.nsfwBlurMinLevel ?? 4);
    const isEA = hit.isEarlyAccess === true;
    const pv = hit.version || (hit.versions?.[0]) || {};
    const base = pv.baseModel || "N/A";

    const el = document.createElement('div');
    el.className = 'civitai-search-card';

    const overlay = shouldBlur ? `<div class="civitai-nsfw-overlay">R</div>` : '';
    const eaBadge = isEA ? `<div class="civitai-ea-badge">EA</div>` : '';

    el.innerHTML = `
      <div class="civitai-thumbnail-container${shouldBlur ? ' blurred' : ''}" data-nsfw-level="${nsfwLvl}">
        ${_thumb(thumbUrl, thumbType, name, type)}
        ${overlay}
        ${eaBadge}
      </div>
      <div class="civitai-card-body">
        <div class="civitai-card-title">${name}</div>
        <div class="civitai-card-meta">
          <span><i class="fas fa-user"></i> ${creator}</span>
          <span class="base-model-badge">${base}</span>
          <span class="civitai-type-pill">${type}</span>
        </div>
        <div class="civitai-card-stats">
          <span><i class="fas fa-download"></i> ${(stats.downloadCount||0).toLocaleString()}</span>
          <span><i class="fas fa-thumbs-up"></i> ${(stats.thumbsUpCount||0).toLocaleString()}</span>
          <span><i class="fas fa-bolt"></i> ${(stats.tippedAmountCount||0).toLocaleString()}</span>
        </div>
        ${tags.length ? `<div class="civitai-card-tags">${tags.map(t=>`<span>${t}</span>`).join('')}</div>` : ''}
      </div>
      <div class="civitai-card-action">
        <button class="civitai-button primary small civitai-search-download-button"
          data-model-id="${mid}" data-model-type="${type}"
          ${isEA ? 'title="Early Access — other versions may be available"' : 'title="Open in Download tab"'}>
          <i class="fas fa-arrow-right"></i> Download
        </button>
      </div>`;

    frag.appendChild(el);
  });

  c.innerHTML = '';
  c.appendChild(frag);

  // Hover video
  c.querySelectorAll('.civitai-hover-video').forEach(v => {
    const p = v.closest('.civitai-thumbnail-container');
    if (p) {
      p.addEventListener('mouseenter', () => { try { v.play(); } catch(_){} });
      p.addEventListener('mouseleave', () => { try { v.pause(); v.currentTime = 0; } catch(_){} });
    }
  });
}
