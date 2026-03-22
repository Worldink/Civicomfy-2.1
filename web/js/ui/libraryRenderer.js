export function renderLibrary(ui, models, container, filter = '') {
  ui.feedback?.ensureFontAwesome();
  if (!models?.length) { container.innerHTML = '<p>No models found. Click "Scan".</p>'; return; }

  const lf = filter.toLowerCase().trim();
  const filtered = lf ? models.filter(m => ((m.model_name || m.filename || '') + ' ' + (m.model_type_folder || '')).toLowerCase().includes(lf)) : models;
  if (!filtered.length) { container.innerHTML = `<p>No match for "${filter}".</p>`; return; }

  const frag = document.createDocumentFragment();
  filtered.forEach(m => {
    const el = document.createElement('div');
    el.className = 'civitai-download-item civitai-library-item';
    const name = m.model_name || m.filename;
    const abbr = m.type_abbreviation || '?';
    const prevRel = m.preview_rel;
    const prevType = m.preview_type || 'image';

    let thumb;
    if (m.has_preview && prevRel) {
      const url = `/civitai/serve_preview?path=${encodeURIComponent(prevRel)}`;
      thumb = prevType === 'video'
        ? `<video class="civitai-thumb-media civitai-hover-video" src="${url}" muted loop playsinline preload="metadata"></video>`
        : `<img src="${url}" class="civitai-thumb-media" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='flex';"><div class="civitai-thumb-fallback" style="display:none;">${abbr}</div>`;
    } else {
      thumb = `<div class="civitai-thumb-fallback">${abbr}</div>`;
    }

    const metaIcon = m.has_metadata
      ? '<span class="civitai-meta-badge" title="Civitai metadata"><i class="fas fa-check-circle" style="color:#4caf50;"></i></span>'
      : '<span class="civitai-meta-badge" title="No metadata"><i class="fas fa-question-circle" style="color:#666;"></i></span>';

    el.innerHTML = `
      <div class="civitai-thumbnail-container" style="width:65px;height:65px;">
        ${thumb}
      </div>
      <div class="civitai-download-info">
        <strong>${name} ${metaIcon}</strong>
        ${m.version_name ? `<p>${m.version_name}</p>` : ''}
        ${m.base_model ? `<p><span class="base-model-badge">${m.base_model}</span></p>` : ''}
        ${m.creator ? `<p style="color:#aaa;"><i class="fas fa-user"></i> ${m.creator}</p>` : ''}
        <p class="filename" title="${m.rel_path}">${m.filename} — ${ui.formatBytes(m.file_size)} — ${m.model_type_folder}</p>
      </div>
      <div class="civitai-download-actions" style="flex-direction:column;gap:5px;">
        ${m.civitai_url ? `<a href="${m.civitai_url}" target="_blank" rel="noopener" class="civitai-button small" title="View on Civitai"><i class="fas fa-external-link-alt"></i></a>` : ''}
        <button class="civitai-button danger small civitai-delete-model-button" data-abs-path="${m.abs_path}" data-name="${name}" title="Delete from disk"><i class="fas fa-trash-alt"></i></button>
      </div>`;

    frag.appendChild(el);
  });

  container.innerHTML = '';
  container.appendChild(frag);

  container.querySelectorAll('.civitai-hover-video').forEach(v => {
    const p = v.closest('.civitai-thumbnail-container');
    if (p) {
      p.addEventListener('mouseenter', () => { try { v.play(); } catch(_){} });
      p.addEventListener('mouseleave', () => { try { v.pause(); v.currentTime = 0; } catch(_){} });
    }
  });
}
