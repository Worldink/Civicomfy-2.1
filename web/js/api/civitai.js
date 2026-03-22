import { api } from "../../../../scripts/api.js";

export class CivitaiDownloaderAPI {
  static async _req(ep, opts = {}) {
    try {
      const url = ep.startsWith("/") ? ep : `/${ep}`;
      const r = await api.fetchApi(url, opts);

      if (!r.ok) {
        // Try multiple ways to extract error info
        let errorMsg = `HTTP ${r.status}`;
        let details = "";
        try {
          const d = await r.json();
          errorMsg = d.error || d.reason || d.message || errorMsg;
          details = d.details || d.detail || d.error || "";
        } catch (_) {
          try {
            const txt = await r.text();
            // aiohttp HTTPError returns HTML with reason in title/body
            const reasonMatch = txt.match(/(?:<title>|<h1>)\d+:\s*(.+?)(?:<\/title>|<\/h1>)/i);
            if (reasonMatch) errorMsg = reasonMatch[1];
            else if (txt.length < 200) details = txt;
          } catch (_2) {}
        }
        const e = new Error(errorMsg);
        e.details = details || errorMsg;
        e.status = r.status;
        throw e;
      }

      if (r.status === 204 || r.headers.get("Content-Length") === "0") return null;
      return await r.json();
    } catch (e) {
      if (!e.details) e.details = e.message;
      throw e;
    }
  }

  static _post(u, b) {
    return this._req(u, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(b),
    });
  }

  // Search
  static searchModels(p)     { return this._post("/civitai/search", p); }
  static getBaseModels()      { return this._req("/civitai/base_models"); }
  static getModelTypes()      { return this._req("/civitai/model_types"); }

  // Model details / Download
  static getModelDetails(p)   { return this._post("/civitai/get_model_details", p); }
  static downloadModel(p)     { return this._post("/civitai/download", p); }
  static cancelDownload(id)   { return this._post("/civitai/cancel", { download_id: id }); }
  static retryDownload(id)    { return this._post("/civitai/retry", { download_id: id }); }

  // Status
  static getStatus()          { return this._req("/civitai/status"); }
  static clearHistory()       { return this._post("/civitai/clear_history", {}); }
  static openPath(id)         { return this._post("/civitai/open_path", { download_id: id }); }

  // Dirs
  static getModelDirs(t)      { return this._req(`/civitai/model_dirs?type=${encodeURIComponent(t||'checkpoints')}`); }
  static createModelType(n)   { return this._post("/civitai/create_model_type", { name: n }); }
  static getGlobalRoot()      { return this._req("/civitai/global_root"); }
  static setGlobalRoot(p)     { return this._post("/civitai/global_root", { path: p }); }
  static clearGlobalRoot()    { return this._post("/civitai/global_root/clear", {}); }

  // Library
  static scanModels()         { return this._req("/civitai/scan_models"); }
  static deleteModel(p)       { return this._post("/civitai/delete_model", { abs_path: p }); }

  // Status check
  static checkCivitaiStatus() { return this._req("/civitai/check_status"); }
}
