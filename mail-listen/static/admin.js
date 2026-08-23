/* Mail Listen 管理台 · Vue 3 + Element Plus 入口
 * 轻量路由（history API，语义与旧版 parseRoute 一致）+ 根组件外壳。
 * 依赖加载顺序：vendor → admin-shared.js → admin-views.js → 本文件
 */

// ==================== 轻量路由 ====================
const VIEW_ROUTES = {
  suppliers: "/admin/suppliers",
  emails: "/admin/emails",
  cutoverTasks: "/admin/cutover-tasks",
  circuits: "/admin/circuits",
  mailAccounts: "/admin/mail-accounts",
  settings: "/admin/settings",
};

const CUTOVER_EMAIL_DETAIL_ROUTE = /^\/admin\/cutover-emails\/(\d+)$/;
const SUPPLIER_FORM_CREATE_ROUTE = "/admin/suppliers/new";
const SUPPLIER_FORM_EDIT_ROUTE = /^\/admin\/suppliers\/(\d+)$/;

const routeState = Vue.reactive({
  view: "suppliers",
  emailRecordId: null,
  supplierId: null,
  query: "",
});

function parseRoute() {
  const path = window.location.pathname.replace(/\/+$/, "");
  if (path === SUPPLIER_FORM_CREATE_ROUTE) {
    return { view: "supplierForm", supplierId: null };
  }
  const supplierMatch = path.match(SUPPLIER_FORM_EDIT_ROUTE);
  if (supplierMatch) {
    return { view: "supplierForm", supplierId: Number(supplierMatch[1]) };
  }
  const detailMatch = path.match(CUTOVER_EMAIL_DETAIL_ROUTE);
  if (detailMatch) {
    return { view: "cutoverEmailDetail", emailRecordId: Number(detailMatch[1]) };
  }
  const view = Object.keys(VIEW_ROUTES).find((item) => VIEW_ROUTES[item] === path) || "suppliers";
  return { view };
}

function applyRoute(route) {
  routeState.view = route.view;
  routeState.emailRecordId = route.view === "cutoverEmailDetail" ? route.emailRecordId : null;
  routeState.supplierId = route.view === "supplierForm" ? route.supplierId : null;
  routeState.query = window.location.search;
}

function navigateTo(view) {
  const route = VIEW_ROUTES[view];
  if (window.location.pathname !== route || window.location.search) {
    history.pushState({ view }, "", route);
  }
  applyRoute(parseRoute());
}

function navigateToSummary(view, params = {}) {
  const route = VIEW_ROUTES[view];
  const query = new URLSearchParams(params).toString();
  const target = query ? `${route}?${query}` : route;
  if (`${window.location.pathname}${window.location.search}` !== target) {
    history.pushState({ view }, "", target);
  }
  applyRoute(parseRoute());
}

function openCutoverEmailDetail(emailRecordId) {
  const route = `/admin/cutover-emails/${emailRecordId}`;
  if (window.location.pathname !== route) {
    history.pushState({ view: "cutoverEmailDetail", emailRecordId }, "", route);
  }
  applyRoute(parseRoute());
}

function openSupplierForm(supplierId = null) {
  const route = supplierId == null ? SUPPLIER_FORM_CREATE_ROUTE : `/admin/suppliers/${supplierId}`;
  if (window.location.pathname !== route) {
    history.pushState({ view: "supplierForm", supplierId }, "", route);
  }
  applyRoute(parseRoute());
}

function initRouting() {
  const route = parseRoute();
  const canonical = VIEW_ROUTES[route.view];
  if (canonical && window.location.pathname !== canonical) {
    history.replaceState({ view: route.view }, "", canonical);
  }
  applyRoute(route);
}

window.addEventListener("popstate", () => applyRoute(parseRoute()));

// ==================== 根组件 ====================
const FULLSCREEN_VIEWS = ["cutoverEmailDetail", "supplierForm"];

const AdminApp = defineComponent({
  name: "AdminApp",
  setup() {
    const viewKey = ref(0);

    const VIEW_COMPONENTS = {
      suppliers: ViewSuppliers,
      emails: ViewEmails,
      cutoverTasks: ViewCutoverTasks,
      circuits: ViewCircuits,
      mailAccounts: ViewMailAccounts,
      settings: ViewSettings,
    };

    // 登录守卫：未登录（无 API Key）时只渲染登录页，登录成功后主壳与各视图重新挂载并自动拉取数据
    const loggedIn = computed(() => Boolean(appStore.apiKey));
    const isDetail = computed(() => FULLSCREEN_VIEWS.includes(routeState.view));
    const currentComponent = computed(() => VIEW_COMPONENTS[routeState.view]);
    // 状态栏文案：i18n key 标记随语言切换动态翻译
    const statusDisplay = computed(() => renderStatusText(appStore.statusText));
    const activeMenu = computed(() => (isDetail.value ? (routeState.view === "supplierForm" ? "suppliers" : "cutoverTasks") : routeState.view));
    const viewTitle = computed(() => {
      if (routeState.view === "supplierForm") {
        return routeState.supplierId == null ? tt("nav.supplierCreate") : tt("nav.supplierEdit");
      }
      return tt(`nav.${routeState.view}`);
    });

    async function handleLogout() {
      logout();
      viewKey.value += 1;
    }

    function summaryValue(value) {
      return appStore.operationsSummaryLoaded ? value : "—";
    }

    function latestEmailTime(value) {
      if (!appStore.operationsSummaryLoaded) {
        return "—";
      }
      if (!value) {
        return tt("operations.noEmail");
      }
      return String(value).slice(11, 16);
    }

    function latestEmailDate(value) {
      return value ? String(value).slice(0, 10) : tt("operations.latestHint");
    }

    watch(
      () => routeState.view,
      (view, previousView) => {
        if (view !== previousView && !FULLSCREEN_VIEWS.includes(view) && appStore.apiKey) {
          loadOperationsSummary();
        }
      },
    );

    onMounted(() => {
      if (appStore.apiKey) {
        loadOperationsSummary();
      }
    });

    return {
      appStore, routeState, viewKey,
      loggedIn, isDetail, currentComponent, activeMenu, viewTitle, statusDisplay,
      epLocale,
      loginComponent: ViewLogin,
      detailComponent: ViewCutoverEmailDetail,
      supplierFormComponent: ViewSupplierForm,
      handleLogout, navigateTo, navigateToSummary, loadOperationsSummary,
      summaryValue, latestEmailTime, latestEmailDate,
      icons: ElementPlusIconsVue,
    };
  },
  template: `
    <el-config-provider :locale="epLocale">
    <component v-if="!loggedIn" :is="loginComponent"></component>
    <el-container v-else class="app-shell">
      <el-aside width="224px" class="sidebar">
        <div class="brand-block">
          <div class="brand-mark">NOC</div>
          <div>
            <h1>{{ $t('common.brandName') }}</h1>
            <p>{{ $t('common.brandTagline') }}</p>
          </div>
        </div>
        <el-menu :default-active="activeMenu" class="side-menu" @select="navigateTo">
          <el-menu-item index="suppliers">
            <el-icon><office-building></office-building></el-icon>
            <span>{{ $t('nav.suppliers') }}</span>
          </el-menu-item>
          <el-menu-item index="emails">
            <el-icon><message></message></el-icon>
            <span>{{ $t('nav.emails') }}</span>
          </el-menu-item>
          <el-menu-item index="cutoverTasks">
            <el-icon><DocumentChecked></DocumentChecked></el-icon>
            <span>{{ $t('nav.cutoverTasks') }}</span>
          </el-menu-item>
          <el-menu-item index="circuits">
            <el-icon><share></share></el-icon>
            <span>{{ $t('nav.circuits') }}</span>
          </el-menu-item>
          <el-menu-item index="mailAccounts">
            <el-icon><MessageBox /></el-icon>
            <span>{{ $t('nav.mailAccounts') }}</span>
          </el-menu-item>
          <el-menu-item index="settings">
            <el-icon><Setting /></el-icon>
            <span>{{ $t('nav.settings') }}</span>
          </el-menu-item>
        </el-menu>
      </el-aside>

      <el-container>
        <el-header class="topbar" height="72px">
          <div>
            <p class="eyebrow">Operations Console</p>
            <h2>{{ viewTitle }}</h2>
          </div>
          <div class="topbar-user">
            <el-button text class="topbar-logout" @click="handleLogout">
              <el-icon><SwitchButton /></el-icon>
              {{ $t('common.logout') }}
            </el-button>
          </div>
        </el-header>

        <el-main class="workspace">
          <section v-if="!isDetail" class="operations-summary" aria-labelledby="operations-summary-title">
            <div class="operations-summary-intro">
              <div class="operations-summary-heading">
                <p>{{ $t('operations.title') }}</p>
                <h3 id="operations-summary-title">{{ $t('operations.subtitle') }}</h3>
              </div>
              <el-button text class="operations-summary-refresh"
                         :loading="appStore.operationsSummaryLoading"
                         :aria-label="$t('operations.refresh')"
                         @click="loadOperationsSummary">
                <el-icon><RefreshRight /></el-icon>
                {{ $t('common.refresh') }}
              </el-button>
              <p class="operations-summary-description">{{ $t('operations.description') }}</p>
              <p v-if="appStore.operationsSummaryError" class="operations-summary-error" role="alert">
                {{ $t('operations.loadFailed') }}
              </p>
            </div>

            <div class="operations-summary-metrics" :aria-busy="appStore.operationsSummaryLoading">
              <button type="button" class="operations-metric"
                      :class="{ 'is-pending': appStore.operationsSummaryLoaded && appStore.operationsSummary.pending_tasks > 0 }"
                      @click="navigateToSummary('cutoverTasks', { status: 'draft' })">
                <span class="operations-metric-label">{{ $t('operations.pendingTasks') }}</span>
                <strong>{{ summaryValue(appStore.operationsSummary.pending_tasks) }}</strong>
                <span class="operations-metric-foot">
                  {{ $t('operations.pendingHint') }}
                  <el-icon aria-hidden="true"><ArrowRight /></el-icon>
                </span>
              </button>

              <button type="button" class="operations-metric"
                      :class="{
                        'is-risk': appStore.operationsSummaryLoaded && appStore.operationsSummary.failed_tasks > 0,
                        'is-clear': appStore.operationsSummaryLoaded && appStore.operationsSummary.failed_tasks === 0,
                      }"
                      @click="navigateToSummary('cutoverTasks', { status: 'report_failed' })">
                <span class="operations-metric-label">{{ $t('operations.failedTasks') }}</span>
                <strong>{{ summaryValue(appStore.operationsSummary.failed_tasks) }}</strong>
                <span class="operations-metric-foot">
                  {{ !appStore.operationsSummaryLoaded
                    ? $t('common.statusLoading')
                    : appStore.operationsSummary.failed_tasks > 0
                      ? $t('operations.failedHint')
                      : $t('operations.failedClear') }}
                  <el-icon aria-hidden="true"><ArrowRight /></el-icon>
                </span>
              </button>

              <button type="button" class="operations-metric"
                      @click="navigateToSummary('emails')">
                <span class="operations-metric-label">{{ $t('operations.todayEmails') }}</span>
                <strong>{{ summaryValue(appStore.operationsSummary.today_emails) }}</strong>
                <span class="operations-metric-foot">
                  {{ $t('operations.todayHint') }}
                  <el-icon aria-hidden="true"><ArrowRight /></el-icon>
                </span>
              </button>

              <button type="button" class="operations-metric operations-metric--time"
                      @click="navigateToSummary('emails')">
                <span class="operations-metric-label">{{ $t('operations.latestEmail') }}</span>
                <strong>{{ latestEmailTime(appStore.operationsSummary.last_email_at) }}</strong>
                <span class="operations-metric-foot">
                  {{ latestEmailDate(appStore.operationsSummary.last_email_at) }}
                  <el-icon aria-hidden="true"><ArrowRight /></el-icon>
                </span>
              </button>
            </div>
          </section>

          <component v-if="routeState.view === 'cutoverEmailDetail'" :is="detailComponent"
                     :key="'detail-' + routeState.emailRecordId"
                     :email-record-id="routeState.emailRecordId"></component>
          <component v-else-if="routeState.view === 'supplierForm'" :is="supplierFormComponent"
                     :key="'supplier-form-' + (routeState.supplierId ?? 'new')"
                     :supplier-id="routeState.supplierId"></component>
          <component v-else :is="currentComponent"
                     :key="viewKey + '-' + routeState.view + routeState.query"></component>
        </el-main>
      </el-container>
    </el-container>
    </el-config-provider>
  `,
});

// ==================== 挂载 ====================
const app = createApp(AdminApp);
app.use(ElementPlus);
app.use(i18n);
for (const [name, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(name, component);
}
app.component("TaskDetailPanel", TaskDetailPanel);

initRouting();
app.mount("#app");
