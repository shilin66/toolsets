/* Operator workspace for one mail. The mail list and processing APIs are shared unchanged. */
const cutoverWorkbenchMessages = {
  'zh-CN': {
    review:'邮件核对', lines:'线路确认', reply:'回复审核', report:'上报处理', history:'处理记录',
    back:'返回任务列表', more:'更多操作', source:'邮件原文', results:'核对识别结果', edit:'编辑识别结果',
    editHint:'仅修正当前邮件，不改变供应商的后续识别规则。',
    saveHint:'保存会重新匹配线路并清除已有手动绑定，不会自动覆盖填报任务。时间修改不重新判定历史回复场景。',
    advanced:'高级信息', current:'当前待办', noPending:'暂无待办，请查看处理记录', sourceZone:'识别时区',
    emptyResult:'尚无可核对的提取结果。请查看解析状态和原邮件。', historicalRisk:'风险标签保留处理时的判断；修改提取结果不会自动重发回复。',
    start:'割接开始', end:'割接结束', backup:'备用割接时间', lineEdit:'邮件中的线路信息',
    lineKey:'{key} · 线路 {index}', invalidTime:'请填写有效的起止时间，结束时间必须晚于开始时间。',
    complex:'复杂字段保留原值，可在高级信息中查看。',
    matched:'已匹配', unmatched:'未匹配', multiple:'多条匹配', blocked:'状态不允许生成', bound:'人工绑定', rawNumbers:'邮件编号',
    reportHint:'客户线路与骨干线路分别确认、分别上报。打开任务核对内容与校验提示。',
    fillDetails:'完整填报内容', reportRecords:'上报记录与截图', openTask:'核对任务', taskRecords:'查看上报记录',
    replyEmpty:'当前没有待审核的回复。', replyScope:'请核对收件人、抄送和正文。回复与上报任务分别处理。',
    readonly:'当前邮箱仅有查看权限。', locked:'任务正在上报，暂不能修改提取结果或线路绑定。',
    staleTasks:'已保存提取或匹配结果。现有填报任务未自动更新，如需采用新结果，请重新生成并人工核对。',
    failedLoad:'详情读取失败，请重试。', attachment:'附件 {index}', received:'邮件已接收', parsed:'邮件解析状态',
    replyState:'回复处理状态', unknownReply:'未登记回复', taskState:'任务当前状态', loadingTask:'正在读取任务…',
    taskLoadFailed:'任务读取失败，请重试。', matchedCount:'已匹配 {matched} 条 · 待确认 {pending} 条',
    noBody:'正文为空，请查看附件。', editsUnsaved:'有尚未保存的修改，请先保存。',
    discardTask:'填报内容有尚未保存的修改，离开后这些修改将丢失。', discard:'放弃修改并继续',
    savedReport:'已保存的上报内容',internalLine:'内部线路 / 系统',impact:'业务影响',reason:'割接原因',noReportLines:'尚无上报线路，请展开填报内容核对。', keyword:'用于线路查询', applied:'已保存并重新匹配线路', noHistory:'暂未记录该处理阶段。',
  },
  en: {
    review:'Email review',lines:'Circuit matching',reply:'Reply review',report:'Reporting',history:'Processing history',back:'Back to tasks',more:'More actions',source:'Source email',results:'Review extracted results',edit:'Edit recognition results',editHint:'Corrections affect this email only, not future supplier rules.',saveHint:'Saving rematches circuits and clears manual bindings. Existing reports and historical reply decisions are not regenerated automatically.',advanced:'Advanced information',current:'Pending actions',noPending:'No pending actions. See history.',sourceZone:'Extraction time zone',emptyResult:'No extracted results yet. Check parsing status and the source email.',historicalRisk:'Risk labels reflect the original decision. Editing extraction does not resend replies.',start:'Cutover start',end:'Cutover end',backup:'Backup window',lineEdit:'Circuit information from the email',lineKey:'{key} · Circuit {index}',invalidTime:'Enter valid times with end after start.',complex:'Structured fields are preserved; inspect them in advanced information.',matched:'Matched',unmatched:'No match',multiple:'Multiple matches',blocked:'Status blocks generation',bound:'Manually bound',rawNumbers:'Email identifiers',reportHint:'Customer and backbone tasks are confirmed and reported independently.',fillDetails:'Full reporting form',reportRecords:'Report history and screenshots',openTask:'Review task',taskRecords:'View report history',replyEmpty:'No reply awaiting review.',replyScope:'Check recipients, CC and body. Replies and reports are handled separately.',readonly:'You have read-only access to this mailbox.',locked:'Reporting is in progress. Extraction and circuit bindings cannot be changed.',staleTasks:'Extraction or matching was saved. Existing task forms remain unchanged; regenerate and review to apply the new results.',failedLoad:'Could not load details. Retry.',attachment:'Attachment {index}',received:'Email received',parsed:'Email parsing status',replyState:'Reply status',unknownReply:'No reply registered',taskState:'Current task status',loadingTask:'Loading task…',taskLoadFailed:'Could not load the task. Retry.',matchedCount:'{matched} matched · {pending} need confirmation',noBody:'No body. Check attachments.',editsUnsaved:'Save or discard unsaved extraction changes first.',keyword:'Used for circuit lookup',applied:'Saved and rematched circuits',noHistory:'No record for this stage.'
  },
};
Object.assign(cutoverWorkbenchMessages.en, {savedReport:'Saved reporting content',internalLine:'Internal circuit / system',impact:'Service impact',reason:'Maintenance reason',noReportLines:'No reporting circuits. Review the full form.',discardTask:'This reporting form has unsaved changes. Leaving will discard them.',discard:'Discard and continue'});
cutoverWorkbenchMessages['zh-HK'] = {...cutoverWorkbenchMessages['zh-CN'], review:'郵件核對',lines:'線路確認',reply:'回覆審核',report:'上報處理',history:'處理記錄',back:'返回任務清單',source:'郵件原文',results:'核對識別結果',edit:'編輯識別結果',advanced:'進階資訊',current:'目前待辦',rawNumbers:'郵件編號',fillDetails:'完整填報內容',reportRecords:'上報記錄與截圖'};
Object.assign(cutoverWorkbenchMessages['zh-CN'], {replyRecords:'回复发送记录', sentAt:'发送时间', notRecorded:'未记录', noCc:'无抄送', legacyReply:'历史记录未保存实际收件人和抄送地址。'});
Object.assign(cutoverWorkbenchMessages['zh-HK'], {replyRecords:'回覆發送記錄', sentAt:'發送時間', notRecorded:'未記錄', noCc:'無抄送', legacyReply:'歷史記錄未保存實際收件人及副本地址。'});
Object.assign(cutoverWorkbenchMessages.en, {replyRecords:'Sent replies', sentAt:'Sent at', notRecorded:'Not recorded', noCc:'None', legacyReply:'Actual recipients and CC were not saved for this historical reply.'});
for (const [locale,messages] of Object.entries(cutoverWorkbenchMessages)) i18n.global.mergeLocaleMessage(locale,{cw:messages});

function useCutoverWorkbench(ctx) {
  const {email, extractionDraft, savedExtractionDraft, extractionBusy, replyBusy, apiForwardBusy, deleteBusy, saveExtraction} = ctx;
  const attachmentPreview = useMailAttachmentPreview(email);
  const activeTab = ref('review');
  const showAdvanced = ref(false);
  const resultDialog = ref(false);
  const resultError = ref('');
  const resultForm = ref({});
  const resultBase = ref({});
  const formStart = ref('');
  const formEnd = ref('');
  const usesDateInputs = ref(false);
  const tasksStale = ref(false);
  const sourceDrawer = ref(false);
  const taskLoading = ref(false);
  const taskError = ref('');
  const isConfigured = computed(() => email.value?.processing_origin !== 'unconfigured');
  const completionBusy = ref(false);
  const workBusy = computed(() => completionBusy.value || extractionBusy.value || replyBusy.value || apiForwardBusy.value || deleteBusy.value);
  const tasksReporting = computed(() => (email.value?.tasks || []).some(task => task.status === 'reporting'));
  const canReply = computed(() => !!email.value && canOperateMailbox(email.value.receiver) && !workBusy.value && !email.value.manual_completion);
  const canEditMail = computed(() => !!email.value && canOperateMailbox(email.value.receiver) && !workBusy.value && !tasksReporting.value && !email.value.manual_completion);
  const readPayload = value => {try {const parsed=JSON.parse(value);return parsed && !Array.isArray(parsed) && typeof parsed==='object' ? parsed : {};} catch {return {};}};
  const savedResult = computed(() => readPayload(savedExtractionDraft.value));
  const resultLines = data => Array.isArray(data.line_array) ? data.line_array : Array.isArray(data.line_array_info?.data) ? data.line_array_info.data : [];
  const editingLines = computed(() => resultLines(resultForm.value));
  const fixedLineKeys = ['ImpactType','ImpactDateTime','ImpactDuration','InteruptionsCounts','InterruptionsCounts'];
  function orderedLineColumns(lines) {
    const keys = [...new Set(lines.flatMap(line => Object.keys(line || {})))].filter(key => !key.startsWith('bound_'));
    return [...keys.filter(key => !fixedLineKeys.includes(key)), ...fixedLineKeys.filter(key => keys.includes(key))];
  }
  const reviewLines = computed(() => resultLines(savedResult.value));
  const reviewLineColumns = computed(() => orderedLineColumns(reviewLines.value));
  const lineColumns = computed(() => orderedLineColumns(editingLines.value));
  const scalar = value => value == null || ['string','number','boolean'].includes(typeof value);
  const fixedKeys = ['carrier_ticket_no','cutover_time','cutover_backup_time','cutover_timezone','cutover_reason','location'];
  const fieldLabel = key => hasI18nKey(`supplierForm.fields.${key}`) ? tt(`supplierForm.fields.${key}`) : extractFieldLabel(key);
  const reviewFields = computed(() => fixedKeys.filter(key => key!=='cutover_backup_time' || savedResult.value[key]).map(key => ({key,label:fieldLabel(key),value:display(savedResult.value[key])})));
  function display(value) {return value == null || value==='' ? '—' : typeof value==='object' ? JSON.stringify(value) : String(value);}
  const hasResult = computed(() => Object.keys(savedResult.value).length>0);
  const lineEntries = computed(() => (email.value?.line_table?.lines || []).map((line,index)=>({line,index})));
  function needsLineReview(line) {return line.circuits?.length!==1 || !!line.task_generation_blocked;}
  const pendingLineCount = computed(() => lineEntries.value.filter(entry=>needsLineReview(entry.line)).length);
  const matchedLineCount = computed(() => lineEntries.value.length-pendingLineCount.value);
  function lineState(line) {return tt('cw.'+(line.task_generation_blocked?'blocked':!line.circuits?.length?'unmatched':line.circuits.length>1?'multiple':line.line?.bound_circuit_id?'bound':'matched'));}
  function lineIdentifiers(line) {return Object.entries(line.line || {}).filter(([key,value]) => !key.startsWith('bound_') && !fixedLineKeys.includes(key) && scalar(value) && value!=='' && value!=null).map(([key,value])=>({key,value}));}
  const currentScene = computed(() => email.value?.unconfigured_analysis?.scene || email.value?.pending_reply_scene || email.value?.cutover_scene || '');
  const needsTimeReview = computed(() => email.value?.unconfigured_analysis?.analysis_status==='needs_review');
  const replyState = computed(() => email.value?.reply_status ? tt('discovery.'+email.value.reply_status) : tt('cw.unknownReply'));
  const pendingActions = computed(() => {
    const record=email.value;if(!record || record.manual_completion)return [];
    const result=[];
    if(record.api_forward?.status==='failed'||record.ai_tasks?.some(task=>task.status==='failed'))result.push({tab:'review',text:tt('cutover.detail.apiForwardStatus.failed')});
    if(needsTimeReview.value)result.push({tab:'review',text:tt('discovery.needs_review')});
    if(record.reply_status==='pending')result.push({tab:'reply',text:tt('cutover.list.replyPending')});
    if(['sending','send_uncertain'].includes(record.reply_status))result.push({tab:'reply',text:replyState.value});
    if(isConfigured.value&&pendingLineCount.value)result.push({tab:'lines',text:tt('cutover.list.unmatchedLines',{count:pendingLineCount.value})});
    for(const status of ['report_failed','reporting','draft','confirmed']) {
      const count=(record.tasks||[]).filter(task=>task.status===status).length;
      if(count)result.push({tab:'report',text:statusText(status)+' · '+count});
    }
    return result;
  });
  function beijing(value){if(!value||!/(Z|[+-]\d{2}:?\d{2})$/.test(value)||!Number.isFinite(Date.parse(value)))return '';
    return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(new Date(value)).replaceAll('/','-');}
  const windowSummary = computed(() => {
    const analysis=email.value?.unconfigured_analysis;
    if(analysis){const start=beijing(analysis.cutover_start),end=beijing(analysis.cutover_end);return {value:[start||'—',end||'—'].join(' — '),zone:'UTC+8'};}
    const raw=String(savedResult.value.cutover_time||''),zone=String(savedResult.value.cutover_timezone||'');
    const parts=raw.split('/');
    const offset=/^(UTC|GMT|Etc\/UTC)$/i.test(zone)?'Z':/^(Asia\/Shanghai|Asia\/Hong_Kong|UTC\+8|GMT\+8)$/i.test(zone)?'+08:00':null;
    if(parts.length===2&&offset&&parts.every(part=>/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?$/.test(part.trim()))){const converted=parts.map(part=>beijing(part.trim().replace(' ','T')+offset));if(converted.every(Boolean))return {value:converted.join(' — '),zone:'UTC+8'};}
    return {value:raw||'—',zone:zone||tt('discovery.needs_review')};
  });
  const safeMailHtml = computed(() => {if(!email.value?.html_content)return '';try{return buildLocalSupplierPreview(email.value.html_content);}catch{return '';}});
  function openAdvanced() {
    activeTab.value='review'; showAdvanced.value=true;
    nextTick(()=>document.getElementById('cw-advanced')?.scrollIntoView({block:'start',behavior:'smooth'}));
  }
  function pickerTime(value) {
    const text=String(value || '').trim().replace('T',' ');
    return text.length===16 ? text+':00' : text;
  }
  function openResultEditor(){
    if(!canEditMail.value||!isConfigured.value)return;
    const base=readPayload(extractionDraft.value);
    if(!Object.keys(base).length){NocMessage.warning(tt('cw.emptyResult'));return;}
    resultBase.value=JSON.parse(JSON.stringify(base));resultForm.value=JSON.parse(JSON.stringify(base));
    const parts=String(base.cutover_time||'').split('/');
    usesDateInputs.value=parts.length===2&&parts.every(part=>/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?$/.test(part.trim()));
    formStart.value=usesDateInputs.value?pickerTime(parts[0]):'';
    formEnd.value=usesDateInputs.value?pickerTime(parts[1]):'';
    resultError.value='';resultDialog.value=true;
  }
  async function saveBusinessResult(){
    if(!canEditMail.value)return;
    const next=JSON.parse(JSON.stringify(resultForm.value));
    if(usesDateInputs.value){
      if(!formStart.value||!formEnd.value||!Number.isFinite(Date.parse(formStart.value))||!Number.isFinite(Date.parse(formEnd.value))||formEnd.value<=formStart.value){resultError.value=tt('cw.invalidTime');return;}
      const parts=String(resultBase.value.cutover_time).split('/').map(pickerTime);
      if(parts[0]!==formStart.value||parts[1]!==formEnd.value)next.cutover_time=[formStart.value,formEnd.value].join('/');
    }
    const previous=extractionDraft.value;
    extractionDraft.value=JSON.stringify(next,null,2);
    if(await saveExtraction(false)){resultDialog.value=false;resultError.value='';}
    else {extractionDraft.value=previous;resultError.value=tt('common.requestFailed');}
  }
  function setTab(tab){activeTab.value=tab;}
  function onTabKey(event){
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    const tabs=[...event.currentTarget.querySelectorAll('[role="tab"]')];
    const index=tabs.indexOf(event.target);if(index<0)return;
    event.preventDefault();
    const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
    tabs[next].click();tabs[next].focus();
  }
  function backToList(){navigateTo('cutoverTasks');}
  watch(()=>email.value?.id,()=>{activeTab.value='review';showAdvanced.value=false;tasksStale.value=false;resultDialog.value=false;});
  return {...attachmentPreview,activeTab,showAdvanced,resultDialog,resultError,resultForm,formStart,formEnd,usesDateInputs,tasksStale,sourceDrawer,taskLoading,taskError,
    isConfigured,workBusy,completionBusy,tasksReporting,canEditMail,canReply,savedResult,hasResult,reviewFields,reviewLines,reviewLineColumns,editingLines,lineColumns,scalar,fieldLabel,display,openAdvanced,
    pendingLineCount,matchedLineCount,lineEntries,lineIdentifiers,lineState,needsLineReview,currentScene,needsTimeReview,replyState,pendingActions,windowSummary,safeMailHtml,
    openResultEditor,saveBusinessResult,setTab,onTabKey,backToList};
}

const CUTOVER_WORKBENCH_TEMPLATE = `
<div class="view-body cutover-workbench" v-loading="loading">
  <div v-if="!loading && !email" class="cw-empty"><p>{{ $t('cw.failedLoad') }}</p><ui-button @click="loadDetail">{{ $t('common.refresh') }}</ui-button></div>
  <template v-if="email">
    <ui-button text class="cw-back" @click="backToList">← {{ $t('cw.back') }}</ui-button>
    <div class="cw-heading"><div><h2>{{ email.supplier_name || email.sender }} <span v-if="savedResult.carrier_ticket_no">· {{ savedResult.carrier_ticket_no }}</span></h2><p class="supplier-context-detail">{{ email.subject }}</p></div>
      <div class="cw-header-actions" role="group" :aria-label="$t('common.actions')"><ui-button v-if="!email.manual_completion" size="small" :disabled="!canEditMail" :loading="completionBusy" @click="completeEmail">{{ $t('manualCutover.complete') }}</ui-button><ui-button size="small" :icon="icons.Message" :disabled="!canOperateMailbox(email.receiver) || workBusy" :loading="readStateBusy" @click="toggleReadState">{{ email.is_read ? $t('common.markAsUnread') : $t('common.markAsRead') }}</ui-button><ui-button size="small" :icon="icons.Setting" @click="openAdvanced">{{ $t('cw.advanced') }}</ui-button><ui-button size="small" type="danger" plain :icon="icons.Delete" class="cutover-email-delete-action" :title="$t('cutover.delete.detailAction')" :disabled="!canOperateMailbox(email.receiver) || workBusy || tasksReporting || readStateBusy" :loading="deleteBusy" @click="deleteEmail">{{ $t('common.delete') }}</ui-button></div>
    </div>
    <div class="cw-window"><div class="cw-window-time"><span>{{ fieldLabel('cutover_time') }}</span><strong>{{ windowSummary.value }}</strong><span class="cw-window-zone">{{ windowSummary.zone }}</span></div><div class="cw-window-tags"><ui-tag v-if="needsTimeReview" class="cw-scene-tag" size="small" type="warning">{{ $t('discovery.needs_review') }}</ui-tag><ui-tag v-else-if="currentScene" class="cw-scene-tag" size="small" :type="currentScene === 'normal' ? 'success' : sceneTagType(currentScene)">{{ sceneText(currentScene) }}</ui-tag><ui-tag v-if="!isConfigured" size="small" type="info">{{ $t('discovery.title') }}</ui-tag><ui-tag v-if="email.mail_type" size="small" type="primary">{{ email.mail_type }}</ui-tag></div></div>
    <div v-if="email.manual_completion" class="manual-completion-audit" role="status"><div><div class="manual-audit-heading"><span class="manual-mark-badge">{{ $t('manualCutover.manualBadge') }}</span><strong>{{ $t('manualCutover.completed') }}</strong><span>{{ email.manual_completion.by }}</span><time>{{ email.manual_completion.at.slice(0,19).replace('T',' ') }}</time></div><p>{{ email.manual_completion.note }}</p></div><ui-button v-if="canOperateMailbox(email.receiver)" size="small" :disabled="workBusy" :loading="completionBusy" :icon="icons.RefreshLeft" @click="undoEmailCompletion">{{ $t('manualCutover.undoComplete') }}</ui-button></div>
    <div v-else class="cw-pending"><strong>{{ $t('cw.current') }}</strong><ui-button v-for="action in pendingActions" :key="action.text" text @click="setTab(action.tab)">{{ action.text }} →</ui-button><span v-if="!pendingActions.length" class="muted">{{ $t('cw.noPending') }}</span></div>
    <details v-if="email.manual_completion_history?.length" class="manual-action-history manual-completion-history"><summary>{{ $t('manualCutover.history') }} · {{ email.manual_completion_history.length }}</summary><ol><li v-for="(event,index) in email.manual_completion_history" :key="index"><div><strong>{{ $t('manualCutover.actions.'+event.action) }}</strong><span>{{ event.by }}</span><time>{{ event.at?.slice(0,19).replace('T',' ') }}</time></div><p>{{ event.note }}</p></li></ol></details>
    <p v-if="!canOperateMailbox(email.receiver)" class="cw-notice">{{ $t('cw.readonly') }}</p><p v-else-if="tasksReporting" class="cw-notice">{{ $t('cw.locked') }}</p>
    <div class="cw-tabs" role="tablist" @keydown="onTabKey" :aria-label="$t('cutover.detail.breadcrumbTitle')">
      <button v-for="tab in ['review', ...(isConfigured ? ['lines'] : []), 'reply', ...(isConfigured ? ['report'] : []), 'history']" :key="tab" :id="'cw-tab-'+tab" role="tab" :aria-controls="'cw-panel-'+tab" :aria-selected="activeTab===tab" :tabindex="activeTab===tab ? 0 : -1" :class="{active:activeTab===tab}" @click="setTab(tab)">{{ $t('cw.'+tab) }}<span v-if="tab==='lines' && pendingLineCount">{{ pendingLineCount }}</span><span v-if="tab==='reply' && email.reply_status==='pending'">{{ $t('discovery.review') }}</span></button>
      <ui-button v-if="activeTab!=='review'" text class="cw-source-link" @click="sourceDrawer=true">{{ $t('cw.source') }} ↗</ui-button>
    </div>
    <section v-show="activeTab==='review'" id="cw-panel-review" role="tabpanel" aria-labelledby="cw-tab-review">
      <div class="cw-compare"><section class="cw-panel cw-source"><div class="cw-panel-head"><h2>{{ $t('cw.source') }}</h2></div><dl class="cw-mail-metadata"><div><dt>{{ $t('common.sender') }}</dt><dd>{{ email.sender }}</dd></div><div><dt>{{ $t('common.receiverMailbox') }}</dt><dd>{{ mailboxLabel(email.receiver) }}</dd></div><div><dt>{{ $t('common.receiveTime') }}</dt><dd>{{ String(email.create_time || '').slice(0,19) }}</dd></div></dl>
<mail-attachment-list :items="attachments" :selected="selectedAttachment" :busy="attachmentBusy" @preview="openAttachment"></mail-attachment-list>
<mail-attachment-preview v-if="selectedAttachment" :item="selectedAttachment" :data="attachmentData" :busy="attachmentBusy" :error="attachmentError" @close="closeAttachment" @retry="openAttachment"></mail-attachment-preview>
<div v-else class="cw-mail-body"><iframe v-if="safeMailHtml" class="email-html-frame" sandbox="" referrerpolicy="no-referrer" :srcdoc="safeMailHtml" :title="$t('cw.source')"></iframe><pre v-else class="email-content-block">{{ email.content || $t('cw.noBody') }}</pre></div>
</section>
      <section class="cw-panel cw-results"><div class="cw-panel-head"><h2>{{ $t('cw.results') }}</h2><ui-button v-if="isConfigured && hasResult" size="small" :disabled="!canEditMail" @click="openResultEditor">{{ $t('cw.edit') }}</ui-button></div>
      <p class="cw-hint">{{ $t('cw.editHint') }}</p>
              <div v-if="email.processing_origin !== 'unconfigured'" class="api-forward-card"
             :class="'api-forward-' + (apiForwardBusy ? 'forwarding' : (email.api_forward.status || 'not_recorded'))"
             role="status" aria-live="polite" :aria-busy="apiForwardBusy">
          <div class="api-forward-main">
            <div class="api-forward-head">
              <strong>{{ $t('cutover.detail.apiForwardTitle') }}</strong>
              <ui-tag :type="apiForwardBusy ? 'warning' : (email.api_forward.status === 'succeeded' ? 'success' : (email.api_forward.status === 'failed' ? 'danger' : (email.api_forward.status === 'forwarding' ? 'warning' : 'info')))"
                      size="small" effect="plain">
                {{ $t('cutover.detail.apiForwardStatus.' + (apiForwardBusy ? 'forwarding' : (email.api_forward.status || 'not_recorded'))) }}
              </ui-tag>
              <span v-if="email.api_forward.updated_at" class="mono muted">
                {{ $t('cutover.detail.apiForwardTime', { time: email.api_forward.updated_at }) }}
              </span>
            </div>
            <p v-if="email.api_forward.error && !apiForwardBusy" class="api-forward-error" role="alert">
              <span>{{ $t('cutover.detail.apiForwardReason') }}</span>
              {{ email.api_forward.error }}
            </p>
          </div>
          <ui-button v-if="email.api_forward.status === 'failed'" type="primary"
                     :loading="apiForwardBusy" :disabled="!canEditMail"
                     @click="retryApiForward">
            {{ $t('cutover.detail.apiForwardRetry') }}
          </ui-button>
        </div>


      <mail-analysis-panel :record="email" @changed="loadDetail"></mail-analysis-panel>
      <template v-if="isConfigured"><div v-if="hasResult" class="cw-fields"><div v-for="field in reviewFields" :key="field.key" class="cw-field"><span>{{ field.label }}</span><strong>{{ field.value }}</strong></div></div><p v-else class="cw-empty">{{ $t('cw.emptyResult') }}</p>
      <section class="cw-result-lines"><div class="cw-panel-head"><h3>{{ $t('supplierReview.lineInfo') }}</h3><span class="muted">{{ $t('supplierReview.lineCount',{count:reviewLines.length}) }}</span></div>
        <div v-if="reviewLines.length" class="cw-result-line-table" tabindex="0" :aria-label="$t('supplierReview.lineInfo')"><table><thead><tr><th scope="col">#</th><th v-for="key in reviewLineColumns" :key="key" scope="col">{{ key }}</th></tr></thead><tbody><tr v-for="(line,index) in reviewLines" :key="index"><th scope="row">{{ index+1 }}</th><td v-for="key in reviewLineColumns" :key="key">{{ display(line[key]) }}</td></tr></tbody></table></div>
        <p v-else class="cw-hint">{{ $t('supplierReview.noLines') }}</p>
      </section>
      <p class="cw-hint">{{ $t('cw.historicalRisk') }}</p>        <!-- 割接场景提示（已回复拒绝割接时展示） -->
        <div v-if="email.processing_origin !== 'unconfigured' && isRejectedScene(email.cutover_scene)"
             class="scene-notice" :class="'scene-' + email.cutover_scene">
          <ui-tag :type="sceneTagType(email.cutover_scene)" effect="dark" size="small">
            {{ sceneText(email.cutover_scene, email.cutover_scene_label) }}
          </ui-tag>
          <span v-if="email.cutover_scene === 'emergency'">{{ $t('cutover.detail.sceneNoticeEmergency') }}</span>
          <span v-else-if="email.cutover_scene === 'major_event'">{{ $t('cutover.detail.sceneNoticeMajorEvent') }}</span>
          <span v-else-if="email.cutover_scene === 'in_window'">{{ $t('cutover.detail.sceneNoticeInWindow') }}</span>
          <span v-else-if="email.cutover_scene === 'rule_skipped'">{{ email.cutover_scene_remark || $t('cutover.detail.sceneNoticeRuleSkipped') }}</span>
          <span v-if="email.reply_time" class="mono muted">{{ email.reply_time }}</span>
        </div>

        <!-- 重复邮件提示 -->
        <div v-if="email.is_duplicate" class="scene-notice scene-duplicate">
          <ui-tag type="info" effect="plain" size="small">{{ $t('cutover.tag.duplicate') }}</ui-tag>
          <span>{{ $t('cutover.detail.duplicateNotice') }}</span>
        </div>


      <div class="cw-panel-footer"><span>{{ $t('cw.matchedCount',{matched:matchedLineCount,pending:pendingLineCount}) }}</span><ui-button text @click="setTab('lines')">{{ $t('cw.lines') }} →</ui-button></div></template>
      </section></div>
      <details id="cw-advanced" class="cw-advanced-toggle" :open="showAdvanced" @toggle="showAdvanced=$event.target.open"><summary>{{ $t('cw.advanced') }}</summary><div v-if="isConfigured && showAdvanced" class="cw-panel">            <div class="extraction-panel">
              <div class="extraction-toolbar">
                <span class="extraction-format-label">JSON</span>
                <span>{{ $t('cutover.detail.extractionEditorHint') }}</span>
                <span v-if="email.supplier_name" class="muted">{{ $t('common.supplier') }}：{{ email.supplier_name }}</span>
              </div>
              <ui-input v-model="extractionDraft" type="textarea" :rows="16" :disabled="!canEditMail"
                        :aria-label="$t('cutover.detail.extractResult')" class="extraction-editor" spellcheck="false"></ui-input>
              <div class="extraction-footer">
                <p class="extraction-footer-note">{{ $t('cutover.detail.extractionSaveHint') }}</p>
                <div class="extraction-actions">
                  <ui-button :disabled="!canEditMail" :loading="extractionBusy" @click="saveExtraction()">{{ $t('cutover.detail.saveRematch') }}</ui-button>
                  <ui-button type="primary" :disabled="!canEditMail" :loading="extractionBusy" @click="saveExtraction(true)">{{ $t('cutover.detail.generateTasks') }}</ui-button>
                </div>
              </div>
            </div>
</div><pre v-else-if="showAdvanced" class="cw-json">{{ email.unconfigured_analysis || {} }}</pre></details>
    </section>
    <section v-if="isConfigured" v-show="activeTab==='lines'" id="cw-panel-lines" role="tabpanel" aria-labelledby="cw-tab-lines">
      <div class="cw-section-head"><div><h2>{{ $t('cw.lines') }}</h2><p>{{ $t('cw.matchedCount',{matched:matchedLineCount,pending:pendingLineCount}) }}</p></div></div>
      <p v-if="tasksStale" class="cw-notice" role="status">{{ $t('cw.staleTasks') }}</p>        <!-- 线路表匹配结果 -->
        <div v-if="email.processing_origin !== 'unconfigured'" class="block-section">
          <div class="block-head">
            <span>{{ $t('cutover.detail.lineTableTitle') }}</span>
            <span v-if="email.line_table && email.line_table.supplier" class="muted">
              {{ $t('cutover.detail.supplierPrefix', { name: email.line_table.supplier }) }}
            </span>
          </div>
          <p v-if="!email.line_table && isRejectedScene(email.cutover_scene)" class="empty-inline">{{ $t('cutover.detail.lineTableRejected') }}</p>
          <p v-else-if="!email.line_table" class="empty-inline">{{ $t('cutover.detail.lineTableNoTask') }}</p>
          <p v-else-if="email.line_table.error" class="warn-text">{{ $t('cutover.detail.lineTableError', { error: email.line_table.error }) }}</p>
          <p v-else-if="!(email.line_table.lines || []).length" class="empty-inline">{{ $t('cutover.detail.lineTableNoLines') }}</p>
          <template v-else>
            <div v-for="{line, index: lineIndex} in lineEntries" :key="lineIndex" class="line-match-block">
              <div class="cw-line-source"><ui-tag :type="needsLineReview(line) ? 'warning' : 'success'">{{ lineState(line) }}</ui-tag><span v-for="identifier in lineIdentifiers(line)" :key="identifier.key"><code>{{ identifier.key }}</code> {{ identifier.value }}</span></div>
              <div class="line-match-heading">
                <p class="cell-main">{{ $t('cutover.detail.lineEntry', { index: lineIndex + 1, keywords: (line.keywords || []).join('、') || '-' }) }}</p>
                <ui-tooltip v-if="isAutomaticLineMatch(line)" :content="$t(editingLineBindings[lineIndex] ? 'cutover.detail.cancelMatchEdit' : 'cutover.detail.editMatch')" :trigger="['hover', 'focus']" placement="top">
                  <ui-button text circle :icon="editingLineBindings[lineIndex] ? icons.Close : icons.Edit"
                             :disabled="!canEditMail" :aria-expanded="!!editingLineBindings[lineIndex]"
                             :aria-label="$t(editingLineBindings[lineIndex] ? 'cutover.detail.cancelMatchEdit' : 'cutover.detail.editMatch')"
                             @click="toggleLineBindingEditor(line, lineIndex)"></ui-button>
                </ui-tooltip>
              </div>
              <div v-if="!isAutomaticLineMatch(line) || editingLineBindings[lineIndex]" class="line-binding-controls">
                <ui-select v-if="line.circuits && line.circuits.length > 1" v-model="manualBindings[lineIndex]"
                           class="line-binding-circuit-select" :disabled="!canEditMail" filterable allow-create clearable default-first-option
                           :placeholder="$t('cutover.detail.selectOrEnterCircuit')" aria-label="Circuit ID"
                           @change="selectCircuitCandidate(line, lineIndex, $event)">
                  <ui-option v-for="(circuit, candidateIndex) in line.circuits" :key="candidateIndex"
                             :label="circuit.circuit_id || '-'" :value="circuit.circuit_id || ''" :disabled="!circuit.circuit_id">
                    <span class="line-candidate-id">{{ circuit.circuit_id || '-' }}</span>
                    <span class="line-candidate-type">{{ circuit.line_type || '-' }} · {{ circuit.line_status || '-' }}</span>
                  </ui-option>
                </ui-select>
                <ui-input v-else v-model="manualBindings[lineIndex]" :disabled="!canEditMail"
                          :placeholder="$t('cutover.detail.bindCircuitPlaceholder')" aria-label="Circuit ID" clearable></ui-input>
                <ui-select v-model="manualBindingTypes[lineIndex]" :disabled="!canEditMail" class="line-binding-type"
                           :aria-label="$t('cutover.detail.bindingType')">
                  <ui-option :label="$t('cutover.detail.bindCustomer')" value="客户"></ui-option>
                  <ui-option :label="$t('cutover.detail.bindBackbone')" value="骨干"></ui-option>
                </ui-select>
                <ui-button :disabled="!canEditMail" :loading="extractionBusy" @click="bindLine(lineIndex)">{{ $t('cutover.detail.bindCircuit') }}</ui-button>
                <span class="muted">{{ $t('cutover.detail.bindCircuitHint') }}</span>
              </div>
              <p v-if="line.manual_unlisted" class="warn-text" role="status">{{ $t('cutover.detail.unlistedBinding') }}</p>
              <p v-if="!(line.circuits || []).length" class="warn-text">{{ $t('cutover.detail.lineNoMatch') }}</p>
              <p v-else-if="line.circuits.length > 1" class="warn-text">
                {{ $t('cutover.detail.lineMultiMatch', { count: line.circuits.length }) }}
              </p>
              <p v-if="line.task_generation_blocked" class="warn-text" role="alert">
                {{ $t('cutover.detail.lineStatusBlocked', { statuses: (line.blocked_statuses || []).join('、') || '-' }) }}
              </p>
              <ui-table v-if="(line.circuits || []).length" :data="line.circuits" stripe>
                <ui-table-column prop="supplier" label="Supplier" min-width="120">
                  <template #default="{ row }">
                    <span class="cell-main">{{ row.supplier || '-' }}</span>
                  </template>
                </ui-table-column>
                <ui-table-column label="Supplier Circuit ID" min-width="220">
                  <template #default="{ row }">
                    <span class="mono pre-wrap">{{ row.supplier_circuit_id || '-' }}</span>
                  </template>
                </ui-table-column>
                <ui-table-column label="Circuit ID" min-width="220">
                  <template #default="{ row }">
                    <span class="mono pre-wrap">{{ row.circuit_id || '-' }}</span>
                  </template>
                </ui-table-column>
                <ui-table-column :label="$t('circuits.lineType')" width="110">
                  <template #default="{ row }">
                    <span>{{ row.line_type || '-' }}</span>
                  </template>
                </ui-table-column>
                <ui-table-column :label="$t('circuits.lineStatus')" width="110">
                  <template #default="{ row }">
                    <span>{{ row.line_status || '-' }}</span>
                  </template>
                </ui-table-column>
                <ui-table-column :label="$t('common.remark')" min-width="160">
                  <template #default="{ row }">
                    <span class="muted pre-wrap">{{ row.remark || '-' }}</span>
                  </template>
                </ui-table-column>
              </ui-table>
            </div>
          </template>
          <div v-if="hasResult" class="cutover-regenerate-footer">
            <div class="cutover-regenerate-summary">
              <span class="cell-main">{{ $t('cutover.detail.regenerateSummary', matchedTypeCounts) }}</span>
              <span class="muted">{{ $t('cutover.detail.regenerateHint') }}</span>
            </div>
            <ui-button plain :disabled="!canEditMail" :loading="extractionBusy" @click="regenerateTasks">
              {{ $t('cutover.detail.regenerateTasks') }}
            </ui-button>
          </div>
        </div>


    </section>
    <section v-show="activeTab==='reply'" id="cw-panel-reply" role="tabpanel" aria-labelledby="cw-tab-reply"><p class="cw-hint">{{ $t('cw.replyScope') }}</p>        <div v-if="email.reply_status === 'pending'" class="reply-pending-card">
          <div class="reply-pending-head">
            <ui-tag type="warning" effect="dark" size="small">{{ $t('cutover.detail.replyPendingTitle') }}</ui-tag>
            <ui-tag v-if="isRejectedScene(email.pending_reply_scene)"
                    :type="sceneTagType(email.pending_reply_scene)" effect="plain" size="small">
              {{ sceneText(email.pending_reply_scene, email.pending_reply_scene_label) }}
            </ui-tag>
            <span class="muted">{{ $t('cutover.detail.replyPendingHint') }}</span>
          </div>
          <div class="reply-recipients">
            <span class="reply-recipients-label">
              <ui-icon class="reply-recipients-icon"><Promotion /></ui-icon>
              {{ $t('cutover.detail.replyRecipient') }}
            </span>
            <ui-select v-model="replyRecipients" :disabled="!canReply" multiple filterable allow-create default-first-option
                       :placeholder="$t('cutover.detail.replyRecipientPlaceholder')" class="reply-recipients-select">
              <ui-option v-for="addr in recipientOptions" :key="addr" :label="addr" :value="addr"></ui-option>
            </ui-select>
          </div>
          <div class="reply-recipients">
            <span class="reply-recipients-label">{{ $t('cutover.detail.replyCc') }}</span>
            <ui-select v-model="replyCcRecipients" :disabled="!canReply" multiple filterable allow-create clearable default-first-option
                       :placeholder="$t('cutover.detail.replyCcPlaceholder')" class="reply-recipients-select">
              <ui-option v-for="addr in replyCcRecipients" :key="addr" :label="addr" :value="addr"></ui-option>
            </ui-select>
          </div>
          <ui-input v-model="replyDraft" type="textarea" :disabled="!canReply" :rows="12"
                    :placeholder="$t('cutover.detail.replyContentLabel')"></ui-input>
          <div class="reply-pending-actions">
            <ui-button :disabled="!canReply" @click="cancelReply">{{ $t('cutover.detail.replyCancel') }}</ui-button>
            <ui-button type="primary" :loading="replyBusy" :disabled="!canReply || !replyDraft.trim()" @click="confirmReply">
              {{ $t('cutover.detail.replyConfirmSend') }}
            </ui-button>
          </div>
        </div>

<div v-if="email.reply_status!=='pending' && (email.reply_status!=='sent' || !email.reply_history?.length)" class="cw-panel cw-empty"><h2>{{ replyState }}</h2><p>{{ email.reply_time || $t('cw.replyEmpty') }}</p></div>
      <section v-if="email.reply_history?.length" class="cw-reply-history" :aria-label="$t('cw.replyRecords')">
        <div class="cw-panel-head"><h2>{{ $t('cw.replyRecords') }}</h2><span class="muted">{{ email.reply_history.length }}</span></div>
        <article v-for="(reply,index) in email.reply_history.slice().reverse()" :key="index" class="cw-panel cw-sent-reply">
          <div class="cw-panel-head"><ui-tag type="success">{{ $t('cutover.detail.replySent') }}</ui-tag><time>{{ $t('cw.sentAt') }}：{{ reply.sent_at || $t('cw.notRecorded') }}</time></div>
          <dl class="cw-reply-addresses"><dt>{{ $t('cutover.detail.replyRecipient') }}</dt><dd>{{ reply.recipients?.join('、') || $t('cw.notRecorded') }}</dd><dt>{{ $t('cutover.detail.replyCc') }}</dt><dd>{{ reply.cc_recipients == null ? $t('cw.notRecorded') : reply.cc_recipients.join('、') || $t('cw.noCc') }}</dd></dl>
          <p v-if="reply.legacy" class="cw-hint">{{ $t('cw.legacyReply') }}</p>
          <div class="cw-reply-body"><h3>{{ $t('cutover.detail.replyContentLabel') }}</h3><pre>{{ reply.content || $t('cw.notRecorded') }}</pre></div>
        </article>
      </section>
    </section>
    <section v-if="isConfigured" v-show="activeTab==='report'" id="cw-panel-report" role="tabpanel" aria-labelledby="cw-tab-report"><div class="cw-section-head"><div><h2>{{ $t('cw.report') }}</h2><p>{{ $t('cw.reportHint') }}</p></div></div><p v-if="tasksStale" class="cw-notice">{{ $t('cw.staleTasks') }}</p>
      <div class="cw-task-grid" :class="{'cw-task-grid-selected':!!detailTask}"><article v-for="task in email.tasks || []" :key="task.id" class="cw-panel cw-task-card"><div class="cw-panel-head"><h2>{{ lineTypeText(task) }}</h2><ui-tag :type="statusTagType(task.status)">{{ statusText(task.status,task.status_label) }}</ui-tag></div><dl><div><dt>{{ $t('cutover.task.filledLines') }}</dt><dd>{{ $t('cutover.task.lineCount',{count:taskLineCount(task)}) }}</dd></div><div><dt>{{ $t('common.carrierTicketNo') }}</dt><dd>{{ task.carrier_ticket_no || '—' }}</dd></div><div><dt>{{ $t('cutover.detail.validationColumn') }}</dt><dd>{{ task.validation_count ? $t('cutover.detail.validationCount',{count:task.validation_count}) : '—' }}</dd></div><div><dt>{{ $t('common.updateTime') }}</dt><dd>{{ String(task.update_time || '').slice(0,19) }}</dd></div></dl><div class="cw-panel-footer"><span class="muted">#{{ task.id }}</span><ui-button type="primary" :loading="taskLoading && requestedTaskId===task.id" @click="openTask(task.id)">{{ $t('cw.openTask') }}</ui-button></div></article></div>
      <div v-if="!email.tasks?.length" class="cw-panel cw-empty"><p>{{ email.is_duplicate ? $t('cutover.detail.taskDuplicateIgnored') : email.cutover_scene==='rule_skipped' ? $t('cutover.detail.taskRuleSkipped') : $t('cutover.detail.taskEmpty') }}</p><ui-button v-if="hasResult && !email.is_duplicate && email.cutover_scene!=='rule_skipped'" :disabled="!canEditMail" @click="setTab('lines')">{{ $t('cw.lines') }} →</ui-button></div>
    </section>
    <section v-show="activeTab==='history'" id="cw-panel-history" role="tabpanel" aria-labelledby="cw-tab-history"><div class="cw-panel cw-history"><div><time>{{ String(email.create_time || '').slice(0,19) }}</time><h3>{{ $t('cw.received') }}</h3><p>{{ email.sender }} → {{ mailboxLabel(email.receiver) }}</p></div><div v-if="isConfigured && email.api_forward?.updated_at"><time>{{ email.api_forward.updated_at }}</time><h3>{{ $t('cw.parsed') }}</h3><p>{{ $t('cutover.detail.apiForwardStatus.'+email.api_forward.status) }}</p><p v-if="email.api_forward.error" class="warn-text">{{ email.api_forward.error }}</p></div><div v-if="email.reply_status"><time>{{ email.reply_time || '—' }}</time><h3>{{ $t('cw.replyState') }}</h3><p>{{ replyState }}</p></div><div v-for="task in email.tasks || []" :key="task.id"><time>{{ String(task.update_time || '').slice(0,19) }}</time><h3>{{ lineTypeText(task) }} · {{ statusText(task.status,task.status_label) }}</h3><p>#{{ task.id }} · {{ $t('cw.taskState') }}</p><ui-button text @click="openTask(task.id, 'history')">{{ $t('cw.taskRecords') }} →</ui-button></div></div></section>
    <div v-show="['report','history'].includes(activeTab)" class="cw-selected-task"><p v-if="taskLoading" role="status">{{ $t('cw.loadingTask') }}</p><div v-else-if="taskError" class="cw-notice" role="alert">{{ taskError }} <ui-button @click="openTask(requestedTaskId, activeTab)">{{ $t('common.refresh') }}</ui-button></div><task-detail-panel v-if="detailTask" :key="detailTask.id" :task="detailTask" operator-mode :history-only="activeTab==='history'" @changed="onTaskChanged" @dirty-change="taskFormDirty=$event" @collapse="requestCloseTask"></task-detail-panel></div>
    <ui-drawer v-model="sourceDrawer" :title="$t('cw.source')" size="55%" append-to-body class="cw-source-drawer"><template v-if="sourceDrawer"><dl class="cw-mail-metadata"><div><dt>{{ $t('common.sender') }}</dt><dd>{{ email.sender }}</dd></div><div><dt>{{ $t('common.receiverMailbox') }}</dt><dd>{{ mailboxLabel(email.receiver) }}</dd></div><div><dt>{{ $t('common.receiveTime') }}</dt><dd>{{ String(email.create_time || '').slice(0,19) }}</dd></div></dl>
<mail-attachment-list :items="attachments" :selected="selectedAttachment" :busy="attachmentBusy" @preview="openAttachment"></mail-attachment-list>
<mail-attachment-preview v-if="selectedAttachment" :item="selectedAttachment" :data="attachmentData" :busy="attachmentBusy" :error="attachmentError" @close="closeAttachment" @retry="openAttachment"></mail-attachment-preview>
<div v-else class="cw-mail-body"><iframe v-if="safeMailHtml" class="email-html-frame" sandbox="" referrerpolicy="no-referrer" :srcdoc="safeMailHtml" :title="$t('cw.source')"></iframe><pre v-else class="email-content-block">{{ email.content || $t('cw.noBody') }}</pre></div>
</template></ui-drawer>
    <ui-dialog v-model="resultDialog" :title="$t('cw.edit')" width="960px" class="cw-result-dialog" :close-on-click-modal="false" :close-on-press-escape="!extractionBusy" :show-close="!extractionBusy">
      <p>{{ $t('cw.editHint') }}</p><p class="cw-notice">{{ $t('cw.saveHint') }}</p>
      <div class="cw-edit-fields"><template v-if="usesDateInputs"><label><span>{{ $t('cw.start') }} · {{ resultForm.cutover_timezone || $t('discovery.needs_review') }}</span><ui-date-picker v-model="formStart" type="datetime" format="YYYY-MM-DD HH:mm:ss" value-format="YYYY-MM-DD HH:mm:ss" :aria-label="$t('cw.start')" :placeholder="$t('cw.start')" :disabled="extractionBusy" clearable></ui-date-picker></label><label><span>{{ $t('cw.end') }}</span><ui-date-picker v-model="formEnd" type="datetime" format="YYYY-MM-DD HH:mm:ss" value-format="YYYY-MM-DD HH:mm:ss" :aria-label="$t('cw.end')" :placeholder="$t('cw.end')" :disabled="extractionBusy" clearable></ui-date-picker></label></template><label v-for="key in ['carrier_ticket_no',...(!usesDateInputs?['cutover_time']:[]),'cutover_backup_time','cutover_timezone','cutover_reason','location']" :key="key"><span>{{ fieldLabel(key) }}</span><ui-input v-if="scalar(resultForm[key])" v-model="resultForm[key]" :aria-label="fieldLabel(key)" :type="key==='cutover_reason'?'textarea':'text'" :rows="2" :disabled="extractionBusy"></ui-input><span v-else>{{ $t('cw.complex') }}</span></label></div>
      <h3>{{ $t('cw.lineEdit') }}</h3><div class="cw-edit-lines"><table><thead><tr><th>#</th><th v-for="key in lineColumns" :key="key">{{ key }}</th></tr></thead><tbody><tr v-for="(line,index) in editingLines" :key="index"><td>{{ index+1 }}</td><td v-for="key in lineColumns" :key="key"><ui-input v-if="scalar(line[key])" v-model="line[key]" :aria-label="$t('cw.lineKey',{key,index:index+1})" :disabled="extractionBusy"></ui-input><span v-else>{{ display(line[key]) }}</span></td></tr></tbody></table></div>
      <p v-if="resultError" class="warn-text" role="alert">{{ resultError }}</p><template #footer><ui-button :disabled="extractionBusy" @click="resultDialog=false">{{ $t('common.cancel') }}</ui-button><ui-button type="primary" :loading="extractionBusy" :disabled="!canEditMail" @click="saveBusinessResult">{{ $t('cutover.detail.saveRematch') }}</ui-button></template>
    </ui-dialog>
  </template>
</div>`;
