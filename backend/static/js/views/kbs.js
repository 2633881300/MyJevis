/* 知识库管理视图：卡片网格
 * 统计数字来自 /documents/list 聚合（并发 3），失败只标注「统计失败」，不影响卡片本身。
 */
window.MJ = window.MJ || {};
MJ.views = MJ.views || {};

MJ.views.kbs = {
  setup: function () {
    var s = MJ.store;

    function statsOf(id) { return MJ.actions.kbStats(id); }

    function openChat(kb) {
      MJ.actions.selectKb(kb);
      MJ.actions.setView("chat");
    }

    function openDocs(kb) {
      MJ.actions.selectKb(kb);
      MJ.actions.setView("docs");
    }

    function createNew() {
      if (MJ.openKbForm) MJ.openKbForm("create", null);
    }

    function edit(kb) {
      if (MJ.openKbForm) MJ.openKbForm("edit", kb);
    }

    async function remove(kb) {
      var ok = await MJ.confirm({
        title: "删除知识库",
        message: "确定删除「" + kb.name + "」吗？\n\n该库下的所有文档与向量数据会一并清除，操作不可恢复。",
        okText: "删除",
        danger: true,
      });
      if (ok) await MJ.actions.deleteKb(kb);
    }

    async function togglePub(kb) {
      await MJ.actions.togglePublic(kb);
    }

    return {
      s: s, statsOf: statsOf, openChat: openChat, openDocs: openDocs,
      createNew: createNew, edit: edit, remove: remove, togglePub: togglePub,
      refresh: function () { MJ.actions.loadStats(null, true); },
    };
  },
  template: [
    '<div class="page">',
    '  <div class="page-head">',
    '    <div>',
    '      <div class="page-title">知识库管理</div>',
    '      <div class="page-sub">共 {{ s.kbs.length }} 个知识库，公开后其他账号可检索其中内容</div>',
    '    </div>',
    '    <div class="grow"></div>',
    '    <button class="btn btn-line" @click="refresh"><mj-ico name="clock" :size="15" />刷新统计</button>',
    '    <button class="btn btn-primary" @click="createNew"><mj-ico name="plus" :size="15" />新建知识库</button>',
    '  </div>',
    '  <div class="page-scroll">',
    '    <div v-if="s.kbsLoading && !s.kbs.length" class="loading-line"><span class="spinner"></span>正在加载知识库…</div>',
    '    <div v-else-if="s.kbsError" class="empty-inline">{{ s.kbsError }}</div>',
    '    <div v-else-if="!s.kbs.length" class="table-card">',
    '      <div class="empty-inline">',
    '        还没有知识库。<br />点右上角「新建知识库」开始，上传文档后即可问答。',
    '      </div>',
    '    </div>',
    '    <div v-else class="kb-grid">',
    '      <div v-for="kb in s.kbs" :key="kb.id" class="kb-card" data-testid="kb-card" :data-kb-id="kb.id" @click="openChat(kb)">',
    '        <div class="kb-card-top">',
    '          <div class="kb-card-ico"><mj-ico name="folder" :size="18" /></div>',
    '          <div class="kb-card-name">{{ kb.name }}</div>',
    '          <span class="badge" :class="kb.is_public ? \'pub\' : \'\'">{{ kb.is_public ? "公开" : "私有" }}</span>',
    '        </div>',
    '        <div class="kb-card-desc" :class="{ empty: !kb.description }">',
    '          {{ kb.description || "暂无描述（公开库检索会用到描述，建议补充）" }}',
    '        </div>',
    '        <div class="kb-stats" data-testid="kb-stats">',
    '          <template v-if="statsOf(kb.id).loading">',
    '            <span class="muted"><span class="spinner" style="display:inline-block;vertical-align:-2px"></span> 统计中…</span>',
    '          </template>',
    '          <template v-else-if="statsOf(kb.id).docs !== null">',
    '            <span><b>{{ statsOf(kb.id).docs }}</b> 个文档</span>',
    '            <span><b>{{ statsOf(kb.id).chunks }}</b> 个文本块</span>',
    '          </template>',
    '          <span v-else class="muted">{{ statsOf(kb.id).error || "统计未完成" }}</span>',
    '        </div>',
    '        <div class="kb-card-foot" @click.stop>',
    '          <button class="btn btn-ghost" style="padding:5px 8px;font-size:12.5px" @click="openDocs(kb)"><mj-ico name="file" :size="14" />文档</button>',
    '          <button class="btn btn-ghost" style="padding:5px 8px;font-size:12.5px" @click="edit(kb)"><mj-ico name="settings" :size="14" />设置</button>',
    '          <button class="btn btn-ghost" style="padding:5px 8px;font-size:12.5px" @click="togglePub(kb)">',
    '            <mj-ico :name="kb.is_public ? \'lock\' : \'globe\'" :size="14" />{{ kb.is_public ? "转私有" : "转公开" }}',
    '          </button>',
    '          <div class="grow"></div>',
    '          <button class="icon-btn" title="删除知识库" data-testid="kb-card-delete" @click="remove(kb)"><mj-ico name="trash" :size="15" /></button>',
    '        </div>',
    '      </div>',
    '      <div class="kb-card kb-card-new" data-testid="kb-new-card" @click="createNew">',
    '        <div class="kb-new-ico"><mj-ico name="plus" :size="20" /></div>',
    '        <div class="kb-new-text">新建知识库</div>',
    '      </div>',
    '    </div>',
    '  </div>',
    '</div>',
  ].join(""),
};
