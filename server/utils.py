"""
Server utilities: request parsing, API key resolution, Civitai model fetching, EA detection.
ALL Civitai API calls are wrapped in asyncio.to_thread to avoid blocking the event loop.
"""
import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from aiohttp import web

from ..api.civitai import CivitaiAPI
from ..utils.helpers import parse_civitai_input, select_primary_file


async def get_request_json(request) -> Dict[str, Any]:
    try:
        return await request.json()
    except Exception as e:
        raise web.HTTPBadRequest(
            body=b'{"error":"Invalid JSON"}',
            content_type="application/json",
        )


def resolve_api_key(payload: Optional[Dict[str, Any]] = None) -> Optional[str]:
    if isinstance(payload, dict):
        k = (payload.get("api_key") or "").strip()
        if k:
            return k
    env = os.getenv("CIVITAI_API_KEY", "").strip()
    return env or None


def is_early_access(model_info: dict = None, version_info: dict = None) -> tuple:
    """
    EA detection. Returns (is_ea: bool, deadline: str or None).
    
    Only two reliable checks:
    1. availability field explicitly set to something other than "Public"
    2. earlyAccessEndsAt is set AND in the future
    """
    mi = model_info or {}
    vi = version_info or {}
    
    # Check 1: availability field on the VERSION (not model — model-level is irrelevant)
    avail = (vi.get("availability") or "").strip().lower()
    if avail and avail not in ("public", ""):
        deadline = vi.get("earlyAccessEndsAt") or vi.get("earlyAccessDeadline")
        return True, deadline
    
    # Check 2: explicit deadline in the future
    for field in ("earlyAccessEndsAt", "earlyAccessDeadline"):
        val = vi.get(field)
        if not val:
            continue
        try:
            dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            if dt > datetime.now(timezone.utc):
                return True, val
            # Deadline is in the past → EA period ended, model is public now
        except (ValueError, TypeError):
            pass
    
    return False, None


def _make_error(msg: str, details: str = "", status: int = 500) -> Dict[str, Any]:
    """Create a consistent error dict for JSON responses."""
    return {"error": msg, "details": details, "status_code": status}


def _is_api_error(result) -> bool:
    """Check if an API result is an error dict."""
    return isinstance(result, dict) and "error" in result


def _get_api_error_msg(result) -> str:
    """Extract human-readable error from API result."""
    if not isinstance(result, dict):
        return "Unknown error"
    err = result.get("error", "Unknown error")
    details = result.get("details", "")
    if isinstance(details, dict):
        details = details.get("message", "") or str(details)
    if details and str(details) != str(err):
        return f"{err}: {details}"
    return str(err)


async def fetch_model_and_version(api: CivitaiAPI, url_or_id: str,
                                   req_version_id=None) -> Dict[str, Any]:
    """
    Resolve model + version + primary file from Civitai.
    Returns dict with model_info, version_info, primary_file, target_model_id, target_version_id.
    On error returns dict with "error" key.
    ALL Civitai calls run in a thread to avoid blocking the event loop.
    """
    model_id, version_id = parse_civitai_input(str(url_or_id))

    # Parse version ID from request
    if req_version_id is not None:
        try:
            vid_int = int(req_version_id)
            if vid_int > 0:
                version_id = vid_int
        except (ValueError, TypeError):
            pass

    # --- Step 1: Ensure we have a model_id ---
    if not model_id and version_id:
        vi = await asyncio.to_thread(api.get_model_version_info, version_id)
        if not vi or _is_api_error(vi):
            return _make_error(f"Cannot fetch version {version_id}", _get_api_error_msg(vi) if vi else "No response from Civitai", 502)
        model_id = vi.get('modelId')
        if not model_id:
            return _make_error(f"Version {version_id} has no parent model ID", status=404)

    if not model_id:
        return _make_error("Cannot determine Model ID from input", status=400)

    # --- Step 2: Fetch model info ---
    mi = await asyncio.to_thread(api.get_model_info, model_id)
    if not mi or _is_api_error(mi):
        return _make_error(f"Cannot fetch model {model_id}", _get_api_error_msg(mi) if mi else "No response from Civitai", 502)

    # --- Step 3: Resolve version ---
    vi = None
    if version_id:
        vi = await asyncio.to_thread(api.get_model_version_info, version_id)
        if not vi or _is_api_error(vi):
            # Try fallback from model info
            for v in (mi.get("modelVersions") or []):
                if v.get("id") == version_id:
                    vi = v
                    break
            if not vi:
                return _make_error(f"Cannot fetch version {version_id}", _get_api_error_msg(vi) if isinstance(vi, dict) else "No response", 502)
    else:
        versions = mi.get("modelVersions") or []
        if not versions:
            return _make_error(f"Model {model_id} has no versions", status=404)
        default_v = next((v for v in versions if v.get('status') == 'Published'), versions[0])
        version_id = default_v.get('id')
        if not version_id:
            return _make_error("Latest version has no ID", status=404)
        vi = await asyncio.to_thread(api.get_model_version_info, version_id)
        if not vi or _is_api_error(vi):
            vi = default_v  # fallback to summary

    # --- Step 4: Find primary file ---
    files = vi.get("files") or []
    if not files and vi.get('downloadUrl'):
        files = [{
            "id": None, "name": vi.get('name', 'file'),
            "primary": True, "type": "Model",
            "sizeKB": vi.get('fileSizeKB'),
            "downloadUrl": vi['downloadUrl'],
            "hashes": {}, "metadata": {},
        }]
    if not files:
        return _make_error(f"Version {version_id} has no downloadable files", status=404)

    pf = select_primary_file(files)
    if not pf:
        return _make_error("No file with a valid download URL found", status=404)

    return {
        "model_info": mi,
        "version_info": vi,
        "primary_file": pf,
        "target_model_id": model_id,
        "target_version_id": version_id,
    }
