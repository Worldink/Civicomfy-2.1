"""
Civicomfy Configuration
"""
import os
import folder_paths

# --- Concurrency & Timeouts ---
MAX_CONCURRENT_DOWNLOADS = 3
DEFAULT_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB — larger chunks = fewer syscalls = faster
DEFAULT_CONNECTIONS = 4
DOWNLOAD_HISTORY_LIMIT = 100
DOWNLOAD_TIMEOUT = 60
HEAD_REQUEST_TIMEOUT = 15
METADATA_DOWNLOAD_TIMEOUT = 20

# --- Paths ---
PLUGIN_ROOT = os.path.dirname(os.path.realpath(__file__))
WEB_DIRECTORY = os.path.join(PLUGIN_ROOT, "web")
JAVASCRIPT_PATH = os.path.join(WEB_DIRECTORY, "js")
PLACEHOLDER_IMAGE_PATH = os.path.join(WEB_DIRECTORY, "images", "placeholder.jpeg")

COMFYUI_ROOT_DIR = folder_paths.base_path

# --- Model Type Mapping ---
# Maps internal key -> (display_name, folder_paths_type)
MODEL_TYPE_DIRS = {
    "checkpoint":       ("Checkpoint",       "checkpoints"),
    "diffusionmodels":  ("Diffusion Models", "diffusers"),
    "unet":             ("Unet",             "unet"),
    "lora":             ("Lora",             "loras"),
    "locon":            ("LoCon",            "loras"),
    "lycoris":          ("LyCORIS",          "loras"),
    "vae":              ("VAE",              "vae"),
    "embedding":        ("Embedding",        "embeddings"),
    "hypernetwork":     ("Hypernetwork",     "hypernetworks"),
    "controlnet":       ("ControlNet",       "controlnet"),
    "upscaler":         ("Upscaler",         "upscale_models"),
    "motionmodule":     ("Motion Module",    "motion_models"),
    "poses":            ("Poses",            "poses"),
    "wildcards":        ("Wildcards",        "wildcards"),
    "other":            ("Other",            None),
}

# Civitai API type mapping for search filters
CIVITAI_API_TYPE_MAP = {
    "checkpoint":       "Checkpoint",
    "lora":             "LORA",
    "locon":            "LoCon",
    "lycoris":          "LORA",
    "vae":              "VAE",
    "embedding":        "TextualInversion",
    "hypernetwork":     "Hypernetwork",
    "controlnet":       "Controlnet",
    "motionmodule":     "MotionModule",
    "poses":            "Poses",
    "wildcards":        "Wildcards",
    "upscaler":         "Upscaler",
    "unet":             "UNET",
    "diffusionmodels":  "Checkpoint",
}

# Type abbreviations for fallback thumbnails
MODEL_TYPE_ABBREVIATIONS = {
    "checkpoint":       "CK",
    "checkpoints":      "CK",
    "lora":             "L",
    "loras":            "L",
    "locon":            "LC",
    "lycoris":          "LY",
    "vae":              "V",
    "embedding":        "E",
    "embeddings":       "E",
    "textualinversion": "E",
    "hypernetwork":     "HN",
    "hypernetworks":    "HN",
    "controlnet":       "CN",
    "upscaler":         "UP",
    "upscale_models":   "UP",
    "motionmodule":     "MM",
    "motion_models":    "MM",
    "unet":             "UN",
    "diffusionmodels":  "DM",
    "diffusers":        "DM",
    "poses":            "P",
    "wildcards":        "W",
    "clip":             "CL",
    "clip_vision":      "CV",
    "other":            "?",
}

# --- File Suffixes ---
METADATA_SUFFIX = ".cminfo.json"
PREVIEW_SUFFIX = ".preview"  # Extension added dynamically (.jpg, .mp4, etc.)

# --- Startup Log ---
print("-" * 30)
print("[Civicomfy Config Initialized]")
print(f"  Plugin Root: {PLUGIN_ROOT}")
print(f"  ComfyUI Base: {COMFYUI_ROOT_DIR}")
print("-" * 30)
