/* MyJevis 共享状态与业务动作
 * 所有视图共用同一份状态，避免切换视图时重复请求。
 * 统计接口按并发 3 限制，失败只影响统计数字，不影响知识库基本信息。
 */
window.MJ = window.MJ || {};

(function (MJ) {
  "use strict";

  var DETAIL_KEY = "mj_detail_mode";
  var STATS_TTL = 60 * 1000;  /* 统计结果缓存 60 秒 */
  var DOCS_TTL = 20 * 1000;
  var STATS_CONCURRENCY = 3;

  var state = Vue.reactive({
    token: MJ.api.getToken(),
    username: MJ.api.getUsername(),
    view: "chat",
    kbs: [],
    kbsLoading: false,
    kbsError: "",
    activeKbId: null,
    stats: {},
    docs: {},
    messages: [],
    detailMode: localStorage.getItem(DETAIL_KEY) === "1",
    panelTab: "trace",
    panelOpen: false,
    drawerOpen: false,
    userMenuOpen: false,
    kbMenuId: null,
    booting: true,
  });

  var msgSeq = 0;

  /* ---------- 工具 ---------- */
  function runLimited(tasks, limit) {
    var idx = 0;
    var workers = [];
    var count = Math.max(1, Math.min(limit, tasks.length));
    for (var i = 0; i < count; i++) {
      workers.push((async function () {
        while (idx < tasks.length) {
          var cur = idx++;
          try { await tasks[cur](); } catch (e) { /* 单个失败不影响其他 */ }
        }
      })());
    }
    return Promise.all(workers);
  }

  function activeKb() {
    for (var i = 0; i < state.kbs.length; i++) {
      if (state.kbs[i].id === state.activeKbId) return state.kbs[i];
    }
    return null;
  }

  function kbStats(kbId) {
    return state.stats[kbId] || { loading: false, error: "", docs: null, chunks: null };
  }

  function kbDocs(kbId) {
    return state.docs[kbId] || { loading: false, error: "", items: [], loadedAt: 0 };
  }

  function isUnauthorized(err) {
    if (err && err.unauthorized) {
      logout(true);
      MJ.toast("登录已过期，请重新登录", "err");
      return true;
    }
    return false;
  }

  /* ---------- 认证 ---------- */
  function resetSession() {
    state.kbs = [];
    state.activeKbId = null;
    state.stats = {};
    state.docs = {};
    state.messages = [];
    state.kbsError = "";
  }

  function logout(silent) {
    MJ.api.clearToken();
    state.token = "";
    state.username = "";
    state.userMenuOpen = false;
    resetSession();
    if (!silent) MJ.toast("已退出登录");
  }

  async function authenticate(mode, username, password) {
    var data = mode === "register"
      ? await MJ.api.register(username, password)
      : await MJ.api.login(username, password);
    MJ.api.setToken(data.access_token, data.username);
    state.token = data.access_token;
    state.username = data.username;
    resetSession();
    greet();
    await loadKbs();
    return data;
  }

  /* ---------- 知识库 ---------- */
  async function loadKbs() {
    state.kbsLoading = true;
    state.kbsError = "";
    try {
      var list = await MJ.api.listKbs();
      state.kbs = Array.isArray(list) ? list : [];
      if (!state.activeKbId && state.kbs.length) {
        state.activeKbId = state.kbs[0].id;
      }
      if (state.activeKbId && !state.kbs.some(function (k) { return k.id === state.activeKbId; })) {
        state.activeKbId = state.kbs.length ? state.kbs[0].id : null;
      }
      loadStats(state.kbs.map(function (k) { return k.id; }));
    } catch (e) {
      if (isUnauthorized(e)) return;
      state.kbsError = e.message || "知识库加载失败";
    } finally {
      state.kbsLoading = false;
    }
  }

  async function loadStats(ids, force) {
    var targets = (ids || state.kbs.map(function (k) { return k.id; })).filter(Boolean);
    var tasks = [];
    targets.forEach(function (id) {
      var cur = state.stats[id];
      var fresh = cur && cur.loadedAt && (Date.now() - cur.loadedAt < STATS_TTL);
      if (!force && (fresh || (cur && cur.loading))) return;

      state.stats[id] = {
        loading: true,
        error: "",
        docs: cur ? cur.docs : null,
        chunks: cur ? cur.chunks : null,
        loadedAt: cur ? cur.loadedAt : 0,
      };

      tasks.push(async function () {
        try {
          var items = await MJ.api.listDocs(id);
          var list = Array.isArray(items) ? items : [];
          var chunks = list.reduce(function (sum, d) { return sum + (d.chunk_count || 0); }, 0);
          state.stats[id] = { loading: false, error: "", docs: list.length, chunks: chunks, loadedAt: Date.now() };
        } catch (e) {
          if (isUnauthorized(e)) throw e;
          /* 统计失败不影响卡片基本信息展示 */
          state.stats[id] = { loading: false, error: "统计失败", docs: null, chunks: null, loadedAt: Date.now() };
        }
      });
    });
    await runLimited(tasks, STATS_CONCURRENCY);
  }

  async function createKb(payload) {
    var created = await MJ.api.createKb(payload);
    await loadKbs();
    loadStats([created.id], true);
    if (created && created.id) state.activeKbId = created.id;
    MJ.toast("知识库已创建", "ok");
    return created;
  }

  async function updateKb(kbId, patch) {
    var updated = await MJ.api.updateKb(kbId, patch);
    var hit = state.kbs.find(function (k) { return k.id === kbId; });
    if (hit) Object.assign(hit, updated);
    return updated;
  }

  async function togglePublic(kb) {
    try {
      var updated = await MJ.api.updateKb(kb.id, { is_public: !kb.is_public });
      Object.assign(kb, updated);
      MJ.toast(updated.is_public ? "已设为公开，其他用户可检索" : "已设为私有", "ok");
    } catch (e) {
      if (isUnauthorized(e)) return;
      MJ.toast(e.message || "操作失败", "err");
    }
  }

  async function deleteKb(kb) {
    try {
      await MJ.api.deleteKb(kb.id);
    } catch (e) {
      if (isUnauthorized(e)) return;
      MJ.toast(e.message || "删除失败，请稍后重试", "err");
      return false;
    }
    delete state.stats[kb.id];
    delete state.docs[kb.id];
    if (state.activeKbId === kb.id) state.activeKbId = null;
    await loadKbs();
    MJ.toast("知识库已删除", "ok");
    return true;
  }

  /* ---------- 文档 ---------- */
  async function loadDocs(kbId, force) {
    var cur = state.docs[kbId];
    var fresh = cur && cur.loadedAt && (Date.now() - cur.loadedAt < DOCS_TTL);
    if (!force && (fresh || (cur && cur.loading))) return kbDocs(kbId);

    state.docs[kbId] = {
      loading: true,
      error: "",
      items: cur ? cur.items : [],
      loadedAt: cur ? cur.loadedAt : 0,
    };
    try {
      var items = await MJ.api.listDocs(kbId);
      state.docs[kbId] = {
        loading: false,
        error: "",
        items: Array.isArray(items) ? items : [],
        loadedAt: Date.now(),
      };
    } catch (e) {
      if (isUnauthorized(e)) return kbDocs(kbId);
      state.docs[kbId] = { loading: false, error: e.message || "文档加载失败", items: [], loadedAt: Date.now() };
    }
    return kbDocs(kbId);
  }

  async function deleteDoc(kbId, doc) {
    try {
      await MJ.api.deleteDoc(doc.id);
    } catch (e) {
      if (isUnauthorized(e)) return false;
      MJ.toast(e.message || "删除失败，请稍后重试", "err");
      return false;
    }
    await loadDocs(kbId, true);
    loadStats([kbId], true);
    MJ.toast("文档已删除", "ok");
    return true;
  }

  async function uploadDoc(kbId, file) {
    var data = await MJ.api.uploadDoc(kbId, file);
    await loadDocs(kbId, true);
    loadStats([kbId], true);
    return data;
  }

  /* ---------- 对话 ---------- */
  function greet() {
    state.messages = [
      Vue.reactive({
        id: ++msgSeq,
        role: "assistant",
        content: "你好，我是你的知识库总管家。先在左侧创建知识库、上传文档，然后直接提问就行。",
        time: Date.now(),
        greeting: true,
        steps: [],
        detail: false,
      }),
    ];
  }

  function lastAssistantWithSteps() {
    for (var i = state.messages.length - 1; i >= 0; i--) {
      var m = state.messages[i];
      if (m.role === "assistant" && m.steps && m.steps.length) return m;
    }
    return null;
  }

  function lastAssistant() {
    for (var i = state.messages.length - 1; i >= 0; i--) {
      if (state.messages[i].role === "assistant") return state.messages[i];
    }
    return null;
  }

  async function send(question) {
    var text = String(question || "").trim();
    if (!text || state.sending) return;

    state.messages.push(Vue.reactive({
      id: ++msgSeq, role: "user", content: text,
      time: Date.now(), steps: [], detail: false,
    }));

    /* 用 reactive 包裹：后续 ai.content / ai.steps 的赋值必须走代理，
       否则依赖它的 computed（如右侧面板的 lastSteps）不会失效。 */
    var ai = Vue.reactive({
      id: ++msgSeq, role: "assistant", content: "",
      time: Date.now(), pending: true,
      steps: [], detail: state.detailMode, error: "", done: false,
    });
    state.messages.push(ai);
    state.sending = true;

    try {
      if (state.detailMode) {
        await sendDetail(text, ai);
      } else {
        await sendStream(text, ai);
      }
    } finally {
      ai.pending = false;
      state.sending = false;
    }
  }

  async function sendStream(question, ai) {
    var finished = false;
    try {
      await MJ.api.chatStream(question, {
        onDelta: function (piece) {
          ai.content += piece;
        },
        onDone: function () {
          finished = true;
          ai.done = true;
        },
        onError: function (message) {
          ai.error = message || "服务暂时不可用";
        },
      });
      if (!ai.content && !ai.error) ai.error = "没有收到回答，请重试";
      if (!ai.error) ai.done = true;
    } catch (e) {
      if (isUnauthorized(e)) return;
      ai.error = e.message || "请求失败，请检查后端是否在运行";
    }
  }

  async function sendDetail(question, ai) {
    try {
      var data = await MJ.api.chatSync(question, 180000);
      ai.content = (data && data.answer) || "";
      ai.steps = (data && Array.isArray(data.intermediate_steps)) ? data.intermediate_steps : [];
      ai.done = true;
      if (!ai.content && !ai.steps.length) ai.error = "后端返回了空结果，请重试";
    } catch (e) {
      if (isUnauthorized(e)) return;
      ai.error = e.message || "详细模式请求失败";
    }
  }

  function setDetailMode(on) {
    state.detailMode = !!on;
    localStorage.setItem(DETAIL_KEY, state.detailMode ? "1" : "0");
  }

  function setView(view) {
    state.view = view;
    state.kbMenuId = null;
    state.drawerOpen = false;
    if (view === "kbs") loadStats(null);
    if (view === "docs" && state.activeKbId) loadDocs(state.activeKbId);
  }

  function selectKb(kb) {
    state.activeKbId = kb.id;
    state.kbMenuId = null;
    if (state.view === "docs") loadDocs(kb.id);
  }

  function boot() {
    if (state.token) {
      greet();
      loadKbs().finally(function () { state.booting = false; });
    } else {
      state.booting = false;
    }
  }

  MJ.store = state;
  MJ.actions = {
    boot: boot,
    logout: logout,
    authenticate: authenticate,
    loadKbs: loadKbs,
    loadStats: loadStats,
    loadDocs: loadDocs,
    createKb: createKb,
    updateKb: updateKb,
    togglePublic: togglePublic,
    deleteKb: deleteKb,
    deleteDoc: deleteDoc,
    uploadDoc: uploadDoc,
    send: send,
    setDetailMode: setDetailMode,
    setView: setView,
    selectKb: selectKb,
    activeKb: activeKb,
    kbStats: kbStats,
    kbDocs: kbDocs,
    lastAssistant: lastAssistant,
    lastAssistantWithSteps: lastAssistantWithSteps,
  };
})(window.MJ);
