"""
Civicomfy - Civitai Model Downloader & Library Manager for ComfyUI
"""
import os

EXTENSION_ROOT = os.path.dirname(os.path.realpath(__file__))

try:
    from .config import WEB_DIRECTORY as _wd
    from .downloader import manager as _dm
    from .server import routes as _routes
    _ok = True
    print("[Civicomfy] Core modules loaded.")
except Exception as e:
    _ok = False
    import traceback
    print(f"[Civicomfy] ERROR loading modules:")
    traceback.print_exc()

if _ok:
    NODE_CLASS_MAPPINGS = {}
    NODE_DISPLAY_NAME_MAPPINGS = {}
    WEB_DIRECTORY = "./web"

    print("-" * 40)
    print("  Civicomfy v2.1 Loaded")
    print(f"  Web: {os.path.abspath(os.path.join(EXTENSION_ROOT, 'web'))}")
    print("-" * 40)
else:
    NODE_CLASS_MAPPINGS = {}
    NODE_DISPLAY_NAME_MAPPINGS = {}
    WEB_DIRECTORY = None
