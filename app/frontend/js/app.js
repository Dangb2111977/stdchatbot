// app/frontend/js/app.js
import { initAuthUI, tryResumeSession, doLogout } from "./auth.js";
import { initChatUI, bootAfterLogin } from "./chat.js";
import { applyI18N, setLang, getLang, t } from "./i18n.js";

const THEME_KEY = "theme";

function getTheme() {
  return localStorage.getItem(THEME_KEY) || "dark";
}
function setTheme(next) {
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem(THEME_KEY, next);
  const themeBtn = document.getElementById("themeBtn");
  if (themeBtn) {
    themeBtn.textContent = (next === "dark") ? t("header.theme.dark") : t("header.theme.light");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // init theme + i18n labels
  setTheme(getTheme());
  applyI18N();

  // wire theme toggle
  document.getElementById("themeBtn")?.addEventListener("click", () => {
    const next = (getTheme() === "dark") ? "light" : "dark";
    setTheme(next);
  });

  // wire language toggle
  document.getElementById("langBtn")?.addEventListener("click", () => {
    setLang(getLang() === "vi" ? "en" : "vi");
    // refresh theme button text in the new language
    setTheme(getTheme());
  });

  // chat + auth boot
  initChatUI();
  initAuthUI({ onAfterLogin: async () => { await bootAfterLogin(); } });

  (async () => {
    const ok = await tryResumeSession();
    if (ok) await bootAfterLogin();
  })();

  document.getElementById("logoutBtn")?.addEventListener("click", doLogout);
});
