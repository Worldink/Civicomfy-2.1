"""Model directory listing and management."""
import os
import json
from aiohttp import web
import server as comfy_server
import folder_paths
from ...utils.helpers import get_model_dir, get_model_folder_paths, get_model_type_folder_name, sanitize_filename
from ...config import PLUGIN_ROOT

ps = comfy_server.PromptServer.instance

_ROOT_SETTINGS = os.path.join(PLUGIN_ROOT, "root_settings.json")


def _load_settings():
    try:
        if os.path.exists(_ROOT_SETTINGS):
            with open(_ROOT_SETTINGS, 'r', encoding='utf-8') as f:
                d = json.load(f)
                return d if isinstance(d, dict) else {}
    except Exception:
        pass
    return {}


def _save_settings(d):
    try:
        with open(_ROOT_SETTINGS, 'w', encoding='utf-8') as f:
            json.dump(d, f, indent=2)
        return True
    except Exception:
        return False


def get_global_root():
    r = _load_settings().get("global_default_root")
    return os.path.abspath(r.strip()) if isinstance(r, str) and r.strip() else None


def get_effective_dir(model_type: str) -> str:
    gr = get_global_root()
    if gr:
        folder = get_model_type_folder_name(model_type)
        return os.path.abspath(os.path.join(gr, folder))
    return get_model_dir(model_type)


@ps.routes.get("/civitai/model_dirs")
async def route_dirs(request):
    mt = request.query.get("type", "checkpoints").lower().strip()
    try:
        base = get_effective_dir(mt)
        os.makedirs(base, exist_ok=True)
        gr = get_global_root()
        return web.json_response({
            "model_type": mt, "base_dir": base,
            "global_root": gr or "",
            "using_global_root": bool(gr),
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@ps.routes.post("/civitai/create_model_type")
async def route_create_type(request):
    try:
        data = await request.json()
        name = (data.get("name") or "").strip()
        if not name:
            return web.json_response({"error": "Missing name"}, status=400)
        safe = sanitize_filename(name)
        if not safe:
            return web.json_response({"error": "Invalid name"}, status=400)
        models_dir = getattr(folder_paths, 'models_dir', None)
        if not models_dir:
            models_dir = os.path.join(getattr(folder_paths, 'base_path', os.getcwd()), 'models')
        p = os.path.abspath(os.path.join(models_dir, safe))
        if os.path.commonpath([p, os.path.abspath(models_dir)]) != os.path.abspath(models_dir):
            return web.json_response({"error": "Invalid path"}, status=400)
        os.makedirs(p, exist_ok=True)
        return web.json_response({"success": True, "name": safe, "path": p})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@ps.routes.get("/civitai/global_root")
async def route_get_global(request):
    gr = get_global_root()
    return web.json_response({"global_root": gr or "", "enabled": bool(gr)})


@ps.routes.post("/civitai/global_root")
async def route_set_global(request):
    try:
        data = await request.json()
        p = os.path.expanduser((data.get("path") or "").strip())
        if not p or not os.path.isabs(p):
            return web.json_response({"error": "Absolute path required"}, status=400)
        ap = os.path.abspath(p)
        os.makedirs(ap, exist_ok=True)
        s = _load_settings()
        s["global_default_root"] = ap
        if not _save_settings(s):
            return web.json_response({"error": "Failed to save"}, status=500)
        return web.json_response({"success": True, "global_root": ap})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@ps.routes.post("/civitai/global_root/clear")
async def route_clear_global(request):
    try:
        s = _load_settings()
        s.pop("global_default_root", None)
        _save_settings(s)
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
