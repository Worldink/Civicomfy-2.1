"""Search via Civitai Meilisearch. EA detection on results."""
import asyncio
import math
from aiohttp import web
import server as comfy_server
from ..utils import get_request_json, resolve_api_key
from ...api.civitai import CivitaiAPI
from ...config import CIVITAI_API_TYPE_MAP

ps = comfy_server.PromptServer.instance
_IMG_BASE = "https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7QA"


@ps.routes.post("/civitai/search")
async def route_search(request):
    try:
        data = await get_request_json(request)
        query = data.get("query", "").strip()
        type_keys = data.get("model_types", [])
        base_models = data.get("base_models", [])
        sort = data.get("sort", "Relevancy")
        limit = int(data.get("limit", 20))
        page = int(data.get("page", 1))
        nsfw = data.get("nsfw")

        if not query and not type_keys and not base_models:
            return web.json_response({
                "error": "Enter a query or filter.",
                "items": [], "metadata": {"totalItems": 0, "currentPage": page, "pageSize": limit, "totalPages": 0},
            }, status=400)

        api = CivitaiAPI(resolve_api_key(data))
        api_types = []
        if isinstance(type_keys, list) and type_keys and "any" not in type_keys:
            for k in type_keys:
                t = CIVITAI_API_TYPE_MAP.get(k.lower())
                if t and t not in api_types:
                    api_types.append(t)

        result = await asyncio.to_thread(
            api.search_models_meili,
            query=query or "", types=api_types or None,
            base_models=[b for b in (base_models or []) if isinstance(b, str) and b] or None,
            sort=sort, limit=limit, page=page, nsfw=nsfw,
        )

        if isinstance(result, dict) and "error" in result:
            return web.json_response(result, status=result.get("status_code") or 500)

        if not isinstance(result, dict) or "hits" not in result:
            return web.json_response({
                "items": [], "metadata": {"totalItems": 0, "currentPage": page, "pageSize": limit, "totalPages": 0},
            })

        items = []
        for hit in result.get("hits", []):
            if not isinstance(hit, dict):
                continue

            # Thumbnail
            thumb_url = None
            thumb_type = "image"
            thumb_nsfw = 0
            images = hit.get("images")
            if images and isinstance(images, list) and images:
                fi = images[0]
                if isinstance(fi, dict) and fi.get("url"):
                    iid = fi["url"]
                    thumb_type = fi.get("type", "image")
                    thumb_nsfw = fi.get("nsfwLevel", 0)
                    if thumb_type == "video":
                        thumb_url = f"{_IMG_BASE}/{iid}/transcode=true,width=450"
                    else:
                        thumb_url = f"{_IMG_BASE}/{iid}/width=256"

            hit["thumbnailUrl"] = thumb_url
            hit["thumbnailType"] = thumb_type
            hit["thumbnailNsfwLevel"] = thumb_nsfw

            # EA detection for search hits: check top-level availability field
            avail = (hit.get("availability") or "Public").strip().lower()
            hit["isEarlyAccess"] = avail not in ("public", "")

            items.append(hit)

        total = result.get("estimatedTotalHits", 0)
        return web.json_response({
            "items": items,
            "metadata": {
                "totalItems": total, "currentPage": page,
                "pageSize": limit, "totalPages": math.ceil(total / limit) if limit > 0 else 0,
            },
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return web.json_response({"error": str(e)}, status=500)
