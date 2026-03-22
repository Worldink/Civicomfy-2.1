"""
Download Manager.
- Prevents duplicate downloads (same output_path)
- Proper shutdown: cancels active downloads, deletes partial files
- Saves max 3 files per model: model + preview + metadata
"""
import atexit
import datetime
import json
import os
import platform
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .chunk_downloader import ChunkDownloader

from ..config import (
    MAX_CONCURRENT_DOWNLOADS, DOWNLOAD_HISTORY_LIMIT, DEFAULT_CONNECTIONS,
    METADATA_SUFFIX, PREVIEW_SUFFIX, METADATA_DOWNLOAD_TIMEOUT, PLUGIN_ROOT,
)

HISTORY_FILE = os.path.join(PLUGIN_ROOT, "download_history.json")
class DownloadManager:
    def __init__(self, max_concurrent: int = MAX_CONCURRENT_DOWNLOADS):
        self.queue: List[Dict[str, Any]] = []
        self.active: Dict[str, Dict[str, Any]] = {}
        self.history: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self.max_concurrent = max(1, max_concurrent)
        self.running = True
        self._load_history()
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # Queue (with duplicate prevention)
    # ------------------------------------------------------------------
    def add_to_queue(self, info: Dict[str, Any]) -> Optional[str]:
        with self._lock:
            out_path = info.get("output_path", "")

            # Prevent duplicate: check if same output_path is already queued or active
            for item in self.queue:
                if item.get("output_path") == out_path:
                    print(f"[Civicomfy] Duplicate blocked (queued): {out_path}")
                    return None
            for _, item in self.active.items():
                if item.get("output_path") == out_path and item.get("status") not in ("completed", "failed", "cancelled"):
                    print(f"[Civicomfy] Duplicate blocked (active): {out_path}")
                    return None

            ts = int(time.time() * 1000)
            hint = os.path.basename(out_path)[:10]
            did = f"dl_{ts}_{hint}"
            info.update({
                "id": did, "status": "queued",
                "added_time": _now(), "progress": 0, "speed": 0,
                "error": None, "start_time": None, "end_time": None,
                "connection_type": "N/A",
            })
            for k in ('url', 'output_path', 'num_connections', 'api_key',
                       'known_size', 'civitai_model_info', 'civitai_version_info',
                       'civitai_primary_file', 'thumbnail', 'filename',
                       'model_url_or_id', 'model_version_id', 'model_type',
                       'force_redownload'):
                info.setdefault(k, None)
            self.queue.append(info)
            return did

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------
    def cancel_download(self, did: str) -> bool:
        dl_inst = None
        with self._lock:
            for i, item in enumerate(self.queue):
                if item["id"] == did:
                    item["status"] = "cancelled"
                    item["end_time"] = _now()
                    item["error"] = "Cancelled from queue"
                    self._to_history(self.queue.pop(i))
                    return True
            if did in self.active:
                ai = self.active[did]
                dl_inst = ai.get("downloader_instance")
                if not dl_inst:
                    ai["status"] = "cancelled"
                    ai["end_time"] = _now()
                    ai["error"] = "Cancelled before start"
                    return True
                if ai["status"] in ("completed", "failed", "cancelled"):
                    return False

        if dl_inst and not dl_inst.is_cancelled:
            dl_inst.cancel()
            return True
        return False

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    _STRIP = frozenset([
        'downloader_instance', 'civitai_model_info', 'civitai_version_info',
        'civitai_primary_file', 'api_key', 'url', 'output_path',
    ])

    def get_status(self) -> Dict[str, List[Dict]]:
        with self._lock:
            def _c(d):
                return {k: v for k, v in d.items() if k not in self._STRIP}
            return {
                "queue": [_c(i) for i in self.queue],
                "active": [_c(i) for i in self.active.values()],
                "history": [_c(i) for i in self.history[:DOWNLOAD_HISTORY_LIMIT]],
            }

    def get_active_paths(self) -> set:
        """Return set of output_path strings currently downloading or queued."""
        with self._lock:
            paths = set()
            for item in self.queue:
                p = item.get("output_path")
                if p:
                    paths.add(os.path.abspath(p))
            for _, item in self.active.items():
                if item.get("status") not in ("completed", "failed", "cancelled"):
                    p = item.get("output_path")
                    if p:
                        paths.add(os.path.abspath(p))
            return paths

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    def _load_history(self):
        if not os.path.exists(HISTORY_FILE):
            self.history = []
            return
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.history = [i for i in data if isinstance(i, dict) and 'id' in i][:DOWNLOAD_HISTORY_LIMIT]
        except Exception:
            self.history = []

    def _save_history(self):
        try:
            tmp = HISTORY_FILE + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.history[:DOWNLOAD_HISTORY_LIMIT], f, indent=2, ensure_ascii=False)
            os.replace(tmp, HISTORY_FILE)
        except Exception as e:
            print(f"[Civicomfy] History save error: {e}")

    def _to_history(self, info: Dict[str, Any]):
        c = {k: v for k, v in info.items() if k != 'downloader_instance'}
        c.setdefault("end_time", _now())
        c.setdefault("status", "unknown")
        self.history.insert(0, c)
        if len(self.history) > DOWNLOAD_HISTORY_LIMIT:
            self.history = self.history[:DOWNLOAD_HISTORY_LIMIT]
        self._save_history()

    def clear_history(self) -> Dict[str, Any]:
        with self._lock:
            n = len(self.history)
            self.history = []
            try:
                if os.path.exists(HISTORY_FILE):
                    os.remove(HISTORY_FILE)
            except Exception as e:
                return {"success": False, "error": str(e)}
            return {"success": True, "message": f"Cleared {n} items."}

    # ------------------------------------------------------------------
    # Retry
    # ------------------------------------------------------------------
    def retry_download(self, original_id: str) -> Dict[str, Any]:
        with self._lock:
            orig = next((i for i in self.history if i.get("id") == original_id), None)
            if not orig:
                return {"success": False, "error": "Not found in history."}
            if orig.get("status") not in ("failed", "cancelled"):
                return {"success": False, "error": f"Cannot retry '{orig.get('status')}'."}
            retry = json.loads(json.dumps(orig))
            for k in ('id', 'status', 'progress', 'speed', 'error',
                       'start_time', 'end_time', 'added_time', 'connection_type',
                       'downloader_instance'):
                retry.pop(k, None)
            retry["force_redownload"] = True

        new_id = self.add_to_queue(retry)
        if not new_id:
            return {"success": False, "error": "Already in queue or downloading."}
        with self._lock:
            self.history = [i for i in self.history if i.get("id") != original_id]
            self._save_history()
        return {"success": True, "new_download_id": new_id}

    # ------------------------------------------------------------------
    # Open folder
    # ------------------------------------------------------------------
    def open_folder(self, did: str) -> Dict[str, Any]:
        with self._lock:
            item = next((i for i in self.history if i.get("id") == did), None)
            if not item:
                item = self.active.get(did)
            if not item:
                return {"success": False, "error": "Not found."}
            if item.get("status") != "completed":
                return {"success": False, "error": "Not completed."}
            fpath = item.get("output_path")

        if not fpath:
            return {"success": False, "error": "No path."}
        folder = os.path.dirname(os.path.abspath(fpath))
        if not os.path.isdir(folder):
            return {"success": False, "error": "Folder missing."}
        try:
            sys = platform.system()
            if sys == "Windows":
                os.startfile(folder)
            elif sys == "Darwin":
                subprocess.check_call(["open", folder])
            else:
                subprocess.check_call(["xdg-open", folder])
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Status update (thread-safe)
    # ------------------------------------------------------------------
    def _update_download_status(self, did: str, **kw):
        with self._lock:
            item = self.active.get(did)
            if not item:
                return
            for k, v in kw.items():
                if v is None:
                    continue
                if k == "progress":
                    v = max(0.0, min(100.0, v))
                if k == "speed":
                    v = max(0.0, v)
                if k == "error":
                    v = str(v)[:500]
                if k == "status" and v in ("completed", "failed", "cancelled"):
                    item.setdefault("end_time", _now())
                item[k] = v

    # ------------------------------------------------------------------
    # Process loop
    # ------------------------------------------------------------------
    def _process_loop(self):
        while self.running:
            did_work = False
            with self._lock:
                done = [d for d, i in self.active.items()
                        if i.get("status") in ("completed", "failed", "cancelled")]
                for d in done:
                    self._to_history(self.active.pop(d))
                    did_work = True

                while len(self.active) < self.max_concurrent and self.queue:
                    info = self.queue.pop(0)
                    if info["status"] == "cancelled":
                        info.setdefault("end_time", _now())
                        self._to_history(info)
                        did_work = True
                        continue
                    info["status"] = "starting"
                    info["start_time"] = _now()
                    info["downloader_instance"] = None
                    self.active[info["id"]] = info
                    t = threading.Thread(target=self._run_download, args=(info,), daemon=True)
                    t.start()
                    did_work = True

            if not did_work:
                time.sleep(0.5)

    # ------------------------------------------------------------------
    # Download execution
    # ------------------------------------------------------------------
    def _run_download(self, info: Dict[str, Any]):
        did = info["id"]
        from .chunk_downloader import ChunkDownloader

        dl: Optional[ChunkDownloader] = None
        success = False
        error = None

        try:
            dl = ChunkDownloader(
                url=info["url"], output_path=info["output_path"],
                num_connections=1, manager=self, download_id=did,
                api_key=info.get("api_key"), known_size=info.get("known_size"),
            )
            with self._lock:
                if did not in self.active or self.active[did]["status"] == "cancelled":
                    return
                self.active[did]["downloader_instance"] = dl

            self._update_download_status(did, status="downloading")
            success = dl.download()
            error = dl.error

            if success:
                self._save_metadata(info)
                self._save_preview(info)
            elif dl.is_cancelled:
                error = error or "Cancelled"
            else:
                error = error or "Failed"

        except Exception as e:
            error = f"Wrapper error: {e}"
            success = False
        finally:
            st = "completed" if success else ("cancelled" if (dl and dl.is_cancelled) else "failed")
            pct = 100.0 if success else (
                dl.downloaded / dl.total_size * 100 if dl and dl.total_size > 0 else 0)
            self._update_download_status(
                did, status=st, progress=min(100.0, pct),
                speed=0, error=error,
                connection_type=dl.connection_type if dl else "N/A")

    # ------------------------------------------------------------------
    # Metadata + Preview
    # ------------------------------------------------------------------
    def _save_metadata(self, info: Dict[str, Any]):
        out = info.get('output_path')
        if not out:
            return
        mi = info.get('civitai_model_info') or {}
        vi = info.get('civitai_version_info') or {}
        pf = info.get('civitai_primary_file') or {}
        base, _ = os.path.splitext(out)
        meta_path = base + METADATA_SUFFIX
        meta = {
            "ModelId": mi.get('id', vi.get('modelId')),
            "ModelName": mi.get('name', (vi.get('model') or {}).get('name')),
            "CreatorUsername": (mi.get('creator') or {}).get('username'),
            "ModelType": mi.get('type'),
            "Tags": mi.get('tags', []),
            "VersionId": vi.get('id'),
            "VersionName": vi.get('name'),
            "BaseModel": vi.get('baseModel'),
            "PrimaryFileName": pf.get('name'),
            "FileMetadata": {
                "fp": (pf.get('metadata') or {}).get('fp'),
                "size": (pf.get('metadata') or {}).get('size'),
                "format": (pf.get('metadata') or {}).get('format', 'Unknown'),
            },
            "Hashes": pf.get('hashes', {}),
            "TrainedWords": vi.get('trainedWords', []),
            "ImportedAt": _now(),
            "CivitaiUrl": f"https://civitai.com/models/{mi.get('id', '')}?modelVersionId={vi.get('id', '')}",
        }
        try:
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Civicomfy] Metadata save error: {e}")

    def _save_preview(self, info: Dict[str, Any]):
        out = info.get('output_path')
        thumb_url = info.get('thumbnail')
        if not out or not thumb_url:
            return
        thumb_type = info.get('thumbnail_type', 'image')
        base, _ = os.path.splitext(out)
        ext = ".mp4" if thumb_type == "video" else ".jpg"
        preview_path = base + PREVIEW_SUFFIX + ext
        resp = None
        try:
            import requests
            headers = {"User-Agent": "Civicomfy/4.0 (ComfyUI)"}
            if info.get('api_key'):
                headers["Authorization"] = f"Bearer {info['api_key']}"
            resp = requests.get(thumb_url, stream=True, headers=headers,
                                timeout=METADATA_DOWNLOAD_TIMEOUT, allow_redirects=True)
            resp.raise_for_status()
            ct = resp.headers.get('Content-Type', '').lower()
            if 'video' in ct and ext != '.mp4':
                preview_path = base + PREVIEW_SUFFIX + '.mp4'
            elif 'image' in ct and ext == '.mp4':
                preview_path = base + PREVIEW_SUFFIX + '.jpg'
            with open(preview_path, 'wb') as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
        except Exception as e:
            print(f"[Civicomfy] Preview save error: {e}")
        finally:
            if resp:
                try:
                    resp.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Shutdown: cancel all, delete partial files
    # ------------------------------------------------------------------
    def shutdown(self):
        print("[Civicomfy] Shutting down download manager...")
        self.running = False

        # Collect all active download instances
        downloaders = []
        partial_paths = []
        with self._lock:
            for did, info in self.active.items():
                dl = info.get("downloader_instance")
                if dl:
                    downloaders.append(dl)
                # Track output path for cleanup
                p = info.get("output_path")
                if p and info.get("status") not in ("completed",):
                    partial_paths.append(p)
            # Also track queued items
            for info in self.queue:
                p = info.get("output_path")
                if p:
                    partial_paths.append(p)

        # Cancel all active downloads
        for dl in downloaders:
            try:
                dl.cancel()
            except Exception:
                pass

        # Wait briefly for threads to finish
        time.sleep(1.0)

        # Delete any partial files left on disk
        for p in partial_paths:
            try:
                if os.path.exists(p):
                    os.remove(p)
                    print(f"[Civicomfy] Removed partial file on shutdown: {p}")
            except Exception as e:
                print(f"[Civicomfy] Could not remove partial file {p}: {e}")

        print("[Civicomfy] Download manager stopped.")
def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
# --- Global instance ---
manager = DownloadManager(max_concurrent=MAX_CONCURRENT_DOWNLOADS)
def _shutdown():
    if manager:
        manager.shutdown()
atexit.register(_shutdown)
