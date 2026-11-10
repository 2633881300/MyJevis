/* 登录 / 注册视图：左侧品牌区 + 右侧表单卡片 */
window.MJ = window.MJ || {};
MJ.views = MJ.views || {};

MJ.views.auth = {
  setup: function () {
    var mode = Vue.ref("login");
    var username = Vue.ref("");
    var password = Vue.ref("");
    var busy = Vue.ref(false);
    var error = Vue.ref("");

    function switchMode(next) {
      mode.value = next;
      error.value = "";
    }

    async function submit() {
      if (busy.value) return;
      var u = username.value.trim();
      var p = password.value;
      if (!u) { error.value = "请输入用户名"; return; }
      if (!p) { error.value = "请输入密码"; return; }
      if (mode.value === "register") {
        if (u.length < 2) { error.value = "用户名至少 2 个字符"; return; }
        if (p.length < 6) { error.value = "密码至少 6 位"; return; }
      }
      busy.value = true;
      error.value = "";
      try {
        await MJ.actions.authenticate(mode.value, u, p);
        MJ.toast(mode.value === "register" ? "注册成功，已登录" : "登录成功", "ok");
      } catch (e) {
        error.value = e && e.message ? e.message : "操作失败";
      } finally {
        busy.value = false;
      }
    }

    return {
      mode: mode, username: username, password: password,
      busy: busy, error: error, switchMode: switchMode, submit: submit,
    };
  },
  template: [
    '<div class="auth">',
    '  <div class="auth-brand">',
    '    <div class="auth-brand-mark">M</div>',
    '    <h1>MyJevis</h1>',
    '    <div class="slogan">多智能体 × RAG 的个人知识库</div>',
    '    <div class="tags">',
    '      <span class="auth-tag">Agent Harness</span>',
    '      <span class="auth-tag">多知识库隔离</span>',
    '      <span class="auth-tag">基于 LangGraph</span>',
    '    </div>',
    '  </div>',
    '  <div class="auth-panel">',
    '    <div class="auth-card" data-testid="auth-card">',
    '      <div class="auth-tabs">',
    '        <button class="auth-tab" data-testid="auth-tab-login" :class="{ on: mode === \'login\' }" @click="switchMode(\'login\')">登录</button>',
    '        <button class="auth-tab" data-testid="auth-tab-register" :class="{ on: mode === \'register\' }" @click="switchMode(\'register\')">注册</button>',
    '      </div>',
    '      <h2>{{ mode === "login" ? "欢迎回来" : "创建账号" }}</h2>',
    '      <p class="sub">{{ mode === "login" ? "登录后继续使用你的知识库" : "注册后自动登录，数据仅存于本机" }}</p>',
    '      <form @submit.prevent="submit">',
    '        <div class="field">',
    '          <label>用户名</label>',
    '          <input v-model="username" data-testid="auth-username" autocomplete="username" :placeholder="mode === \'register\' ? \'至少 2 个字符\' : \'请输入用户名\'" />',
    '        </div>',
    '        <div class="field">',
    '          <label>密码</label>',
    '          <input v-model="password" data-testid="auth-password" type="password" :autocomplete="mode === \'register\' ? \'new-password\' : \'current-password\'" :placeholder="mode === \'register\' ? \'至少 6 位\' : \'请输入密码\'" />',
    '        </div>',
    '        <p v-if="error" data-testid="auth-error" style="color:var(--danger);font-size:12.5px;margin:-4px 0 10px">{{ error }}</p>',
    '        <button class="btn btn-primary btn-block" data-testid="auth-submit" type="submit" :disabled="busy">',
    '          <span v-if="busy" class="spinner"></span>',
    '          <span>{{ busy ? "处理中…" : (mode === "login" ? "登录" : "注册并登录") }}</span>',
    '        </button>',
    '      </form>',
    '      <p class="auth-foot">',
    '        {{ mode === "login" ? "还没有账号？" : "已有账号？" }}',
    '        <a @click="switchMode(mode === \'login\' ? \'register\' : \'login\')">{{ mode === "login" ? "立即注册" : "去登录" }}</a>',
    '      </p>',
    '    </div>',
    '  </div>',
    '</div>',
  ].join(""),
};
