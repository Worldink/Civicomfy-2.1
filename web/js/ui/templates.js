export function modalTemplate(settings = {}) {
  return `
  <div class="civitai-downloader-modal-content">
    <div class="civitai-downloader-header">
      <h2>Civicomfy</h2>
      <button class="civitai-close-button" id="civitai-close-modal">&times;</button>
    </div>
    <div class="civitai-downloader-body">
      <div class="civitai-downloader-tabs">
        <button class="civitai-downloader-tab active" data-tab="search">Search</button>
        <button class="civitai-downloader-tab" data-tab="download">Download</button>
        <button class="civitai-downloader-tab" data-tab="status">Status <span id="civitai-status-indicator" style="display:none;">(<span id="civitai-active-count">0</span>)</span></button>
        <button class="civitai-downloader-tab" data-tab="library">Library</button>
        <button class="civitai-downloader-tab" data-tab="settings">Settings</button>
      </div>

      <!-- SEARCH -->
      <div id="civitai-tab-search" class="civitai-downloader-tab-content active">
        <form id="civitai-search-form">
          <div class="civitai-search-controls">
            <input type="text" id="civitai-search-query" class="civitai-input" placeholder="Search models on Civitai...">
            <select id="civitai-search-type" class="civitai-select"><option value="any">Any Type</option></select>
            <select id="civitai-search-base-model" class="civitai-select"><option value="any">Any Base</option></select>
            <select id="civitai-search-sort" class="civitai-select">
              <option value="Relevancy" selected>Relevancy</option>
              <option value="Most Downloaded">Most Downloaded</option>
              <option value="Highest Rated">Highest Rated</option>
              <option value="Most Liked">Most Liked</option>
              <option value="Most Collected">Most Collected</option>
              <option value="Most Buzz">Most Buzz</option>
              <option value="Newest">Newest</option>
            </select>
            <button type="submit" id="civitai-search-submit" class="civitai-button primary">Search</button>
          </div>
        </form>
        <div id="civitai-search-results" class="civitai-search-results"></div>
        <div id="civitai-search-pagination" style="text-align:center;margin-top:16px;"></div>
      </div>

      <!-- DOWNLOAD -->
      <div id="civitai-tab-download" class="civitai-downloader-tab-content">
        <div id="civitai-download-preview-area" class="civitai-download-preview-area">
          <div class="civitai-empty-state">
            <i class="fas fa-cloud-download-alt" style="font-size:2.5em;opacity:.3;"></i>
            <p>Search for a model and click the download button, or paste a Civitai URL below.</p>
          </div>
        </div>
        <form id="civitai-download-form" class="civitai-download-form-bottom">
          <div class="civitai-form-row">
            <div class="civitai-form-group" style="flex:2;">
              <label for="civitai-model-url">Civitai URL or Model ID</label>
              <input type="text" id="civitai-model-url" class="civitai-input" placeholder="https://civitai.com/models/12345" required>
            </div>
            <div class="civitai-form-group" style="flex:1;">
              <label for="civitai-model-type">Save To</label>
              <div style="display:flex;gap:5px;">
                <select id="civitai-model-type" class="civitai-select" required></select>
                <button type="button" id="civitai-create-model-type" class="civitai-button small" title="New folder"><i class="fas fa-folder-plus"></i></button>
              </div>
            </div>
          </div>
          <div class="civitai-form-row">
            <div class="civitai-form-group" style="flex:1;">
              <label for="civitai-subfolder">Subfolder (optional)</label>
              <input type="text" id="civitai-subfolder" class="civitai-input" placeholder="e.g. illustrious">
            </div>
            <div class="civitai-form-group" style="flex:1;">
              <label for="civitai-custom-filename">Custom Filename (optional)</label>
              <input type="text" id="civitai-custom-filename" class="civitai-input" placeholder="Leave blank for original">
            </div>
          </div>
          <!-- Hidden fields for internal state -->
          <input type="hidden" id="civitai-model-version-id" value="">
          <button type="submit" id="civitai-download-submit" class="civitai-button primary civitai-download-btn">
            <i class="fas fa-download"></i> Download
          </button>
        </form>
      </div>

      <!-- STATUS -->
      <div id="civitai-tab-status" class="civitai-downloader-tab-content">
        <div id="civitai-status-content">
          <div class="civitai-status-section">
            <h3>Active Downloads</h3>
            <div id="civitai-active-list" class="civitai-download-list"><p>No active downloads.</p></div>
          </div>
          <div class="civitai-status-section">
            <h3>Queued</h3>
            <div id="civitai-queued-list" class="civitai-download-list"><p>Queue empty.</p></div>
          </div>
          <div class="civitai-status-section">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
              <h3>History</h3>
              <button id="civitai-clear-history-button" class="civitai-button danger small"><i class="fas fa-trash-alt"></i> Clear</button>
            </div>
            <div id="civitai-history-list" class="civitai-download-list"><p>No history.</p></div>
          </div>
        </div>
      </div>

      <!-- LIBRARY -->
      <div id="civitai-tab-library" class="civitai-downloader-tab-content">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
          <h3 style="margin:0;">Installed Models</h3>
          <button id="civitai-library-scan" class="civitai-button primary small"><i class="fas fa-sync-alt"></i> Scan</button>
        </div>
        <input type="text" id="civitai-library-search" class="civitai-input" placeholder="Filter..." style="max-width:350px;margin-bottom:14px;">
        <div id="civitai-library-list" class="civitai-download-list"><p>Click "Scan" to discover models.</p></div>
      </div>

      <!-- SETTINGS -->
      <div id="civitai-tab-settings" class="civitai-downloader-tab-content">
        <form id="civitai-settings-form">
          <div class="civitai-settings-container">
            <div class="civitai-settings-section">
              <h4>API & Paths</h4>
              <div class="civitai-form-group">
                <label for="civitai-settings-api-key">Civitai API Key <span style="font-weight:normal;color:#888;">(optional)</span></label>
                <input type="password" id="civitai-settings-api-key" class="civitai-input" placeholder="Not required for most models" autocomplete="new-password">
                <p style="font-size:.82em;color:#999;margin-top:5px;">Only needed for some restricted models. Get yours at <a href="https://civitai.com/user/account" target="_blank" rel="noopener" style="color:var(--accent-color,#5c8aff);">civitai.com/user/account</a></p>
              </div>
              <div class="civitai-form-group">
                <label for="civitai-settings-global-root">Global Root</label>
                <input type="text" id="civitai-settings-global-root" class="civitai-input" placeholder="/path/to/models">
                <div style="display:flex;gap:6px;margin-top:6px;">
                  <button type="button" id="civitai-settings-set-global-root" class="civitai-button small">Set</button>
                  <button type="button" id="civitai-settings-clear-global-root" class="civitai-button danger small">Clear</button>
                </div>
              </div>
              <div class="civitai-form-group">
                <label for="civitai-settings-default-type">Default Type</label>
                <select id="civitai-settings-default-type" class="civitai-select"></select>
              </div>
            </div>
            <div class="civitai-settings-section">
              <h4>Civitai Status <button type="button" id="civitai-refresh-status" class="civitai-button small" style="float:right;padding:2px 8px;" title="Refresh"><i class="fas fa-sync-alt"></i></button></h4>
              <div id="civitai-service-status" class="civitai-service-status">
                <div class="civitai-status-row"><span class="civitai-dot" id="civitai-dot-statuspage"></span> <span>Status Page</span> <span class="civitai-status-msg" id="civitai-msg-statuspage">Checking...</span></div>
                <div class="civitai-status-row"><span class="civitai-dot" id="civitai-dot-api"></span> <span>REST API</span> <span class="civitai-status-msg" id="civitai-msg-api">Checking...</span></div>
                <div class="civitai-status-row"><span class="civitai-dot" id="civitai-dot-search"></span> <span>Search Engine</span> <span class="civitai-status-msg" id="civitai-msg-search">Checking...</span></div>
              </div>
              <a href="https://status.civitai.com/status/public" target="_blank" rel="noopener" class="civitai-status-link"><i class="fas fa-external-link-alt"></i> View full status on status.civitai.com</a>
            </div>
            <div class="civitai-settings-section">
              <h4>Interface</h4>
              <div class="civitai-form-group inline">
                <input type="checkbox" id="civitai-settings-auto-open-status" class="civitai-checkbox">
                <label for="civitai-settings-auto-open-status">Switch to Status after download</label>
              </div>
              <div class="civitai-form-group inline">
                <input type="checkbox" id="civitai-settings-hide-mature" class="civitai-checkbox" ${settings.hideMatureInSearch ? 'checked' : ''}>
                <label for="civitai-settings-hide-mature">Blur mature thumbnails</label>
              </div>
              <div class="civitai-form-group">
                <label for="civitai-settings-nsfw-threshold">Blur Threshold</label>
                <input type="number" id="civitai-settings-nsfw-threshold" class="civitai-input" value="${settings.nsfwBlurMinLevel ?? 4}" min="0" max="128">
              </div>
            </div>
          </div>
          <button type="submit" id="civitai-settings-save" class="civitai-button primary" style="margin-top:16px;">Save</button>
        </form>
      </div>
    </div>
    <div id="civitai-toast" class="civitai-toast"></div>
    <div id="civitai-confirm-clear-modal" class="civitai-confirmation-modal">
      <div class="civitai-confirmation-modal-content">
        <h4>Confirm</h4>
        <p id="civitai-confirm-text">Are you sure?</p>
        <div class="civitai-confirmation-modal-actions">
          <button id="civitai-confirm-no" class="civitai-button secondary">Cancel</button>
          <button id="civitai-confirm-yes" class="civitai-button danger">Confirm</button>
        </div>
      </div>
    </div>
  </div>`;
}
