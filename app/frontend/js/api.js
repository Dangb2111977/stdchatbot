// app/frontend/js/api.js
// Gọi API backend + tự xử lý Bearer/refresh (NHƯNG bỏ qua cho /auth/*)
import { getAccessToken, refreshAccessToken } from "./auth.js";

export const API_BASE = window.API_BASE || "http://127.0.0.1:8000";
export const EP = {
  refresh: "/auth/refresh",
  logout: "/auth/logout",
  login: "/auth/login",
  register: "/auth/register",
  me: "/me",

  conversations: "/conversations",
  convoRename: (id) => `/conversations/${id}`,
  convoMessages: (id) => `/conversations/${id}/messages`,

  chat: "/chat",
  chatImage: "/chat-image",
};

const DEFAULT_TIMEOUT_MS = 60_000;

function isAuthPath(path) {
  const p = typeof path === "string" ? path : "";
  return (
    p.includes("/auth/login") ||
    p.includes("/auth/register") ||
    p.includes("/auth/refresh")
  );
}

async function parsePayload(res) {
  const ct = res.headers.get("Content-Type") || "";
  if (ct.includes("application/json")) {
    try { return await res.json(); } catch { return null; }
  }
  try { return await res.text(); } catch { return null; }
}

export async function apiFetch(path, opt = {}) {
  const url = path.startsWith("http") ? path : API_BASE + path;
  const headers = new Headers(opt.headers || {});

  // Không gắn Bearer cho /auth/*
  const access = getAccessToken();
  if (access && !headers.has("Authorization") && !isAuthPath(path)) {
    headers.set("Authorization", "Bearer " + access);
  }

  // ---- Timeout + AbortController (an toàn) ----
  const timeout = opt.timeout ?? DEFAULT_TIMEOUT_MS;
  const controller =
    typeof AbortController !== "undefined" ? new AbortController() : null;
  const signal = controller ? controller.signal : undefined;

  const timerId = setTimeout(() => {
    if (controller && typeof controller.abort === "function") {
      controller.abort();
    }
  }, timeout);

  let res = await fetch(url, { ...opt, headers, signal });

  // Không auto-refresh trên /auth/*
  if (res.status === 401 && !isAuthPath(path)) {
    try {
      const ok = await refreshAccessToken();
      if (ok) {
        const access2 = getAccessToken();
        const h2 = new Headers(headers);
        h2.set("Authorization", "Bearer " + access2);
        res = await fetch(url, { ...opt, headers: h2, signal });
      }
    } catch {
      // ignore
    }
  }

  clearTimeout(timerId);
  return res;
}

async function ensureOkJson(res) {
  if (!res.ok) {
    const payload = await parsePayload(res);
    const err = new Error(`HTTP ${res.status}`);
    err.status = res.status;
    err.payload = payload;
    throw err;
  }
  return parsePayload(res);
}

/* ===== Conversations ===== */
export async function apiConvos() {
  const r = await apiFetch(EP.conversations);
  return ensureOkJson(r);
}

export async function apiCreateConvo(title = "") {
  const r = await apiFetch(EP.conversations, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  return ensureOkJson(r); // { id, title }
}

export async function apiRenameConvo(id, title) {
  const r = await apiFetch(EP.convoRename(id), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!r.ok) {
    const payload = await parsePayload(r);
    const err = new Error(`HTTP ${r.status}`);
    err.status = r.status; err.payload = payload; throw err;
  }
  return true;
}

export async function apiDeleteConvo(id) {
  const r = await apiFetch(EP.convoRename(id), { method: "DELETE" });
  if (!r.ok && r.status !== 204) {
    const payload = await parsePayload(r);
    const err = new Error(`HTTP ${r.status}`);
    err.status = r.status; err.payload = payload; throw err;
  }
  return true;
}

export async function apiMessages(id) {
  const r = await apiFetch(EP.convoMessages(id));
  return ensureOkJson(r); // [{role, mtype, content, ...}, ...]
}

/* ===== Chat ===== */
export async function apiChat({ question, history = null, convo_id, top_k = 6, lang = "vi", trace = false }) {
  const payload = { question, history, convo_id, top_k, lang, trace };
  const r = await apiFetch(EP.chat, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return ensureOkJson(r); // { answer, trace?, convo_id }
}

export async function apiChatImage({ question, file, convo_id, top_k = 6, lang = "vi", trace = false }) {
  const form = new FormData();
  if (question) form.append("question", question);
  if (file) form.append("image", file);
  form.append("convo_id", convo_id);
  form.append("top_k", String(top_k));
  form.append("lang", lang);
  form.append("trace", String(!!trace));

  const r = await apiFetch(EP.chatImage, { method: "POST", body: form });
  return ensureOkJson(r); // { answer, image_path, convo_id }
}
