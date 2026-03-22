"""Get download status."""
from aiohttp import web
import server as comfy_server
from ...downloader.manager import manager

ps = comfy_server.PromptServer.instance


@ps.routes.get("/civitai/status")
async def route_status(request):
    try:
        return web.json_response(manager.get_status())
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
