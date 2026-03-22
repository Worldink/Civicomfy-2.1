"""Check Civitai service status via direct pings + status page."""
import asyncio
import time
import requests
from aiohttp import web
import server as comfy_server

ps = comfy_server.PromptServer.instance

_STATUS_URL = "https://status.civitai.com/status/public"
_API_CHECK_URL = "https://civitai.com/api/v1/models?limit=1"
_MEILI_CHECK_URL = "https://search.civitai.com/health"

_cache = {"data": None, "ts": 0}
_CACHE_TTL = 30

_OK_WORDS = frozenset(["up", "operational", "ok", "healthy", "active", "running"])
_DEGRADED_WORDS = frozenset(["degraded", "degraded_performance", "partial", "partial_outage", "slow"])
_DOWN_WORDS = frozenset(["down", "major_outage", "outage", "offline", "unavailable"])


def _classify(status_str: str) -> str:
    """Classify a status string into ok/degraded/offline."""
    s = (status_str or "").strip().lower().replace(" ", "_")
    if s in _OK_WORDS:
        return "ok"
    if s in _DEGRADED_WORDS:
        return "degraded"
    if s in _DOWN_WORDS:
        return "offline"
    # Heuristic fallbacks
    if "up" in s or "ok" in s or "operational" in s:
        return "ok"
    if "degrad" in s or "partial" in s or "slow" in s:
        return "degraded"
    if "down" in s or "outage" in s or "off" in s:
        return "offline"
    return "unknown"


def _parse_status_page(data) -> dict:
    """Parse status page response - handles multiple common formats."""
    services = []

    if not isinstance(data, dict):
        return {"status": "ok", "message": "Status page reachable", "services": []}

    # Try common structures
    items = None

    # Format 1: { "result": { "status": [...] } }
    res = data.get("result", {})
    if isinstance(res, dict):
        items = res.get("status") or res.get("components") or res.get("monitors")

    # Format 2: { "components": [...] }
    if not items:
        items = data.get("components") or data.get("status") or data.get("monitors") or data.get("services")

    # Format 3: { "data": { "components": [...] } }
    if not items and isinstance(data.get("data"), dict):
        items = data["data"].get("components") or data["data"].get("status")

    if not isinstance(items, list) or not items:
        return {"status": "ok", "message": "Status page reachable", "services": []}

    ok_count = 0
    degraded_count = 0
    down_count = 0
    problems = []

    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("monitor") or item.get("title") or "Service"
        raw_status = item.get("status") or item.get("state") or item.get("currentStatus") or ""
        # Some APIs use numeric status (1=up, 2=degraded, 3=down)
        if isinstance(raw_status, (int, float)):
            raw_status = {0: "unknown", 1: "up", 2: "degraded", 3: "down", 4: "down"}.get(int(raw_status), "unknown")
        classified = _classify(str(raw_status))
        services.append({"name": name, "status": classified})

        if classified == "ok":
            ok_count += 1
        elif classified == "degraded":
            degraded_count += 1
            problems.append(f"{name}: degraded")
        elif classified == "offline":
            down_count += 1
            problems.append(f"{name}: down")

    total = ok_count + degraded_count + down_count
    if total == 0:
        return {"status": "ok", "message": "Status page reachable", "services": services}

    # Overall status logic
    if down_count == total:
        overall = "offline"
        msg = "All services down"
    elif down_count > 0:
        overall = "degraded"
        msg = f"{ok_count}/{total} operational — {'; '.join(problems[:3])}"
    elif degraded_count > 0:
        overall = "degraded"
        msg = f"{ok_count}/{total} fully operational — {'; '.join(problems[:3])}"
    else:
        overall = "ok"
        msg = f"All {total} services operational"

    return {"status": overall, "message": msg, "services": services}


def _check_services():
    now = time.time()
    if _cache["data"] and (now - _cache["ts"]) < _CACHE_TTL:
        return _cache["data"]

    result = {
        "status_page": {"status": "unknown", "message": "Checking..."},
        "api": {"status": "unknown", "message": "Checking..."},
        "search": {"status": "unknown", "message": "Checking..."},
    }

    # 1. Official status page
    try:
        resp = requests.get(_STATUS_URL, timeout=10)
        resp.raise_for_status()
        result["status_page"] = _parse_status_page(resp.json())
    except requests.exceptions.Timeout:
        result["status_page"] = {"status": "timeout", "message": "Status page timed out"}
    except requests.exceptions.ConnectionError:
        result["status_page"] = {"status": "offline", "message": "Cannot reach status.civitai.com"}
    except Exception as e:
        # If we can reach the page but can't parse it, it's probably fine
        result["status_page"] = {"status": "ok", "message": "Status page reachable (parse error)"}

    # 2. Direct API ping
    try:
        resp = requests.get(_API_CHECK_URL, timeout=10)
        if resp.status_code == 200:
            result["api"] = {"status": "ok", "message": "API responding normally"}
        elif resp.status_code == 503:
            result["api"] = {"status": "maintenance", "message": "API in maintenance mode"}
        elif resp.status_code == 429:
            result["api"] = {"status": "ok", "message": "API online (rate limited)"}
        else:
            result["api"] = {"status": "degraded", "message": f"API returned HTTP {resp.status_code}"}
    except requests.exceptions.Timeout:
        result["api"] = {"status": "timeout", "message": "API not responding"}
    except requests.exceptions.ConnectionError:
        result["api"] = {"status": "offline", "message": "Cannot reach Civitai API"}
    except Exception as e:
        result["api"] = {"status": "error", "message": str(e)[:80]}

    # 3. Search engine health
    try:
        resp = requests.get(_MEILI_CHECK_URL, timeout=10)
        if resp.status_code == 200:
            result["search"] = {"status": "ok", "message": "Search engine healthy"}
        else:
            result["search"] = {"status": "degraded", "message": f"HTTP {resp.status_code}"}
    except requests.exceptions.Timeout:
        result["search"] = {"status": "timeout", "message": "Search not responding"}
    except requests.exceptions.ConnectionError:
        result["search"] = {"status": "offline", "message": "Cannot reach search engine"}
    except Exception as e:
        result["search"] = {"status": "error", "message": str(e)[:80]}

    _cache["data"] = result
    _cache["ts"] = now
    return result


@ps.routes.get("/civitai/check_status")
async def route_check_status(request):
    try:
        result = await asyncio.to_thread(_check_services)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({
            "status_page": {"status": "error", "message": str(e)[:80]},
            "api": {"status": "error", "message": str(e)[:80]},
            "search": {"status": "error", "message": str(e)[:80]},
        })

