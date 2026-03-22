"""Return model types from ComfyUI's models/ directory."""
import os
from aiohttp import web
import server as comfy_server
import folder_paths

ps = comfy_server.PromptServer.instance


@ps.routes.get("/civitai/model_types")
async def route_types(request):
    try:
        models_dir = getattr(folder_paths, 'models_dir', None)
        if not models_dir:
            models_dir = os.path.join(getattr(folder_paths, 'base_path', os.getcwd()), 'models')
        if not os.path.isdir(models_dir):
            return web.json_response({})
        entries = {}
        for name in sorted(os.listdir(models_dir)):
            if os.path.isdir(os.path.join(models_dir, name)):
                entries[name] = name
        return web.json_response(entries)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
