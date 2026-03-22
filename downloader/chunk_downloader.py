"""
Optimized file downloader with auto-resume on connection drops.
- Shared requests.Session (TCP+TLS reuse)
- Auto-retry with resume (Range headers) on mid-stream failures
- 4MB read chunks + 16MB write buffer
- Accept-Encoding: identity (no CDN gzip on binaries)
- Partial file kept between retries, deleted only on final failure
"""
import os
import time
import threading
from pathlib import Path
from typing import Optional, Dict, TYPE_CHECKING

import requests
if TYPE_CHECKING:
    from .manager import DownloadManager

from ..config import DEFAULT_CHUNK_SIZE, HEAD_REQUEST_TIMEOUT

_CONNECT_TIMEOUT = 30
_READ_TIMEOUT = 300
_WRITE_BUFFER = 16 * 1024 * 1024
_MAX_RETRIES = 5       # retry on mid-stream drops
_RETRY_DELAY = 3       # seconds between retries (grows: 3, 6, 9, 12, 15)

# Shared session
class ChunkDownloader:
    STATUS_INTERVAL = 0.5

    def __init__(self, url: str, output_path: str, num_connections: int = 1,
                 chunk_size: int = DEFAULT_CHUNK_SIZE,
                 manager: Optional['DownloadManager'] = None,
                 download_id: Optional[str] = None,
                 api_key: Optional[str] = None,
                 known_size: Optional[int] = None):
        self.output_path = Path(output_path)
        self.chunk_size = chunk_size
        self.manager = manager
        self.download_id = download_id
        self.api_key = api_key
        self.url = self._with_token(url, api_key)

        self.total_size = known_size if known_size and known_size > 0 else 0
        self.downloaded = 0
        self.connection_type = "Single"
        self.error: Optional[str] = None

        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._t0 = 0.0
        self._last_t = 0.0
        self._last_bytes = 0
        self._speed = 0.0

    @staticmethod
    def _with_token(url: str, api_key: Optional[str]) -> str:
        if not api_key or "civitai.com" not in url:
            return url
        if "token=" in url:
            return url
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}token={api_key}"

    def _headers(self, for_download: bool = False, resume_from: int = 0) -> Dict[str, str]:
        h: Dict[str, str] = {"User-Agent": "Civicomfy/4.0 (ComfyUI)"}
        if self.api_key and "token=" not in self.url:
            h["Authorization"] = f"Bearer {self.api_key}"
        if for_download:
            h["Accept-Encoding"] = "identity"
        if resume_from > 0:
            h["Range"] = f"bytes={resume_from}-"
        return h

    @property
    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self):
        if not self.is_cancelled:
            self._cancel.set()
            self.error = self.error or "Download cancelled"
            if self.manager and self.download_id:
                self.manager._update_download_status(
                    self.download_id, status="cancelled", error=self.error)

    def _progress(self, n: int):
        with self._lock:
            self.downloaded += n
            now = time.monotonic()
            dt = now - self._last_t
            if dt >= self.STATUS_INTERVAL or (self.total_size > 0 and self.downloaded >= self.total_size):
                pct = min(self.downloaded / self.total_size * 100, 100.0) if self.total_size > 0 else 0
                if dt > 0:
                    self._speed = (self.downloaded - self._last_bytes) / dt
                self._last_t = now
                self._last_bytes = self.downloaded
                if self.manager and self.download_id:
                    self.manager._update_download_status(
                        self.download_id, progress=pct, speed=self._speed, status="downloading")

    def _head_check(self):
        """Best-effort: get file size and resolve redirects."""
        try:
            r = requests.head(self.url, allow_redirects=True,
                              timeout=HEAD_REQUEST_TIMEOUT, headers=self._headers())
            r.raise_for_status()
            if r.url != self.url:
                self.url = self._with_token(r.url, self.api_key)
            if self.total_size <= 0:
                cl = int(r.headers.get('Content-Length', 0))
                if cl > 0:
                    self.total_size = cl
        except Exception:
            pass

    def _do_download_with_resume(self) -> bool:
        """Download with auto-resume on connection drops."""
        if self.manager and self.download_id:
            self.manager._update_download_status(
                self.download_id, connection_type="Single", status="downloading")

        self._t0 = time.monotonic()
        self._last_t = self._t0

        for attempt in range(_MAX_RETRIES + 1):
            if self.is_cancelled:
                return False

            # Check how much we already have on disk
            resume_from = 0
            if self.output_path.exists():
                resume_from = self.output_path.stat().st_size
                if self.total_size > 0 and resume_from >= self.total_size:
                    # File already complete
                    self.downloaded = resume_from
                    return True

            self.downloaded = resume_from
            self._last_bytes = resume_from
            resp = None

            try:
                hdrs = self._headers(for_download=True, resume_from=resume_from)
                resp = requests.get(
                    self.url, stream=True, allow_redirects=True,
                    timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT), headers=hdrs)

                # Handle resume response
                if resume_from > 0 and resp.status_code == 206:
                    # Server supports resume — append to existing file
                    print(f"[Civicomfy DL {self.download_id}] Resuming from {resume_from} bytes (attempt {attempt + 1})")
                elif resume_from > 0 and resp.status_code == 200:
                    # Server doesn't support resume — restart from scratch
                    print(f"[Civicomfy DL {self.download_id}] Server doesn't support resume, restarting")
                    resume_from = 0
                    self.downloaded = 0
                    self._last_bytes = 0
                elif resp.status_code == 416:
                    # Range not satisfiable — file might be complete
                    if self.total_size > 0 and resume_from >= self.total_size:
                        self.downloaded = resume_from
                        return True
                    # Otherwise restart
                    resume_from = 0
                    self.downloaded = 0
                    resp.close()
                    continue
                else:
                    resp.raise_for_status()

                # Update total size from Content-Range or Content-Length
                if self.total_size <= 0:
                    cr = resp.headers.get('Content-Range', '')
                    if '/' in cr:
                        try:
                            self.total_size = int(cr.split('/')[-1])
                        except (ValueError, IndexError):
                            pass
                    if self.total_size <= 0:
                        cl = int(resp.headers.get('Content-Length', 0))
                        if cl > 0:
                            self.total_size = cl + resume_from

                self.output_path.parent.mkdir(parents=True, exist_ok=True)
                mode = 'ab' if resume_from > 0 else 'wb'

                with open(self.output_path, mode, buffering=_WRITE_BUFFER) as f:
                    for chunk in resp.iter_content(self.chunk_size):
                        if self.is_cancelled:
                            return False
                        if chunk:
                            f.write(chunk)
                            self._progress(len(chunk))

                # Check if download is complete
                if self.total_size > 0 and self.downloaded >= self.total_size:
                    return True
                if self.total_size <= 0 and self.downloaded > 0:
                    return True  # Unknown size but got data

                # Got 0 new bytes this attempt
                if self.downloaded == resume_from:
                    if attempt < _MAX_RETRIES:
                        print(f"[Civicomfy DL {self.download_id}] No data received, retrying ({attempt + 1}/{_MAX_RETRIES})")
                        time.sleep(_RETRY_DELAY)
                        continue
                    self.error = "0 bytes received after all retries"
                    return False

                return True

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                    requests.exceptions.ChunkedEncodingError, ConnectionError) as e:
                # Recoverable errors — retry with resume
                if resp:
                    try:
                        resp.close()
                    except Exception:
                        pass

                if self.is_cancelled:
                    return False

                if attempt < _MAX_RETRIES:
                    wait = _RETRY_DELAY * (attempt + 1)
                    print(f"[Civicomfy DL {self.download_id}] Connection dropped at {self.downloaded} bytes: {type(e).__name__}. "
                          f"Retry {attempt + 1}/{_MAX_RETRIES} in {wait}s...")
                    if self.manager and self.download_id:
                        self.manager._update_download_status(
                            self.download_id, speed=0,
                            error=f"Reconnecting... (retry {attempt + 1}/{_MAX_RETRIES})")
                    time.sleep(wait)
                    continue
                else:
                    self.error = f"Connection lost after {_MAX_RETRIES} retries: {type(e).__name__}"
                    return False

            except requests.exceptions.HTTPError as e:
                code = e.response.status_code if e.response else None

                # Permanent errors — don't retry
                if code == 401:
                    self.error = "Unauthorized — API key may be needed"
                    return False
                if code == 403:
                    self.error = "Forbidden — check API key or access"
                    return False
                if code == 404:
                    self.error = "Not found — model may have been removed"
                    return False

                # Retryable: 5xx, 429, or no response at all
                if resp:
                    try:
                        resp.close()
                    except Exception:
                        pass

                if self.is_cancelled:
                    return False

                err_desc = f"HTTP {code}" if code else "No response"
                if attempt < _MAX_RETRIES:
                    wait = _RETRY_DELAY * (attempt + 1)
                    print(f"[Civicomfy DL {self.download_id}] Server error ({err_desc}) at {self.downloaded} bytes. "
                          f"Retry {attempt + 1}/{_MAX_RETRIES} in {wait}s...")
                    if self.manager and self.download_id:
                        self.manager._update_download_status(
                            self.download_id, speed=0,
                            error=f"Server error ({err_desc}), retrying... ({attempt + 1}/{_MAX_RETRIES})")
                    time.sleep(wait)
                    continue
                else:
                    self.error = f"Server error ({err_desc}) after {_MAX_RETRIES} retries"
                    return False

            except OSError as e:
                self.error = f"Disk error: {e}"
                return False

            except Exception as e:
                if not self.error:
                    self.error = f"Failed: {e}"
                return False

            finally:
                if resp:
                    try:
                        resp.close()
                    except Exception:
                        pass

        self.error = self.error or "Download failed after all retries"
        return False

    def _delete_partial(self):
        try:
            if self.output_path.exists():
                self.output_path.unlink()
        except Exception:
            pass

    def download(self) -> bool:
        self.error = None
        success = False
        self._head_check()

        try:
            success = self._do_download_with_resume()
        except KeyboardInterrupt:
            self.cancel()
        except Exception as e:
            if not self.error:
                self.error = f"Unexpected: {e}"

        # Only delete partial file on FINAL failure (not on cancel — user might retry)
        if not success and not self.is_cancelled:
            self._delete_partial()

        if self.manager and self.download_id:
            st = "completed" if success else ("cancelled" if self.is_cancelled else "failed")
            pct = 100.0 if success else (
                self.downloaded / self.total_size * 100 if self.total_size > 0 else 0)
            self.manager._update_download_status(
                self.download_id, status=st, progress=min(100.0, pct),
                speed=0, error=self.error, connection_type=self.connection_type)

        return success
