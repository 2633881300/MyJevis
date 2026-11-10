/* 文档管理视图：表格
 * 后端 DocumentResponse 只有 id / filename / chunk_count / created_at，
 * 因此表格不显示「文件大小」列，避免编造字段。
 */
window.MJ = window.MJ || {};
MJ.views = MJ.views || {};

MJ.views.docs = {
  setup: function () {
    var s = MJ.store;
    var fileRef = Vue.ref(null);
    var uploading = Vue.ref(false);

    var activeKb = Vue.computed(function () { return MJ.actions.activeKb(); });
    var docsState = Vue.computed(function () {
      return s.activeKbId ? MJ.actions.kbDocs(s.activeKbId) : { loading: false, error: "", items: [] };
    });
    var totalChunks = Vue.computed(function () {
      return docsState.value.items.reduce(function (sum, d) { return sum + (d.chunk_count || 0); }, 0);
    });

    function onKbChange(e) {
      var id = Number(e.target.value);
      var kb = s.kbs.find(function (k) { return k.id === id; });
      if (kb) MJ.actions.selectKb(kb);
    }

    function refresh() {
      if (s.activeKbId) MJ.actions.loadDocs(s.activeKbId, true);
    }

    function pickFile() {
      if (!s.activeKbId) return MJ.toast("请先选择一个知识库", "err");
      fileRef.value.click();
    }

    async function onFileChange(e) {
      var file = e.target.files && e.target.files[0];
      e.target.value = "";
      if (!file) return;
      uploading.value = true;
      try {
        var data = await MJ.actions.uploadDoc(s.activeKbId, file);
        MJ.toast("已入库：" + data.filename + "（" + data.chunk_count + " 个文本块）", "ok");
      } catch (err) {
        MJ.toast(err.message || "上传失败", "err");
      } finally {
        uploading.value = false;
      }
    }

    async function remove(doc) {
      var ok = await MJ.confirm({
        title: "删除文档",
        message: "确定删除「" + doc.filename + "」吗？\n\n删除后该文档内容将无法被检索，操作不可恢复。",
        okText: "删除",
        danger: true,
      });
      if (ok) await MJ.actions.deleteDoc(s.activeKbId, doc);
    }

    Vue.onMounted(function () {
      if (s.activeKbId) MJ.actions.loadDocs(s.activeKbId);
    });

    return {
      s: s, fileRef: fileRef, uploading: uploading, activeKb: activeKb,
      docsState: docsState, totalChunks: totalChunks,
      onKbChange: onKbChange, refresh: refresh, pickFile: pickFile,
      onFileChange: onFileChange, remove: remove,
      fileExt: MJ.fileExt, fmtDateTime: MJ.fmtDateTime,
      fmtExtLabel: function (name) {
        var ext = MJ.fileExt(name);
        return ext.length > 5 ? ext.slice(0, 5) : ext;
      },
    };
  },
  template: [
    '<div class="page">',
    '  <div class="page-head">',
    '    <div>',
    '      <div class="page-title">文档管理</div>',
    '      <div class="page-sub">',
    '        <template v-if="activeKb">「{{ activeKb.name }}」· {{ docsState.items.length }} 个文档 · {{ totalChunks }} 个文本块</template>',
    '        <template v-else>请选择一个知识库</template>',
    '      </div>',
    '    </div>',
    '    <div class="grow"></div>',
    '    <select class="select" data-testid="kb-select" :value="s.activeKbId || \'\'" @change="onKbChange">',
    '      <option v-for="kb in s.kbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>',
    '    </select>',
    '    <button class="btn btn-line" :disabled="!s.activeKbId" @click="refresh"><mj-ico name="clock" :size="15" />刷新</button>',
    '    <input ref="fileRef" type="file" accept=".txt,.md,.markdown,.docx,.pdf" style="display:none" @change="onFileChange" />',
    '    <button class="btn btn-primary" data-testid="docs-upload" :disabled="!s.activeKbId || uploading" @click="pickFile">',
    '      <mj-ico name="upload" :size="15" /><span>{{ uploading ? "入库中…" : "上传文档" }}</span>',
    '    </button>',
    '  </div>',

    '  <div class="page-scroll">',
    '    <div v-if="!s.activeKbId" class="table-card"><div class="empty-inline">请先在左上角选择一个知识库</div></div>',
    '    <div v-else class="table-card">',
    '      <div v-if="docsState.loading && !docsState.items.length" class="loading-line" style="padding:24px"><span class="spinner"></span>正在加载文档…</div>',
    '      <div v-else-if="docsState.error" class="empty-inline">{{ docsState.error }}</div>',
    '      <div v-else-if="!docsState.items.length" class="empty-inline">',
    '        这个知识库还没有文档。<br />点右上角「上传文档」，支持 txt / md / docx / 文本型 pdf。',
    '      </div>',
    '      <div v-else class="table-scroll">',
    '        <table class="tbl" data-testid="docs-table">',
    '          <thead><tr>',
    '            <th style="width:44%">文件名</th>',
    '            <th style="width:12%">格式</th>',
    '            <th style="width:14%">文本块</th>',
    '            <th style="width:20%">上传时间</th>',
    '            <th style="width:10%;text-align:right">操作</th>',
    '          </tr></thead>',
    '          <tbody>',
    '            <tr v-for="d in docsState.items" :key="d.id" data-testid="doc-row" :data-doc-id="d.id">',
    '              <td>',
    '                <div class="cell-file">',
    '                  <span class="file-ico" :class="fileExt(d.filename)">{{ fmtExtLabel(d.filename) }}</span>',
    '                  <span class="file-name" :title="d.filename">{{ d.filename }}</span>',
    '                </div>',
    '              </td>',
    '              <td><span class="badge">{{ fileExt(d.filename) }}</span></td>',
    '              <td class="mono-sm">{{ d.chunk_count }}</td>',
    '              <td class="mono-sm">{{ fmtDateTime(d.created_at) }}</td>',
    '              <td>',
    '                <div class="row-actions">',
    '                  <button class="icon-btn" title="删除文档" data-testid="doc-delete" @click="remove(d)"><mj-ico name="trash" :size="15" /></button>',
    '                </div>',
    '              </td>',
    '            </tr>',
    '          </tbody>',
    '        </table>',
    '      </div>',
    '    </div>',
    '    <p class="hint-inline" style="margin-top:10px">',
    '      删除文档会同时清理向量数据；若清理失败，接口会报错并保留数据库记录，可重试。',
    '    </p>',
    '  </div>',
    '</div>',
  ].join(""),
};
