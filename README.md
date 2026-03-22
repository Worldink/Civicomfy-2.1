# Civicomfy v4.0

**Civitai Model Downloader & Library Manager for ComfyUI**

## Features

### Search Tab
- **Meilisearch-powered** search from Civitai
- **Base models loaded dynamically** from Civitai facets (auto-updated)
- Single "Download" button per model — version selection in Download tab
- **EA detection**: orange badge, download blocked until public
- **Video thumbnails**: hover to play
- **Relevancy** sort by default
- NSFW blur with configurable threshold

### Download Tab
- Beautiful preview with **image gallery** from selected version
- **Version selector**: all versions shown, switch instantly
- **Trained words** displayed when available
- **File variant selector** for versions with multiple files
- **View on Civitai** link (exact version URL with `?modelVersionId=`)
- **Already installed** check: blocks re-download of same version
- **EA protection**: download disabled for Early Access
- **Subfolder support**: optionally organize by base model (e.g. `illustrious/`)
- **Ghost fix**: switching models cancels stale requests
- No force re-download clutter

### Status Tab
- Real-time progress: **MB/total, %, speed, ETA**
- Cancel / Retry / Open folder
- Download history with clear option

### Library Tab
- **Auto-scan** of entire ComfyUI models folder
- Shows all installed models with preview & metadata
- **Fallback initials** (CK, L, V, etc.) when no preview available
- **View on Civitai** for models with metadata
- **Delete button**: removes model + metadata + preview from disk
- After deletion, model can be re-downloaded immediately
- Filter/search installed models

### Settings
- API key, global root, default type, NSFW threshold

## File Structure

Each download creates **max 3 files** flat in the type folder:

```
models/checkpoints/
  ├── model.safetensors
  ├── model.cminfo.json
  └── model.preview.jpg    (or .mp4)
```

## Install

Copy `Civicomfy/` to `ComfyUI/custom_nodes/` → restart ComfyUI → click "Civicomfy" button.

## License

MIT
