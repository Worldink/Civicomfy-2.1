"""Delete a model file and its associated metadata/preview from disk.
Blocks deletion if the file is currently being downloaded."""
import os
import asyncio
from aiohttp import web
import server as comfy_server
import folder_paths
from ...config import METADATA_SUFFIX, PREVIEW_SUFFIX
from ...downloader.manager import manager as download_manager

ps = comfy_server.PromptServer.instance

_PREVIEW_EXTS = ['.jpg', '.jpeg', '.png', '.webp', '.mp4', '.gif']


def _delete_model_files(abs_path: str, models_dir: str, active_paths: set) -> dict:
    """Delete a model file and all associated sidecar files."""
    abs_path = os.path.abspath(abs_path)
    models_dir_abs = os.path.abspath(models_dir)

    # Security check
    if not abs_path.startswith(models_dir_abs):
        return {"success": False, "error": "Path outside models directory."}

    if not os.path.isfile(abs_path):
        return {"success": False, "error": "File not found."}

    # Block deletion if file is currently downloading
    if abs_path in active_paths:
        return {"success": False, "error": "Cannot delete — this file is currently downloading. Cancel the download first."}

    deleted = []
    errors = []

    base, _ = os.path.splitext(abs_path)

    # Files to delete: model + metadata + preview
    targets = [abs_path]

    # Metadata
    meta = base + METADATA_SUFFIX
    if os.path.exists(meta):
        targets.append(meta)

    # Preview (check all extensions)
    for ext in _PREVIEW_EXTS:
        preview = base + PREVIEW_SUFFIX + ext
        if os.path.exists(preview):
            targets.append(preview)
    # Legacy preview
    legacy = base + ".preview.jpeg"
    if os.path.exists(legacy):
        targets.append(legacy)

    for t in targets:
        try:
            os.remove(t)
            deleted.append(os.path.basename(t))
        except PermissionError:
            errors.append(f"{os.path.basename(t)}: file is in use (try closing any programs using it)")
        except Exception as e:
            errors.append(f"{os.path.basename(t)}: {e}")

    return {
        "success": len(errors) == 0,
        "deleted": deleted,
        "errors": errors,
        "message": f"Deleted {len(deleted)} file(s)." + (f" {len(errors)} error(s)." if errors else ""),
    }


@ps.routes.post("/civitai/delete_model")
async def route_delete_model(request):
    """Delete a model and its associated files from disk."""
    try:
        data = await request.json()
        abs_path = (data.get("abs_path") or "").strip()

        if not abs_path:
            return web.json_response({"error": "Missing abs_path"}, status=400)

        models_dir = getattr(folder_paths, 'models_dir', None)
        if not models_dir:
            models_dir = os.path.join(
                getattr(folder_paths, 'base_path', os.getcwd()), 'models')

        # Get active download paths for safety check
        active_paths = download_manager.get_active_paths()

        result = await asyncio.to_thread(_delete_model_files, abs_path, models_dir, active_paths)
        status = 200 if result["success"] else 400
        return web.json_response(result, status=status)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return web.json_response({"error": str(e)}, status=500)
