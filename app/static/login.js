const LOGIN_THEME_STORAGE_KEY = "refined-oil-workbench-theme";
const loginDom = {
  form: document.getElementById("login-form"),
  username: document.getElementById("login-username"),
  password: document.getElementById("login-password"),
  remember: document.getElementById("login-remember"),
  submit: document.getElementById("login-submit"),
  error: document.getElementById("login-error"),
  status: document.getElementById("login-status"),
  themeButtons: Array.from(document.querySelectorAll("[data-theme-value]")),
};

function loginSetStatus(text, mode = "idle") {
  if (!loginDom.status) return;
  loginDom.status.textContent = text;
  loginDom.status.className = `chip soft-chip${mode === "loading" ? " is-loading" : ""}${mode === "error" ? " is-error" : ""}`;
}

function loginShowError(text = "") {
  if (!loginDom.error) return;
  loginDom.error.hidden = !text;
  loginDom.error.textContent = text;
}

function loginApplyTheme(theme) {
  const nextTheme = theme === "dark" ? "dark" : "light";
  document.body.dataset.theme = nextTheme;
  loginDom.themeButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.themeValue === nextTheme);
  });
  try {
    window.localStorage.setItem(LOGIN_THEME_STORAGE_KEY, nextTheme);
  } catch {}
}

function loginResolveTheme() {
  try {
    return window.localStorage.getItem(LOGIN_THEME_STORAGE_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

async function submitLogin(event) {
  event.preventDefault();
  const username = loginDom.username.value.trim();
  const password = loginDom.password.value;
  if (!username || !password) {
    loginShowError("请输入用户名和密码");
    return;
  }

  loginDom.submit.disabled = true;
  loginShowError("");
  loginSetStatus("登录中", "loading");

  try {
    const response = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username,
        password,
        remember_me: loginDom.remember.checked,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "登录失败");
    }
    loginSetStatus("登录成功");
    window.location.replace("/workbench");
  } catch (error) {
    loginSetStatus("登录失败", "error");
    loginShowError(error.message || String(error));
  } finally {
    loginDom.submit.disabled = false;
  }
}

async function initLogin() {
  loginApplyTheme(loginResolveTheme());
  loginDom.themeButtons.forEach((button) => {
    button.addEventListener("click", () => loginApplyTheme(button.dataset.themeValue));
  });
  loginDom.form?.addEventListener("submit", submitLogin);
  loginSetStatus("请输入账号");
}

initLogin();
