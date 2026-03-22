"""
Download route. Robust EA detection, version-installed check, token auth, all JSON responses.
"""
import asyncio
import os
import json
import re
import traceback
from aiohttp import web
import server as comfy_server
import folder_paths
from ..utils import get_request_json, resolve_api_key, fetch_model_and_version, is_early_access
from ...api.civitai import CivitaiAPI
from ...utils.helpers import get_model_dir, sanitize_filename, guess_precision
from ...downloader.manager import manager as download_manager
from ...config import METADATA_SUFFIX

ps = comfy_server.PromptServer.instance
_MODEL_EXTS = ('.safetensors', '.ckpt', '.pt', '.pth', '.bin', '.onnx', '.gguf')


def _is_version_installed(model_id, version_id):
    """True only if BOTH .cminfo.json AND model file exist."""
    if not model_id or not version_id:
        return False, None
    try:
        mid_int, vid_int = int(model_id), int(version_id)
    except (ValueError, TypeError):
        return False, None

    models_dir = getattr(folder_paths, 'models_dir', None)
    if not models_dir:
        models_dir = os.path.join(getattr(folder_paths, 'base_path', os.getcwd()), 'models')
    if not os.path.isdir(models_dir):
        return False, None

    for root, _, files in os.walk(models_dir):
        for f in files:
            if not f.endswith(METADATA_SUFFIX):
                continue
            fp = os.path.join(root, f)
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    meta = json.load(fh)
                if int(meta.get("ModelId", 0)) != mid_int or int(meta.get("VersionId", 0)) != vid_int:
                    continue
                base = fp[:-len(METADATA_SUFFIX)]
                for ext in _MODEL_EXTS:
                    mp = base + ext
                    if os.path.isfile(mp) and os.path.getsize(mp) > 0:
                        return True, mp
                # Orphaned metadata
                try:
                    os.remove(fp)
                except Exception:
                    pass
                return False, None
            except Exception:
                continue
    return False, None


@ps.routes.post("/civitai/download")
async def route_download(request):
    try:
        data = await get_request_json(request)
    except Exception:
        return web.json_response({"error": "Invalid request body"}, status=400)

    try:
        url_or_id = data.get("model_url_or_id")
        model_type = data.get("model_type", "checkpoint")
        req_vid = data.get("model_version_id")
        custom_fn = (data.get("custom_filename") or "").strip()
        req_file_id = data.get("file_id")
        subfolder = (data.get("subfolder") or "").strip()

        if not url_or_id:
            return web.json_response({"error": "Missing model URL or ID"}, status=400)

        api_key = resolve_api_key(data)
        api = CivitaiAPI(api_key)

        d = await fetch_model_and_version(api, url_or_id, req_vid)
        if "error" in d:
            return web.json_response({"error": d["error"], "details": d.get("details", "")},
                                      status=d.get("status_code", 500) or 500)

        mi, vi, pf = d["model_info"], d["version_info"], d["primary_file"]
        mid, vid = d["target_model_id"], d["target_version_id"]

        # EA check (robust — multiple fields)
        ea, ea_deadline = is_early_access(model_info=mi, version_info=vi)
        if ea:
            return web.json_response({
                "status": "blocked",
                "message": "This model version is Early Access and cannot be downloaded yet.",
                "is_early_access": True,
                "early_access_deadline": ea_deadline,
            }, status=403)

        # Installed check
        installed, installed_path = await asyncio.to_thread(_is_version_installed, mid, vid)
        if installed:
            return web.json_response({
                "status": "already_installed",
                "message": "This version is already installed.",
                "path": installed_path,
            })

        # File selection
        if req_file_id is not None:
            try:
                fid = int(str(req_file_id).strip())
                found = next((f for f in (vi.get("files") or [])
                              if isinstance(f, dict) and f.get("id") == fid and f.get("downloadUrl")), None)
                if found:
                    pf = found
            except (ValueError, TypeError):
                pass

        download_url = pf.get("downloadUrl")
        if not download_url:
            return web.json_response({"error": "No download URL"}, status=404)

        # Token auth for Civitai CDN
        if api_key and "civitai.com" in download_url:
            sep = "&" if "?" in download_url else "?"
            download_url = f"{download_url}{sep}token={api_key}"

        # Filename
        api_filename = pf.get("name", f"model_{mid}_v{vid}")
        final_fn = sanitize_filename(api_filename)
        if custom_fn:
            safe = sanitize_filename(custom_fn)
            base, ext = os.path.splitext(safe)
            if not ext:
                _, api_ext = os.path.splitext(api_filename)
                ext = api_ext or ".safetensors"
            final_fn = base + ext

        # Output directory
        try:
            output_dir = get_model_dir(model_type)
        except Exception as e:
            return web.json_response({"error": f"Cannot resolve directory: {e}"}, status=500)

        if subfolder:
            parts = [sanitize_filename(p) for p in subfolder.replace('\\', '/').split('/')
                     if p and p not in ('.', '..')]
            if parts:
                output_dir = os.path.join(output_dir, *parts)
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            return web.json_response({"error": f"Cannot create directory: {e}"}, status=500)

        output_path = os.path.join(output_dir, final_fn)

        # Thumbnail
        thumb_url = None
        thumb_type = "image"
        thumb_nsfw = None
        imgs = vi.get("images") or []
        if imgs and isinstance(imgs[0], dict) and imgs[0].get("url"):
            fi = imgs[0]
            thumb_url = fi["url"]
            thumb_type = fi.get("type", "image")
            thumb_nsfw = fi.get("nsfwLevel")
            if thumb_type != "video" and thumb_url and "/width=" in thumb_url:
                thumb_url = re.sub(r"/width=\d+", "/width=256", thumb_url)

        model_name = mi.get('name', 'Model')
        version_name = vi.get('name', 'Version')
        api_size_kb = pf.get("sizeKB")
        api_size = int(api_size_kb * 1024) if api_size_kb else None
        pm = pf.get('metadata') or {}

        info = {
            "url": download_url, "output_path": output_path,
            "num_connections": 1, "known_size": api_size,
            "api_key": api_key, "model_url_or_id": url_or_id,
            "model_version_id": req_vid, "force_redownload": True,
            "filename": final_fn, "model_name": model_name,
            "version_name": version_name, "thumbnail": thumb_url,
            "thumbnail_type": thumb_type, "thumbnail_nsfw_level": thumb_nsfw,
            "model_type": model_type,
            "file_precision": guess_precision(pf),
            "file_model_size": pm.get("size"), "file_format": pm.get("format"),
            "civitai_model_id": mid, "civitai_version_id": vid,
            "civitai_model_info": mi, "civitai_version_info": vi,
            "civitai_primary_file": pf,
        }

        did = download_manager.add_to_queue(info)

        return web.json_response({
            "status": "queued",
            "message": f"Download queued: '{final_fn}'",
            "download_id": did,
            "details": {
                "filename": final_fn, "model_name": model_name,
                "version_name": version_name, "thumbnail": thumb_url,
                "path": output_path, "size_kb": api_size_kb,
            },
        })

    except Exception as e:
        traceback.print_exc()
        return web.json_response({"error": f"Download failed: {str(e)}"}, status=500)
