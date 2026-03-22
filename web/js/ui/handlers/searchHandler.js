import { CivitaiDownloaderAPI } from "../../api/civitai.js";

let _lastSearchId = 0;

export async function handleSearchSubmit(ui) {
  const searchId = ++_lastSearchId;
  ui.searchSubmitButton.disabled = true;
  ui.searchSubmitButton.textContent = 'Searching...';
  ui.searchResultsContainer.innerHTML = '<p><i class="fas fa-spinner fa-spin"></i> Searching...</p>';
  ui.searchPaginationContainer.innerHTML = '';

  try {
    const r = await CivitaiDownloaderAPI.searchModels({
      query: ui.searchQueryInput.value.trim(),
      model_types: ui.searchTypeSelect.value === 'any' ? [] : [ui.searchTypeSelect.value],
      base_models: ui.searchBaseModelSelect.value === 'any' ? [] : [ui.searchBaseModelSelect.value],
      sort: ui.searchSortSelect.value,
      limit: ui.searchPagination.limit,
      page: ui.searchPagination.currentPage,
      api_key: ui.settings.apiKey,
    });
    if (searchId !== _lastSearchId) return; // Stale — newer search in flight
    if (!r?.items || !r?.metadata) throw new Error("Invalid response.");
    ui.renderSearchResults(r.items);
    ui.renderSearchPagination(r.metadata);
  } catch (e) {
    if (searchId !== _lastSearchId) return; // Stale
    ui.searchResultsContainer.innerHTML = `<p style="color:#ff6b6b;">${e.details || e.message}</p>`;
    ui.showToast(`Search failed`, 'error');
  } finally {
    if (searchId === _lastSearchId) {
      ui.searchSubmitButton.disabled = false;
      ui.searchSubmitButton.textContent = 'Search';
    }
  }
}
