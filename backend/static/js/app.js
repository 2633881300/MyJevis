/* 应用入口：顶栏、侧栏、视图切换、知识库表单
 * 加载顺序要求：vue → api.js → ui.js → store.js → views/*.js → app.js
 */
window.MJ = window.MJ || {};

(function (MJ) {
  "use strict";

  /* ---------------- 顶栏 ---------------- */
  var Topbar = {
    setup: function () {
      var s = MJ.store;
      function logout() { s.userMenuOpen = false; MJ.actions.logout(); }
      function toggleUser() { s.userMenuOpen = !s.userMenuOpen; }
      function togglePanel() { s.panelOpen = !s.panelOpen; }
      function toggleDrawer() { s.drawerOpen = !s.drawerOpen; }
      return { s: s, logout: logout, toggleUser: toggleUser, togglePanel: togglePanel, toggleDrawer: toggleDrawer };
    },
    template: [
      '<header class="topbar">',
      '  <button class="icon-btn drawer-btn" title="知识库列表" @click="toggleDrawer"><mj-ico name="menu" :size="18" /></button>',
      '  <div class="brand">',
      '    <div class="brand-mark">M</div>',
      '    <span class="brand-name">MyJevis</span>',
      '    <span class="brand-ver">v0.2.0</span>',
      '    <span class="brand-sub">AI Knowledge Workspace</span>',
      '  </div>',
      '  <div class="topbar-spacer"></div>',
      '  <button class="icon-btn mobile-only" title="Agent 信息" @click="togglePanel"><mj-ico name="spark" :size="17" /></button>',
      '  <div class="user-chip" data-testid="user-chip" @click.stop="toggleUser">',
      '    <div class="avatar">{{ (s.username || "U").slice(0, 1).toUpperCase() }}</div>',
      '    <span class="user-name">{{ s.username || "未登录" }}</span>',
      '    <mj-ico name="chevron" :size="13" class="chev" />',
      '    <div v-if="s.userMenuOpen" class="menu" data-testid="user-menu" @click.stop>',
      '      <div class="menu-item" style="cursor:default;color:var(--text-3);font-size:12px">已登录：{{ s.username }}</div>',
      '      <div class="menu-item danger" data-testid="logout" @click="logout"><mj-ico name="close" :size="14" />退出登录</div>',
      '    </div>',
      '  </div>',
      '</header>',
    ].join(""),
  };

  /* ---------------- 侧栏 ---------------- */
  var Sidebar = {
    setup: function () {
      var s = MJ.store;

      function goto(view) { MJ.actions.setView(view); }

      function pick(kb) { MJ.actions.selectKb(kb); }

      function createNew() {
        if (MJ.openKbForm) MJ.openKbForm("create", null);
      }

      function toggleMenu(id, e) {
        if (e) e.stopPropagation();
        s.kbMenuId = s.kbMenuId === id ? null : id;
      }

      function openDocs(kb) {
        s.kbMenuId = null;
        MJ.actions.selectKb(kb);
        MJ.actions.setView("docs");
      }

      function editKb(kb) {
        s.kbMenuId = null;
        if (MJ.openKbForm) MJ.openKbForm("edit", kb);
      }

      async function removeKb(kb) {
        s.kbMenuId = null;
        var ok = await MJ.confirm({
          title: "删除知识库",
          message: "确定删除「" + kb.name + "」吗？\n\n该库下的所有文档与向量数据会一并清除，操作不可恢复。",
          okText: "删除",
          danger: true,
        });
        if (ok) await MJ.actions.deleteKb(kb);
      }

      function initial(name) { return String(name || "?").slice(0, 1).toUpperCase(); }

      return {
        s: s, goto: goto, pick: pick, createNew: createNew, toggleMenu: toggleMenu,
        openDocs: openDocs, editKb: editKb, removeKb: removeKb, initial: initial,
      };
    },
    template: [
      '<aside class="sidebar">',
      '  <nav class="nav">',
      '    <div class="nav-item" data-testid="nav-chat" :class="{ on: s.view === \'chat\' }" @click="goto(\'chat\')">',
      '      <mj-ico class="ico" name="chat" :size="17" /><span>智能问答</span>',
      '    </div>',
      '    <div class="nav-item" data-testid="nav-kbs" :class="{ on: s.view === \'kbs\' }" @click="goto(\'kbs\')">',
      '      <mj-ico class="ico" name="folder" :size="17" /><span>知识库管理</span>',
      '    </div>',
      '    <div class="nav-item" data-testid="nav-docs" :class="{ on: s.view === \'docs\' }" @click="goto(\'docs\')">',
      '      <mj-ico class="ico" name="file" :size="17" /><span>文档管理</span>',
      '    </div>',
      '  </nav>',

      '  <div class="kb-section">',
      '    <div class="kb-section-head">',
      '      <span class="label">我的知识库</span>',
      '      <span class="count">({{ s.kbs.length }})</span>',
      '      <span class="grow"></span>',
      '      <button class="kb-add" data-testid="kb-add" title="新建知识库" @click="createNew"><mj-ico name="plus" :size="15" /></button>',
      '    </div>',
      '    <div class="kb-list" data-testid="kb-list">',
      '      <div v-for="kb in s.kbs" :key="kb.id" class="kb-item" data-testid="kb-item" :data-kb-id="kb.id" :class="{ on: kb.id === s.activeKbId }" @click="pick(kb)">',
      '        <div class="kb-dot">{{ initial(kb.name) }}</div>',
      '        <span class="kb-title" :title="kb.name">{{ kb.name }}</span>',
      '        <span class="badge" :class="kb.is_public ? \'pub\' : \'\'">{{ kb.is_public ? "公开" : "私有" }}</span>',
      '        <button class="kb-more" data-testid="kb-more" :class="{ on: s.kbMenuId === kb.id }" @click="toggleMenu(kb.id, $event)"><mj-ico name="menu" :size="13" /></button>',
      '        <div v-if="s.kbMenuId === kb.id" class="kb-menu" data-testid="kb-menu" @click.stop>',
      '          <div class="kb-menu-item" data-testid="kb-menu-docs" @click="openDocs(kb)">管理文档</div>',
      '          <div class="kb-menu-item" data-testid="kb-menu-edit" @click="editKb(kb)">重命名 / 描述</div>',
      '          <div class="kb-menu-item danger" data-testid="kb-menu-delete" @click="removeKb(kb)">删除知识库</div>',
      '        </div>',
      '      </div>',
      '      <div v-if="s.kbsLoading && !s.kbs.length" class="loading-line" style="justify-content:center"><span class="spinner"></span></div>',
      '      <div v-else-if="!s.kbs.length" class="empty-inline" style="padding:20px 8px;font-size:12px">还没有知识库<br />点上方 + 新建</div>',
      '    </div>',
      '  </div>',

      '  <div class="sidebar-foot">',
      '    <div class="brand-card">',
      '      <div class="t1">多智能体 × RAG</div>',
      '      <div class="t2">基于 LangGraph 的知识库系统</div>',
      '    </div>',
      '  </div>',
      '</aside>',
    ].join(""),
  };

  /* ---------------- 知识库表单 ---------------- */
  var KbForm = {
    setup: function () {
      var ui = MJ.uiState;
      var saving = Vue.ref(false);
      var error = Vue.ref("");

      var form = Vue.computed(function () { return ui.kbForm; });

      function close() {
        if (saving.value) return;
        ui.kbForm = null;
        error.value = "";
      }

      async function submit() {
        var f = ui.kbForm;
        if (!f || saving.value) return;
        var name = String(f.name || "").trim();
        if (!name) { error.value = "请填写知识库名称"; return; }
        if (name.length > 128) { error.value = "名称不能超过 128 个字符"; return; }
        saving.value = true;
        error.value = "";
        try {
          if (f.mode === "create") {
            await MJ.actions.createKb({ name: name, description: String(f.description || "").trim() });
          } else {
            await MJ.actions.updateKb(f.id, {
              name: name,
              description: String(f.description || "").trim(),
              is_public: !!f.is_public,
            });
            MJ.toast("知识库已更新", "ok");
          }
          ui.kbForm = null;
        } catch (e) {
          error.value = e.message || "保存失败";
        } finally {
          saving.value = false;
        }
      }

      return { ui: ui, form: form, saving: saving, error: error, close: close, submit: submit };
    },
    template: [
      '<div v-if="form" class="overlay" @click.self="close">',
      '  <div class="dialog" role="dialog" aria-modal="true" data-testid="kb-form">',
      '    <div class="dialog-head">',
      '      <h3>{{ form.mode === "create" ? "新建知识库" : "知识库设置" }}</h3>',
      '      <button class="icon-btn" @click="close"><mj-ico name="close" :size="16" /></button>',
      '    </div>',
      '    <div class="dialog-body">',
      '      <div class="field">',
      '        <label>名称</label>',
      '        <input v-model="form.name" data-testid="kb-form-name" maxlength="128" placeholder="例如：操作系统笔记" @keyup.enter="submit" />',
      '      </div>',
      '      <div class="field">',
      '        <label>描述（可选）</label>',
      '        <textarea v-model="form.description" data-testid="kb-form-desc" maxlength="255" placeholder="这个库讲什么？公开库检索会用它做语义匹配"></textarea>',
      '        <p class="hint-inline">描述越具体，其他用户通过公开库提问时越容易被检索到。</p>',
      '      </div>',
      '      <div v-if="form.mode === \'edit\'" class="field">',
      '        <label>可见性</label>',
      '        <div class="checkline">',
      '          <div class="switch" data-testid="kb-form-public" :class="{ on: form.is_public }" @click="form.is_public = !form.is_public"></div>',
      '          <span>{{ form.is_public ? "公开：其他账号可检索该库内容" : "私有：仅自己可访问" }}</span>',
      '        </div>',
      '      </div>',
      '      <p v-if="error" data-testid="kb-form-error" style="color:var(--danger);font-size:12.5px;margin-top:6px">{{ error }}</p>',
      '    </div>',
      '    <div class="dialog-foot">',
      '      <button class="btn btn-line" @click="close">取消</button>',
      '      <button class="btn btn-primary" data-testid="kb-form-submit" :disabled="saving" @click="submit">',
      '        <span v-if="saving" class="spinner"></span>',
      '        <span>{{ saving ? "保存中…" : (form.mode === "create" ? "创建" : "保存") }}</span>',
      '      </button>',
      '    </div>',
      '  </div>',
      '</div>',
    ].join(""),
  };

  /* ---------------- 根组件 ---------------- */
  var Root = {
    setup: function () {
      var s = MJ.store;

      function closeUserMenu() { s.userMenuOpen = false; }

      Vue.onMounted(function () {
        document.addEventListener("click", closeUserMenu);
        MJ.actions.boot();
      });
      Vue.onUnmounted(function () { document.removeEventListener("click", closeUserMenu); });

      return { s: s };
    },
    template: [
      '<div class="app">',
      '  <template v-if="s.token">',
      '    <mj-topbar></mj-topbar>',
      '    <div class="app-body">',
      '      <mj-sidebar :class="{ open: s.drawerOpen }"></mj-sidebar>',
      '      <div v-if="s.drawerOpen" class="drawer-mask" @click="s.drawerOpen = false"></div>',
      '      <main class="main">',
      '        <mj-chat v-if="s.view === \'chat\'"></mj-chat>',
      '        <mj-kbs v-else-if="s.view === \'kbs\'"></mj-kbs>',
      '        <mj-docs v-else></mj-docs>',
      '      </main>',
      '      <mj-panel v-if="s.view === \'chat\'"></mj-panel>',
      '    </div>',
      '  </template>',
      '  <mj-auth v-else></mj-auth>',
      '  <mj-kb-form></mj-kb-form>',
      '  <mj-toasts></mj-toasts>',
      '  <mj-confirm></mj-confirm>',
      '</div>',
    ].join(""),
  };

  /* ---------------- 对外入口 ---------------- */
  MJ.openKbForm = function (mode, kb) {
    MJ.uiState.kbForm = {
      mode: mode || "create",
      id: kb ? kb.id : null,
      name: kb ? kb.name : "",
      description: kb ? kb.description || "" : "",
      is_public: kb ? !!kb.is_public : false,
    };
  };

  /* ---------------- 挂载 ---------------- */
  var app = Vue.createApp(Root);

  Object.keys(MJ.components || {}).forEach(function (name) {
    app.component(name, MJ.components[name]);
  });
  app.component("mj-topbar", Topbar);
  app.component("mj-sidebar", Sidebar);
  app.component("mj-kb-form", KbForm);
  app.component("mj-auth", MJ.views.auth);
  app.component("mj-chat", MJ.views.chat);
  app.component("mj-panel", MJ.views.panel);
  app.component("mj-kbs", MJ.views.kbs);
  app.component("mj-docs", MJ.views.docs);

  app.config.errorHandler = function (err) {
    console.error("[MyJevis]", err);
  };

  app.mount("#app");
})(window.MJ);
