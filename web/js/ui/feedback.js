export class Feedback {
  constructor(el) {
    this.el = el;
    this._t = null;
  }
  ensureFontAwesome() {
    if (!document.getElementById('civitai-fa-link')) {
      const l = document.createElement('link');
      l.id = 'civitai-fa-link';
      l.rel = 'stylesheet';
      l.href = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css';
      l.crossOrigin = 'anonymous';
      document.head.appendChild(l);
    }
  }
  show(msg, type = 'info', dur = 3000) {
    if (!this.el) return;
    if (this._t) clearTimeout(this._t);
    this.el.textContent = msg;
    this.el.className = `civitai-toast ${type}`;
    requestAnimationFrame(() => this.el.classList.add('show'));
    this._t = setTimeout(() => { this.el.classList.remove('show'); this._t = null; }, dur);
  }
}
