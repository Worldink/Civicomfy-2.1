export function setCookie(name, value, days) {
  let expires = "";
  if (days) {
    const d = new Date();
    d.setTime(d.getTime() + days * 86400000);
    expires = "; expires=" + d.toUTCString();
  }
  document.cookie = `${name}=${value || ""}${expires}; path=/; SameSite=Lax`;
}

export function getCookie(name) {
  const eq = name + "=";
  for (let c of document.cookie.split(";")) {
    c = c.trimStart();
    if (c.startsWith(eq)) return c.substring(eq.length);
  }
  return null;
}
