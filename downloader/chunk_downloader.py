"""
Single-connection file downloader with progress reporting.
Handles Civitai CDN auth via query param (headers stripped on redirect).
"""
import os
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Tuple, TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .manager import DownloadManager

from ..config import DEFAULT_CHUNK_SIZE, DOWNLOAD_TIMEOUT, HEAD_REQUEST_TIMEOUT


class ChunkDownloader:
    STATUS_INTERVAL = 0.5

    def __init__(self, url: str, output_path: str, num_connections: int = 1,
                 chunk_size: int = DEFAULT_CHUNK_SIZE,
                 manager: Optional['DownloadManager'] = None,
                 download_id: Optional[str] = None,
                 api_key: Optional[str] = None,
                 known_size: Optional[int] = None):
        self.initial_url = url
        self.url = self._apply_token(url, api_key)
        self.output_path = Path(output_path)
        self.chunk_size = chunk_size
        self.manager = manager
        self.download_id = download_id
        self.api_key = api_key

        self.total_size = known_size if known_size and known_size > 0 else 0
        self.downloaded = 0
        self.connection_type = "N/A"
        self.error: Optional[str] = None

        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._t0 = 0.0
        self._last_t = 0.0
        self._last_bytes = 0
        self._speed = 0.0

    @staticmethod
    def _apply_token(url: str, api_key: Optional[str]) -> str:
        """Append token as query param for Civitai downloads (CDN strips auth headers)."""
        if not api_key:
            return url
        if "civitai.com" in url:
            sep = "&" if "?" in url else "?"
            return f"{url}{sep}token={api_key}"
        return url

    def _headers(self, range_hdr: Optional[str] = None) -> Dict[str, str]:
        h: Dict[str, str] = {}
        # Only add Bearer header if token is NOT already in the URL as query param
        # (Civitai CDN can reject requests with both)
        if self.api_key and "token=" not in self.url:
            h["Authorization"] = f"Bearer {self.api_key}"
        if range_hdr:
            h["Range"] = range_hdr
        return h

    @property
    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self):
        if not self.is_cancelled:
            self._cancel.set()
            self.error = "Download cancelled by user"
            if self.manager and self.download_id:
                self.manager._update_download_status(
                    self.download_id, status="cancelled", error=self.error)

    def _update_progress(self, n: int):
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

    def _head_check(self) -> Tuple[str, bool]:
        """HEAD check for redirect resolution and range support."""
        try:
            resp = requests.head(
                self.url, allow_redirects=True,
                timeout=HEAD_REQUEST_TIMEOUT, headers=self._headers())
            resp.raise_for_status()
            final_url = self._apply_token(resp.url, self.api_key) if "civitai.com" not in resp.url else resp.url
            self.url = final_url
            supports_range = resp.headers.get('accept-ranges', 'none').lower() == 'bytes'
            if self.total_size <= 0:
                cl = int(resp.headers.get('Content-Length', 0))
                if cl > 0:
                    self.total_size = cl
            return self.url, supports_range
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response else None
            print(f"[Civicomfy DL {self.download_id}] HEAD failed: {f'HTTP {code}' if code else 'no response'}")
            if code in (401, 403):
                self.error = f"Access denied (HTTP {code}) — check your API key"
            # Continue anyway, GET might work
            return self.url, False
        except Exception as e:
            print(f"[Civicomfy DL {self.download_id}] HEAD failed: {e}")
            return self.url, False

    def _single_download(self) -> bool:
        self.connection_type = "Single"
        if self.manager and self.download_id:
            self.manager._update_download_status(
                self.download_id, connection_type="Single", status="downloading")

        self._t0 = self._t0 or time.monotonic()
        self._last_t = self._t0
        self._last_bytes = 0
        self.downloaded = 0
        resp = None
        try:
            resp = requests.get(self.url, stream=True, timeout=DOWNLOAD_TIMEOUT,
                                allow_redirects=True, headers=self._headers())
            resp.raise_for_status()

            if resp.url != self.url:
                self.url = resp.url
            if self.total_size <= 0:
                cl = int(resp.headers.get('Content-Length', 0))
                if cl > 0:
                    self.total_size = cl

            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.output_path, 'wb') as f:
                for chunk in resp.iter_content(self.chunk_size):
                    if self.is_cancelled:
                        return False
                    if chunk:
                        f.write(chunk)
                        self._update_progress(len(chunk))

            # Verify we got data
            if self.downloaded == 0:
                self.error = "Download completed but 0 bytes received"
                return False

            return not self.error

        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response else None
            if code == 401:
                self.error = "Unauthorized (401) — API key required or invalid"
            elif code == 403:
                self.error = "Forbidden (403) — access denied, check API key"
            elif code == 404:
                self.error = "File not found (404) — model may have been removed"
            elif code == 503:
                self.error = "Civitai is in maintenance (503) — try later"
            else:
                self.error = f"Download failed (HTTP {code})" if code else "Download failed — no response from server"
            return False
        except requests.exceptions.ConnectionError:
            self.error = "Connection failed — Civitai may be offline"
            return False
        except requests.exceptions.Timeout:
            self.error = "Download timed out — try again later"
            return False
        except Exception as e:
            if not self.error:
                self.error = f"Download failed: {e}"
            return False
        finally:
            if resp:
                resp.close()

    def _cleanup(self, success: bool):
        if not success and self.output_path.exists():
            try:
                self.output_path.unlink()
            except Exception:
                pass

    def download(self) -> bool:
        self._t0 = time.monotonic()
        self.downloaded = 0
        self.error = None
        success = False

        self._head_check()

        # If HEAD already set an error (e.g. 401/403), abort early
        if self.error:
            return False

        try:
            success = self._single_download()
        except KeyboardInterrupt:
            self.cancel()
            success = False
        except Exception as e:
            if not self.error:
                self.error = f"Unexpected: {e}"
            success = False
        finally:
            self._cleanup(success and not self.is_cancelled and not self.error)
            if self.manager and self.download_id:
                st = "completed" if success else ("cancelled" if self.is_cancelled else "failed")
                pct = 100.0 if success else (
                    self.downloaded / self.total_size * 100 if self.total_size > 0 else 0)
                self.manager._update_download_status(
                    self.download_id, status=st, progress=min(100.0, pct),
                    speed=0, error=self.error, connection_type=self.connection_type)
        return success and not self.error and not self.is_cancelled
