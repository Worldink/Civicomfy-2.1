"""Save/load user settings to a persistent JSON file on disk."""
import json
import os
from aiohttp import web
import server as comfy_server
from ...config import PLUGIN_ROOT

ps = comfy_server.PromptServer.instance

_SETTINGS_FILE = os.path.join(PLUGIN_ROOT, "user_settings.json")


def _load():
    if not os.path.exists(_SETTINGS_FILE):
        return {}
    try:
        with open(_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(data: dict) -> bool:
    try:
        tmp = _SETTINGS_FILE + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, _SETTINGS_FILE)
        return True
    except Exception as e:
        print(f"[Civicomfy] Settings save error: {e}")
        return False


@ps.routes.get("/civitai/settings")
async def route_load_settings(request):
    return web.json_response(_load())


@ps.routes.post("/civitai/settings")
async def route_save_settings(request):
    try:
        data = await request.json()
        if not isinstance(data, dict):
            return web.json_response({"error": "Invalid data"}, status=400)
        if _save(data):
            return web.json_response({"success": True})
        return web.json_response({"error": "Failed to write settings file"}, status=500)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
