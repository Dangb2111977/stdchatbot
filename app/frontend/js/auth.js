// auth.js — Logout tức thì (fire-and-forget), refresh token, login/register UI

import { API_BASE, EP } from "./api.js";
import { applyI18N, t } from "./i18n.js";

const AUTH = {
  access: localStorage.getItem("access_token") || "",
  refresh: localStorage.getItem("refresh_token") || "",
};

export const isAuthed = () => !!AUTH.access;
export const getAccessToken = () => AUTH.access;

function setTokens({ access_token, refresh_token }) {
  if (access_token) { AUTH.access = access_token; localStorage.setItem("access_token", access_token); }
  if (refresh_token) { AUTH.refresh = refresh_token; localStorage.setItem("refresh_token", refresh_token); }
}
function clearTokens() {
  AUTH.access = ""; AUTH.refresh = "";
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

export async function refreshAccessToken() {
  if (!AUTH.refresh) return false;
  const r = await fetch(API_BASE + EP.refresh, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: AUTH.refresh }),
  });
  if (!r.ok) return false;
  const d = await r.json();
  setTokens({ access_token: d.access_token });
  return true;
}

export async function tryResumeSession() {
  if (!AUTH.access && AUTH.refresh) return await refreshAccessToken();
  return !!AUTH.access;
}

// ⬇️ LOGOUT tức thì: không chờ network; gửi yêu cầu kiểu fire-and-forget
export function doLogout() {
  const url = API_BASE + EP.logout;
  const payload = JSON.stringify({ refresh_token: AUTH.refresh || "" });

  try {
    if (navigator && typeof navigator.sendBeacon === "function") {
      // Gửi trong nền, không block UI
      const blob = new Blob([payload], { type: "application/json" });
      navigator.sendBeacon(url, blob);
    } else {
      // Fallback: fetch keepalive với timeout ngắn để không kẹt UI
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 400); // 400ms là đủ
      fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
        keepalive: true,
        signal: ctrl.signal,
      }).catch(() => {}).finally(() => clearTimeout(timer));
    }
  } catch {}

  // Xóa session & chuyển UI NGAY LẬP TỨC
  clearTokens();
  try {
    const app = document.getElementById("appScreen");
    const auth = document.getElementById("authScreen");
    if (app) app.style.display = "none";
    if (auth) auth.classList.remove("hidden");
  } catch {}

  // Reload nhẹ để reset sạch state/JS module
  setTimeout(() => {
    try {
      location.replace(location.origin + location.pathname);
    } catch {
      location.reload();
    }
  }, 10);
}

export function initAuthUI({ onAfterLogin }) {
  const authScreen = document.getElementById("authScreen");
  const appScreen  = document.getElementById("appScreen");
  const loginBox = document.getElementById("loginBox");
  const regBox   = document.getElementById("regBox");
  const authTitle = document.getElementById("authTitle");

  document.getElementById("toRegister")?.addEventListener("click", () => {
    loginBox.hidden = true; regBox.hidden = false;
    authTitle.setAttribute("data-i18n","auth.title.register"); applyI18N();
  });
  document.getElementById("backLogin")?.addEventListener("click", () => {
    regBox.hidden = true; loginBox.hidden = false;
    authTitle.setAttribute("data-i18n","auth.title.login"); applyI18N();
  });

  document.getElementById("doLogin")?.addEventListener("click", async () => {
    const u = (document.getElementById("loginUser").value || "").trim();
    const p = (document.getElementById("loginPass").value || "").trim();
    if (!u || !p) return alert(t("toast.needCred"));
    const r = await fetch(API_BASE + EP.login, {
      method:"POST",
      headers:{ "Content-Type":"application/json" },
      body: JSON.stringify({ username:u, password:p })
    });
    const txt = await r.text();
    if (!r.ok) return alert(t("toast.loginFail") + txt);
    setTokens(JSON.parse(txt||"{}"));
    authScreen.classList.add("hidden");
    appScreen.style.display="flex";
    await onAfterLogin?.();
  });

  document.getElementById("doRegister")?.addEventListener("click", async () => {
    const u = (document.getElementById("regUser").value || "").trim();
    const p = (document.getElementById("regPass").value || "").trim();
    if (!u || !p) return alert(t("toast.registerNeed"));
    const r = await fetch(API_BASE + EP.register, {
      method:"POST",
      headers:{ "Content-Type":"application/json" },
      body: JSON.stringify({ username:u, password:p })
    });
    const txt = await r.text();
    if (!r.ok) return alert(t("toast.registerFail") + txt);
    setTokens(JSON.parse(txt||"{}"));
    authScreen.classList.add("hidden");
    appScreen.style.display="flex";
    await onAfterLogin?.();
  });
}
