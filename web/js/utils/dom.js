export function addCssLink(relativeHref, id = "civitai-downloader-styles") {
  if (document.getElementById(id)) return;
  try {
    const url = new URL(relativeHref, import.meta.url);
    const link = document.createElement("link");
    link.id = id;
    link.rel = "stylesheet";
    link.href = url.href;
    document.head.appendChild(link);
  } catch (e) {
    console.error("[Civicomfy] CSS link error:", e);
  }
}
