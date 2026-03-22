"""
Download Manager: queue, execute, track downloads.
Saves max 3 files per model: model + preview (first image only) + metadata JSON.
All files go to the model type root folder (flat, no subfolders by default).
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

import requests

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
    # Queue
    # ------------------------------------------------------------------
    def add_to_queue(self, info: Dict[str, Any]) -> str:
        with self._lock:
            ts = int(time.time() * 1000)
            hint = os.path.basename(info.get('output_path', ''))[:10]
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
            # Check queue
            for i, item in enumerate(self.queue):
                if item["id"] == did:
                    item["status"] = "cancelled"
                    item["end_time"] = _now()
                    item["error"] = "Cancelled from queue"
                    self._to_history(self.queue.pop(i))
                    return True
            # Check active
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
    # Status (for frontend)
    # ------------------------------------------------------------------
    _STRIP = frozenset([
        'downloader_instance', 'civitai_model_info', 'civitai_version_info',
        'civitai_primary_file', 'api_key', 'url', 'output_path',
    ])

    def get_status(self) -> Dict[str, List[Dict]]:
        with self._lock:
            def _clean(d):
                return {k: v for k, v in d.items() if k not in self._STRIP}
            return {
                "queue": [_clean(i) for i in self.queue],
                "active": [_clean(i) for i in self.active.values()],
                "history": [_clean(i) for i in self.history[:DOWNLOAD_HISTORY_LIMIT]],
            }

    # ------------------------------------------------------------------
    # History persistence
    # ------------------------------------------------------------------
    def _load_history(self):
        if not os.path.exists(HISTORY_FILE):
            self.history = []
            return
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.history = [i for i in data if isinstance(i, dict) and 'id' in i
                            ][:DOWNLOAD_HISTORY_LIMIT]
        except Exception:
            self.history = []

    def _save_history(self):
        try:
            tmp = HISTORY_FILE + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.history[:DOWNLOAD_HISTORY_LIMIT], f, indent=2, ensure_ascii=False)
            os.replace(tmp, HISTORY_FILE)
        except Exception as e:
            print(f"[Civicomfy] Error saving history: {e}")

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
                return {"success": False, "error": f"Cannot retry status '{orig.get('status')}'."}
            retry = json.loads(json.dumps(orig))
            for k in ('id', 'status', 'progress', 'speed', 'error',
                       'start_time', 'end_time', 'added_time', 'connection_type',
                       'downloader_instance'):
                retry.pop(k, None)
            retry["force_redownload"] = True

        new_id = self.add_to_queue(retry)
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
                # Move finished to history
                done = [d for d, i in self.active.items()
                        if i.get("status") in ("completed", "failed", "cancelled")]
                for d in done:
                    self._to_history(self.active.pop(d))
                    did_work = True

                # Start new downloads
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
                num_connections=info.get("num_connections", 1),
                manager=self, download_id=did,
                api_key=info.get("api_key"),
                known_size=info.get("known_size"),
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
    # Save metadata JSON (1 of 3 files)
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
            "EarlyAccessDeadline": vi.get('earlyAccessDeadline'),
            "VersionPublishedAt": vi.get('publishedAt'),
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
            print(f"[Civicomfy] Error saving metadata: {e}")

    # ------------------------------------------------------------------
    # Save preview - ONLY FIRST IMAGE (2 of 3 files)
    # ------------------------------------------------------------------
    def _save_preview(self, info: Dict[str, Any]):
        out = info.get('output_path')
        if not out:
            return

        # Find thumbnail URL - prefer the one already resolved, else dig into version info
        thumb_url = info.get('thumbnail')
        thumb_type = info.get('thumbnail_type', 'image')  # 'image' or 'video'

        if not thumb_url:
            vi = info.get('civitai_version_info') or {}
            imgs = vi.get('images') or []
            if imgs and isinstance(imgs[0], dict) and imgs[0].get('url'):
                thumb_url = imgs[0]['url']
                thumb_type = imgs[0].get('type', 'image')

        if not thumb_url:
            return

        # Determine extension based on content type
        base, _ = os.path.splitext(out)
        ext = ".mp4" if thumb_type == "video" else ".jpg"
        preview_path = base + PREVIEW_SUFFIX + ext

        resp = None
        try:
            headers = {}
            if info.get('api_key'):
                headers["Authorization"] = f"Bearer {info['api_key']}"
            resp = requests.get(thumb_url, stream=True, headers=headers,
                                timeout=METADATA_DOWNLOAD_TIMEOUT, allow_redirects=True)
            resp.raise_for_status()
            ct = resp.headers.get('Content-Type', '').lower()
            # Adjust extension based on actual content type
            if 'video' in ct and ext != '.mp4':
                ext = '.mp4'
                preview_path = base + PREVIEW_SUFFIX + ext
            elif 'image' in ct and ext == '.mp4':
                ext = '.jpg'
                preview_path = base + PREVIEW_SUFFIX + ext
            with open(preview_path, 'wb') as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
        except Exception as e:
            print(f"[Civicomfy] Error saving preview: {e}")
        finally:
            if resp:
                resp.close()


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# --- Global instance ---
manager = DownloadManager(max_concurrent=MAX_CONCURRENT_DOWNLOADS)


def _shutdown():
    if manager:
        manager.running = False
        time.sleep(0.3)


atexit.register(_shutdown)
