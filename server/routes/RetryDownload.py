"""Retry a failed/cancelled download."""
import asyncio
from aiohttp import web
import server as comfy_server
from ...downloader.manager import manager

ps = comfy_server.PromptServer.instance


@ps.routes.post("/civitai/retry")
async def route_retry(request):
    try:
        data = await request.json()
        did = data.get("download_id")
        if not did:
            return web.json_response({"error": "Missing download_id"}, status=400)
        result = await asyncio.to_thread(manager.retry_download, did)
        status = 200 if result.get("success") else 400
        return web.json_response(result, status=status)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
