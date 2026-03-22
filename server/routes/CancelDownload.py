"""Cancel a download."""
from aiohttp import web
import server as comfy_server
from ..utils import get_request_json
from ...downloader.manager import manager

ps = comfy_server.PromptServer.instance


@ps.routes.post("/civitai/cancel")
async def route_cancel(request):
    try:
        data = await get_request_json(request)
        did = data.get("download_id")
        if not did:
            return web.json_response({"error": "Missing download_id"}, status=400)
        ok = manager.cancel_download(did)
        if ok:
            return web.json_response({"status": "cancelled", "download_id": did})
        return web.json_response({"error": f"Download {did} not found or already finished"}, status=404)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
