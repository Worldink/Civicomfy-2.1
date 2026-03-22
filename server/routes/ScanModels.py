"""Scan models folder to build a library view of downloaded models.
Returns all model files with associated metadata/preview info.
Supports fallback initials when no Civitai info is linked."""
import os
import json
import asyncio
from aiohttp import web
import server as comfy_server
import folder_paths
from ...config import METADATA_SUFFIX, PREVIEW_SUFFIX, MODEL_TYPE_ABBREVIATIONS

ps = comfy_server.PromptServer.instance

# Known model file extensions
_MODEL_EXTS = frozenset([
    '.safetensors', '.ckpt', '.pt', '.pth', '.bin',
    '.onnx', '.gguf', '.pkl',
])

# Known preview extensions
_PREVIEW_EXTS = frozenset(['.jpg', '.jpeg', '.png', '.webp', '.mp4', '.gif'])


def _get_type_abbrev(folder_name: str) -> str:
    """Get abbreviation for a model type folder name."""
    key = folder_name.lower().strip().replace(" ", "").replace("-", "").replace("_", "")
    # Try direct match first
    if folder_name.lower() in MODEL_TYPE_ABBREVIATIONS:
        return MODEL_TYPE_ABBREVIATIONS[folder_name.lower()]
    # Try compact match
    for k, v in MODEL_TYPE_ABBREVIATIONS.items():
        if k.replace("_", "") == key:
            return v
    # Fallback: first 2 uppercase chars
    return folder_name[:2].upper() if folder_name else "?"


def _scan_directory(models_dir: str) -> list:
    """Scan models directory and return list of found model entries."""
    results = []

    if not os.path.isdir(models_dir):
        return results

    for type_folder in sorted(os.listdir(models_dir)):
        type_path = os.path.join(models_dir, type_folder)
        if not os.path.isdir(type_path):
            continue

        abbrev = _get_type_abbrev(type_folder)

        # Walk the type folder (including subdirs)
        for root, dirs, files in os.walk(type_path):
            for fname in files:
                base, ext = os.path.splitext(fname)
                if ext.lower() not in _MODEL_EXTS:
                    continue

                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, models_dir)

                # Look for associated metadata
                meta_path = os.path.join(root, base + METADATA_SUFFIX)
                meta_data = None
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            meta_data = json.load(f)
                    except Exception:
                        pass

                # Look for preview file
                preview_path = None
                preview_type = None
                for pext in _PREVIEW_EXTS:
                    candidate = os.path.join(root, base + PREVIEW_SUFFIX + pext)
                    if os.path.exists(candidate):
                        preview_path = candidate
                        preview_type = "video" if pext == ".mp4" else "image"
                        break
                # Also check legacy .preview.jpeg
                if not preview_path:
                    legacy = os.path.join(root, base + ".preview.jpeg")
                    if os.path.exists(legacy):
                        preview_path = legacy
                        preview_type = "image"

                # Build entry
                try:
                    file_size = os.path.getsize(full_path)
                except Exception:
                    file_size = 0

                entry = {
                    "filename": fname,
                    "rel_path": rel_path,
                    "abs_path": full_path,
                    "file_size": file_size,
                    "model_type_folder": type_folder,
                    "type_abbreviation": abbrev,
                    "has_metadata": meta_data is not None,
                    "has_preview": preview_path is not None,
                    "preview_type": preview_type,
                    # Preview URL will be constructed by frontend using a serve endpoint
                    "preview_rel": os.path.relpath(preview_path, models_dir) if preview_path else None,
                }

                # Extract info from metadata if available
                if meta_data and isinstance(meta_data, dict):
                    entry.update({
                        "civitai_model_id": meta_data.get("ModelId"),
                        "civitai_version_id": meta_data.get("VersionId"),
                        "model_name": meta_data.get("ModelName"),
                        "version_name": meta_data.get("VersionName"),
                        "base_model": meta_data.get("BaseModel"),
                        "model_type_civitai": meta_data.get("ModelType"),
                        "creator": meta_data.get("CreatorUsername"),
                        "civitai_url": meta_data.get("CivitaiUrl"),
                        "trained_words": meta_data.get("TrainedWords", []),
                        "imported_at": meta_data.get("ImportedAt"),
                    })
                else:
                    entry.update({
                        "civitai_model_id": None,
                        "civitai_version_id": None,
                        "model_name": base,  # Use filename as name
                        "version_name": None,
                        "base_model": None,
                        "model_type_civitai": None,
                        "creator": None,
                        "civitai_url": None,
                        "trained_words": [],
                        "imported_at": None,
                    })

                results.append(entry)

    return results


@ps.routes.get("/civitai/scan_models")
async def route_scan_models(request):
    """Scan the models directory and return all found model files with metadata."""
    try:
        models_dir = getattr(folder_paths, 'models_dir', None)
        if not models_dir:
            models_dir = os.path.join(
                getattr(folder_paths, 'base_path', os.getcwd()), 'models')

        # Get active download paths to mark them
        active_paths = set()
        try:
            from ...downloader.manager import manager as _dm
            active_paths = _dm.get_active_paths()
        except Exception:
            pass

        # Run scan in thread to avoid blocking
        results = await asyncio.to_thread(_scan_directory, models_dir)

        # Mark entries that are currently being downloaded
        for entry in results:
            entry["is_downloading"] = os.path.abspath(entry["abs_path"]) in active_paths

        return web.json_response({
            "success": True,
            "models_dir": models_dir,
            "count": len(results),
            "models": results,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return web.json_response({"error": str(e)}, status=500)


@ps.routes.get("/civitai/serve_preview")
async def route_serve_preview(request):
    """Serve a preview file from the models directory."""
    rel = request.query.get("path", "").strip()
    if not rel:
        raise web.HTTPBadRequest(reason="Missing path")

    models_dir = getattr(folder_paths, 'models_dir', None)
    if not models_dir:
        models_dir = os.path.join(
            getattr(folder_paths, 'base_path', os.getcwd()), 'models')

    full = os.path.abspath(os.path.join(models_dir, rel))
    # Security: ensure path is within models_dir
    if not full.startswith(os.path.abspath(models_dir)):
        raise web.HTTPForbidden(reason="Path outside models directory")
    if not os.path.isfile(full):
        raise web.HTTPNotFound(reason="File not found")

    return web.FileResponse(full)
