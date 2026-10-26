const discoveryZh = {
  unpublished: '未启用', statusFilter: '草稿状态', historyTitle: '已启用记录', historyHint: '保留生成依据与邮件样本，便于追溯；后续邮件使用正式配置。', historyEmptyTitle: '暂无已启用记录', historyEmpty: '审核启用后的草稿会保留在这里。', historyTotal: '共 {count} 条已启用记录',
  nameRequiredForPublish: '启用前请填写供应商名称',
  title: '未配置供应商', settings: '未配置供应商邮件处理', settingsHint: '仅处理上线后新到达的邮件。正式供应商继续按现有规则处理。',
  discover: '自动发现并生成配置草稿', analyze: '分析所有割接通知的时间', filter: '发件人范围', all: '全部处理', allowlist: '仅处理指定发件人', blocklist: '排除指定发件人',
  listHint: "每行一个完整邮箱或 *{'@'}example.com，域名规则不包含子域名。", save: '保存设置', saved: '设置已保存',
  drafts: '配置草稿', formal: '正式配置', empty: '暂无候选供应商。开启自动发现后，新邮件的分类样本会汇集到这里。',
  queueTitle: '供应商审核队列', queueHint: '从新邮件收集样本，核对提取规则后启用供应商配置。', supplier: '候选供应商',
  draftTotal: '共 {count} 份草稿', emptyTitle: '暂无配置草稿', details: '样本与生成依据', closeDetails: '收起详情', viewConfig: '查看配置',
  deleteTitle: '删除配置草稿', deleteConfirm: '删除“{supplier}”的配置草稿？原始邮件、时间分析结果和已启用的供应商配置都会保留。对于仍未配置的供应商，自动发现开启后，后续新邮件可重新创建草稿。', deleted: '配置草稿已删除',
  collecting: '收集样本中', generating: '生成中', review: '待审核', published: '已启用', generation_failed: '生成失败',
  samples: '邮件样本', viewOriginal: '查看完整邮件', originalHint: '摘要仅展示部分正文，点击主题或右侧图标查看原邮件及线路表格。', summaryUnavailable: '暂无文本摘要，请查看完整原文', count: '样本数', evidence: '生成依据', questions: '待确认事项', edit: '审核配置', publish: '确认启用',
  publishConfirm: '启用后，该发件人的后续新邮件将使用此配置。请确认已审核规则与通知样本。', publishedMessage: '供应商配置已启用', saveDraft: '保存草稿', draftSaved: '草稿已保存',
  draftHint: '请核对生成依据、提取规则和通知样本；保存草稿不会启用配置。', retry: '重试失败任务', retryAccepted: '已登记重试',
  analysis: '整体割接时间分析（UTC+8）', classification: '邮件分类', configTask: '配置草稿生成', timeTask: '割接时间分析',
  pending: '等待处理', running: '处理中', succeeded: '已完成', failed: '失败', needs_review: '时间待核实',
  normal: '正常割接', start: '割接开始', end: '割接结束', timezone: '来源时区', assessed: '判定时间', source: '原文时间依据', reason: '判断依据',
  guard: '重保窗口', analysisHint: '分析仅针对整体割接时间；回复需人工审核后发送。', noLines: '本邮件未生成线路上报任务。供应商规则启用后，仅后续新邮件进入线路处理。', viewDraft: '查看供应商草稿',
  sent: '回复已发送', cancelled: '回复已取消', sending: '回复发送中', send_uncertain: '发送结果待核对，请先检查发件箱',
};
const discoveryEn = {
  unpublished: 'Not enabled', statusFilter: 'Draft status', historyTitle: 'Enabled history', historyHint: 'Evidence and mail samples are retained for reference. New mail uses the active configuration.', historyEmptyTitle: 'No enabled records', historyEmpty: 'Drafts appear here after they are reviewed and enabled.', historyTotal: '{count} enabled records',
  nameRequiredForPublish: 'Enter a supplier name before enabling the configuration',
  title: 'Unconfigured supplier', settings: 'Unconfigured supplier mail', settingsHint: 'Only newly received mail is processed. Configured suppliers use their existing rules.',
  discover: 'Discover suppliers and draft configurations', analyze: 'Analyze time in every cutover notice', filter: 'Sender scope', all: 'All senders', allowlist: 'Only listed senders', blocklist: 'Exclude listed senders',
  listHint: "One address or *{'@'}example.com per line. Domain rules exclude subdomains.", save: 'Save settings', saved: 'Settings saved',
  drafts: 'Configuration drafts', formal: 'Active configurations', empty: 'No candidates yet. Enable discovery to collect samples from new mail.',
  queueTitle: 'Supplier review queue', queueHint: 'Collect samples from new mail and review extraction rules before enabling a supplier.', supplier: 'Supplier candidate',
  draftTotal: '{count} drafts', emptyTitle: 'No configuration drafts', details: 'Samples and generation evidence', closeDetails: 'Close details', viewConfig: 'View configuration',
  deleteTitle: 'Delete configuration draft', deleteConfirm: 'Delete the configuration draft for “{supplier}”? Original mail, time analysis results, and enabled supplier configurations will be kept. For suppliers that remain unconfigured, subsequent new mail can create a new draft when automatic discovery is enabled.', deleted: 'Configuration draft deleted',
  collecting: 'Collecting samples', generating: 'Generating', review: 'Awaiting review', published: 'Enabled', generation_failed: 'Generation failed',
  samples: 'Mail samples', viewOriginal: 'View complete email', originalHint: 'Summaries show part of the body. Open the subject or the action to view the original email and circuit tables.', summaryUnavailable: 'No text summary; open the complete original', count: 'Samples', evidence: 'Evidence', questions: 'Open questions', edit: 'Review configuration', publish: 'Enable configuration',
  publishConfirm: 'Future mail from this sender will use these rules. Confirm that you have reviewed the rules and notice samples.', publishedMessage: 'Supplier configuration enabled', saveDraft: 'Save draft', draftSaved: 'Draft saved',
  draftHint: 'Review the evidence, extraction rules and notice samples. Saving a draft does not enable it.', retry: 'Retry failed task', retryAccepted: 'Retry queued',
  analysis: 'Overall cutover time analysis (UTC+8)', classification: 'Mail classification', configTask: 'Configuration draft', timeTask: 'Cutover time analysis',
  pending: 'Queued', running: 'Processing', succeeded: 'Completed', failed: 'Failed', needs_review: 'Time needs review', normal: 'Normal cutover',
  start: 'Start', end: 'End', timezone: 'Source timezone', assessed: 'Assessed at', source: 'Source time text', reason: 'Assessment', guard: 'Guard window',
  analysisHint: 'Only the overall window is analyzed. A person must review and send the reply.', noLines: 'This mail has no circuit reporting tasks. Once supplier rules are enabled, only subsequent mail enters circuit processing.', viewDraft: 'View supplier draft',
  sent: 'Reply sent', cancelled: 'Reply cancelled', sending: 'Sending reply', send_uncertain: 'Delivery uncertain; check Sent mail first',
};
const discoveryHk = {
  unpublished: '未啟用', statusFilter: '草稿狀態', historyTitle: '已啟用記錄', historyHint: '保留生成依據與郵件樣本，便於追溯；後續郵件使用正式配置。', historyEmptyTitle: '暫無已啟用記錄', historyEmpty: '審核啟用後的草稿會保留在這裏。', historyTotal: '共 {count} 條已啟用記錄',
  nameRequiredForPublish: '啟用前請填寫供應商名稱',
  title: '未配置供應商', settings: '未配置供應商郵件處理', settingsHint: '僅處理上線後新到達的郵件。正式供應商繼續按現有規則處理。',
  discover: '自動發現並生成配置草稿', analyze: '分析所有割接通知的時間', filter: '寄件人範圍', all: '全部處理', allowlist: '僅處理指定寄件人', blocklist: '排除指定寄件人',
  listHint: "每行一個完整郵箱或 *{'@'}example.com，網域規則不包含子網域。", save: '儲存設定', saved: '設定已儲存',
  drafts: '配置草稿', formal: '正式配置', empty: '暫無候選供應商。開啟自動發現後，新郵件的分類樣本會匯集到這裏。',
  queueTitle: '供應商審核佇列', queueHint: '從新郵件收集樣本，核對提取規則後啟用供應商配置。', supplier: '候選供應商',
  draftTotal: '共 {count} 份草稿', emptyTitle: '暫無配置草稿', details: '樣本與生成依據', closeDetails: '收起詳情', viewConfig: '檢視配置',
  deleteTitle: '刪除配置草稿', deleteConfirm: '刪除「{supplier}」的配置草稿？原始郵件、時間分析結果和已啟用的供應商配置都會保留。對於仍未配置的供應商，自動發現開啟後，後續新郵件可重新建立草稿。', deleted: '配置草稿已刪除',
  collecting: '收集樣本中', generating: '生成中', review: '待審核', published: '已啟用', generation_failed: '生成失敗',
  samples: '郵件樣本', viewOriginal: '查看完整郵件', originalHint: '摘要僅展示部分正文，點擊主題或右側圖示查看原郵件及線路表格。', summaryUnavailable: '暫無文字摘要，請查看完整原文', count: '樣本數', evidence: '生成依據', questions: '待確認事項', edit: '審核配置', publish: '確認啟用',
  publishConfirm: '啟用後，該寄件人的後續新郵件將使用此配置。請確認已審核規則與通知樣本。', publishedMessage: '供應商配置已啟用', saveDraft: '儲存草稿', draftSaved: '草稿已儲存',
  draftHint: '請核對生成依據、提取規則和通知樣本；儲存草稿不會啟用配置。', retry: '重試失敗任務', retryAccepted: '已登記重試',
  analysis: '整體割接時間分析（UTC+8）', classification: '郵件分類', configTask: '配置草稿生成', timeTask: '割接時間分析',
  pending: '等待處理', running: '處理中', succeeded: '已完成', failed: '失敗', needs_review: '時間待核實',
  normal: '正常割接', start: '割接開始', end: '割接結束', timezone: '來源時區', assessed: '判定時間', source: '原文時間依據', reason: '判斷依據',
  guard: '重保視窗', analysisHint: '分析僅針對整體割接時間；回覆需人工審核後傳送。', noLines: '本郵件未生成線路上報任務。供應商規則啟用後，僅後續新郵件進入線路處理。', viewDraft: '查看供應商草稿',
  sent: '回覆已傳送', cancelled: '回覆已取消', sending: '回覆傳送中', send_uncertain: '傳送結果待核對，請先檢查寄件備份',
};
for (const [locale, messages] of Object.entries({'zh-CN': discoveryZh, en: discoveryEn, 'zh-HK': discoveryHk})) {
  i18n.global.mergeLocaleMessage(locale, {discovery: messages});
}

const DiscoverySettings = defineComponent({
  setup() {
    const values = reactive({supplier_auto_discovery_enabled: false, unconfigured_cutover_analysis_enabled: false, unconfigured_sender_filter_mode: 'all'});
    const senders = ref('');
    const busy = ref(false);
    const error = ref('');
    const loaded = ref(false);
    onMounted(async () => {
      busy.value = true;
      try {
        const result = await requestJson('/api/system/settings');
        Object.keys(values).forEach(key => values[key] = result[key]);
        senders.value = result.unconfigured_sender_filter_list.join('\n');
        loaded.value = true;
      } catch (exc) { error.value = exc.message; }
      finally { busy.value = false; }
    });
    async function save() {
      busy.value = true;
      error.value = '';
      try {
        await requestJson('/api/system/settings', {method: 'PUT', body: JSON.stringify({...values,
          unconfigured_sender_filter_list: senders.value.split('\n').map(value => value.trim()).filter(Boolean)})});
        NocMessage.success(tt('discovery.saved'));
      } catch (exc) { error.value = exc.message; }
      finally { busy.value = false; }
    }
    return {values, senders, busy, error, loaded, save};
  },
  template: `<section class="block-section discovery-settings" v-loading="busy">
    <div class="block-head">{{ $t('discovery.settings') }}</div>
    <p class="field-hint">{{ $t('discovery.settingsHint') }}</p>
    <p v-if="error" class="warn-text" role="alert">{{ error }}</p>
    <ui-form label-width="240px" :disabled="!loaded || busy">
      <ui-form-item :label="$t('discovery.discover')"><ui-switch v-model="values.supplier_auto_discovery_enabled" :aria-label="$t('discovery.discover')"></ui-switch></ui-form-item>
      <ui-form-item :label="$t('discovery.analyze')"><ui-switch v-model="values.unconfigured_cutover_analysis_enabled" :aria-label="$t('discovery.analyze')"></ui-switch></ui-form-item>
      <ui-form-item :label="$t('discovery.filter')"><ui-radio-group v-model="values.unconfigured_sender_filter_mode">
        <ui-radio-button v-for="mode in ['all','allowlist','blocklist']" :key="mode" :value="mode">{{ $t('discovery.' + mode) }}</ui-radio-button>
      </ui-radio-group></ui-form-item>
      <ui-form-item v-if="values.unconfigured_sender_filter_mode !== 'all'" :label="$t('discovery.' + values.unconfigured_sender_filter_mode)">
        <div class="discovery-sender-list"><ui-input type="textarea" :rows="5" v-model="senders" :aria-label="$t('discovery.filter')"></ui-input><p class="field-hint">{{ $t('discovery.listHint') }}</p></div>
      </ui-form-item>
      <div class="settings-actions"><ui-button type="primary" :loading="busy" @click="save">{{ $t('discovery.save') }}</ui-button></div>
    </ui-form>
  </section>`,
});

const SupplierDraftsTable = defineComponent({
  setup() {
    const items = ref([]), selected = ref(null), busy = ref(false), error = ref('');
    const status = ref('unpublished');
    const page = ref(1), total = ref(0), samplePage = ref(1);
    const editing = ref(false), source = ref(null);
    const detailBusy = ref(false), selectingId = ref(null), deletingId = ref(null), retrying = ref(false);
    const deletedIds = new Set();
    let listRequest = 0, detailRequest = 0, sourceRequest = 0, disposed = false;

    function supplierName(row) { return row.draft?.config?.name?.trim() || row.sender; }
    function statusTagType(status) {
      return {review:'warning', published:'success', generation_failed:'danger', generating:'primary'}[status] || 'info';
    }
    function timeParts(value) { return String(value || '—').split(/[ T]/, 2); }
    function setDraftQuery(id) {
      const url = new URL(window.location.href);
      if (id) url.searchParams.set('draft', String(id));
      else url.searchParams.delete('draft');
      window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash);
    }
    function closeSource() { sourceRequest += 1; source.value = null; }
    function clearSelection() {
      detailRequest += 1;
      selected.value = null; editing.value = false; detailBusy.value = false; selectingId.value = null;
      samplePage.value = 1;
      closeSource();
      setDraftQuery(null);
    }

    async function load(refreshSelection = true) {
      const request = ++listRequest, selectionAtStart = detailRequest;
      busy.value = true;
      try {
        const result = await requestJson(`/api/supplier-drafts?page=${page.value}&status=${status.value}`);
        if (disposed || request !== listRequest) return;
        const lastPage = Math.max(1, Math.ceil(result.total / 20));
        if (page.value > lastPage) {
          page.value = lastPage;
          await load(refreshSelection);
          return;
        }
        items.value = result.items.filter(row => !deletedIds.has(row.id));
        total.value = result.total; error.value = '';
        if (refreshSelection && selected.value && !editing.value && selectionAtStart === detailRequest) {
          await select(selected.value, {keepPage:true});
        }
      } catch (exc) { if (!disposed && request === listRequest) error.value = exc.message; }
      finally { if (!disposed && request === listRequest) busy.value = false; }
    }

    async function select(row, {edit = false, keepPage = false, reveal = false} = {}) {
      if (!row || deletedIds.has(row.id) || deletingId.value === row.id) return;
      if (!keepPage || selected.value?.id !== row.id) samplePage.value = 1;
      const request = ++detailRequest;
      selectingId.value = row.id; detailBusy.value = true;
      try {
        const result = await requestJson(`/api/supplier-drafts/${row.id}?page=${samplePage.value}`);
        if (disposed || request !== detailRequest || deletedIds.has(row.id) || deletingId.value === row.id) return;
        const resultStatus = result.status === 'published' ? 'published' : 'unpublished';
        if (resultStatus !== status.value) {
          if (!reveal) { clearSelection(); await load(false); return; }
          status.value = resultStatus;
          page.value = 1;
          await load(false);
          if (disposed || request !== detailRequest) return;
        }
        selected.value = result; editing.value = edit && result.status === 'review';
        closeSource(); setDraftQuery(row.id);
      } catch (exc) {
        if (disposed || request !== detailRequest) return;
        if (exc.status === 404 && (selected.value?.id === row.id || Number(new URLSearchParams(window.location.search).get('draft')) === row.id)) clearSelection();
        NocMessage.error(exc.message);
      } finally {
        if (!disposed && request === detailRequest) { detailBusy.value = false; selectingId.value = null; }
      }
    }

    function changePage(value) { page.value = value; load(); }
    function changeStatus(value) {
      if (value === status.value) return;
      status.value = value; page.value = 1; items.value = []; total.value = 0; error.value = '';
      clearSelection();
      load(false);
    }
    function changeSamplePage(value) { samplePage.value = value; select(selected.value, {keepPage:true}); }

    async function retry() {
      if (!selected.value) return;
      const row = selected.value;
      retrying.value = true;
      try {
        await requestJson(`/api/supplier-drafts/${row.id}/retry`, {method:'POST'});
        if (selected.value?.id === row.id) await select(row, {keepPage:true});
        await load(false);
      }
      catch (exc) { NocMessage.error(exc.message); }
      finally { retrying.value = false; }
    }

    async function removeDraft(row) {
      if (deletingId.value !== null) return;
      try {
        await NocDialog.confirm(tt('discovery.deleteConfirm', {supplier:supplierName(row)}), tt('discovery.deleteTitle'), {
          confirmButtonText:tt('common.confirmDelete'), cancelButtonText:tt('common.cancel'), type:'warning',
        });
      } catch { return; }
      if (disposed) return;
      deletingId.value = row.id;
      listRequest += 1; detailRequest += 1; sourceRequest += 1;
      busy.value = false; detailBusy.value = false; selectingId.value = null;
      try {
        await requestJson(`/api/supplier-drafts/${row.id}`, {method:'DELETE', body:JSON.stringify({revision:row.revision})});
        if (disposed) return;
        deletedIds.add(row.id);
        items.value = items.value.filter(item => item.id !== row.id);
        total.value = Math.max(0, total.value - 1);
        if (selected.value?.id === row.id || Number(new URLSearchParams(window.location.search).get('draft')) === row.id) clearSelection();
        page.value = Math.min(page.value, Math.max(1, Math.ceil(total.value / 20)));
        NocMessage.success(tt('discovery.deleted'));
        await load();
      } catch (exc) {
        if (!disposed) { error.value = exc.message; NocMessage.error(exc.message); }
      } finally { if (!disposed) deletingId.value = null; }
    }

    async function openSource(row) {
      const request = ++sourceRequest;
      try {
        const result = await requestJson(`/api/emails/${row.id}/source`);
        if (!disposed && request === sourceRequest) source.value = result;
      } catch (exc) { if (!disposed && request === sourceRequest) NocMessage.error(exc.message); }
    }
    async function closeEditor() {
      editing.value = false;
      if (selected.value) await select(selected.value, {keepPage:true});
      await load(false);
    }
    async function published() {
      const id = selected.value?.id;
      items.value = items.value.filter(row => row.id !== id);
      total.value = Math.max(0, total.value - 1);
      clearSelection();
      await load(false);
    }
    onMounted(async () => {
      const id = Number(new URLSearchParams(window.location.search).get('draft'));
      await load(false);
      if (!disposed && id && detailRequest === 0) await select({id}, {reveal:true});
    });
    onUnmounted(() => { disposed = true; listRequest += 1; detailRequest += 1; sourceRequest += 1; });
    return {items, selected, busy, error, status, changeStatus, published, page, total, samplePage, editing, source, detailBusy, selectingId, deletingId, retrying,
      supplierName, statusTagType, timeParts, load, select, retry, openSource, closeSource, closeEditor, clearSelection,
      changePage, changeSamplePage, removeDraft, icons:ElementPlusIconsVue};
  },
  template: `<div class="supplier-drafts-workspace">
    <supplier-draft-editor v-if="editing && selected" :draft-id="selected.id" @close="closeEditor" @published="published"></supplier-draft-editor>
    <template v-else>
      <section class="drafts-list-panel" :aria-label="$t(status === 'published' ? 'discovery.historyTitle' : 'discovery.queueTitle')">
        <header class="drafts-panel-header">
          <div><div class="drafts-panel-title"><h2>{{ $t(status === 'published' ? 'discovery.historyTitle' : 'discovery.queueTitle') }}</h2><span class="drafts-total-count">{{ total }}</span></div>
            <p>{{ $t(status === 'published' ? 'discovery.historyHint' : 'discovery.queueHint') }}</p></div>
          <div class="drafts-header-actions">
          <ui-radio-group :model-value="status" @update:model-value="changeStatus" size="small" :disabled="deletingId !== null" :aria-label="$t('discovery.statusFilter')">
            <ui-radio-button value="unpublished">{{ $t('discovery.unpublished') }}</ui-radio-button>
            <ui-radio-button value="published">{{ $t('discovery.published') }}</ui-radio-button>
          </ui-radio-group>
          <ui-action class="drafts-refresh" icon="Refresh" :label="$t('common.refresh')" :loading="busy" :disabled="deletingId !== null" @click="load()"></ui-action>
          </div>
        </header>
        <p v-if="error" class="warn-text drafts-list-error" role="alert">{{ error }}</p>
        <ui-table v-loading="busy" class="drafts-list-table" :data="items" row-key="id" :row-class-name="({row}) => row.id === selected?.id ? 'is-selected' : ''">
          <ui-table-column :label="$t('discovery.supplier')" min-width="240">
            <template #default="{row}"><div class="draft-supplier-identity"><span class="draft-supplier-name" :title="supplierName(row)">{{ supplierName(row) }}</span>
              <span v-if="supplierName(row) !== row.sender" class="draft-supplier-address" :title="row.sender">{{ row.sender }}</span></div></template>
          </ui-table-column>
          <ui-table-column :label="$t('common.status')" width="150"><template #default="{row}"><ui-tag class="draft-status-badge" effect="light" :type="statusTagType(row.status)">{{ $t('discovery.'+row.status) }}</ui-tag></template></ui-table-column>
          <ui-table-column :label="$t('discovery.count')" width="88" align="center"><template #default="{row}"><span class="draft-sample-number">{{ row.sample_count }}</span></template></ui-table-column>
          <ui-table-column :label="$t('common.updateTime')" width="140"><template #default="{row}"><span class="draft-update-date">{{ timeParts(row.update_time)[0] }}</span><span class="draft-update-clock">{{ timeParts(row.update_time)[1] }}</span></template></ui-table-column>
          <ui-table-column :label="$t('common.actions')" width="152" align="center" fixed="right">
            <template #default="{row}"><div class="draft-list-row-actions">
              <ui-action v-if="row.status === 'review'" type="primary" :loading="selectingId === row.id" :disabled="deletingId !== null" @click="select(row, {edit:true})" icon="Edit" :label="$t(row.id === selected?.id ? 'discovery.viewConfig' : 'discovery.edit')"></ui-action>
              <ui-action :disabled="deletingId !== null" @click="select(row)" icon="Document" :label="$t('discovery.samples')"></ui-action>
              <ui-action type="danger" :loading="deletingId === row.id" :disabled="deletingId !== null && deletingId !== row.id" @click="removeDraft(row)" icon="Delete" :label="$t('common.delete')"></ui-action>
            </div></template>
          </ui-table-column>
          <template #empty><div class="drafts-empty-state"><ui-icon :size="28" aria-hidden="true"><component :is="icons.Document"></component></ui-icon><strong>{{ $t(status === 'published' ? 'discovery.historyEmptyTitle' : 'discovery.emptyTitle') }}</strong><p>{{ $t(status === 'published' ? 'discovery.historyEmpty' : 'discovery.empty') }}</p></div></template>
        </ui-table>
        <footer class="drafts-panel-footer"><span>{{ $t(status === 'published' ? 'discovery.historyTotal' : 'discovery.draftTotal', {count:total}) }}</span>
          <ui-pagination :current-page="page" :total="total" :page-size="20" layout="prev, pager, next" :disabled="busy || deletingId !== null" @current-change="changePage"></ui-pagination>
        </footer>
      </section>
      <section v-if="selected" class="block-section draft-review-panel" v-loading="detailBusy">
        <header class="draft-detail-header"><div><p>{{ $t('discovery.details') }}</p><div class="draft-detail-title"><h2>{{ supplierName(selected) }}</h2><ui-tag :type="statusTagType(selected.status)">{{ $t('discovery.' + selected.status) }}</ui-tag></div>
          <span v-if="supplierName(selected) !== selected.sender" class="draft-supplier-address">{{ selected.sender }}</span></div>
          <div class="draft-detail-actions">
            <ui-button v-if="selected.status === 'review'" type="primary" :disabled="deletingId !== null" @click="editing=true">{{ $t('discovery.edit') }}</ui-button>
            <ui-button v-if="selected.status === 'generation_failed'" :loading="retrying" :disabled="deletingId !== null" @click="retry">{{ $t('discovery.retry') }}</ui-button>
            <ui-action :disabled="deletingId !== null" @click="clearSelection" icon="Close" :label="$t('discovery.closeDetails')"></ui-action>
          </div>
        </header>
        <p v-if="selected.last_error" role="alert" class="warn-text">{{ selected.last_error }}</p>
        <div v-if="selected.draft && (selected.draft.evidence?.length || selected.draft.unresolved_questions?.length)" class="draft-review-notes">
          <section v-if="selected.draft.evidence?.length"><h3>{{ $t('discovery.evidence') }}</h3><ul><li v-for="(text,index) in selected.draft.evidence" :key="index">{{ text }}</li></ul></section>
          <section v-if="selected.draft.unresolved_questions?.length" class="draft-open-questions"><h3>{{ $t('discovery.questions') }}</h3><ul><li v-for="(text,index) in selected.draft.unresolved_questions" :key="index">{{ text }}</li></ul></section>
        </div>
        <div class="draft-sample-counts"><ui-tag v-for="(count,type) in selected.sample_counts" :key="type" type="info">{{ type }} {{ count }}</ui-tag></div>
        <p class="field-hint">{{ $t('discovery.originalHint') }}</p>
        <ui-table :data="selected.samples"><ui-table-column prop="mail_type" :label="$t('discovery.classification')" width="130"></ui-table-column>
          <ui-table-column prop="subject" :label="$t('common.subject')" min-width="250"><template #default="{row}"><button type="button" class="draft-sample-subject" @click="openSource(row)">{{ row.subject || $t('discovery.viewOriginal') }}</button></template></ui-table-column>
          <ui-table-column prop="content_summary" :label="$t('emails.contentSummary')" min-width="250"><template #default="{row}"><div class="draft-sample-summary">{{ row.content_summary || $t('discovery.summaryUnavailable') }}</div></template></ui-table-column>
          <ui-table-column :label="$t('common.actions')" width="88" align="center"><template #default="{row}"><ui-action icon="Document" :label="$t('discovery.viewOriginal')" @click="openSource(row)"></ui-action></template></ui-table-column>
        </ui-table>
        <ui-pagination :current-page="samplePage" :total="selected.sample_count" :page-size="20" layout="prev, pager, next" :disabled="detailBusy || deletingId !== null" @current-change="changeSamplePage"></ui-pagination>
      </section>
    </template>
    <ui-dialog :model-value="!!source" :title="source?.subject || $t('discovery.viewOriginal')" width="1040px" class="draft-source-dialog" @close="closeSource">
      <template v-if="source">
        <dl class="draft-source-meta">
          <div><dt>{{ $t('common.sender') }}</dt><dd>{{ source.sender }}</dd></div>
          <div><dt>{{ $t('common.receiverMailbox') }}</dt><dd>{{ source.receiver }}</dd></div>
          <div><dt>{{ $t('common.receiveTime') }}</dt><dd>{{ source.create_time }}</dd></div>
        </dl>
        <div class="email-content-body">
          <iframe v-if="source.preview_html" class="email-html-frame draft-source-frame" sandbox="" referrerpolicy="no-referrer"
                  :title="$t('discovery.viewOriginal')" :srcdoc="source.preview_html"></iframe>
          <pre v-else class="email-content-block draft-source-text">{{ source.content || $t('cutover.detail.noContent') }}</pre>
        </div>
        <div v-if="source.attachment_urls?.length" class="attachment-list"><a v-for="(url,index) in source.attachment_urls" :key="url" :href="url" target="_blank" rel="noopener noreferrer">{{ $t('common.attachment',{index:index+1}) }}</a></div>
      </template>
      <template #footer><ui-button @click="closeSource">{{ $t('common.close') }}</ui-button></template>
    </ui-dialog>
  </div>`,
});

const MailAnalysisPanel = defineComponent({
  props: {record: {type: Object, required: true}}, emits: ['changed'],
  setup(props, {emit}) {
    const busy = ref(false);
    const taskKeys = {unconfigured_mail_analyze:'classification', supplier_config_draft:'configTask', cutover_time_extract:'timeTask'};
    async function retry(task) {
      busy.value = true;
      try { await requestJson(`/api/emails/${props.record.id}/analysis-retry`, {method:'POST', body:JSON.stringify({task_type:task.task_type})}); emit('changed'); }
      catch (exc) { NocMessage.error(exc.message); }
      finally { busy.value = false; }
    }
    function openDraft() { navigateToSummary('suppliers', {draft:props.record.supplier_draft_id}); }
    function beijingTime(value) {
      if (!value || !Number.isFinite(Date.parse(value))) return '—';
      return new Intl.DateTimeFormat('zh-CN', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(new Date(value)).replaceAll('/', '-');
    }
    function analysisValue(key) {
      const value = props.record.unconfigured_analysis[key];
      return ['cutover_start','cutover_end','assessed_at'].includes(key) ? beijingTime(value) : value || '—';
    }
    return {busy, taskKeys, retry, openDraft, sceneText, sceneTagType, beijingTime, analysisValue};
  },
  template: `<section v-if="record.processing_origin === 'unconfigured' && (record.ai_tasks?.length || record.unconfigured_analysis)" class="block-section mail-analysis-panel">
    <div class="block-head"><span>{{ $t('discovery.analysis') }}</span><div class="toolbar-actions">
      <ui-button v-if="record.supplier_draft_id" link type="primary" @click="openDraft">{{ $t('discovery.viewDraft') }}</ui-button>
      <ui-action icon="Refresh" :disabled="busy" @click="$emit('changed')" :label="$t('common.refresh')"></ui-action>
    </div></div>
    <p class="field-hint">{{ $t('discovery.analysisHint') }}</p>
    <div v-for="task in record.ai_tasks || []" :key="task.task_type" class="mail-analysis-task">
      <span>{{ $t('discovery.'+taskKeys[task.task_type]) }}</span><ui-tag :type="task.status === 'failed' ? 'danger' : 'info'">{{ $t('discovery.'+task.status) }}</ui-tag>
      <span v-if="task.last_error" class="warn-text">{{ task.last_error }}</span><ui-button v-if="task.status === 'failed'" :loading="busy" @click="retry(task)">{{ $t('discovery.retry') }}</ui-button>
    </div>
    <template v-if="record.unconfigured_analysis">
      <div class="mail-analysis-heading"><ui-tag :type="record.unconfigured_analysis.analysis_status === 'needs_review' ? 'warning' : sceneTagType(record.unconfigured_analysis.scene)">
        {{ record.unconfigured_analysis.analysis_status === 'needs_review' ? $t('discovery.needs_review') : record.unconfigured_analysis.scene === 'normal' ? $t('discovery.normal') : sceneText(record.unconfigured_analysis.scene) }}</ui-tag>
        <span>{{ record.unconfigured_analysis.reason }}</span></div>
      <ui-descriptions :column="1" border>
        <ui-descriptions-item v-for="(label,key) in {cutover_start:'start',cutover_end:'end',source_timezone:'timezone',assessed_at:'assessed',source_time_text:'source'}" :key="key" :label="$t('discovery.'+label)">{{ analysisValue(key) }}</ui-descriptions-item>
        <ui-descriptions-item v-if="record.unconfigured_analysis.security_window" :label="$t('discovery.guard')">{{ beijingTime(record.unconfigured_analysis.security_window.start) }} / {{ beijingTime(record.unconfigured_analysis.security_window.end) }}</ui-descriptions-item>
      </ui-descriptions>
    </template>
    <p v-if="['sent','cancelled','sending','send_uncertain'].includes(record.reply_status)" role="status">{{ $t('discovery.'+record.reply_status) }}</p>
    <p class="field-hint">{{ $t('discovery.noLines') }}</p>
  </section>`,
});
