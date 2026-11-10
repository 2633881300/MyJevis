/* MyJevis UI 基础件
 * - mj-ico：内联 SVG 图标（不依赖图标库）
 * - toast / confirm：替换原生 alert、confirm、prompt
 * - formatText：先转义再套用极简格式，避免 XSS
 */
window.MJ = window.MJ || {};

(function (MJ) {
  "use strict";

  /* ---------- 图标 ---------- */
  var ICONS = {
    chat: ["M20.5 11.6a8.2 8.2 0 0 1-8.3 8.2 8.8 8.8 0 0 1-3.2-.6L4.5 20.5l1.5-4.2a8.1 8.1 0 0 1-.8-3.6A8.2 8.2 0 0 1 12.5 3.4a8.2 8.2 0 0 1 8 8.2Z"],
    folder: ["M3.2 8A1.8 1.8 0 0 1 5 6.2h4l1.9 2h8.1A1.8 1.8 0 0 1 20.8 10v7.2a1.8 1.8 0 0 1-1.8 1.8H5a1.8 1.8 0 0 1-1.8-1.8Z"],
    file: ["M13.4 3.2H7a1.8 1.8 0 0 0-1.8 1.8v14a1.8 1.8 0 0 0 1.8 1.8h10a1.8 1.8 0 0 0 1.8-1.8V8.5Z", "M13.4 3.2v5.3h5.4"],
    plus: ["M12 5.6v12.8M5.6 12h12.8"],
    upload: ["M12 16.4V4.6M7.6 9 12 4.6 16.4 9", "M4.6 19.4h14.8"],
    settings: ["M12 15.1a3.1 3.1 0 1 0 0-6.2 3.1 3.1 0 0 0 0 6.2Z", "M18.6 14.2a1.4 1.4 0 0 0 .3 1.6 1.7 1.7 0 1 1-2.4 2.4 1.4 1.4 0 0 0-1.6-.3 1.4 1.4 0 0 0-.9 1.3v.2a1.7 1.7 0 1 1-3.4 0v-.1a1.4 1.4 0 0 0-.9-1.3 1.4 1.4 0 0 0-1.6.3 1.7 1.7 0 1 1-2.4-2.4 1.4 1.4 0 0 0 .3-1.6 1.4 1.4 0 0 0-1.3-.9H4.5a1.7 1.7 0 1 1 0-3.4h.1a1.4 1.4 0 0 0 1.3-.9 1.4 1.4 0 0 0-.3-1.6 1.7 1.7 0 1 1 2.4-2.4 1.4 1.4 0 0 0 1.6.3h.1a1.4 1.4 0 0 0 .9-1.3V4.5a1.7 1.7 0 1 1 3.4 0v.1a1.4 1.4 0 0 0 .9 1.3 1.4 1.4 0 0 0 1.6-.3 1.7 1.7 0 1 1 2.4 2.4 1.4 1.4 0 0 0-.3 1.6v.1a1.4 1.4 0 0 0 1.3.9h.2a1.7 1.7 0 1 1 0 3.4h-.1a1.4 1.4 0 0 0-1.3.9Z"],
    trash: ["M4.6 7.2h14.8M9.5 4.6h5", "M6.6 7.2l.9 12.1a1.5 1.5 0 0 0 1.5 1.4h6.1a1.5 1.5 0 0 0 1.5-1.4l.9-12.1", "M10.2 11v5.6M13.8 11v5.6"],
    copy: ["M9.4 9.4h9.1v10H9.4z", "M5.5 15.2h-.4a1 1 0 0 1-1-1V4.9a1 1 0 0 1 1-1h9.3a1 1 0 0 1 1 1v.5"],
    send: ["M5 12h13.4", "M12.6 5.2 19.2 12l-6.6 6.8"],
    chevron: ["M6.2 9.6 12 15.4l5.8-5.8"],
    check: ["M5 12.6 9.5 17.2 19 7.4"],
    close: ["M6.6 6.6 17.4 17.4M17.4 6.6 6.6 17.4"],
    info: ["M12 20.6a8.6 8.6 0 1 0 0-17.2 8.6 8.6 0 0 0 0 17.2Z", "M12 11.2v5.2M12 7.8v.1"],
    alert: ["M10.4 3.9 2.7 17.1a1.8 1.8 0 0 0 1.6 2.7h15.4a1.8 1.8 0 0 0 1.6-2.7L13.6 3.9a1.8 1.8 0 0 0-3.2 0Z", "M12 9v4.2M12 16.4v.1"],
    spark: ["M12 3.4l1.8 5.3 5.3 1.8-5.3 1.8L12 17.6l-1.8-5.3-5.3-1.8 5.3-1.8Z"],
    user: ["M12 12.1a3.9 3.9 0 1 0 0-7.8 3.9 3.9 0 0 0 0 7.8Z", "M4.6 20.4a7.4 7.4 0 0 1 14.8 0"],
    lock: ["M7.6 10.4V8a4.4 4.4 0 0 1 8.8 0v2.4", "M5.9 10.4h12.2a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H5.9a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1Z"],
    globe: ["M12 20.6a8.6 8.6 0 1 0 0-17.2 8.6 8.6 0 0 0 0 17.2Z", "M3.6 12h16.8", "M12 3.4c2.2 2.4 3.4 5.4 3.4 8.6S14.2 18.2 12 20.6c-2.2-2.4-3.4-5.4-3.4-8.6S9.8 5.8 12 3.4Z"],
    menu: ["M4 7.2h16M4 12h16M4 16.8h16"],
    code: ["M9 8.4 4.6 12 9 15.6M15 8.4 19.4 12 15 15.6"],
    clock: ["M12 20.6a8.6 8.6 0 1 0 0-17.2 8.6 8.6 0 0 0 0 17.2Z", "M12 7.4V12l3.1 1.9"],
    tool: ["M14.6 6.6a3.6 3.6 0 0 1 4.8 4.8l-9.2 9.2-4.4.8.8-4.4Z"],
    spark2: ["M4.5 19.5v-4M4.5 15.5V12M19.5 4.5v4M19.5 15.5v4", "M2.5 17.5h4M17.5 6.5h4"],
  };

  MJ.icons = ICONS;

  /* ---------- 文本安全格式化 ---------- */
  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  /* 行内格式：粗体与代码。输入必须是已转义文本。 */
  function inlineFmt(text) {
    return text
      .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`\n]+)`/g, "<code>$1</code>");
  }

  function splitRow(line) {
    return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(function (c) { return c.trim(); });
  }

  /* 先整体转义，再按行处理：Markdown 表格转成真表，标题转粗体，其余保留换行。
   * 转义在最前面，内容里不可能残留可执行标签，因此 v-html 使用是安全的。 */
  function formatText(str) {
    var safe = escapeHtml(str == null ? "" : str);
    var lines = safe.split("\n");
    var out = [];
    var i = 0;

    var isRow = function (l) { return /^\s*\|.*\|\s*$/.test(l); };
    var isSep = function (l) { return /^\s*\|[\s:|-]+\|\s*$/.test(l) && l.indexOf("-") >= 0; };

    while (i < lines.length) {
      if (isRow(lines[i]) && i + 1 < lines.length && isSep(lines[i + 1])) {
        var head = splitRow(lines[i]);
        var body = [];
        i += 2;
        while (i < lines.length && isRow(lines[i])) { body.push(splitRow(lines[i])); i++; }

        var html = '<table class="md-table"><thead><tr>';
        head.forEach(function (c) { html += "<th>" + inlineFmt(c) + "</th>"; });
        html += "</tr></thead><tbody>";
        body.forEach(function (row) {
          html += "<tr>";
          for (var k = 0; k < head.length; k++) html += "<td>" + inlineFmt(row[k] || "") + "</td>";
          html += "</tr>";
        });
        html += "</tbody></table>";
        out.push(html);
        continue;
      }

      var line = lines[i].replace(/^#{1,6}[ \t]+(.+)$/, "<strong>$1</strong>");
      out.push(inlineFmt(line));
      i++;
    }
    return out.join("\n");
  }

  /* ---------- 时间与文件名 ---------- */
  function pad2(n) { return n < 10 ? "0" + n : String(n); }

  /* 后端统一用 datetime.utcnow() 存时间，返回的是无时区的 UTC 字符串。
   * 这里补上 Z 再转本地时区，避免把 UTC 当成当地时间显示。
   * 客户端消息直接传时间戳（number），走同一条路径。 */
  function toLocalDate(value) {
    if (value == null || value === "") return null;
    if (typeof value === "number") return new Date(value);
    var s = String(value).trim();
    if (!s) return null;
    if (/[zZ]$/.test(s) || /[+-]\d{2}:?\d{2}$/.test(s)) {
      var d1 = new Date(s);
      return isNaN(d1.getTime()) ? null : d1;
    }
    var d2 = new Date(s.replace(" ", "T") + "Z");
    return isNaN(d2.getTime()) ? null : d2;
  }

  function fmtDateTime(value) {
    var d = toLocalDate(value);
    if (!d) return "";
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate()) +
      " " + pad2(d.getHours()) + ":" + pad2(d.getMinutes());
  }

  function fmtClock(value) {
    var d = toLocalDate(value);
    if (!d) return "";
    return pad2(d.getHours()) + ":" + pad2(d.getMinutes());
  }
  function fileExt(name) {
    var i = String(name || "").lastIndexOf(".");
    return i >= 0 ? String(name).slice(i + 1).toLowerCase() : "file";
  }
  function truncate(str, max) {
    var s = String(str == null ? "" : str).replace(/\s+/g, " ").trim();
    return s.length > max ? s.slice(0, max) + "…" : s;
  }

  /* ---------- 交互状态 ---------- */
  var uiState = Vue.reactive({
    toasts: [],
    confirm: null,   /* { title, message, okText, danger, resolve } */
    kbForm: null,    /* { mode, kb, name, description, is_public } */
  });

  var seq = 0;

  function toast(message, type) {
    var id = ++seq;
    uiState.toasts.push({ id: id, message: String(message || ""), type: type || "info" });
    setTimeout(function () {
      var idx = uiState.toasts.findIndex(function (t) { return t.id === id; });
      if (idx >= 0) uiState.toasts.splice(idx, 1);
    }, 3600);
  }

  function confirmDialog(options) {
    options = options || {};
    return new Promise(function (resolve) {
      uiState.confirm = {
        title: options.title || "确认操作",
        message: options.message || "确定要执行这个操作吗？",
        okText: options.okText || "确定",
        cancelText: options.cancelText || "取消",
        danger: !!options.danger,
        resolve: resolve,
      };
    });
  }

  function closeConfirm(result) {
    var cur = uiState.confirm;
    uiState.confirm = null;
    if (cur && cur.resolve) cur.resolve(!!result);
  }

  async function copyText(text) {
    var content = String(text || "");
    if (!content) return false;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(content);
        return true;
      }
    } catch (e) { /* 退化到下面的方案 */ }

    try {
      var ta = document.createElement("textarea");
      ta.value = content;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      var ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch (e) {
      return false;
    }
  }

  /* ---------- 组件 ---------- */
  var Ico = {
    props: { name: { type: String, required: true }, size: { type: [Number, String], default: 16 } },
    computed: {
      paths: function () { return ICONS[this.name] || ICONS.info; },
      px: function () { return typeof this.size === "number" ? this.size + "px" : this.size; },
    },
    template:
      '<svg :width="px" :height="px" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path v-for="(d, i) in paths" :key="i" :d="d" /></svg>',
  };

  var Toasts = {
    setup: function () {
      return { ui: uiState, formatText: formatText };
    },
    template:
      '<div class="toasts" data-testid="toasts">' +
      '<div v-for="t in ui.toasts" :key="t.id" class="toast" :class="t.type" data-testid="toast" :data-type="t.type">' +
      '<mj-ico :name="t.type === \'err\' ? \'alert\' : (t.type === \'ok\' ? \'check\' : \'info\')" :size="14" />' +
      '<span>{{ t.message }}</span>' +
      "</div></div>",
  };

  var Confirm = {
    setup: function () {
      return { ui: uiState, close: closeConfirm };
    },
    template:
      '<div v-if="ui.confirm" class="overlay" @click.self="close(false)">' +
      '<div class="dialog" role="dialog" aria-modal="true" data-testid="confirm">' +
      '<div class="dialog-head">' +
      '<h3 data-testid="confirm-title">{{ ui.confirm.title }}</h3>' +
      '<button class="icon-btn" @click="close(false)"><mj-ico name="close" :size="16" /></button>' +
      "</div>" +
      '<div class="dialog-body" style="white-space:pre-wrap" data-testid="confirm-message">{{ ui.confirm.message }}</div>' +
      '<div class="dialog-foot">' +
      '<button class="btn btn-line" data-testid="confirm-cancel" @click="close(false)">{{ ui.confirm.cancelText }}</button>' +
      '<button class="btn" data-testid="confirm-ok" :class="ui.confirm.danger ? \'btn-danger-line\' : \'btn-primary\'" @click="close(true)">{{ ui.confirm.okText }}</button>' +
      "</div></div></div>",
  };

  MJ.uiState = uiState;
  MJ.toast = toast;
  MJ.confirm = confirmDialog;
  MJ.closeConfirm = closeConfirm;
  MJ.copyText = copyText;
  MJ.formatText = formatText;
  MJ.escapeHtml = escapeHtml;
  MJ.fmtDateTime = fmtDateTime;
  MJ.fmtClock = fmtClock;
  MJ.fileExt = fileExt;
  MJ.truncate = truncate;
  MJ.components = { "mj-ico": Ico, "mj-toasts": Toasts, "mj-confirm": Confirm };
})(window.MJ);
