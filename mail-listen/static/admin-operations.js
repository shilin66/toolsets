/* Operations overview: aggregates first, paginated evidence on demand. */
const ViewOperations = defineComponent({
  name: 'ViewOperations',
  setup() {
    const boxes = ref([]), selected = ref([]), allScope = ref(false);
    const period = ref('week'), start = ref(''), end = ref(''), environment = ref('all');
    const summary = ref(null), loading = ref(true), error = ref(''), applied = ref(null);
    const tab = ref('overview'), focus = ref('volume'), list = ref(null), detail = ref(null);
    const search = ref(''), status = ref('active'), sort = ref('received'), page = ref(1), pageSize = ref(20);
    const listQuery = ref(null);
    const kind = ref('orders'), detailSupplier = ref(null), detailName = ref('全部运营商'), detailPage = ref(1);
    const tableLoading = ref(false), tableError = ref(''), exporting = ref(false);
    let summaryVersion = 0, tableVersion = 0, alive = true, optionsLoaded = false;
    const admin = computed(() => Boolean(appStore.user?.is_admin));
    const number = value => value == null ? '—' : Number(value).toLocaleString('zh-CN');
    function preset() {
      if (period.value === 'custom') return;
      const today = new Intl.DateTimeFormat('sv-SE', {timeZone: 'Asia/Shanghai'}).format(new Date());
      const d = new Date(today + 'T00:00:00Z'), a = new Date(d), b = new Date(d);
      if (period.value === 'month') a.setUTCDate(1);
      else {
        a.setUTCDate(a.getUTCDate() - (a.getUTCDay() + 6) % 7 - (period.value === 'previous' ? 7 : 0));
        b.setTime(a.getTime()); b.setUTCDate(b.getUTCDate() + 6);
      }
      start.value = a.toISOString().slice(0,10); end.value = b.toISOString().slice(0,10);
    }
    function selectAll() { allScope.value = admin.value; selected.value = boxes.value.map(b => b.account_id); }
    function clearBoxes() { allScope.value = false; selected.value = []; }
    function query(extra = {}) { return new URLSearchParams(Object.entries({...applied.value, ...extra}).filter(([, value]) => value != null)).toString(); }
    const endDateDisabled = timestamp => Boolean(start.value) && timestamp < new Date(start.value + 'T00:00:00').getTime();
    async function apply() {
      if (!start.value || !end.value || end.value < start.value) {
        error.value = '请选择完整的日期范围，结束日期不能早于开始日期';
        return;
      }
      const version = ++summaryVersion; ++tableVersion;
      summary.value = null; list.value = null; detail.value = null;
      error.value = ''; tableError.value = ''; loading.value = true; tableLoading.value = false;
      page.value = 1; detailPage.value = 1;
      try {
        if (!optionsLoaded) {
          const options = await requestJson('/api/operations/options');
          if (!alive || version !== summaryVersion) return;
          boxes.value = options.mailboxes; selectAll(); optionsLoaded = true;
        }
        applied.value = {start: start.value, end: end.value, environment: environment.value,
          ...(!allScope.value ? {mailboxes: selected.value.join(',')} : {})};
        const result = await requestJson('/api/operations/summary?' + query());
        if (!alive || version !== summaryVersion) return;
        summary.value = result;
        if (tab.value !== 'overview') await loadTable();
      } catch (e) { if (alive && version === summaryVersion) error.value = e.message; }
      finally { if (alive && version === summaryVersion) loading.value = false; }
    }
    async function loadTable() {
      const version = ++tableVersion, showing = tab.value;
      tableLoading.value = true; tableError.value = ''; list.value = null; detail.value = null;
      try {
        const extra = showing === 'suppliers'
          ? {search: search.value, status: status.value, sort: sort.value, page: page.value, page_size: pageSize.value}
          : {kind: kind.value, supplier: detailSupplier.value, page: detailPage.value, page_size: 20};
        const result = await requestJson('/api/operations/' + (showing === 'suppliers' ? 'suppliers' : 'details') + '?' + query(extra));
        if (!alive || version !== tableVersion) return;
        if (showing === 'suppliers') { list.value = result; listQuery.value = extra; } else detail.value = result;
      } catch (e) { if (alive && version === tableVersion) tableError.value = e.message; }
      finally { if (alive && version === tableVersion) tableLoading.value = false; }
    }
    function showTab(value) {
      ++tableVersion; tableLoading.value = false; tableError.value = ''; tab.value = value;
      if (value !== 'overview') loadTable();
    }
    function filterList() { page.value = 1; loadTable(); }
    function openDetails(value, row = null) {
      kind.value = value; detailSupplier.value = row ? row.sender : null; detailName.value = row?.name || '全部运营商';
      detailPage.value = 1; showTab('details');
    }
    function changeKind() { detailPage.value = 1; loadTable(); }
    function turnPage(delta) { if (tab.value === 'suppliers') page.value += delta; else detailPage.value += delta; loadTable(); }
    async function exportCsv() {
      exporting.value = true;
      try {
        const url = await requestBlobUrl('/api/operations/export?' + query(listQuery.value));
        const anchor = document.createElement('a'); anchor.href = url;
        anchor.download = `运营统计_${applied.value.start}_${applied.value.end}.csv`; anchor.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (e) { NocMessage.error(e.message); }
      finally { exporting.value = false; }
    }
    const cards = computed(() => {
      const m = summary.value?.metrics || {};
      return [
        ['接收邮件', m.received_emails, null],
        ['割接通知邮件', m.cutover_emails, null],
        ['上报邮件', m.reported_emails, 'emails'],
        ['上报工单', m.reported_orders, 'orders'],
        ['上报线路', m.reported_lines, 'lines'],
        ['回复邮件', m.reply_emails, 'replies'],
        ['已接入运营商', m.connected_suppliers, null],
        ['本期新增接入', m.new_suppliers, null],
      ];
    });
    const chartMax = computed(() => Math.max(1, ...(summary.value?.trend || []).map(w => Math.max(w.received, w.reported))));
    const focusRows = computed(() => summary.value?.focus[focus.value] || []);
    const focusMetric = computed(() => ({volume: 'received', onboarding: 'cutover', pending: 'pending'})[focus.value]);
    const focusMax = computed(() => Math.max(1, ...focusRows.value.map(r => r[focusMetric.value])));
    const pageData = computed(() => tab.value === 'suppliers' ? list.value : detail.value);
    const pages = computed(() => Math.max(1, Math.ceil((pageData.value?.total || 0) / (pageData.value?.page_size || 20))));
    onMounted(() => { preset(); apply(); });
    onUnmounted(() => { alive = false; ++summaryVersion; ++tableVersion; });
    return {boxes, selected, allScope, admin, period, start, end, environment,
      summary, loading, error, applied, tab, focus, list, detail, search, status, sort, page, pageSize,
      kind, detailSupplier, detailName, detailPage, tableLoading, tableError, exporting, cards, chartMax,
      focusRows, focusMetric, focusMax, pageData, pages, number, preset, endDateDisabled, selectAll, clearBoxes, apply,
      loadTable, showTab, filterList, openDetails, changeKind, turnPage, exportCsv, openCutoverEmailDetail};
  },
  template: `
  <div class="stats-page">
    <div class="stats-heading"><div><div class="stats-eyebrow">OPERATIONS / 运营统计</div><h2>每周运营，一览全局</h2>
      <p class="muted">看接入进展、邮件处理与上报产出，按需查看运营商及业务明细。</p></div>
      <span class="stats-scope-badge">{{ admin ? '管理员 · 全局可见' : '仅统计有操作权限的邮箱' }}</span></div>
    <form class="stats-filters" @submit.prevent="apply">
      <label>统计周期<ui-select aria-label="统计周期" v-model="period" @change="preset"><ui-option value="week" label="本周"></ui-option><ui-option value="previous" label="上周"></ui-option><ui-option value="month" label="本月"></ui-option><ui-option value="custom" label="自定义"></ui-option></ui-select></label>
      <label>开始日期<ui-date-picker v-model="start" type="date" value-format="YYYY-MM-DD" aria-label="开始日期" @change="period='custom'"></ui-date-picker></label>
      <label>结束日期<ui-date-picker v-model="end" type="date" value-format="YYYY-MM-DD" aria-label="结束日期" :is-date-disabled="endDateDisabled" @change="period='custom'"></ui-date-picker></label>
      <div class="stats-mailbox-filter"><span>监听邮箱 <small v-if="allScope">含历史邮箱</small></span>
        <ui-select v-model="selected" multiple filterable clearable max-tag-count="responsive" aria-label="监听邮箱" placeholder="请选择邮箱" @change="allScope=false">
          <ui-option v-for="box in boxes" :key="box.account_id" :value="box.account_id" :label="box.name ? box.name + ' · ' + box.email_address : box.email_address"></ui-option>
          <template #action><div class="stats-inline-actions"><ui-button size="small" @click="selectAll">全选</ui-button><ui-button size="small" @click="clearBoxes">清空</ui-button></div></template>
        </ui-select>
      </div>
      <label>上报环境<ui-select aria-label="上报环境" v-model="environment"><ui-option value="production" label="生产环境"></ui-option><ui-option value="test" label="测试环境"></ui-option><ui-option value="all" label="所有环境"></ui-option></ui-select></label>
      <button type="submit" class="stats-primary" :disabled="loading">{{ loading ? '查询中…' : '查询统计' }}</button>
    </form>
    <p v-if="error" class="stats-error" role="alert">{{ error }} <button @click="apply">重试</button></p>
    <p v-if="loading" class="stats-loading" role="status">正在汇总当前范围的数据…</p>
    <template v-if="summary && !loading">
      <p class="stats-context">{{ applied.start }} 至 {{ applied.end }} · 北京时间 · {{ applied.environment === 'production' ? '生产上报' : applied.environment === 'test' ? '测试上报' : '所有环境上报' }} · {{ 'mailboxes' in applied ? summary.scope.mailbox_count + ' 个监听邮箱' : '全部邮箱（含历史）' }}<span>邮件与回复数量包含所选邮箱全部业务；环境只筛选上报记录。</span></p>
      <div class="stats-cards"><component :is="card[2] ? 'button' : 'div'" v-for="card in cards" :key="card[0]" class="stats-card" :class="{'is-link': card[2]}" @click="card[2] && openDetails(card[2])">
        <span class="stats-card-label">{{ card[0] }}<span v-if="card[2]" aria-hidden="true">↗</span></span><strong>{{ number(card[1]) }}</strong>
      </component></div>
      <div class="stats-coverage"><div><strong>本期来件运营商</strong><span>已接入 {{ number(summary.metrics.incoming_suppliers) }} 家 · 未配置发件地址 {{ number(summary.metrics.unmapped_senders) }} 个</span></div>
        <strong v-if="summary.metrics.coverage_percent != null">来件接入率 {{ summary.metrics.coverage_percent }}%</strong></div>
      <div class="stats-tabs" role="tablist" aria-label="统计视图"><button role="tab" :aria-selected="tab==='overview'" @click="showTab('overview')">运营概览</button><button role="tab" :aria-selected="tab==='suppliers'" @click="showTab('suppliers')">运营商明细</button><button v-if="tab==='details'" role="tab" aria-selected="true">业务明细</button></div>
      <div v-if="tab==='overview'" class="stats-overview">
        <section class="stats-panel"><div class="stats-panel-head"><div><h3>最近 8 周处理趋势</h3><p class="muted">截至所选结束日期 · 按周汇总</p></div><div class="stats-legend"><span>接收邮件</span><span>完整成功邮件</span></div></div>
          <div class="stats-chart" role="img" aria-label="最近八周邮件处理趋势，每组展示接收邮件与完整成功上报邮件数量">
            <div class="stats-week" v-for="week in summary.trend" :key="week.start"><div class="stats-bars"><div :style="{height: Math.max(2,week.received/chartMax*160)+'px'}"><span>{{ number(week.received) }}</span></div><div :style="{height: Math.max(2,week.reported/chartMax*160)+'px'}"><span>{{ number(week.reported) }}</span></div></div><small>{{ week.start.slice(5) }}</small></div>
          </div><p class="stats-chart-note">上报邮件以完整成功计数；本周截至当前已入库数据。</p>
        </section>
        <section class="stats-panel"><div class="stats-panel-head"><div><h3>重点运营商</h3><p class="muted">最多展示 10 家，优先关注有业务的运营商</p></div></div>
          <div class="stats-focus-tabs"><button :aria-pressed="focus==='volume'" @click="focus='volume'">来件量 TOP 10</button><button :aria-pressed="focus==='onboarding'" @click="focus='onboarding'">待接入</button><button :aria-pressed="focus==='pending'" @click="focus='pending'">当前待处理</button></div>
          <div class="stats-focus-list"><div v-for="(row,i) in focusRows" :key="row.sender" class="stats-focus-row"><span class="stats-rank">{{ i+1 }}</span><div class="stats-focus-name"><strong :title="row.name">{{ row.name }}</strong><div class="stats-meter"><i :style="{width:(row[focusMetric]/focusMax*100)+'%'}"></i></div></div><strong>{{ number(row[focusMetric]) }}</strong><small>{{ focus==='pending' ? '任务' : '封' }}</small></div>
          <p v-if="!focusRows.length" class="stats-empty">{{ focus==='onboarding' ? '当前范围没有待核实的割接发件方' : '当前范围暂无数据' }}</p></div>
          <button class="stats-text-link" @click="status=focus==='onboarding'?'unconfigured':focus==='pending'?'pending':'active';page=1;showTab('suppliers')">查看运营商明细 →</button>
        </section>
      </div>
      <section v-else class="stats-panel stats-table-panel">
        <template v-if="tab==='suppliers'"><div class="stats-panel-head"><div><h3>按运营商汇总</h3><p class="muted">按运营商查看邮件、工单和线路的上报数量。</p></div><button @click="exportCsv" :disabled="exporting || tableLoading || !list">{{ exporting ? '导出中…' : '导出筛选结果 CSV' }}</button></div>
          <form class="stats-table-filters" @submit.prevent="filterList"><input v-model="search" placeholder="搜索运营商名称或发件地址" aria-label="搜索运营商"><ui-select v-model="status" aria-label="运营商状态" @change="filterList"><ui-option value="active" label="本期有业务"></ui-option><ui-option value="all" label="全部运营商"></ui-option><ui-option value="configured" label="已接入"></ui-option><ui-option value="unconfigured" label="未配置发件方"></ui-option><ui-option value="pending" label="当前待处理"></ui-option></ui-select><ui-select v-model="sort" aria-label="排序方式" @change="filterList"><ui-option value="received" label="接收邮件最多"></ui-option><ui-option value="reported" label="上报邮件最多"></ui-option><ui-option value="pending" label="待处理最多"></ui-option><ui-option value="name" label="运营商名称"></ui-option></ui-select><button type="submit">搜索</button></form>
        </template>
        <div v-else class="stats-panel-head"><div><h3>{{ detailName }} · 业务明细</h3><p class="muted">点击来源邮件查看割接详情。</p></div><ui-select v-model="kind" @change="changeKind" aria-label="明细类型"><ui-option value="orders" label="上报工单"></ui-option><ui-option value="lines" label="上报线路"></ui-option><ui-option value="emails" label="上报邮件"></ui-option><ui-option value="replies" label="回复邮件"></ui-option></ui-select></div>
        <p v-if="tableLoading" class="stats-loading" role="status">正在查询明细…</p><p v-if="tableError" class="stats-error" role="alert">{{ tableError }} <button @click="loadTable">重试</button></p>
        <div v-if="pageData" class="stats-table-scroll">
          <table v-if="tab==='suppliers'" class="stats-table"><thead><tr><th>运营商 / 发件地址</th><th>接收</th><th>割接邮件</th><th>完整上报邮件</th><th>上报工单</th><th>线路</th><th>回复</th><th>待处理</th></tr></thead><tbody><tr v-for="row in list.items" :key="row.sender"><td><button class="stats-name-link" @click="openDetails('orders',row)">{{ row.name }}</button><small>{{ row.sender }} · {{ row.configured ? '已接入' : '未配置' }}</small></td><td>{{ number(row.received) }}</td><td>{{ number(row.cutover) }}</td><td><button class="stats-count-link" @click="openDetails('emails',row)">{{ number(row.reported) }}</button></td><td><button class="stats-count-link" @click="openDetails('orders',row)">{{ number(row.orders) }}</button></td><td><button class="stats-count-link" @click="openDetails('lines',row)">{{ number(row.lines) }}</button></td><td><button class="stats-count-link" @click="openDetails('replies',row)">{{ number(row.replies) }}</button></td><td>{{ number(row.pending) }}<small v-if="row.failed" class="stats-error">{{ row.failed }} 失败</small></td></tr></tbody></table>
          <table v-else class="stats-table"><thead><tr><th>来源</th><th v-if="kind==='orders' || kind==='lines'">工单编号</th><th v-if="kind==='lines'">线路编号</th><th v-if="kind==='orders'">已成功任务 / 总任务</th><th v-if="kind==='emails'">邮件主题 / 接收邮箱</th><th>统计日期（北京）</th><th>查看</th></tr></thead><tbody><tr v-for="(row,i) in detail.items" :key="i"><td>{{ row.sender }}</td><td v-if="kind==='orders' || kind==='lines'">{{ row.ticket }}</td><td v-if="kind==='lines'">{{ row.line_id }}</td><td v-if="kind==='orders'">{{ row.done }} / {{ row.tasks }}<small>{{ row.done===row.tasks ? '完整成功' : '部分成功' }}</small></td><td v-if="kind==='emails'">{{ row.subject }}<small>{{ row.receiver }}</small></td><td>{{ row.completed }}</td><td><button class="stats-count-link" @click="openCutoverEmailDetail(row.email_id)">来源邮件 ↗</button></td></tr></tbody></table>
          <p v-if="!pageData.items.length" class="stats-empty">当前条件没有数据，请调整周期、邮箱或搜索条件。</p>
        </div>
        <div v-if="pageData" class="stats-pagination"><span>共 {{ number(pageData.total) }} 条</span><label v-if="tab==='suppliers'">每页 <ui-select v-model="pageSize" @change="filterList" aria-label="每页条数"><ui-option :value="20" label="20 条"></ui-option><ui-option :value="50" label="50 条"></ui-option></ui-select></label><button :disabled="pageData.page<=1" @click="turnPage(-1)">上一页</button><span>{{ pageData.page }} / {{ pages }}</span><button :disabled="pageData.page>=pages" @click="turnPage(1)">下一页</button></div>
      </section>
    </template>
  </div>`,
});
