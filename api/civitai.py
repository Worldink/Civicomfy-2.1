"""
Civitai API v1 + Meilisearch wrapper.
Uses shared requests.Session for connection pooling.
"""
import requests
import json
from typing import List, Optional, Dict, Any, Union
from requests.adapters import HTTPAdapter

# Public Meilisearch bearer (same for all users)
_MEILI_BEARER = "8c46eb2508e21db1e9828a97968d91ab1ca1caa5f70a00e88a2ba1e286603b61"
_MEILI_URL = "https://search.civitai.com/multi-search"
_MEILI_INDEX = "models_v9"

# Shared session for all API calls (connection reuse = faster)
_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=4, pool_maxsize=4, max_retries=1)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


class CivitaiAPI:
    """Wrapper for Civitai REST API v1 and Meilisearch."""

    BASE_URL = "https://civitai.com/api/v1"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self._headers: Dict[str, str] = {}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------
    def _request(self, method: str, endpoint: str, *,
                 params: Optional[Dict] = None,
                 json_data: Optional[Dict] = None,
                 stream: bool = False,
                 timeout: int = 30) -> Union[Dict[str, Any], requests.Response, None]:
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        headers = dict(self._headers)
        if json_data is not None:
            headers["Content-Type"] = "application/json"

        try:
            resp = _session.request(
                method, url, headers=headers, params=params,
                json=json_data, stream=stream, allow_redirects=True, timeout=timeout,
            )
            resp.raise_for_status()
            if stream:
                return resp
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()

        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else None
            detail = None
            if e.response is not None:
                try:
                    detail = e.response.json()
                except Exception:
                    detail = (e.response.text or "")[:300]
            msg = f"HTTP {code}" if code else "Request failed (no response)"
            if code == 401:
                msg = "Unauthorized (401) — API key may be required"
            elif code == 403:
                msg = "Forbidden (403) — access denied"
            elif code == 404:
                msg = "Not found (404)"
            elif code == 503:
                msg = "Service unavailable (503) — Civitai may be in maintenance"
            return {"error": msg, "details": detail, "status_code": code}

        except requests.exceptions.ConnectionError:
            return {"error": "Cannot connect to Civitai — server may be offline", "details": "Check your connection or Civitai status.", "status_code": None}

        except requests.exceptions.Timeout:
            return {"error": "Request timed out — Civitai not responding", "details": "Try again later.", "status_code": None}

        except requests.exceptions.RequestException as e:
            return {"error": f"Network error: {str(e)[:100]}", "details": None, "status_code": None}

        except json.JSONDecodeError:
            return {"error": "Invalid JSON", "details": None, "status_code": None}

    # ------------------------------------------------------------------
    # REST endpoints
    # ------------------------------------------------------------------
    def get_model_info(self, model_id: int) -> Optional[Dict[str, Any]]:
        return self._request("GET", f"/models/{model_id}")

    def get_model_version_info(self, version_id: int) -> Optional[Dict[str, Any]]:
        return self._request("GET", f"/model-versions/{version_id}")

    # ------------------------------------------------------------------
    # Meilisearch
    # ------------------------------------------------------------------
    def search_models_meili(self, *, query: str = "",
                            types: Optional[List[str]] = None,
                            base_models: Optional[List[str]] = None,
                            sort: str = "Most Downloaded",
                            limit: int = 20, page: int = 1,
                            nsfw: Optional[bool] = None) -> Dict[str, Any]:
        offset = max(0, (page - 1) * limit)

        sort_map = {
            "Relevancy":       None,
            "Most Downloaded":  "metrics.downloadCount:desc",
            "Highest Rated":    "metrics.thumbsUpCount:desc",
            "Most Liked":       "metrics.favoriteCount:desc",
            "Most Discussed":   "metrics.commentCount:desc",
            "Most Collected":   "metrics.collectedCount:desc",
            "Most Buzz":        "metrics.tippedAmountCount:desc",
            "Newest":           "createdAt:desc",
        }

        # Build filters
        filters: list = []
        if types:
            filters.append([f'"type"="{t}"' for t in types])
        if base_models:
            filters.append([f'"version.baseModel"="{bm}"' for bm in base_models])
        if nsfw is None or nsfw is False:
            filters.append("nsfwLevel IN [1, 2, 4]")

        # NOTE: We intentionally do NOT filter "availability = Public" here
        # so EA models appear in results. The frontend marks them as EA
        # and blocks their download until released.

        q_obj: Dict[str, Any] = {
            "q": query or "",
            "indexUid": _MEILI_INDEX,
            "facets": [
                "type", "version.baseModel", "nsfwLevel",
                "category.name", "user.username",
            ],
            "attributesToHighlight": [],
            "limit": max(1, min(100, limit)),
            "offset": offset,
            "filter": filters,
        }
        meili_sort = sort_map.get(sort)
        if meili_sort:
            q_obj["sort"] = [meili_sort]

        payload = {"queries": [q_obj]}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_MEILI_BEARER}",
        }

        try:
            resp = _session.post(_MEILI_URL, headers=headers, json=payload, timeout=25)
            resp.raise_for_status()
            data = resp.json()
            results_list = data.get("results", [])
            if not results_list:
                return {"hits": [], "limit": limit, "offset": offset, "estimatedTotalHits": 0}
            first = results_list[0]
            if isinstance(first, dict) and "hits" in first:
                return first
            return {"hits": [], "limit": limit, "offset": offset, "estimatedTotalHits": 0}

        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else None
            detail = None
            if e.response is not None:
                try:
                    detail = e.response.json()
                except Exception:
                    detail = (e.response.text or "")[:300]
            return {"error": f"Search error{' (HTTP ' + str(code) + ')' if code else ''}", "details": detail, "status_code": code}

        except requests.exceptions.ConnectionError:
            return {"error": "Search unavailable — cannot reach Civitai", "details": "Check connection or Civitai status.", "status_code": None}

        except requests.exceptions.Timeout:
            return {"error": "Search timed out", "details": "Civitai search not responding.", "status_code": None}

        except requests.exceptions.RequestException as e:
            return {"error": f"Search error: {str(e)[:80]}", "details": None, "status_code": None}

        except json.JSONDecodeError:
            return {"error": "Invalid JSON from Meili", "details": None, "status_code": None}
