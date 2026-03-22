import { app } from "../../../scripts/app.js";
import { addCssLink } from "./utils/dom.js";
import { CivitaiDownloaderUI } from "./ui/UI.js";

const NAME = "Civicomfy";

function addMenuButton() {
  const grp = document.querySelector(".comfyui-button-group");
  if (!grp) { setTimeout(addMenuButton, 500); return; }
  if (document.getElementById("civitai-downloader-button")) return;

  const btn = document.createElement("button");
  btn.textContent = NAME;
  btn.id = "civitai-downloader-button";
  btn.title = "Open Civicomfy";

  btn.onclick = async () => {
    if (!window.civitaiDownloaderUI) {
      window.civitaiDownloaderUI = new CivitaiDownloaderUI();
      document.body.appendChild(window.civitaiDownloaderUI.modal);
      try {
        await window.civitaiDownloaderUI.initializeUI();
      } catch (e) {
        console.error(`[${NAME}] Init error:`, e);
      }
    }
    window.civitaiDownloaderUI?.openModal();
  };

  grp.appendChild(btn);

  // Fallback
  if (!grp.contains(btn)) {
    const menu = document.querySelector(".comfy-menu");
    if (menu) menu.appendChild(btn);
  }
}

app.registerExtension({
  name: "Civicomfy.CivitaiDownloader",
  async setup() {
    addCssLink("../civitaiDownloader.css");
    addMenuButton();
  },
});
