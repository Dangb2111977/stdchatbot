// app/frontend/js/i18n.js
const I18N = {
  vi: {
    "auth.title.login": "Đăng nhập",
    "auth.title.register": "Đăng ký",
    "auth.username.label": "Username",
    "auth.password.label": "Mật khẩu",
    "auth.username.ph": "username",
    "auth.password.ph": "••••••••",
    "auth.login": "Đăng nhập",
    "auth.quickregister": "Đăng ký nhanh",
    "auth.create": "Tạo tài khoản",
    "auth.back": "Quay lại",

    "sidebar.new": "+ Tạo hội thoại",
    "sidebar.clear": "Xóa",
    "sidebar.logout": "Đăng xuất",
    "sidebar.empty": "Chưa có hội thoại",

    "header.title": "Hội thoại",
    "header.theme.dark": "Tối",
    "header.theme.light": "Sáng",
    "header.delete": "🗑 Xóa",

    "messages.empty": "Chưa có hội thoại. Tạo hội thoại mới nhé!",
    "image.pick": "📷 Chọn ảnh",
    "image.aria": "Chọn ảnh",
    "input.placeholder": "Hỏi: Sau quan hệ 5 ngày test HIV được chưa?",
    "send": "Gửi",

    "toast.needCred": "Nhập username & mật khẩu",
    "toast.loginFail": "Đăng nhập thất bại: ",
    "toast.registerNeed": "Username & mật khẩu bắt buộc",
    "toast.registerFail": "Đăng ký thất bại: ",
    "toast.sessionExpired": "⚠️ Phiên đã hết hạn, vui lòng đăng nhập.",
    "toast.deleteConfirm": "Xóa cuộc trò chuyện hiện tại?",
    "toast.deleteFail": "Xóa thất bại: ",
    "toast.analyzing": "Đang phân tích ảnh…",
    "toast.writing": "Đang soạn trả lời…",
  },
  en: {
    "auth.title.login": "Sign in",
    "auth.title.register": "Register",
    "auth.username.label": "Username",
    "auth.password.label": "Password",
    "auth.username.ph": "username",
    "auth.password.ph": "••••••••",
    "auth.login": "Sign in",
    "auth.quickregister": "Quick sign-up",
    "auth.create": "Create account",
    "auth.back": "Back",

    "sidebar.new": "+ New chat",
    "sidebar.clear": "Clear",
    "sidebar.logout": "Logout",
    "sidebar.empty": "No conversations",

    "header.title": "Conversation",
    "header.theme.dark": "Dark",
    "header.theme.light": "Light",
    "header.delete": "🗑 Delete",

    "messages.empty": "No messages yet. Start a new conversation!",
    "image.pick": "📷 Choose image",
    "image.aria": "Choose image",
    "input.placeholder": "Ask: Is 5 days after exposure too early to test for HIV?",
    "send": "Send",

    "toast.needCred": "Enter username & password",
    "toast.loginFail": "Login failed: ",
    "toast.registerNeed": "Username & password are required",
    "toast.registerFail": "Register failed: ",
    "toast.sessionExpired": "⚠️ Session expired, please sign in.",
    "toast.deleteConfirm": "Delete this conversation?",
    "toast.deleteFail": "Delete failed: ",
    "toast.analyzing": "Analyzing image…",
    "toast.writing": "Composing answer…",
  }
};

let LANG = localStorage.getItem("lang") ||
           (navigator.language?.toLowerCase().startsWith("vi") ? "vi" : "en");

export const getLang = () => LANG;
export const setLang = (next) => {
  LANG = next; localStorage.setItem("lang", next); applyI18N();
};
export const t = (key) => (I18N[LANG] && I18N[LANG][key]) || I18N.vi[key] || key;

export function applyI18N() {
  document.documentElement.setAttribute("lang", LANG);

  // đổi nhãn nút ngôn ngữ
  const langBtn = document.getElementById("langBtn");
  if (langBtn) langBtn.textContent = (LANG === "vi" ? "VI" : "EN");

  // áp i18n cho các element
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    const attrs = (el.getAttribute("data-i18n-attr") || "")
                    .split(",").map(s => s.trim()).filter(Boolean);
    const val = t(key);
    if (!attrs.length || attrs.includes("text")) el.textContent = val;
    if (attrs.includes("placeholder")) el.setAttribute("placeholder", val);
    if (attrs.includes("title")) el.setAttribute("title", val);
    if (attrs.includes("aria-label")) el.setAttribute("aria-label", val);
  });

  // cập nhật nhãn theme theo trạng thái hiện tại
  const themeBtn = document.getElementById("themeBtn");
  if (themeBtn) {
    const cur = document.documentElement.getAttribute("data-theme") || "dark";
    themeBtn.textContent = (cur === "dark") ? t("header.theme.dark") : t("header.theme.light");
  }
}
