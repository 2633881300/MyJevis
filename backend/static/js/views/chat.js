/* 聊天视图 + 右侧 Agent 信息面板
 * 普通模式：/chat/stream 逐段输出，无执行轨迹
 * 详细模式：/chat 同步返回，展示真实的顶层工具调用
 */
window.MJ = window.MJ || {};
MJ.views = MJ.views || {};

(function (MJ) {
  "use strict";

  var TOOL_LABELS = {
    search_public_knowledge: "公开库检索",
    list_knowledge_bases: "列出知识库",
    list_documents: "列出文档",
    get_user_profile: "读取用户画像",
    update_user_profile: "更新用户画像",
    search_knowledge: "知识库检索",
  };

  function toolLabel(name) {
    if (!name) return "工具调用";
    if (name.indexOf("ask_kb_") === 0) return "知识库子 Agent";
    return TOOL_LABELS[name] || name;
  }

  function toolTarget(name, args) {
    /* 只有子 Agent 需要标出「问的是哪个库」，其余工具的参数已经在 argSummary 里 */
    if (name && name.indexOf("ask_kb_") === 0) {
      return "知识库 ID " + name.replace("ask_kb_", "");
    }
    return "";
  }

  function argSummary(args) {
    if (!args || typeof args !== "object") return "";
    var parts = [];
    Object.keys(args).forEach(function (key) {
      parts.push(key + ": " + MJ.truncate(args[key], 90));
    });
    return parts.join(" · ");
  }

  /* 子 Agent 的 result 就是最终答案本身，重复展示既冗余又等于把内容再贴一遍 */
  function showsResult(tool) {
    return !(tool && String(tool).indexOf("ask_kb_") === 0);
  }

  /* ---------------- 聊天视图 ---------------- */
  MJ.views.chat = {
    setup: function () {
      var s = MJ.store;
      var question = Vue.ref("");
      var kbMenuOpen = Vue.ref(false);
      var fileRef = Vue.ref(null);
      var scrollRef = Vue.ref(null);
      var uploading = Vue.ref(false);

      var activeKb = Vue.computed(function () { return MJ.actions.activeKb(); });
      var stats = Vue.computed(function () {
        return s.activeKbId ? MJ.actions.kbStats(s.activeKbId) : { docs: null, chunks: null, loading: false, error: "" };
      });
      var isEmpty = Vue.computed(function () {
        return s.messages.length <= 1;
      });

      var samples = [
        "这个知识库里主要讲了什么？",
        "帮我总结一下核心要点",
        "我上传过哪些文档？",
      ];

      function scrollToBottom() {
        Vue.nextTick(function () {
          var el = scrollRef.value;
          if (el) el.scrollTop = el.scrollHeight;
        });
      }

      Vue.watch(
        function () {
          return s.messages.length + "|" + s.messages.map(function (m) { return (m.content || "").length; }).join(",");
        },
        scrollToBottom
      );

      function pickKb(kb) {
        MJ.actions.selectKb(kb);
        kbMenuOpen.value = false;
      }

      function openSettings() {
        if (!activeKb.value) return MJ.toast("请先选择一个知识库", "err");
        if (MJ.openKbForm) MJ.openKbForm("edit", activeKb.value);
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

      function submit() {
        var text = question.value.trim();
        if (!text) return;
        question.value = "";
        MJ.actions.send(text);
      }

      function useSample(text) {
        question.value = text;
      }

      async function copyAnswer(msg) {
        var ok = await MJ.copyText(msg.content);
        MJ.toast(ok ? "已复制回答" : "复制失败，请手动选择", ok ? "ok" : "err");
      }

      function onDocClick() { kbMenuOpen.value = false; }
      Vue.onMounted(function () {
        document.addEventListener("click", onDocClick);
        scrollToBottom();
      });
      Vue.onUnmounted(function () { document.removeEventListener("click", onDocClick); });

      return {
        s: s, question: question, kbMenuOpen: kbMenuOpen, fileRef: fileRef,
        scrollRef: scrollRef, uploading: uploading, activeKb: activeKb,
        stats: stats, isEmpty: isEmpty, samples: samples,
        pickKb: pickKb, openSettings: openSettings, pickFile: pickFile,
        onFileChange: onFileChange, submit: submit, useSample: useSample,
        copyAnswer: copyAnswer, formatText: MJ.formatText, fmtClock: MJ.fmtClock,
        fmtDateTime: MJ.fmtDateTime,
      };
    },
    template: [
      '<section class="workspace" data-testid="chat">',
      '  <header class="ws-head">',
      '    <div class="kb-switch" data-testid="kb-switch" @click.stop="kbMenuOpen = !kbMenuOpen" style="position:relative">',
      '      <span class="ws-title">{{ activeKb ? activeKb.name : "未选择知识库" }}</span>',
      '      <span v-if="activeKb" class="badge" :class="activeKb.is_public ? \'pub\' : \'\'">{{ activeKb.is_public ? "公开" : "私有" }}</span>',
      '      <mj-ico class="chev" name="chevron" :size="14" />',
      '      <div v-if="kbMenuOpen" class="menu" style="left:0;right:auto;top:36px;min-width:220px" @click.stop>',
      '        <div v-for="kb in s.kbs" :key="kb.id" class="menu-item" @click="pickKb(kb)">',
      '          <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ kb.name }}</span>',
      '          <span class="badge" :class="kb.is_public ? \'pub\' : \'\'">{{ kb.is_public ? "公开" : "私有" }}</span>',
      '        </div>',
      '        <div v-if="!s.kbs.length" class="empty-inline" style="padding:14px">还没有知识库</div>',
      '      </div>',
      '    </div>',
      '    <div class="grow"></div>',
      '    <button class="btn btn-ghost" :disabled="!activeKb" @click="openSettings">',
      '      <mj-ico name="settings" :size="15" /><span>知识库设置</span>',
      '    </button>',
      '    <input ref="fileRef" type="file" accept=".txt,.md,.markdown,.docx,.pdf" style="display:none" @change="onFileChange" />',
      '    <button class="btn btn-primary" :disabled="!s.activeKbId || uploading" @click="pickFile">',
      '      <mj-ico :name="uploading ? \'clock\' : \'upload\'" :size="15" />',
      '      <span>{{ uploading ? "入库中…" : "上传文档" }}</span>',
      '    </button>',
      '  </header>',

      '  <div v-if="!s.kbs.length" class="chat-empty">',
      '    <div class="chat-empty-card">',
      '      <div class="chat-empty-mark"><mj-ico name="folder" :size="24" /></div>',
      '      <h3>还没有知识库</h3>',
      '      <p>先在左侧创建一个知识库并上传文档，再回来提问。</p>',
      '    </div>',
      '  </div>',

      '  <div v-else class="chat-scroll" ref="scrollRef">',
      '    <div class="chat-inner">',
      '      <div v-for="m in s.messages" :key="m.id" class="msg" data-testid="msg" :data-role="m.role" :class="m.role">',
      '        <div v-if="m.role === \'assistant\'" class="avatar lg">M</div>',
      '        <div v-else class="avatar lg gray">{{ (s.username || "我").slice(0, 1).toUpperCase() }}</div>',
      '        <div class="msg-col">',
      '          <div v-if="m.role === \'assistant\'" class="msg-meta">',
      '            <span class="name">MyJevis</span>',
      '            <span>{{ fmtClock(m.time) }}</span>',
      '            <span v-if="m.detail" class="badge brand">详细模式</span>',
      '          </div>',
      '          <div v-if="m.role === \'user\'" class="bubble-user">{{ m.content }}</div>',
      '          <template v-else>',
      '            <span v-if="m.pending && !m.content" class="typing" data-testid="typing"><i></i><i></i><i></i></span>',
      '            <div v-else class="msg-text" data-testid="msg-text" v-html="formatText(m.content)"></div>',
      '            <p v-if="m.error" style="color:var(--danger);font-size:12.5px;margin-top:6px">{{ m.error }}</p>',
      '            <div v-if="!m.pending && m.content" class="msg-actions">',
      '              <button class="msg-act" @click="copyAnswer(m)"><mj-ico name="copy" :size="13" />复制</button>',
      '              <span v-if="m.steps && m.steps.length" class="msg-act" style="cursor:default">',
      '                <mj-ico name="tool" :size="13" />{{ m.steps.length }} 次工具调用',
      '              </span>',
      '            </div>',
      '          </template>',
      '        </div>',
      '      </div>',

      '      <div v-if="isEmpty" class="chat-samples" style="justify-content:flex-start;margin-top:4px">',
      '        <button v-for="t in samples" :key="t" class="sample-chip" @click="useSample(t)">{{ t }}</button>',
      '      </div>',
      '    </div>',
      '  </div>',

      '  <div class="composer">',
      '    <div class="composer-box">',
      '      <div class="composer-row">',
      '        <button class="icon-btn" title="上传文档" :disabled="!s.activeKbId" @click="pickFile"><mj-ico name="plus" :size="17" /></button>',
      '        <textarea v-model="question" data-testid="chat-input" rows="1" :disabled="!s.activeKbId"',
      '          :placeholder="s.activeKbId ? \'向 MyJevis 提问，基于所选知识库获取回答…\' : \'请先在左侧选择一个知识库\'"',
      '          @keydown.enter.exact.prevent="submit"></textarea>',
      '      </div>',
      '      <div class="composer-foot">',
      '        <span class="composer-hint">Shift + Enter 换行，Enter 发送</span>',
      '        <button class="send-btn" data-testid="chat-send" :disabled="s.sending || !question.trim() || !s.activeKbId" @click="submit">',
      '          <mj-ico name="send" :size="16" />',
      '        </button>',
      '      </div>',
      '    </div>',
      '  </div>',
      '</section>',
    ].join(""),
  };

  /* ---------------- 右侧面板 ---------------- */
  MJ.views.panel = {
    setup: function () {
      var s = MJ.store;
      var activeKb = Vue.computed(function () { return MJ.actions.activeKb(); });
      var stats = Vue.computed(function () {
        return s.activeKbId ? MJ.actions.kbStats(s.activeKbId) : { docs: null, chunks: null, loading: false, error: "" };
      });
      var lastSteps = Vue.computed(function () {
        var m = MJ.actions.lastAssistantWithSteps();
        return m ? m.steps : [];
      });
      var rounds = Vue.computed(function () {
        return s.messages.filter(function (m) { return m.role === "user"; }).length;
      });

      function setTab(tab) { s.panelTab = tab; }
      function toggleDetail() { MJ.actions.setDetailMode(!s.detailMode); }

      return {
        s: s, activeKb: activeKb, stats: stats, lastSteps: lastSteps, rounds: rounds,
        setTab: setTab, toggleDetail: toggleDetail,
        toolLabel: toolLabel, toolTarget: toolTarget, argSummary: argSummary,
        showsResult: showsResult,
        truncate: MJ.truncate, formatText: MJ.formatText,
      };
    },
    template: [
      '<aside class="panel" data-testid="panel" :class="{ \'as-drawer\': s.panelOpen }">',
      '  <div class="panel-head">',
      '    <div class="panel-title-row">',
      '      <span class="panel-title">Agent 信息</span>',
      '      <button class="icon-btn mobile-only" @click="s.panelOpen = false"><mj-ico name="close" :size="15" /></button>',
      '    </div>',
      '    <div class="tabs">',
      '      <button class="tab" data-testid="panel-tab-trace" :class="{ on: s.panelTab === \'trace\' }" @click="setTab(\'trace\')">执行过程</button>',
      '      <button class="tab" data-testid="panel-tab-tools" :class="{ on: s.panelTab === \'tools\' }" @click="setTab(\'tools\')">工具调用</button>',
      '    </div>',
      '  </div>',

      '  <div class="panel-body">',
      '    <div class="panel-note" :style="s.detailMode ? \'border-color:#E6E2FB;background:#F7F5FF\' : \'\'">',
      '      <template v-if="s.detailMode">详细模式已开启：走同步接口，可返回真实工具调用，但作答不再逐字出现。</template>',
      '      <template v-else>普通模式：流式作答，仅返回最终答案，不含工具调用轨迹。</template>',
      '    </div>',

      '    <div v-if="s.panelTab === \'trace\'">',
      '      <div v-if="lastSteps.length" class="steps">',
      '        <div v-for="(st, i) in lastSteps" :key="i" class="step" data-testid="step">',
      '          <div class="step-rail">',
      '            <div class="step-dot">{{ i + 1 }}</div>',
      '            <div v-if="i < lastSteps.length - 1" class="step-line"></div>',
      '          </div>',
      '          <div class="step-body">',
      '            <div class="step-name">{{ toolLabel(st.tool) }}</div>',
      '            <div class="step-sub">{{ toolTarget(st.tool, st.args) }}<span v-if="toolTarget(st.tool, st.args)"> · </span>{{ argSummary(st.args) }}</div>',
      '            <div v-if="st.result && showsResult(st.tool)" class="step-result">{{ truncate(st.result, 180) }}</div>',
      '          </div>',
      '        </div>',
      '      </div>',
      '      <div v-else-if="s.detailMode" class="empty-state">',
      '        <div class="empty-ico"><mj-ico name="tool" :size="18" /></div>',
      '        <h4>本次会话暂无工具调用</h4>',
      '        <p>详细模式已开启，提问后这里会显示真实的工具名、参数与结果摘要。</p>',
      '      </div>',
      '      <div v-else class="empty-state">',
      '        <div class="empty-ico"><mj-ico name="clock" :size="18" /></div>',
      '        <h4>执行轨迹暂未开放</h4>',
      '        <p>流式接口只推送最终答案的 token，不包含工具调用事件。<br />打开下方「详细模式」可查看真实轨迹。</p>',
      '      </div>',
      '      <p v-if="lastSteps.length" class="hint-inline" style="margin-top:10px">',
      '        仅显示顶层工具调用；子 Agent 内部的检索步骤不对外返回，因此不会出现在这里。',
      '      </p>',
      '    </div>',

      '    <div v-else>',
      '      <div v-if="lastSteps.length" class="steps">',
      '        <div v-for="(st, i) in lastSteps" :key="i" style="padding:8px 0;border-bottom:1px solid var(--border)">',
      '          <div style="font-family:var(--mono);font-size:12px;color:var(--brand-700)">{{ st.tool }}</div>',
      '          <div class="step-sub">{{ argSummary(st.args) }}</div>',
      '        </div>',
      '      </div>',
      '      <div v-else class="empty-state">',
      '        <div class="empty-ico"><mj-ico name="code" :size="18" /></div>',
      '        <h4>暂无调用记录</h4>',
      '        <p>详细模式下提问后，这里按原始工具名列出调用参数。</p>',
      '      </div>',
      '    </div>',

      '    <div class="info-card" style="margin-top:16px">',
      '      <div class="info-card-title"><mj-ico name="info" :size="14" />当前会话信息</div>',
      '      <div class="info-row"><span class="k">知识库</span><span class="v">{{ activeKb ? activeKb.name : "未选择" }}</span></div>',
      '      <div class="info-row"><span class="k">可见性</span><span class="v">{{ activeKb ? (activeKb.is_public ? "公开" : "私有") : "-" }}</span></div>',
      '      <div class="info-row">',
      '        <span class="k">文档 / 文本块</span>',
      '        <span class="v">',
      '          <template v-if="stats.loading"><span class="spinner" style="display:inline-block;vertical-align:-2px"></span></template>',
      '          <template v-else-if="stats.docs !== null">{{ stats.docs }} 篇 / {{ stats.chunks }} 块</template>',
      '          <span v-else class="muted">{{ stats.error || "未统计" }}</span>',
      '        </span>',
      '      </div>',
      '      <div class="info-row"><span class="k">本轮提问</span><span class="v">{{ rounds }} 次</span></div>',
      '      <div class="info-row"><span class="k">回答模式</span><span class="v">{{ s.detailMode ? "详细（非流式）" : "普通（流式）" }}</span></div>',
      '      <div class="switch-row" data-testid="detail-row">',
      '        <span class="label">详细模式</span>',
      '        <div class="switch" data-testid="detail-switch" :class="{ on: s.detailMode }" @click="toggleDetail"></div>',
      '      </div>',
      '      <p class="hint-inline">开启后请求同步接口，可拿到真实工具调用，但答案不会逐字出现。</p>',
      '    </div>',
      '  </div>',
      '</aside>',
    ].join(""),
  };
})(window.MJ);
