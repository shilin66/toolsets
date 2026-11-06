/* Mail Listen 管理台 · Vue 3 + Naive UI 共享层
 * 提供全局状态（API Key / 摘要统计 / 状态栏）、请求封装与状态文案映射。
 * 依赖加载顺序：vue.global.prod.js → naive-ui.js → admin-naive.js → 本文件 → admin-i18n.js
 * 文案映射函数运行时调用 tt()（定义于 admin-i18n.js），因此可随语言切换响应式更新。
 */
const NocMessage = NocUI.message;
const NocDialog = NocUI.dialog;

const portalDefaultEnvironment = (
  document.body.dataset.rpaDefaultEnvironment === "production"
    ? "production"
    : "test"
);

const appStore = Vue.reactive({
  apiKey: "", // Compatibility flag for mounted views; never contains a credential.
  user: null,
  csrfToken: "",
  authVersion: 0,
  authLoading: true,
  portalStatus: null,
  mailboxGrants: [],
  portalEnvironment: localStorage.getItem("mailListenPortalEnvironment") || portalDefaultEnvironment,
  menuCollapsed: localStorage.getItem("mailListenMenuCollapsed") === "1",
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
    "X-CSRF-Token": appStore.csrfToken,
    "Content-Type": "application/json",
  };
}

// Credentials stay in the HttpOnly session cookie. Memory caches follow identity.
function setPrincipal(user) {
  appStore.authVersion += 1;
  appStore.user = user;
  appStore.csrfToken = user?.csrf_token || "";
  appStore.apiKey = user ? "session" : "";
  appStore.portalStatus = null;
  appStore.mailboxGrants = [];
  mailAccountOptionsCache = null;
  mailAccountOptionsPromise = null;
  appStore.operationsSummaryLoaded = false;
  Object.assign(appStore.operationsSummary, {pending_tasks: 0, failed_tasks: 0, today_emails: 0, last_email_at: null});
  localStorage.removeItem("mailListenApiKey");
}

function logout() {
  setPrincipal(null);
  setStatusKey("common.statusLoading");
}

async function endSession() {
  await requestFull('/api/auth/logout', {method: 'POST'});
  logout();
  localStorage.setItem('mailListenAuthChanged', String(Date.now()));
}

async function loginSession(credentials) {
  const response = await fetch('/api/auth/login', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(credentials)});
  const payload = await response.json();
  if (!response.ok || !payload.success) {
    const error = new Error(payload.message || '登录失败');
    error.status = response.status;
    throw error;
  }
  setPrincipal(payload.data);
  localStorage.setItem('mailListenAuthChanged', String(Date.now()));
}

async function restoreSession() {
  try {
    const response = await fetch('/api/auth/session');
    const user = response.ok ? (await response.json()).data : null;
    if (user) setPrincipal(user);
    else {
      const legacyKey = localStorage.getItem('mailListenApiKey');
      if (legacyKey) await loginSession({mode: 'admin', api_key: legacyKey});
    }
  } catch (_) { logout(); }
  finally { appStore.authLoading = false; }
}

window.addEventListener('storage', (event) => {
  if (event.key === 'mailListenAuthChanged') window.location.reload();
});

let portalStatusRequest = 0;
let portalStatusInFlight = null;
function getPortalSessionStatus(environment) {
  const authVersion = appStore.authVersion;
  if (portalStatusInFlight?.environment === environment && portalStatusInFlight.authVersion === authVersion) {
    return portalStatusInFlight.promise;
  }
  const check = { environment, authVersion };
  const query = environment ? `?environment=${encodeURIComponent(environment)}` : '';
  check.promise = requestJson(`/api/rpa/session${query}`).finally(() => {
    if (portalStatusInFlight === check) portalStatusInFlight = null;
  });
  portalStatusInFlight = check;
  return check.promise;
}

async function refreshPortalStatus() {
  if (!appStore.user || appStore.user.is_admin) return;
  const environment = appStore.portalEnvironment;
  const authVersion = appStore.authVersion;
  const requestId = ++portalStatusRequest;
  const isCurrent = () => requestId === portalStatusRequest
    && authVersion === appStore.authVersion && environment === appStore.portalEnvironment;
  try {
    const status = await getPortalSessionStatus(environment);
    if (isCurrent()) appStore.portalStatus = status;
  } catch (error) {
    if (isCurrent()) appStore.portalStatus = {
      authenticated: false, state: error.code === 'RPA_BUSY' ? 'busy' : 'unavailable',
      portal_username: appStore.portalStatus?.portal_username, message: error.message};
  }
}

function portalSessionPresentation(status) {
  const account = status?.portal_username || '';
  let label;
  if (!status) label = '未检查';
  else if (status.reporting) label = '执行中';
  else if (status.state === 'busy') label = '账号忙碌';
  else if (status.authenticated) label = '已登录';
  else if (status.configured === false) label = '未配置';
  else if (status.state === 'login_required') label = account ? '登录失效' : '未登录';
  else label = '检查失败';
  return {account, label};
}

function canOperateMailbox(address) {
  return Boolean(appStore.user?.is_admin || appStore.mailboxGrants.some(
    grant => grant.email_address.toLowerCase() === String(address || '').trim().toLowerCase() && grant.can_operate));
}

function persistPortalEnvironment(environment) {
  appStore.portalStatus = null;
  appStore.portalEnvironment = environment;
  localStorage.setItem("mailListenPortalEnvironment", environment);
}

// 侧边栏收起偏好：仅存浏览器 localStorage，不影响后端配置
function persistMenuCollapsed(collapsed) {
  appStore.menuCollapsed = collapsed;
  localStorage.setItem("mailListenMenuCollapsed", collapsed ? "1" : "0");
}

async function checkApiKey(key) {
  await loginSession({mode: 'admin', api_key: key});
}

async function requestJson(path, options = {}) {
  const version = appStore.authVersion;
  if (!appStore.apiKey) {
    throw new Error(tt("common.apiKeyRequired"));
  }
  const headers = apiHeaders();
  if (options.body instanceof FormData) delete headers['Content-Type'];
  const response = await fetch(path, {
    ...options,
    headers,
  });
  const payload = await response.json();
  if (version !== appStore.authVersion) throw new Error('登录用户已变更，请刷新');
  if (response.status === 401) {
    // 登录态失效（如后端更换 API Key）：清除凭据回到登录页
    logout();
    throw new Error(tt("login.keyExpired"));
  }
  if (!response.ok || payload.success === false) {
    const error = new Error(payload.message || tt("common.requestFailed"));
    error.status = response.status;
    error.code = payload.code || "";
    error.data = payload.data || null;
    throw error;
  }
  return payload.data;
}

async function requestBlobUrl(path) {
  const version = appStore.authVersion;
  if (!appStore.apiKey) {
    throw new Error(tt("common.apiKeyRequired"));
  }
  const response = await fetch(path, { headers: apiHeaders() });
  if (version !== appStore.authVersion) throw new Error('登录用户已变更，请刷新');
  if (response.status === 401) {
    logout();
    throw new Error(tt("login.keyExpired"));
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.message || tt("common.requestFailed"));
  }
  return URL.createObjectURL(await response.blob());
}

async function requestFull(path, options = {}) {
  const version = appStore.authVersion;
  if (!appStore.apiKey) {
    throw new Error(tt("common.apiKeyRequired"));
  }
  const response = await fetch(path, {
    ...options,
    headers: apiHeaders(),
  });
  const payload = await response.json();
  if (version !== appStore.authVersion) throw new Error('登录用户已变更，请刷新');
  if (response.status === 401) {
    logout();
    throw new Error(tt("login.keyExpired"));
  }
  if (!response.ok || payload.success === false) {
    const error = new Error(payload.message || tt("common.requestFailed"));
    error.status = response.status;
    error.code = payload.code || "";
    error.data = payload.data || null;
    throw error;
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
const CUTOVER_STATUS_KEYS = ["draft", "confirmed", "reporting", "reported", "report_failed", "completed"];

const CUTOVER_STATUS_TAG = {
  draft: "warning",
  confirmed: "primary",
  reporting: "info",
  reported: "success",
  completed: "success",
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
    return Array.isArray(fill.backbone_circuits)
      ? fill.backbone_circuits.length
      : (task.line_count || 0);
  }
  return Array.isArray(fill.circuits)
    ? fill.circuits.length
    : (task.line_count || 0);
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
      const accounts = await requestJson("/api/me/mailboxes");
      appStore.mailboxGrants = accounts || [];
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

function cutoverEmailTags(row) {
  const tags = [];
  const scene = row.unconfigured_analysis?.scene || row.pending_reply_scene || row.cutover_scene;
  if (row.processing_origin === 'unconfigured') {
    tags.push({key:'unconfigured', label:tt('discovery.title'), type:'info'});
    if (row.unconfigured_analysis?.analysis_status === 'needs_review') {
      tags.push({key:'needs_review', label:tt('discovery.needs_review'), type:'warning'});
    }
  }
  if (isRejectedScene(scene)) {
    tags.push({ key: scene, label: sceneText(scene), type: sceneTagType(scene) });
  }
  if (row.is_duplicate) {
    tags.push({ key: 'duplicate', label: tt('cutover.tag.duplicate'), type: 'info' });
  }
  if (row.mail_type) {
    tags.push({ key: 'mail_type', label: row.mail_type, type: 'primary' });
  }
  return tags;
}

function cutoverEmailStates(row) {
  if (row.manual_completion) return [{key: "completed", label: tt("cutover.status.completed"), type: "success"}];
  const states = [];
  if (row.processing_origin === 'unconfigured') {
    const jobs = row.ai_tasks || [];
    const state = jobs.some(job => job.status === 'failed') ? 'failed'
      : jobs.some(job => ['pending','running'].includes(job.status)) ? 'running'
      : row.unconfigured_analysis?.analysis_status === 'needs_review' ? 'needs_review'
      : row.unconfigured_analysis ? 'succeeded' : null;
    if (state) states.push({key:state,label:tt('discovery.'+state),type:state === 'failed' ? 'danger' : 'info'});
    if (row.reply_status === 'pending') states.push({key:'reply_pending',label:tt('cutover.list.replyPending'),type:'warning'});
    else if (row.reply_status) states.push({key:row.reply_status,label:tt('discovery.'+row.reply_status),type:'info'});
    return states;
  }
  if (row.reply_status === 'pending') {
    states.push({ key: 'reply_pending', label: tt('cutover.list.replyPending'), type: 'warning' });
  }
  const counts = new Map();
  for (const task of row.tasks || []) {
    counts.set(task.status, (counts.get(task.status) || 0) + 1);
  }
  const priority = ['report_failed', 'reporting', 'draft', 'confirmed', 'reported'];
  for (const status of [...counts.keys()].sort((a, b) => priority.indexOf(a) - priority.indexOf(b))) {
    states.push({ key: status, label: statusText(status), type: statusTagType(status), count: counts.get(status) });
  }
  if (!states.length) {
    const key = row.is_duplicate ? 'duplicate_ignored'
      : row.cutover_scene === 'rule_skipped' ? 'rule_skipped'
      : isRejectedScene(row.cutover_scene) && row.reply_status === 'sent' ? 'rejected_closed'
      : 'no_task';
    states.push({ key, label: tt(`cutover.list.emailStatus.${key}`), type: 'info' });
  }
  return states;
}
