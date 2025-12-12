// frontend/js/voice.js
// Voice layer: STT (Web Speech Recognition) + TTS (SpeechSynthesis)
// Bám theo ngôn ngữ hiện tại của app (vi/en) từ i18n.

let recognition = null;
let sttActive = false;

let ttsEnabled = true;

// Hàm lấy ngôn ngữ app (inject từ chat.js)
let getAppLang = () => "vi"; // trả 'vi' | 'en' | 'auto'
let autoDetectTTS = false;   // chỉ dùng nếu app lang = 'auto'

// Locale hiện tại cho STT/TTS
let sttLocale = "vi-VN";
let ttsLocale = "vi-VN";

// Track utterance TTS hiện tại
let currentUtterance = null;

// Track xem câu hỏi cuối cùng có dùng voice hay không
let lastInputWasVoice = false;

let onPartialCb = null;
let onFinalCb = null;

/* ---------------- Helpers ---------------- */
function mapAppLangToLocale(appLang) {
  const v = (appLang || "").toLowerCase();
  if (v.startsWith("en")) return "en-US";
  if (v.startsWith("vi")) return "vi-VN";
  return "vi-VN";
}

function pickVoice(lang) {
  const vs = window.speechSynthesis?.getVoices?.() || [];
  return (
    vs.find((v) => (v.lang || "").toLowerCase().startsWith(lang.toLowerCase())) ||
    vs[0]
  );
}

// Heuristic nhỏ để auto detect khi app lang = 'auto'
function detectTTSLang(text = "") {
  const viRegex =
    /[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđĐ]/;
  if (viRegex.test(text)) return "vi-VN";

  const enWords =
    /\b(the|and|is|are|you|your|with|from|for|about|have|has|not|can|should|what|when|where|why|which)\b/i;
  const asciiMostly = /^[\x00-\x7F\s.,;:!?'"()\[\]\-–—/\\%+&0-9]*$/;
  if (enWords.test(text) || asciiMostly.test(text)) return "en-US";

  return ttsLocale || "vi-VN";
}

function warmUpVoices() {
  if (!window.speechSynthesis) return;
  window.speechSynthesis.onvoiceschanged = () => {};
  const dummy = new SpeechSynthesisUtterance("");
  window.speechSynthesis.speak(dummy);
  window.speechSynthesis.cancel();
}

/* --------------- Public API ---------------- */
export function initVoice({
  getAppLangFn, // () => 'vi' | 'en' | 'auto'
  onPartial, // (text) => void
  onFinal, // (text) => void
  autoTTS = false, // nếu true và app-lang='auto' => detect theo text
} = {}) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return false;

  getAppLang = typeof getAppLangFn === "function" ? getAppLangFn : getAppLang;
  autoDetectTTS = !!autoTTS;

  onPartialCb = onPartial || null;
  onFinalCb = onFinal || null;

  // set locale ban đầu theo app
  updateVoiceFromApp();

  recognition = new SR();
  recognition.lang = sttLocale;
  recognition.interimResults = true;
  recognition.continuous = false;

  recognition.onresult = (e) => {
    let finalText = "",
      interim = "";
    for (let i = e.resultIndex; i < e.results.length; ++i) {
      const t = e.results[i][0].transcript;
      if (e.results[i].isFinal) finalText += t;
      else interim += t;
    }
    if (interim && onPartialCb) onPartialCb(interim);
    if (finalText) {
      // đánh dấu: câu hỏi này đến từ voice
      lastInputWasVoice = true;
      if (onFinalCb) onFinalCb(finalText.trim());
    }
  };
  recognition.onend = () => {
    sttActive = false;
  };
  recognition.onerror = (e) => {
    console.warn("STT error:", e.error);
    sttActive = false;
  };

  warmUpVoices();

  // cập nhật khi app đổi ngôn ngữ
  window.addEventListener("i18n:lang-changed", updateVoiceFromApp);
  try {
    const mo = new MutationObserver(updateVoiceFromApp);
    mo.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["lang"],
    });
  } catch {}

  return true;
}

export function updateVoiceFromApp() {
  const appLang = (getAppLang() || "vi").toLowerCase(); // 'vi' | 'en' | 'auto'
  const baseLang = appLang === "auto" ? "vi" : appLang; // mặc định VI nếu auto

  sttLocale = mapAppLangToLocale(baseLang);
  ttsLocale = mapAppLangToLocale(baseLang);

  if (recognition) {
    const wasActive = sttActive;
    try {
      if (wasActive) recognition.stop();
    } catch {}
    recognition.lang = sttLocale;
    try {
      if (wasActive) recognition.start();
    } catch {}
  }
}

/* ------- STT control ------- */
export function startSTT() {
  if (!recognition || sttActive) return;
  recognition.lang = sttLocale;
  sttActive = true;
  recognition.start();
}

export function stopSTT() {
  if (recognition && sttActive) recognition.stop();
  sttActive = false;
}

/* ------- TTS helpers ------- */
export function setTTSEnabled(v) {
  ttsEnabled = !!v;
}
export function isTTSEnabled() {
  return ttsEnabled;
}

export function isSpeaking() {
  return !!(
    window.speechSynthesis && window.speechSynthesis.speaking
  );
}

export function stopSpeaking() {
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
  currentUtterance = null;
}

/**
 * Đọc text (dùng cho chế độ đọc thủ công, ví dụ click vào bubble).
 * Luôn dùng voice theo ngôn ngữ app (VI/EN), trừ khi truyền langOverride.
 */
export function speak(text, langOverride = null, rate = 1, onend = null) {
  if (!ttsEnabled || !window.speechSynthesis) return null;

  stopSpeaking(); // cancel utterance cũ

  const appLang = (getAppLang() || "vi").toLowerCase();
  let lang = langOverride;

  if (!lang) {
    if (autoDetectTTS && appLang === "auto") {
      lang = detectTTSLang(text || "");
    } else {
      lang = ttsLocale; // VI hoặc EN đúng theo UI
    }
  }

  const u = new SpeechSynthesisUtterance(text || "");
  u.lang = lang;

  const v = pickVoice(lang);
  if (v) u.voice = v;

  u.rate = rate;
  u.onend = () => {
    currentUtterance = null;
    if (onend) onend();
  };
  u.onerror = () => {
    currentUtterance = null;
    if (onend) onend();
  };

  currentUtterance = u;
  window.speechSynthesis.speak(u);
  return u;
}

/**
 * Chỉ đọc câu trả lời NẾU câu hỏi vừa rồi đến từ voice (STT).
 * Dùng cho auto-read: trong chat.js thay vì gọi speak(answer),
 * hãy gọi speakAnswerIfVoice(answer).
 */
export function speakAnswerIfVoice(text, langOverride = null, rate = 1, onend = null) {
  if (!lastInputWasVoice) return null; // câu hỏi không phải từ voice → không đọc
  lastInputWasVoice = false;           // reset cờ
  return speak(text, langOverride, rate, onend);
}
