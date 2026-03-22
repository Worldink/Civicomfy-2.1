"""Clear download history."""
import asyncio
from aiohttp import web
import server as comfy_server
from ...downloader.manager import manager

ps = comfy_server.PromptServer.instance


@ps.routes.post("/civitai/clear_history")
async def route_clear(request):
    try:
        result = await asyncio.to_thread(manager.clear_history)
        status = 200 if result.get("success") else 500
        return web.json_response(result, status=status)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
