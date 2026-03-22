/**
 * Download status renderer with smart DOM diffing.
 * Only updates elements that changed — thumbnails never reload/flash.
 */
const PH = `/extensions/Civicomfy/images/placeholder.jpeg`;

// Track what we've rendered per container to avoid full re-renders
const _rendered = new WeakMap();

export function renderDownloadList(ui, items, container, emptyMsg) {
  if (!items?.length) {
    container.innerHTML = `<p>${emptyMsg}</p>`;
    _rendered.delete(container);
    return;
  }

  const prev = _rendered.get(container) || {};
  const newMap = {};
  const frag = document.createDocumentFragment();
  let changed = false;

  items.forEach(item => {
    const id = item.id || '?';
    // Build a signature of the data that affects rendering
    const sig = `${item.status}|${Math.round(item.progress || 0)}|${Math.round(item.speed || 0)}|${item.error || ''}`;
    newMap[id] = sig;

    // If this item exists and hasn't changed, keep the existing DOM node
    const existingEl = container.querySelector(`.civitai-download-item[data-id="${id}"]`);
    if (existingEl && prev[id] === sig) {
      frag.appendChild(existingEl);
      return;
    }

    // If item exists but data changed, update in-place for progress items
    if (existingEl && prev[id] && item.status === 'downloading') {
      _updateInPlace(ui, existingEl, item);
      frag.appendChild(existingEl);
      newMap[id] = sig;
      changed = true;
      return;
    }

    // New item or significant change — create fresh element
    const el = _createItem(ui, item);
    frag.appendChild(el);
    changed = true;
  });

  // Check if items were removed
  if (Object.keys(prev).length !== Object.keys(newMap).length) {
    changed = true;
  }

  if (changed || container.children.length !== items.length) {
    container.innerHTML = '';
    container.appendChild(frag);
    _setupHoverVideo(container);
    ui.ensureFontAwesome();
  }

  _rendered.set(container, newMap);
}

function _updateInPlace(ui, el, item) {
  // Update progress bar width
  const bar = el.querySelector('.civitai-progress-bar');
  const pct = Math.max(0, Math.min(100, item.progress || 0));
  if (bar) {
    bar.style.width = `${pct}%`;
    bar.textContent = pct > 12 ? `${pct.toFixed(0)}%` : '';
  }

  // Update progress detail text
  const detail = el.querySelector('.civitai-progress-detail');
  if (detail) {
    const total = item.known_size || 0;
    const dl = total > 0 ? total * pct / 100 : 0;
    const speed = Math.max(0, item.speed || 0);
    let eta = '';
    if (speed > 0 && total > 0) {
      const sec = (total - dl) / speed;
      eta = sec < 60 ? `~${Math.round(sec)}s` : sec < 3600 ? `~${Math.floor(sec/60)}m ${Math.round(sec%60)}s` : `~${Math.floor(sec/3600)}h`;
    }
    const dlText = total > 0 ? `${ui.formatBytes(dl)} / ${ui.formatBytes(total)}` : '';
    const left = detail.querySelector('.civitai-dl-left');
    const right = detail.querySelector('.civitai-dl-right');
    if (left) left.textContent = `${pct.toFixed(1)}%${dlText ? ' — ' + dlText : ''}`;
    if (right) right.textContent = `${speed > 0 ? ui.formatSpeed(speed) : ''}${eta ? ' — ' + eta : ''}`;
  }
}

function _createItem(ui, item) {
  const id = item.id || '?';
  const pct = Math.max(0, Math.min(100, item.progress || 0));
  const speed = Math.max(0, item.speed || 0);
  const st = item.status || 'unknown';
  const total = item.known_size || 0;
  const dl = total > 0 ? total * pct / 100 : 0;
  const err = item.error;
  const fname = item.filename || 'N/A';
  const thumb = item.thumbnail || PH;
  const thumbType = item.thumbnail_type || 'image';

  let eta = '';
  if (st === 'downloading' && speed > 0 && total > 0) {
    const sec = (total - dl) / speed;
    eta = sec < 60 ? `~${Math.round(sec)}s` : sec < 3600 ? `~${Math.floor(sec/60)}m ${Math.round(sec%60)}s` : `~${Math.floor(sec/3600)}h`;
  }

  const barCls = st === 'completed' ? 'completed' : st === 'failed' ? 'failed' : st === 'cancelled' ? 'cancelled' : '';

  const el = document.createElement('div');
  el.className = 'civitai-download-item';
  el.dataset.id = id;

  let thumbHTML;
  if (thumbType === 'video' && thumb) {
    thumbHTML = `<video class="civitai-thumb-media civitai-hover-video" src="${thumb}" muted loop playsinline preload="metadata"></video>`;
  } else {
    thumbHTML = `<img src="${thumb}" class="civitai-thumb-media" loading="lazy" onerror="this.src='${PH}';">`;
  }

  let h = `
    <div class="civitai-thumbnail-container" style="width:60px;height:60px;">
      ${thumbHTML}
    </div>
    <div class="civitai-download-info">
      <strong>${item.model_name || 'Model'}</strong>
      ${item.version_name ? `<p>${item.version_name}</p>` : ''}
      <p class="filename">${fname}</p>
      ${err ? `<p class="error-message"><i class="fas fa-exclamation-triangle"></i> ${String(err).substring(0,120)}</p>` : ''}`;

  if (st === 'downloading' || st === 'starting' || st === 'completed') {
    const dlText = total > 0 ? `${ui.formatBytes(dl)} / ${ui.formatBytes(total)}` : '';
    h += `<div class="civitai-progress-container"><div class="civitai-progress-bar ${barCls}" style="width:${pct}%;">${pct > 12 ? pct.toFixed(0)+'%' : ''}</div></div>
      <div class="civitai-progress-detail"><span class="civitai-dl-left">${pct.toFixed(1)}%${dlText ? ' — ' + dlText : ''}</span><span class="civitai-dl-right">${st === 'downloading' && speed > 0 ? ui.formatSpeed(speed) : ''}${eta ? ' — ' + eta : ''}</span></div>`;
  } else {
    h += `<div class="status-line-simple">${st.charAt(0).toUpperCase() + st.slice(1)}</div>`;
  }

  h += `</div><div class="civitai-download-actions">`;
  if (['queued','downloading','starting'].includes(st))
    h += `<button class="civitai-button danger small civitai-cancel-button" data-id="${id}" title="Cancel"><i class="fas fa-times"></i></button>`;
  if (['failed','cancelled'].includes(st))
    h += `<button class="civitai-button small civitai-retry-button" data-id="${id}" title="Retry"><i class="fas fa-redo"></i></button>`;
  if (st === 'completed')
    h += `<button class="civitai-button small civitai-openpath-button" data-id="${id}" title="Open Folder"><i class="fas fa-folder-open"></i></button>`;
  h += `</div>`;

  el.innerHTML = h;
  return el;
}

function _setupHoverVideo(container) {
  container.querySelectorAll('.civitai-hover-video').forEach(v => {
    const p = v.closest('.civitai-thumbnail-container');
    if (p && !p._hoverBound) {
      p._hoverBound = true;
      p.addEventListener('mouseenter', () => { try { v.play(); } catch(_){} });
      p.addEventListener('mouseleave', () => { try { v.pause(); v.currentTime = 0; } catch(_){} });
    }
  });
}
