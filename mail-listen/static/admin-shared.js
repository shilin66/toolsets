/* Mail Listen 管理台 · Vue 3 + Element Plus 共享层
 * 提供全局状态（API Key / 摘要统计 / 状态栏）、请求封装与状态文案映射。
 * 依赖加载顺序：vue.global.prod.js → element-plus.js → 本文件 → admin-i18n.js
 * 文案映射函数运行时调用 tt()（定义于 admin-i18n.js），因此可随语言切换响应式更新。
 */
const { ElMessage, ElMessageBox } = ElementPlus;

const appStore = Vue.reactive({
  apiKey: localStorage.getItem("mailListenApiKey") || "",
  statusText: "",
  statusTone: "ok",
  supplierCount: 0,
  emailCount: 0,
  ticketCount: 0,
  operationsSummary: {
    pending_tasks: 0,
    failed_tasks: 0,
    today_emails: 0,
    last_email_at: null,
  },
  operationsSummaryLoaded: false,
  operationsSummaryLoading: false,
  operationsSummaryError: "",
});

// 状态栏：文案 key 以 i18n: 前缀存储，渲染时动态翻译，语言切换后自动更新；后端原文直接存储展示
const STATUS_I18N_PREFIX = "i18n:";

function setStatus(message, tone = "ok") {
  appStore.statusText = message;
  appStore.statusTone = tone;
}

function setStatusKey(key, tone = "ok") {
  appStore.statusText = STATUS_I18N_PREFIX + key;
  appStore.statusTone = tone;
}

function renderStatusText(text) {
  if (typeof text === "string" && text.startsWith(STATUS_I18N_PREFIX)) {
    return tt(text.slice(STATUS_I18N_PREFIX.length));
  }
  return text;
}

function apiHeaders() {
  return {
    Authorization: `Bearer ${appStore.apiKey}`,
    "Content-Type": "application/json",
  };
}

// ---------- 登录态：密码即 API Key，仅存于浏览器 localStorage ----------
function persistApiKey(key) {
  appStore.apiKey = key;
  localStorage.setItem("mailListenApiKey", key);
}

function logout() {
  appStore.apiKey = "";
  localStorage.removeItem("mailListenApiKey");
  appStore.operationsSummaryLoaded = false;
  setStatusKey("common.statusLoading");
}

async function checkApiKey(key) {
  const response = await fetch("/api/auth/check", {
    headers: { Authorization: `Bearer ${key}` },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.success === false) {
    throw new Error(response.status === 401 ? tt("login.keyInvalid") : (payload.message || tt("common.requestFailed")));
  }
}

async function requestJson(path, options = {}) {
  if (!appStore.apiKey) {
    throw new Error(tt("common.apiKeyRequired"));
  }
  const response = await fetch(path, {
    ...options,
    headers: apiHeaders(),
  });
  const payload = await response.json();
  if (response.status === 401) {
    // 登录态失效（如后端更换 API Key）：清除凭据回到登录页
    logout();
    throw new Error(tt("login.keyExpired"));
  }
  if (!response.ok || payload.success === false) {
    throw new Error(payload.message || tt("common.requestFailed"));
  }
  return payload.data;
}

async function requestFull(path, options = {}) {
  if (!appStore.apiKey) {
    throw new Error(tt("common.apiKeyRequired"));
  }
  const response = await fetch(path, {
    ...options,
    headers: apiHeaders(),
  });
  const payload = await response.json();
  if (response.status === 401) {
    logout();
    throw new Error(tt("login.keyExpired"));
  }
  if (!response.ok || payload.success === false) {
    throw new Error(payload.message || tt("common.requestFailed"));
  }
  return payload;
}

async function loadOperationsSummary() {
  if (!appStore.apiKey) {
    appStore.operationsSummaryLoaded = false;
    return;
  }

  appStore.operationsSummaryLoading = true;
  appStore.operationsSummaryError = "";
  try {
    const data = await requestJson("/api/dashboard/summary");
    Object.assign(appStore.operationsSummary, data);
    appStore.operationsSummaryLoaded = true;
  } catch (error) {
    appStore.operationsSummaryLoaded = false;
    appStore.operationsSummaryError = error.message;
  } finally {
    appStore.operationsSummaryLoading = false;
  }
}

function shortText(value, size = 120) {
  const text = String(value || "");
  if (text.length <= size) {
    return text;
  }
  return `${text.slice(0, size)}...`;
}

// ---------- 割接任务状态/类型文案（运行时按当前语言取值） ----------
const CUTOVER_STATUS_KEYS = ["draft", "confirmed", "reporting", "reported", "report_failed"];

const CUTOVER_STATUS_TAG = {
  draft: "warning",
  confirmed: "primary",
  reporting: "info",
  reported: "success",
  report_failed: "danger",
};

function statusTagType(status) {
  return CUTOVER_STATUS_TAG[status] || "info";
}

function statusText(status, label) {
  const key = `cutover.status.${status}`;
  if (label) {
    return label;
  }
  return status && hasI18nKey(key) ? tt(key) : (status || tt("common.unset"));
}

function lineTypeText(task) {
  const key = `cutover.lineType.${task.line_type}`;
  return task.line_type_label
    || (task.line_type && hasI18nKey(key) ? tt(key) : task.line_type)
    || "-";
}

// ---------- 割接场景（正常/紧急/重保期/窗口内/命中特殊规则） ----------
// 除 normal 外均为不生成上报任务的场景：
// emergency/major_event/in_window 为 FastGPT 已回复拒绝割接，rule_skipped 为命中供应商特殊规则
const CUTOVER_SCENE_TAG = {
  emergency: "danger",
  major_event: "warning",
  in_window: "primary",
  rule_skipped: "info",
};

function sceneText(scene, label) {
  const key = `cutover.scene.${scene}`;
  return label || (scene && hasI18nKey(key) ? tt(key) : scene) || "";
}

function sceneTagType(scene) {
  return CUTOVER_SCENE_TAG[scene] || "info";
}

function isRejectedScene(scene) {
  return Boolean(scene) && scene !== "normal";
}

// 邮件标签：场景标签 + 重复邮件（is_duplicate 由后端查询时计算），文案运行时按当前语言取值
const CUTOVER_TAG_KEYS = ["emergency", "major_event", "in_window", "rule_skipped", "duplicate"];

function taskLineCount(task) {
  const fill = task.fill_result || {};
  if (task.line_type === "backbone") {
    return (fill.backbone_circuits || []).length;
  }
  return (fill.circuits || []).length;
}

// ==================== 邮箱账号选项（多邮箱展示共享） ====================
// 缓存邮箱账号列表，供各页面筛选下拉与“接收邮箱”列显示使用；
// 邮箱配置页保存/删除后调 loadMailAccountOptions(true) 强制刷新。
let mailAccountOptionsCache = null;
let mailAccountOptionsPromise = null;

async function loadMailAccountOptions(force = false) {
  if (mailAccountOptionsCache && !force) {
    return mailAccountOptionsCache;
  }
  if (mailAccountOptionsPromise && !force) {
    return mailAccountOptionsPromise;
  }
  mailAccountOptionsPromise = (async () => {
    try {
      const accounts = await requestJson("/api/system/mail-accounts");
      mailAccountOptionsCache = (accounts || []).map((account) => ({
        value: account.email_address,
        label: account.name ? `${account.name}（${account.email_address}）` : account.email_address,
        name: account.name || "",
        address: account.email_address,
      }));
    } catch (error) {
      mailAccountOptionsCache = mailAccountOptionsCache || [];
    } finally {
      mailAccountOptionsPromise = null;
    }
    return mailAccountOptionsCache;
  })();
  return mailAccountOptionsPromise;
}

function mailboxLabel(address) {
  if (!address) {
    return "-";
  }
  const target = String(address).toLowerCase();
  const hit = (mailAccountOptionsCache || []).find(
    (option) => option.address.toLowerCase() === target
  );
  return hit && hit.name ? `${hit.name}（${hit.address}）` : address;
}
