"""Model details: all versions, images, installed check, robust EA. All JSON responses."""
import asyncio
import os
import json
import traceback
from aiohttp import web
import server as comfy_server
import folder_paths
from ..utils import get_request_json, resolve_api_key, is_early_access
from ...api.civitai import CivitaiAPI
from ...utils.helpers import guess_precision, parse_civitai_input, select_primary_file
from ...config import METADATA_SUFFIX

ps = comfy_server.PromptServer.instance
_MODEL_EXTS = ('.safetensors', '.ckpt', '.pt', '.pth', '.bin', '.onnx', '.gguf')


def _scan_installed():
    """Set of (model_id, version_id) tuples. Only if model file exists."""
    installed = set()
    models_dir = getattr(folder_paths, 'models_dir', None)
    if not models_dir:
        models_dir = os.path.join(getattr(folder_paths, 'base_path', os.getcwd()), 'models')
    if not os.path.isdir(models_dir):
        return installed
    for root, _, files in os.walk(models_dir):
        for f in files:
            if not f.endswith(METADATA_SUFFIX):
                continue
            fp = os.path.join(root, f)
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    meta = json.load(fh)
                mid, vid = meta.get("ModelId"), meta.get("VersionId")
                if not mid or not vid:
                    continue
                base = fp[:-len(METADATA_SUFFIX)]
                if any(os.path.isfile(base + ext) for ext in _MODEL_EXTS):
                    installed.add((int(mid), int(vid)))
            except Exception:
                pass
    return installed


@ps.routes.post("/civitai/get_model_details")
async def route_get_model_details(request):
    try:
        data = await get_request_json(request)
    except Exception:
        return web.json_response({"success": False, "error": "Invalid request"}, status=400)

    try:
        url_or_id = data.get("model_url_or_id")
        req_vid = data.get("model_version_id")
        if not url_or_id:
            return web.json_response({"success": False, "error": "Missing model_url_or_id"}, status=400)

        api = CivitaiAPI(resolve_api_key(data))

        # Parse input
        model_id, version_id = parse_civitai_input(str(url_or_id))
        if req_vid is not None:
            try:
                v = int(req_vid)
                if v > 0:
                    version_id = v
            except (ValueError, TypeError):
                pass

        # Resolve model_id
        if not model_id and version_id:
            vi = await asyncio.to_thread(api.get_model_version_info, version_id)
            if vi and "error" not in vi:
                model_id = vi.get('modelId')
        if not model_id:
            return web.json_response({"success": False, "error": "Cannot determine Model ID"}, status=400)

        # Fetch full model info
        mi = await asyncio.to_thread(api.get_model_info, model_id)
        if not mi or "error" in mi:
            err = mi.get("error", "No response") if isinstance(mi, dict) else "No response from Civitai"
            return web.json_response({"success": False, "error": f"Cannot fetch model: {err}"}, status=502)

        all_versions_raw = mi.get("modelVersions") or []

        # Default to latest version
        if not version_id and all_versions_raw:
            default_v = next((v for v in all_versions_raw if v.get('status') == 'Published'), all_versions_raw[0])
            version_id = default_v.get('id')

        # Fetch selected version details
        vi = None
        if version_id:
            vi = await asyncio.to_thread(api.get_model_version_info, version_id)
            if not vi or "error" in vi:
                vi = next((v for v in all_versions_raw if v.get('id') == version_id), None)
        if not vi and all_versions_raw:
            vi = all_versions_raw[0]
            version_id = vi.get('id')
        if not vi:
            return web.json_response({"success": False, "error": "No version data"}, status=404)

        # All versions list with EA check per version
        all_versions = []
        for v in all_versions_raw:
            v_ea, v_deadline = is_early_access(model_info=mi, version_info=v)
            all_versions.append({
                "id": v.get("id"),
                "name": v.get("name", "Unknown"),
                "baseModel": v.get("baseModel"),
                "publishedAt": v.get("publishedAt"),
                "is_early_access": v_ea,
                "early_access_deadline": v_deadline,
            })

        # Files for selected version
        pf = select_primary_file(vi.get("files") or []) or {}
        pm = pf.get('metadata') or {}
        files_list = []
        for f in (vi.get("files") or []):
            if not isinstance(f, dict):
                continue
            fm = f.get("metadata") or {}
            files_list.append({
                "id": f.get("id"), "name": f.get("name"),
                "size_kb": f.get("sizeKB"), "format": fm.get("format"),
                "model_size": fm.get("size"), "precision": guess_precision(f),
                "downloadable": bool(f.get("downloadUrl")),
            })

        # Images
        images = []
        for img in (vi.get("images") or []):
            if isinstance(img, dict) and img.get("url"):
                images.append({
                    "url": img["url"], "type": img.get("type", "image"),
                    "nsfwLevel": img.get("nsfwLevel", 0),
                })

        stats = mi.get('stats') or vi.get('stats') or {}

        # EA for selected version
        sel_ea, sel_deadline = is_early_access(model_info=mi, version_info=vi)

        # Installed check
        installed_set = await asyncio.to_thread(_scan_installed)
        already_dl = (int(model_id), int(version_id)) in installed_set if model_id and version_id else False

        return web.json_response({
            "success": True,
            "model_id": model_id,
            "version_id": version_id,
            "model_name": mi.get('name', 'Unknown'),
            "version_name": vi.get('name', 'Unknown'),
            "creator_username": (mi.get('creator') or {}).get('username', 'Unknown'),
            "model_type": mi.get('type', 'Unknown'),
            "description_html": mi.get('description') or "",
            "version_description_html": vi.get('description') or "",
            "stats": {
                "downloads": stats.get('downloadCount', 0),
                "likes": stats.get('thumbsUpCount', 0),
                "dislikes": stats.get('thumbsDownCount', 0),
                "buzz": stats.get('tippedAmountCount', 0),
            },
            "file_info": {
                "name": pf.get('name', 'N/A'), "size_kb": pf.get('sizeKB', 0),
                "format": pm.get('format', 'N/A'), "model_size": pm.get('size', 'N/A'),
                "precision": guess_precision(pf),
            },
            "files": files_list,
            "all_versions": all_versions,
            "images": images,
            "base_model": vi.get("baseModel", "N/A"),
            "trained_words": vi.get("trainedWords", []),
            "is_early_access": sel_ea,
            "early_access_deadline": sel_deadline,
            "already_downloaded": already_dl,
        })

    except Exception as e:
        traceback.print_exc()
        return web.json_response({"success": False, "error": f"Internal error: {str(e)}"}, status=500)
