"""Base models list fetched dynamically from Civitai Meilisearch facets."""
import time
import asyncio
import requests
from aiohttp import web
import server as comfy_server

ps = comfy_server.PromptServer.instance

_MEILI_URL = "https://search.civitai.com/multi-search"
_MEILI_BEARER = "8c46eb2508e21db1e9828a97968d91ab1ca1caa5f70a00e88a2ba1e286603b61"
_cache = {"models": [], "ts": 0}
_TTL = 3600

_FALLBACK = [
    "AuraFlow","CogVideoX","Flux.1 D","Flux.1 S","Hunyuan 1","Hunyuan Video",
    "Illustrious","Kolors","LTXV","Lumina","Mochi","NoobAI","Other","Pony",
    "SD 1.5","SD 2.1","SD 3.5","SD 3.5 Large","SD 3.5 Medium",
    "SDXL 0.9","SDXL 1.0","SDXL Hyper","SDXL Lightning","SDXL Turbo",
    "SVD","Stable Cascade","Wan Video",
]


def _fetch():
    now = time.time()
    if _cache["models"] and (now - _cache["ts"]) < _TTL:
        return _cache["models"]
    try:
        resp = requests.post(_MEILI_URL, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_MEILI_BEARER}",
        }, json={"queries": [{"q": "", "indexUid": "models_v9",
                              "facets": ["version.baseModel"], "limit": 0}]}, timeout=15)
        resp.raise_for_status()
        dist = resp.json().get("results", [{}])[0].get("facetDistribution", {})
        bm = dist.get("version.baseModel", {})
        result = sorted(bm.keys(), key=lambda k: bm[k], reverse=True)
        if result:
            _cache["models"] = result
            _cache["ts"] = now
            return result
    except Exception as e:
        print(f"[Civicomfy] Base models fetch failed: {e}")
    return _cache["models"] or _FALLBACK


@ps.routes.get("/civitai/base_models")
async def route_base_models(request):
    models = await asyncio.to_thread(_fetch)
    return web.json_response({"base_models": models})
