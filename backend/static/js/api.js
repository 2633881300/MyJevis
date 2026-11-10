/* MyJevis API 层
 * 统一处理：Authorization 头、JSON 序列化、错误信息提取、SSE 流式解析、超时取消。
 * 不改动任何后端接口路径与请求协议。
 */
window.MJ = window.MJ || {};

(function (MJ) {
  "use strict";

  var TOKEN_KEY = "mj_token";
  var USER_KEY = "mj_user";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY) || "";
  }
  function setToken(token, username) {
    localStorage.setItem(TOKEN_KEY, token || "");
    localStorage.setItem(USER_KEY, username || "");
  }
  function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }
  function getUsername() {
    return localStorage.getItem(USER_KEY) || "";
  }

  /* 把后端的 detail 统一转成可读文本，避免把原始异常抛给用户 */
  function pickMessage(data, status) {
    if (data && typeof data.detail === "string" && data.detail) return data.detail;
    if (data && Array.isArray(data.detail) && data.detail.length) {
      var first = data.detail[0];
      if (first && typeof first.msg === "string") return first.msg;
    }
    if (status === 401) return "登录已过期，请重新登录";
    if (status === 403) return "没有权限执行该操作";
    if (status === 404) return "资源不存在";
    if (status >= 500) return "服务暂时不可用，请稍后重试";
    return "请求失败（HTTP " + status + "）";
  }

  async function request(path, options) {
    options = options || {};
    var headers = Object.assign({ "Content-Type": "application/json" }, options.headers || {});
    var token = getToken();
    if (token) headers["Authorization"] = "Bearer " + token;

    var body = options.body;
    if (body !== undefined && body !== null && typeof body !== "string" && !(body instanceof FormData)) {
      body = JSON.stringify(body);
    }
    if (body instanceof FormData) delete headers["Content-Type"];

    var resp;
    try {
      resp = await fetch(path, {
        method: options.method || "GET",
        headers: headers,
        body: body,
        signal: options.signal,
      });
    } catch (e) {
      if (e && e.name === "AbortError") {
        var abortErr = new Error(options.timeoutMessage || "请求超时，请稍后重试");
        abortErr.aborted = true;
        throw abortErr;
      }
      throw new Error("网络异常，请检查后端服务是否在运行");
    }

    var text = await resp.text();
    var data = null;
    if (text) {
      try { data = JSON.parse(text); } catch (e) { data = null; }
    }

    if (!resp.ok) {
      var err = new Error(pickMessage(data, resp.status));
      err.status = resp.status;
      if (resp.status === 401 && token) {
        clearToken();
        /* 交给调用方决定是否跳回登录页 */
        err.unauthorized = true;
      }
      throw err;
    }
    return data;
  }

  /* 带超时的请求：AbortController 在超时后中断，避免界面一直等待 */
  function withTimeout(fn, ms) {
    var ctrl = new AbortController();
    var timer = setTimeout(function () { ctrl.abort(); }, ms);
    return fn(ctrl.signal).finally(function () { clearTimeout(timer); });
  }

  /* ---------- 认证 ---------- */
  function login(username, password) {
    return request("/auth/login", { method: "POST", body: { username: username, password: password } });
  }
  function register(username, password) {
    return request("/auth/register", { method: "POST", body: { username: username, password: password } });
  }

  /* ---------- 知识库 ---------- */
  function listKbs() {
    return request("/knowledge-bases");
  }
  function createKb(payload) {
    return request("/knowledge-bases", { method: "POST", body: payload });
  }
  function updateKb(kbId, patch) {
    return request("/knowledge-bases/" + kbId, { method: "PATCH", body: patch });
  }
  function deleteKb(kbId) {
    return request("/knowledge-bases/" + kbId, { method: "DELETE" });
  }
  function listPublicKbs() {
    return request("/knowledge-bases/public");
  }

  /* ---------- 文档 ---------- */
  function listDocs(kbId) {
    return request("/documents/list?knowledge_base_id=" + encodeURIComponent(kbId));
  }
  function deleteDoc(docId) {
    return request("/documents/" + docId, { method: "DELETE" });
  }
  function uploadDoc(kbId, file) {
    var fd = new FormData();
    fd.append("knowledge_base_id", kbId);
    fd.append("file", file);
    return request("/documents/upload", { method: "POST", body: fd });
  }

  /* ---------- 问答 ---------- */
  /* 详细模式：同步接口，返回 answer + 真实的 intermediate_steps */
  function chatSync(question, timeoutMs) {
    return withTimeout(function (signal) {
      return request("/chat", { method: "POST", body: { question: question }, signal: signal });
    }, timeoutMs || 180000);
  }

  /* 普通模式：SSE 流式，逐段回调 */
  async function chatStream(question, handlers) {
    handlers = handlers || {};
    var headers = { "Content-Type": "application/json" };
    var token = getToken();
    if (token) headers["Authorization"] = "Bearer " + token;

    var resp;
    try {
      resp = await fetch("/chat/stream", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({ question: question }),
      });
    } catch (e) {
      throw new Error("网络异常，请检查后端服务是否在运行");
    }

    if (!resp.ok || !resp.body) {
      throw new Error(pickMessage(null, resp.status));
    }

    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buf = "";

    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buf += decoder.decode(chunk.value, { stream: true });
      var parts = buf.split("\n\n");
      buf = parts.pop();
      for (var i = 0; i < parts.length; i++) {
        var line = parts[i].trim();
        if (!line || line.indexOf("data:") !== 0) continue;
        var payload;
        try {
          payload = JSON.parse(line.slice(5).trim());
        } catch (e) {
          continue;
        }
        if (payload.type === "token") {
          if (handlers.onDelta) handlers.onDelta(payload.data);
        } else if (payload.type === "error") {
          if (handlers.onError) handlers.onError(payload.data);
        } else if (payload.type === "done") {
          if (handlers.onDone) handlers.onDone();
        }
      }
    }
    if (handlers.onDone) handlers.onDone();
  }

  MJ.api = {
    getToken: getToken,
    setToken: setToken,
    clearToken: clearToken,
    getUsername: getUsername,
    request: request,
    login: login,
    register: register,
    listKbs: listKbs,
    createKb: createKb,
    updateKb: updateKb,
    deleteKb: deleteKb,
    listPublicKbs: listPublicKbs,
    listDocs: listDocs,
    deleteDoc: deleteDoc,
    uploadDoc: uploadDoc,
    chatSync: chatSync,
    chatStream: chatStream,
  };
})(window.MJ);
