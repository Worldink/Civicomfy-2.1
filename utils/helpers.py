"""
Utility helpers for path resolution, filename sanitization, file selection.
"""
import os
import re
import urllib.parse
from typing import Optional, List, Dict, Any, Tuple

import folder_paths
from ..config import PLUGIN_ROOT, MODEL_TYPE_DIRS

# ---------------------------------------------------------------------------
# Model type / folder resolution
# ---------------------------------------------------------------------------
_ALIAS_MAP = {
    "checkpoint": "checkpoints", "checkpoints": "checkpoints",
    "diffusionmodel": "diffusion_models", "diffusionmodels": "diffusion_models",
    "diffusion_model": "diffusion_models", "diffusion_models": "diffusion_models",
    "diffusers": "diffusers",
    "unet": "unet",
    "lora": "loras", "loras": "loras",
    "locon": "loras", "lycoris": "loras",
    "vae": "vae",
    "embedding": "embeddings", "embeddings": "embeddings", "textualinversion": "embeddings",
    "hypernetwork": "hypernetworks", "hypernetworks": "hypernetworks",
    "controlnet": "controlnet",
    "upscaler": "upscale_models", "upscalers": "upscale_models",
    "upscale_model": "upscale_models", "upscale_models": "upscale_models",
    "motionmodule": "motion_models", "motionmodules": "motion_models",
    "motion_model": "motion_models", "motion_models": "motion_models",
    "clip": "clip", "clip_vision": "clip_vision",
}
_ALIAS_COMPACT = {re.sub(r'[^a-z0-9]', '', k): v for k, v in _ALIAS_MAP.items()}


def _norm(t: str) -> str:
    return (t or "").strip().lower().replace(" ", "_").replace("-", "_")


def get_model_type_folder_name(model_type: str) -> str:
    n = _norm(model_type)
    if not n:
        return "checkpoints"
    if n in _ALIAS_MAP:
        return _ALIAS_MAP[n]
    c = re.sub(r'[^a-z0-9]', '', n)
    if c in _ALIAS_COMPACT:
        return _ALIAS_COMPACT[c]
    entry = MODEL_TYPE_DIRS.get(n)
    if entry and entry[1]:
        return str(entry[1])
    return n


def get_model_folder_paths(model_type: str) -> List[str]:
    """All known directories for a model type via folder_paths."""
    roots: List[str] = []
    candidates = set()
    n = _norm(model_type)
    folder = get_model_type_folder_name(model_type)
    candidates.add(n)
    candidates.add(folder)
    entry = MODEL_TYPE_DIRS.get(n)
    if entry and entry[1]:
        candidates.add(entry[1])
    # singular/plural
    if n.endswith("s"):
        candidates.add(n[:-1])
    else:
        candidates.add(n + "s")

    for key in candidates:
        if not key:
            continue
        try:
            paths = folder_paths.get_folder_paths(key)
            if isinstance(paths, (list, tuple)):
                for p in paths:
                    ap = os.path.abspath(str(p))
                    if ap not in roots:
                        roots.append(ap)
        except Exception:
            pass
    return roots


def get_model_dir(model_type: str) -> str:
    """Primary directory for a model type. Creates if missing."""
    paths = get_model_folder_paths(model_type)
    full = paths[0] if paths else None
    if not full:
        models_dir = getattr(folder_paths, 'models_dir', None)
        if not models_dir:
            models_dir = os.path.join(getattr(folder_paths, 'base_path', os.getcwd()), 'models')
        full = os.path.join(models_dir, get_model_type_folder_name(model_type))
    os.makedirs(full, exist_ok=True)
    return full


# ---------------------------------------------------------------------------
# URL / ID parsing
# ---------------------------------------------------------------------------
def parse_civitai_input(url_or_id: str) -> Tuple[Optional[int], Optional[int]]:
    """Parse Civitai URL or ID. Returns (model_id, version_id)."""
    if not url_or_id:
        return None, None
    url_or_id = str(url_or_id).strip()

    if url_or_id.isdigit():
        return int(url_or_id), None

    model_id = None
    version_id = None
    try:
        parsed = urllib.parse.urlparse(url_or_id)
        if not parsed.scheme or not parsed.netloc:
            if url_or_id.startswith(("/models/", "/model-versions/")):
                parsed = urllib.parse.urlparse("https://civitai.com" + url_or_id)
            else:
                return None, None
        if parsed.netloc and "civitai.com" not in parsed.netloc.lower():
            return None, None

        parts = [p for p in parsed.path.split('/') if p]
        qp = urllib.parse.parse_qs(parsed.query)

        # Version from query string
        if 'modelVersionId' in qp:
            try:
                version_id = int(qp['modelVersionId'][0])
            except (ValueError, IndexError):
                pass

        # Model from path
        if "models" in parts:
            idx = parts.index("models")
            if idx + 1 < len(parts) and parts[idx + 1].isdigit():
                model_id = int(parts[idx + 1])

        # Version from path
        if version_id is None and "model-versions" in parts:
            idx = parts.index("model-versions")
            if idx + 1 < len(parts) and parts[idx + 1].isdigit():
                version_id = int(parts[idx + 1])

    except Exception:
        return None, None

    return model_id, version_id


# ---------------------------------------------------------------------------
# Filename sanitization
# ---------------------------------------------------------------------------
_RESERVED = frozenset(
    ['CON', 'PRN', 'AUX', 'NUL'] +
    [f'COM{i}' for i in range(1, 10)] +
    [f'LPT{i}' for i in range(1, 10)]
)


def sanitize_filename(name: str, default: str = "downloaded_model") -> str:
    if not name:
        return default
    if isinstance(name, bytes):
        try:
            name = name.decode('utf-8')
        except UnicodeDecodeError:
            return default
    s = re.sub(r'[\x00-\x1f<>:"/\\|?*]', '_', name)
    s = re.sub(r'[_ ]{2,}', '_', s)
    s = s.strip('. _')
    base, ext = os.path.splitext(s)
    if base.upper() in _RESERVED:
        s = f"_{base}{ext}"
    if not s or s in ('.', '..'):
        s = default
    if len(s) > 200:
        b, e = os.path.splitext(s)
        s = b[:200 - len(e)] + e
    return s


# ---------------------------------------------------------------------------
# File selection
# ---------------------------------------------------------------------------
def select_primary_file(files: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Pick the best file from a version's file list."""
    if not files:
        return None
    primary = next((f for f in files if isinstance(f, dict) and f.get("primary") and f.get("downloadUrl")), None)
    if primary:
        return primary

    def _key(f):
        if not isinstance(f, dict) or not f.get('downloadUrl'):
            return 99
        nm = (f.get("name") or "").lower()
        meta = f.get("metadata") or {}
        fmt = (meta.get("format") or "").lower()
        sz = (meta.get("size") or "").lower()
        is_st = ".safetensors" in nm or fmt == "safetensor"
        is_pk = ".ckpt" in nm or ".pt" in nm or fmt == "pickletensor"
        is_pr = sz == "pruned"
        if is_st and is_pr:
            return 0
        if is_st:
            return 1
        if is_pk and is_pr:
            return 2
        if is_pk:
            return 3
        return 10

    valid = [f for f in files if isinstance(f, dict) and f.get("downloadUrl")]
    return sorted(valid, key=_key)[0] if valid else None


def guess_precision(file_dict: Dict[str, Any]) -> str:
    """Guess precision from file name / metadata."""
    try:
        nm = (file_dict.get('name') or '').lower()
        meta = file_dict.get('metadata') or {}
        for k in ('precision', 'dtype', 'fp'):
            v = (meta.get(k) or '').lower()
            if v:
                return v
        if 'fp8' in nm or 'int8' in nm:
            return 'fp8'
        if 'fp16' in nm or 'bf16' in nm:
            return 'fp16'
        if 'fp32' in nm:
            return 'fp32'
    except Exception:
        pass
    return 'N/A'
