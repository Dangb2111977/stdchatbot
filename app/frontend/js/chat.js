// chat.js — sidebar + chat view (trace enabled for text chat)
import {
  apiConvos, apiCreateConvo, apiRenameConvo,
  apiDeleteConvo, apiMessages, apiChat, apiChatImage,
  API_BASE
} from "./api.js";
import { isAuthed, doLogout } from "./auth.js";
import { applyI18N, t } from "./i18n.js";

// ===== Voice (STT/TTS) – follow app i18n lang =====
import {
  initVoice, startSTT, stopSTT,
  speak, isTTSEnabled, setTTSEnabled,
  updateVoiceFromApp, isSpeaking, stopSpeaking,
  speakAnswerIfVoice,        // ✅ thêm dòng này
} from "./voice.js";

/* ===================== State ===================== */
let chats = [];
let messages = [];
let currentId = null;
let selectedImageFile = null;

const LAST_KEY = "medchat_last_convo_v1";
const $ = (s) => document.querySelector(s);

/* ===================== Utils ===================== */
function toAbs(u) {
  if (!u) return u;
  if (/^(data:|blob:|https?:\/\/)/i.test(u)) return u;
  const base = (API_BASE || "").replace(/\/+$/, "");
  const path = String(u).replace(/^\/+/, "");
  return `${base}/${path}`;
}

function findLastIndex(arr, pred) {
  for (let i = arr.length - 1; i >= 0; i--) if (pred(arr[i], i)) return i;
  return -1;
}

const PLACEHOLDER_TITLES = new Set(["", "conversation", "hội thoại"]);
const isPlaceholderTitle = (s) => !s || PLACEHOLDER_TITLES.has(String(s).trim().toLowerCase());

async function maybeRenameConvoFrom(textCandidate) {
  const txt = (textCandidate || "").trim();
  if (!txt) return;
  const cur = chats.find(x => x.id === currentId);
  if (!cur) return;
  if (isPlaceholderTitle(cur.title)) {
    const newTitle = txt.slice(0, 60);
    try { await apiRenameConvo(currentId, newTitle); cur.title = newTitle; updateHeader(); renderChatList(); } catch {}
  }
}

async function backfillOldTitles(limit = 10) {
  const targets = chats.filter(c => isPlaceholderTitle(c.title)).slice(0, limit);
  for (const c of targets) {
    try {
      const msgs = await apiMessages(c.id);
      const firstUser =
        msgs.find(m => m.role === "user" && m.mtype !== "image")?.content?.trim() ||
        msgs.find(m => m.role === "user" && m.mtype === "image" && m.content)?.content?.trim();
      if (firstUser) {
        const title = firstUser.slice(0, 60);
        await apiRenameConvo(c.id, title);
        c.title = title;
      }
    } catch {}
  }
}

/* ===================== Renderers ===================== */
function renderChatList() {
  const list = $("#chatList");
  list.innerHTML = "";
  if (!chats.length) {
    list.innerHTML = `<div class="muted" data-i18n="sidebar.empty">Chưa có hội thoại</div>`;
    applyI18N(); return;
  }
  chats.forEach((c) => {
    const d = document.createElement("div");
    d.className = "chat-item" + (c.id === currentId ? " active" : "");
    const title = c.title && !isPlaceholderTitle(c.title) ? c.title : "Conversation";
    d.innerHTML = `
      <div class="chat-title">${title}</div>
      <div class="chat-meta">${new Date(c.updated_at || c.created_at).toLocaleString()}</div>
    `;
    d.onclick = () => loadChat(c.id);
    list.appendChild(d);
  });
}

function renderMessages() {
  const box = $("#messages");
  box.innerHTML = "";
  if (!messages.length) {
    box.innerHTML = `<div class="empty" data-i18n="messages.empty">${t("messages.empty")}</div>`;
    applyI18N(); return;
  }
  for (const m of messages) {
    const b = document.createElement("div");
    b.className = "bubble " + (m.role === "user" ? "user" : "bot");
    if (m.mtype === "image") {
      const src = toAbs(m.image_path);
      if (src) b.innerHTML = `<img class="msg-img" src="${src}" alt="User image">`;
      if (m.content) b.innerHTML += `<div class="img-caption">${m.content}</div>`;
      if (m.__temp) b.classList.add("pending");
    } else {
      b.innerHTML = (m.content || "").replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    }
    box.appendChild(b);
  }
  box.scrollTop = box.scrollHeight;
}

function updateHeader() {
  const cur = chats.find((x) => x.id === currentId);
  $("#headerTitle").textContent = cur?.title && !isPlaceholderTitle(cur.title)
    ? cur.title : t("header.title");
}

/* ===================== Data flows ===================== */
async function refreshConvos() {
  chats = await apiConvos();
  chats.sort((a, b) => new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at));
}

async function loadChat(id) {
  currentId = id;
  localStorage.setItem(LAST_KEY, id);
  const raw = await apiMessages(id);
  messages = raw.map(m =>
    (m.mtype === "image" && m.image_path) ? { ...m, image_path: toAbs(m.image_path) } : m
  );
  renderMessages(); renderChatList(); updateHeader();
}

async function ensureFreshConvo() {
  if (!currentId) {
    const c = await apiCreateConvo("");
    currentId = c.id;
    localStorage.setItem(LAST_KEY, currentId);
    await refreshConvos(); renderChatList();
  }
}

function buildHistory() {
  const hist = [];
  for (let i = 0; i < messages.length; i++) {
    const it = messages[i];
    if (it.role === "user" && it.mtype !== "image" && it.content) {
      const next = messages.slice(i + 1).find(x => x.role === "bot" && x.content);
      if (next) hist.push([it.content, next.content]);
    }
  }
  return hist;
}

/* ===================== Voice helpers ===================== */
function resolveAppLang() {
  const htmlLang = document.documentElement.getAttribute("lang");
  if (htmlLang) return htmlLang.toLowerCase().startsWith("en") ? "en" : "vi";
  if (typeof window.i18nGetLang === "function") return window.i18nGetLang();
  if (typeof window.getLang === "function") return window.getLang();
  if (window.APP_LANG) return String(window.APP_LANG).toLowerCase();
  return "vi";
}

// ✅ chỉ đọc câu trả lời khi:
// 1) người dùng bật ttsToggle, VÀ
// 2) câu hỏi vừa rồi đến từ voice (STT) – logic xử lý trong speakAnswerIfVoice()
function maybeSpeak(text) {
  const ttsChk = $("#ttsToggle");
  const allowed = ttsChk ? ttsChk.checked : isTTSEnabled();
  if (!allowed) return;
  speakAnswerIfVoice(text || "");
}

// --- Click-to-speak / click-again-to-stop ---
let lastSpeakEl = null;
function wireClickToSpeak() {
  const box = $("#messages");
  if (!box) return;
  box.addEventListener("click", (e) => {
    const el = e.target.closest(".bubble");
    if (!el) return;

    // ignore pure image bubbles
    if (el.querySelector("img")) return;

    const text = (el.innerText || "").trim();
    if (!text) return;

    // same bubble clicked while speaking -> stop
    if (isSpeaking() && lastSpeakEl === el) {
      stopSpeaking();
      el.classList.remove("speaking");
      lastSpeakEl = null;
      return;
    }

    // start speaking this bubble (manual TTS, không phụ thuộc voice input)
    if (lastSpeakEl) lastSpeakEl.classList.remove("speaking");
    stopSpeaking();
    lastSpeakEl = el;
    el.classList.add("speaking");
    speak(text, null, 1, () => {
      if (lastSpeakEl === el) {
        el.classList.remove("speaking");
        lastSpeakEl = null;
      }
    });
  });
}

function wireVoice() {
  const ok = initVoice({
    getAppLangFn: resolveAppLang,
    onFinal: (txt) => {
      const inp = $("#input");
      if (inp) inp.value = txt;
      $("#sendBtn")?.click();
    },
    // autoTTS: true, // bật nếu bạn có chế độ app-lang='auto'
  });
  if (!ok) console.warn("Browser does not support SpeechRecognition.");

  const micBtn = $("#micBtn");
  const ttsToggle = $("#ttsToggle");
  if (ttsToggle) {
    setTTSEnabled(!!ttsToggle.checked);
    ttsToggle.addEventListener("change", (e) => setTTSEnabled(e.target.checked));
  }

  if (micBtn) {
    let hold = false;
    micBtn.addEventListener("mousedown", () => { hold = true; startSTT(); micBtn.textContent = "🛑"; });
    window.addEventListener("mouseup", () => {
      if (hold) { stopSTT(); micBtn.textContent = "🎤"; hold = false; }
    });
    micBtn.addEventListener("click", () => {
      if (hold) return;
      if (micBtn.textContent === "🎤") { startSTT(); micBtn.textContent = "🛑"; }
      else { stopSTT(); micBtn.textContent = "🎤"; }
    });
  }

  wireClickToSpeak();
}

/* ===================== Send ===================== */
async function sendTextOrImage() {
  if (!isAuthed()) return alert(t("toast.sessionExpired"));

  const input = $("#input");
  const text = (input.value || "").trim();
  const hasImg = !!selectedImageFile;
  if (!text && !hasImg) return;

  await ensureFreshConvo();

  let previewIdx = findLastIndex(messages, m => m.__temp && m.role === "user" && m.mtype === "image");
  if (hasImg) {
    if (previewIdx !== -1) {
      messages[previewIdx].content = text || messages[previewIdx].content || "";
    } else {
      messages.push({
        role: "user",
        mtype: "image",
        image_path: selectedImageFile.__dataUrl || "",
        content: text || "",
        __temp: true
      });
      previewIdx = messages.length - 1;
    }
  } else {
    messages.push({ role: "user", mtype: "text", content: text });
  }
  renderMessages();

  const history = buildHistory();

  try {
    let answer = "";
    if (hasImg) {
      const data = await apiChatImage({ question: text, file: selectedImageFile, convo_id: currentId });
      answer = data?.answer || "";

      const serverUrl = data?.image_path || data?.image_url || data?.saved_image_url;
      if (previewIdx !== -1) {
        if (serverUrl) messages[previewIdx].image_path = toAbs(serverUrl);
        delete messages[previewIdx].__temp;
      }
      await maybeRenameConvoFrom(text);
      messages.push({ role: "bot", mtype: "text", content: answer });
      maybeSpeak(answer);          // ✅ chỉ đọc nếu câu hỏi là voice
    } else {
      const data = await apiChat({
        question: text, history, convo_id: currentId,
        top_k: 6, lang: "vi", trace: true
      });
      answer = data?.answer || "";
      await maybeRenameConvoFrom(text);

      messages.push({ role: "bot", mtype: "text", content: answer });
      maybeSpeak(answer);          // ✅ chỉ đọc nếu câu hỏi là voice

      // if (data?.trace) {
      //   const k = (data.trace.candidates || []).length;
      //   messages.push({
      //     role: "bot", mtype: "text",
      //     content: `[trace] mode=${data.trace.mode} used=${data.trace.used_context ? "yes" : "no"} k=${k}`
      //   });
      // }
    }

    renderMessages();
    await refreshConvos(); renderChatList(); updateHeader();
  } catch (e) {
    messages.push({ role: "bot", mtype: "text", content: "❌ " + (e?.message || e) });
    renderMessages();
  } finally {
    $("#input").value = "";
    $("#imageInput").value = "";
    selectedImageFile = null;
  }
}

/* ===================== Wiring ===================== */
function wireComposer() {
  $("#imageBtn")?.addEventListener("click", () => $("#imageInput").click());
  $("#imageInput")?.addEventListener("change", (e) => {
    const f = e.target.files?.[0]; if (!f) return;
    selectedImageFile = f;
    const fr = new FileReader();
    fr.onload = () => {
      selectedImageFile.__dataUrl = fr.result;
      let idx = findLastIndex(messages, m => m.__temp && m.role === "user" && m.mtype === "image");
      if (idx !== -1) messages[idx].image_path = fr.result;
      else messages.push({ role: "user", mtype: "image", image_path: fr.result, content: "", __temp: true });
      renderMessages();
    };
    fr.readAsDataURL(f);
  });

  $("#sendBtn")?.addEventListener("click", sendTextOrImage);
  $("#input")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendTextOrImage(); }
  });
}

function wireSidebar() {
  $("#newChatBtn")?.addEventListener("click", async () => {
    localStorage.removeItem(LAST_KEY);
    const c = await apiCreateConvo("");
    currentId = c.id; localStorage.setItem(LAST_KEY, currentId);
    messages = []; await refreshConvos(); renderChatList(); renderMessages(); updateHeader();
  });

  $("#deleteBtn")?.addEventListener("click", async () => {
    if (!currentId) return alert(t("toast.deleteConfirm"));
    if (!confirm(t("toast.deleteConfirm"))) return;
    await apiDeleteConvo(currentId);
    currentId = null; messages = []; await refreshConvos(); renderChatList(); renderMessages(); updateHeader();
  });

  $("#logoutBtn")?.addEventListener("click", (e) => {
    e.preventDefault();
    const btn = e.currentTarget; if (btn) btn.disabled = true;
    try { doLogout(); } catch {}
    setTimeout(() => {
      try { location.replace(location.origin + location.pathname); } catch { location.reload(); }
    }, 50);
  });
}

/* ===================== Public API ===================== */
export function initChatUI() { wireComposer(); wireSidebar(); wireVoice(); }

export async function bootAfterLogin() {
  await refreshConvos();
  await backfillOldTitles(10);

  const last = localStorage.getItem(LAST_KEY);
  if (last && chats.some(c => c.id === last)) await loadChat(last);
  else { renderChatList(); renderMessages(); updateHeader(); }

  // Nếu i18n đổi ngôn ngữ mà không phát event/đổi html[lang], hãy gọi:
  // updateVoiceFromApp();
}
