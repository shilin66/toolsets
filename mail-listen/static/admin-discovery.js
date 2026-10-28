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

const draftReviewMessages = {
  "zh-CN": {
    "title": "审核供应商草稿",
    "unnamed": "待命名供应商",
    "intro": "AI 已整理配置建议，请人工核对后启用。保存草稿不会影响正在处理的邮件。",
    "identity": "确认供应商",
    "samples": "核对邮件样本",
    "rules": "检查提取内容",
    "test": "测试提取效果",
    "nameMissing": "名称待填写",
    "nameFilled": "名称已填写 · 请核对回复地址",
    "sampleMissing": "割接通知样本待补全",
    "sampleReady": "样本已填写 · 请核对原文",
    "queryMissing": "尚未选择线路查询信息",
    "queryCount": "已选择 {count} 项线路查询信息",
    "untested": "尚未测试",
    "tested": "已有测试结果 · 请对照原文",
    "source": "查看原邮件",
    "sourceHint": "核对来源",
    "sampleCount": "已收集 {count} 封邮件",
    "manualName": "供应商名称由您填写，便于后续查找和管理。",
    "senderLabel": "来信发件地址",
    "senderHint": "后续来自此地址的邮件会使用这份配置。",
    "replyHint": "核对正文是否指定了其他回复邮箱；留空时使用来信发件地址。",
    "sampleHint": "用于教系统识别不同邮件类型。请核对割接通知的主题和正文；其他分类有实际样本时再补充。",
    "fixedTitle": "割接信息的识别方式",
    "fixedHint": "逐项核对系统应从哪里读取时间、原因、地点和影响信息。需要调整时，用业务语言描述；使用默认规则不代表已验证准确。",
    "lineTitle": "用于匹配内部线路的信息",
    "lineHint": "每条线路的线路编号、服务编号、订单号等可用于查询内部线路。请保留邮件里的完整编号，并勾选需要查询的项目。",
    "quickHint": "只添加邮件中实际出现的编号；添加后请核对识别说明。",
    "addIdentifier": "添加{label}",
    "fieldCode": "字段 key",
    "fieldCodeHint": "直接作为提取结果的 key，保留大小写和下划线，例如 CircuitId、TGN_NMS_ID。",
    "extractRule": "在哪里找到这项信息",
    "queryUse": "用这项信息查询内部线路",
    "identifierRule": "从正文或可读附件中，提取每条受影响线路对应的{label}。同一行的编号归属同一条线路，保留完整字符串、前导零和标点；不要使用维护工单号，没有明确值时返回空字符串。",
    "otherTitle": "其他信息（可选）",
    "otherHint": "仅在现有信息不够时添加，例如需要额外记录的业务属性。不用于匹配内部线路。",
    "testHint": "使用当前割接通知样本测试，不会启用配置或发送邮件。原邮件附件不会自动带入；如需核对附件中的线路，请先上传对应附件。",
    "testResultHint": "请核对时间、原因和线路编号。返回结果不代表已经准确；修改样本或规则后请重新测试。",
    "advanced": "高级设置：完整提示词",
    "extraHint": "可直接描述特殊情况，例如“正文为通知摘要，线路编号以附件表格为准”。",
    "questions": "AI 提醒您核对",
    "questionsHint": "这是生成时留下的疑问，请结合实际邮件判断。",
    "evidence": "查看 AI 生成依据",
    "nextCollecting": "等待收到割接通知后生成配置",
    "nextGenerating": "正在整理邮件中的配置建议",
    "nextReview": "填写名称，核对后启用",
    "nextFailed": "查看原因后可重试",
    "nextPublished": "后续邮件已使用正式配置",
    "fields": {
      "carrier_ticket_no": "运营商单号",
      "cutover_time": "割接时间",
      "cutover_backup_time": "备用割接时间",
      "cutover_timezone": "时区",
      "cutover_reason": "割接原因",
      "location": "割接地点",
      "ImpactType": "影响类型",
      "ImpactDateTime": "线路中断时间",
      "ImpactDuration": "单次中断时长",
      "InteruptionsCounts": "中断次数",
      "CircuitId": "线路编号",
      "ServiceId": "服务编号",
      "OrderNumber": "订单号",
      "CustomerCircuitId": "客户线路编号"
    }
  },
  "en": {
    "title": "Review supplier draft",
    "unnamed": "Supplier name needed",
    "intro": "AI has prepared suggested rules. Review them before enabling. Saving a draft does not affect mail processing.",
    "identity": "Confirm supplier",
    "samples": "Review mail samples",
    "rules": "Check extracted information",
    "test": "Test extraction",
    "nameMissing": "Supplier name needed",
    "nameFilled": "Name entered · check reply address",
    "sampleMissing": "Complete the cutover notice sample",
    "sampleReady": "Sample entered · check original mail",
    "queryMissing": "No circuit lookup fields selected",
    "queryCount": "{count} circuit lookup fields selected",
    "untested": "Not tested yet",
    "tested": "Results available · compare with original",
    "source": "View original email",
    "sourceHint": "Source material",
    "sampleCount": "{count} mail samples collected",
    "manualName": "Enter a supplier name to identify and manage this configuration.",
    "senderLabel": "Incoming sender address",
    "senderHint": "Future mail from this address will use this configuration.",
    "replyHint": "Check whether the body specifies a different reply address. Leave blank to use the sender address.",
    "sampleHint": "Samples teach the system to recognize mail types. Review the notice subject and body; add other categories when real samples are available.",
    "fixedTitle": "How maintenance information is identified",
    "fixedHint": "Review where time, reason, location and impact are read from. Describe changes in business terms. Default rules have not necessarily been verified.",
    "lineTitle": "Information used to find internal circuits",
    "lineHint": "Circuit IDs, service IDs and order numbers can identify internal circuits. Keep complete identifiers and select the ones to use for lookup.",
    "quickHint": "Only add identifiers present in the mail; review their extraction instructions.",
    "addIdentifier": "Add {label}",
    "fieldCode": "Field key",
    "fieldCodeHint": "Used directly as the extraction output key. Preserve casing and underscores, e.g. CircuitId or TGN_NMS_ID.",
    "extractRule": "Where to find this information",
    "queryUse": "Use for internal circuit lookup",
    "identifierRule": "Extract the {label} for each affected circuit from the body or readable attachment. Keep identifiers from the same row with the same circuit. Preserve full strings, leading zeros and punctuation. Exclude maintenance tickets; return an empty string if no explicit value exists.",
    "otherTitle": "Other information (optional)",
    "otherHint": "Add business attributes only when existing fields are insufficient. These are not used for circuit lookup.",
    "testHint": "Test the current notice sample without enabling the configuration or sending mail. Original attachments are not included automatically; upload relevant files to test their circuit information.",
    "testResultHint": "Check time, reason and circuit identifiers against the original. Results still need review. Test again after changing samples or rules.",
    "advanced": "Advanced: complete prompt",
    "extraHint": "Describe special cases, e.g. “The body is a summary; use circuit identifiers from the attachment table.”",
    "questions": "AI review notes",
    "questionsHint": "These questions were recorded during generation. Check them against the original mail.",
    "evidence": "View AI generation evidence",
    "nextCollecting": "Waiting for a cutover notice",
    "nextGenerating": "Preparing suggested rules",
    "nextReview": "Name, review and enable",
    "nextFailed": "Review the error and retry",
    "nextPublished": "New mail uses the active configuration",
    "fields": {
      "carrier_ticket_no": "Carrier ticket",
      "cutover_time": "Maintenance window",
      "cutover_backup_time": "Backup window",
      "cutover_timezone": "Time zone",
      "cutover_reason": "Maintenance reason",
      "location": "Location",
      "ImpactType": "Impact type",
      "ImpactDateTime": "Circuit outage window",
      "ImpactDuration": "Outage duration",
      "InteruptionsCounts": "Interruption count",
      "CircuitId": "Circuit ID",
      "ServiceId": "Service ID",
      "OrderNumber": "Order number",
      "CustomerCircuitId": "Customer circuit ID"
    }
  },
  "zh-HK": {
    "title": "審核供應商草稿",
    "unnamed": "待命名供應商",
    "intro": "AI 已整理配置建議，請人工核對後啟用。儲存草稿不會影響正在處理的郵件。",
    "identity": "確認供應商",
    "samples": "核對郵件樣本",
    "rules": "檢查提取內容",
    "test": "測試提取效果",
    "nameMissing": "名稱待填寫",
    "nameFilled": "名稱已填寫 · 請核對回覆地址",
    "sampleMissing": "割接通知樣本待補全",
    "sampleReady": "樣本已填寫 · 請核對原文",
    "queryMissing": "尚未選擇線路查詢資訊",
    "queryCount": "已選擇 {count} 項線路查詢資訊",
    "untested": "尚未測試",
    "tested": "已有測試結果 · 請對照原文",
    "source": "查看原郵件",
    "sourceHint": "核對來源",
    "sampleCount": "已收集 {count} 封郵件",
    "manualName": "供應商名稱由您填寫，便於後續查找和管理。",
    "senderLabel": "來信寄件地址",
    "senderHint": "後續來自此地址的郵件會使用這份配置。",
    "replyHint": "核對正文是否指定其他回覆郵箱；留空時使用來信寄件地址。",
    "sampleHint": "用於教系統識別不同郵件類型。請核對割接通知的主旨和正文；其他分類有實際樣本時再補充。",
    "fixedTitle": "割接資訊的識別方式",
    "fixedHint": "逐項核對系統應從哪裏讀取時間、原因、地點和影響資訊。需要調整時，用業務語言描述；使用預設規則不代表已驗證準確。",
    "lineTitle": "用於匹配內部線路的資訊",
    "lineHint": "每條線路的線路編號、服務編號、訂單號等可用於查詢內部線路。請保留郵件裏的完整編號，並勾選需要查詢的項目。",
    "quickHint": "只新增郵件中實際出現的編號；新增後請核對識別說明。",
    "addIdentifier": "新增{label}",
    "fieldCode": "欄位 key",
    "fieldCodeHint": "直接作為提取結果的 key，保留大小寫和底線，例如 CircuitId、TGN_NMS_ID。",
    "extractRule": "在哪裏找到這項資訊",
    "queryUse": "用這項資訊查詢內部線路",
    "identifierRule": "從正文或可讀附件中，提取每條受影響線路對應的{label}。同一行的編號歸屬同一條線路，保留完整字串、前導零和標點；不要使用維護工單號，沒有明確值時回傳空字串。",
    "otherTitle": "其他資訊（可選）",
    "otherHint": "僅在現有資訊不夠時新增，例如需額外記錄的業務屬性。不用於匹配內部線路。",
    "testHint": "使用目前割接通知樣本測試，不會啟用配置或傳送郵件。原郵件附件不會自動帶入；如需核對附件中的線路，請先上傳對應附件。",
    "testResultHint": "請核對時間、原因和線路編號。回傳結果不代表已經準確；修改樣本或規則後請重新測試。",
    "advanced": "進階設定：完整提示詞",
    "extraHint": "可直接描述特殊情況，例如「正文為通知摘要，線路編號以附件表格為準」。",
    "questions": "AI 提醒您核對",
    "questionsHint": "這是生成時留下的疑問，請結合實際郵件判斷。",
    "evidence": "查看 AI 生成依據",
    "nextCollecting": "等待收到割接通知後生成配置",
    "nextGenerating": "正在整理郵件中的配置建議",
    "nextReview": "填寫名稱，核對後啟用",
    "nextFailed": "查看原因後可重試",
    "nextPublished": "後續郵件已使用正式配置",
    "fields": {
      "carrier_ticket_no": "營運商單號",
      "cutover_time": "割接時間",
      "cutover_backup_time": "備用割接時間",
      "cutover_timezone": "時區",
      "cutover_reason": "割接原因",
      "location": "割接地點",
      "ImpactType": "影響類型",
      "ImpactDateTime": "線路中斷時間",
      "ImpactDuration": "單次中斷時長",
      "InteruptionsCounts": "中斷次數",
      "CircuitId": "線路編號",
      "ServiceId": "服務編號",
      "OrderNumber": "訂單號",
      "CustomerCircuitId": "客戶線路編號"
    }
  }
};
for (const [locale, messages] of Object.entries(draftReviewMessages)) {
  i18n.global.mergeLocaleMessage(locale, {draftReview: messages});
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
    const page = ref(1), total = ref(0);
    const editing = ref(false);
    const selectingId = ref(null), deletingId = ref(null), retrying = ref(null);
    const deletedIds = new Set();
    let listRequest = 0, detailRequest = 0, disposed = false;

    function supplierName(row) { return row.draft?.config?.name?.trim() || row.sender; }
    function statusTagType(status) {
      return {review:'warning', published:'success', generation_failed:'danger', generating:'primary'}[status] || 'info';
    }
    function nextAction(status) {
      const key = {collecting:'nextCollecting', generating:'nextGenerating', review:'nextReview', generation_failed:'nextFailed', published:'nextPublished'}[status];
      return key ? tt('draftReview.'+key) : '';
    }
    function timeParts(value) { return String(value || '—').split(/[ T]/, 2); }
    function setDraftQuery(id) {
      const url = new URL(window.location.href);
      if (id) url.searchParams.set('draft', String(id));
      else url.searchParams.delete('draft');
      window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash);
    }
    function clearSelection() {
      detailRequest += 1;
      selected.value = null; editing.value = false; selectingId.value = null;
      setDraftQuery(null);
    }

    async function load() {
      const request = ++listRequest;
      busy.value = true;
      try {
        const result = await requestJson(`/api/supplier-drafts?page=${page.value}&status=${status.value}`);
        if (disposed || request !== listRequest) return;
        const lastPage = Math.max(1, Math.ceil(result.total / 20));
        if (page.value > lastPage) {
          page.value = lastPage;
          await load();
          return;
        }
        items.value = result.items.filter(row => !deletedIds.has(row.id));
        total.value = result.total; error.value = '';
      } catch (exc) { if (!disposed && request === listRequest) error.value = exc.message; }
      finally { if (!disposed && request === listRequest) busy.value = false; }
    }

    async function select(row, {reveal = false} = {}) {
      if (!row || deletedIds.has(row.id) || deletingId.value === row.id) return;
      const request = ++detailRequest;
      selectingId.value = row.id;
      try {
        const result = await requestJson(`/api/supplier-drafts/${row.id}`);
        if (disposed || request !== detailRequest || deletedIds.has(row.id) || deletingId.value === row.id) return;
        const resultStatus = result.status === 'published' ? 'published' : 'unpublished';
        if (resultStatus !== status.value) {
          if (!reveal) { clearSelection(); await load(); return; }
          status.value = resultStatus;
          page.value = 1;
          await load();
          if (disposed || request !== detailRequest) return;
        }
        selected.value = result; editing.value = true;
        setDraftQuery(row.id);
      } catch (exc) {
        if (disposed || request !== detailRequest) return;
        if (exc.status === 404 && (selected.value?.id === row.id || Number(new URLSearchParams(window.location.search).get('draft')) === row.id)) clearSelection();
        NocMessage.error(exc.message);
      } finally {
        if (!disposed && request === detailRequest) { selectingId.value = null; }
      }
    }

    function changePage(value) { page.value = value; load(); }
    function changeStatus(value) {
      if (value === status.value) return;
      status.value = value; page.value = 1; items.value = []; total.value = 0; error.value = '';
      clearSelection();
      load();
    }

    async function retry(row) {
      if (!row || retrying.value !== null) return;
      retrying.value = row.id;
      try {
        await requestJson(`/api/supplier-drafts/${row.id}/retry`, {method:'POST'});
        if (disposed) return;
        await load();
        NocMessage.success(tt('discovery.retryAccepted'));
      }
      catch (exc) { NocMessage.error(exc.message); }
      finally { retrying.value = null; }
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
      listRequest += 1; detailRequest += 1;
      busy.value = false; selectingId.value = null;
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

    async function closeEditor() {
      clearSelection();
      await load();
    }
    async function published() {
      const id = selected.value?.id;
      items.value = items.value.filter(row => row.id !== id);
      total.value = Math.max(0, total.value - 1);
      clearSelection();
      await load();
    }
    onMounted(async () => {
      const id = Number(new URLSearchParams(window.location.search).get('draft'));
      await load();
      if (!disposed && id && detailRequest === 0) await select({id}, {reveal:true});
    });
    onUnmounted(() => { disposed = true; listRequest += 1; detailRequest += 1; });
    return {items, selected, busy, error, status, changeStatus, published, page, total, editing, selectingId, deletingId, retrying,
      supplierName, statusTagType, nextAction, timeParts, load, select, retry, closeEditor, clearSelection,
      changePage, removeDraft, icons:ElementPlusIconsVue};
  },
  template: `<div class="supplier-drafts-workspace">
    <supplier-draft-editor v-if="editing && selected" :key="selected.id" :draft-id="selected.id" @close="closeEditor" @published="published"></supplier-draft-editor>
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
          <ui-table-column :label="$t('common.status')" width="200"><template #default="{row}"><ui-tag class="draft-status-badge" effect="light" :type="statusTagType(row.status)">{{ $t('discovery.'+row.status) }}</ui-tag><p class="draft-next-action">{{ nextAction(row.status) }}</p><p v-if="row.last_error" class="draft-row-error" :title="row.last_error">{{ row.last_error }}</p></template></ui-table-column>
          <ui-table-column :label="$t('discovery.count')" width="88" align="center"><template #default="{row}"><span class="draft-sample-number">{{ row.sample_count }}</span></template></ui-table-column>
          <ui-table-column :label="$t('common.updateTime')" width="140"><template #default="{row}"><span class="draft-update-date">{{ timeParts(row.update_time)[0] }}</span><span class="draft-update-clock">{{ timeParts(row.update_time)[1] }}</span></template></ui-table-column>
          <ui-table-column :label="$t('common.actions')" width="224" align="center" fixed="right">
            <template #default="{row}"><div class="draft-list-row-actions">
              <ui-button size="small" :type="row.status === 'review' ? 'primary' : 'default'" :loading="selectingId === row.id" :disabled="deletingId !== null || retrying !== null" @click="select(row)">{{ $t(row.status === 'review' ? 'discovery.edit' : row.status === 'published' ? 'supplierReview.viewRecord' : 'supplierReview.viewMails') }}</ui-button>
              <ui-button v-if="row.status === 'generation_failed'" size="small" :loading="retrying === row.id" :disabled="deletingId !== null || (retrying !== null && retrying !== row.id)" @click="retry(row)">{{ $t('discovery.retry') }}</ui-button>
              <ui-action type="danger" :loading="deletingId === row.id" :disabled="retrying !== null || (deletingId !== null && deletingId !== row.id)" @click="removeDraft(row)" icon="Delete" :label="$t('common.delete')"></ui-action>
            </div></template>
          </ui-table-column>
          <template #empty><div class="drafts-empty-state"><ui-icon :size="28" aria-hidden="true"><component :is="icons.Document"></component></ui-icon><strong>{{ $t(status === 'published' ? 'discovery.historyEmptyTitle' : 'discovery.emptyTitle') }}</strong><p>{{ $t(status === 'published' ? 'discovery.historyEmpty' : 'discovery.empty') }}</p></div></template>
        </ui-table>
        <footer class="drafts-panel-footer"><span>{{ $t(status === 'published' ? 'discovery.historyTotal' : 'discovery.draftTotal', {count:total}) }}</span>
          <ui-pagination :current-page="page" :total="total" :page-size="20" layout="prev, pager, next" :disabled="busy || deletingId !== null" @current-change="changePage"></ui-pagination>
        </footer>
      </section>
    </template>
  </div>`,
});

const MailAnalysisPanel = defineComponent({
  props: {record: {type: Object, required: true}}, emits: ['changed'],
  setup(props, {emit}) {
    const busy = ref(false);
    const canRetry = computed(() => canOperateMailbox(props.record.receiver) && !busy.value);
    const taskKeys = {unconfigured_mail_analyze:'classification', supplier_config_draft:'configTask', cutover_time_extract:'timeTask'};
    async function retry(task) {
      if (!canRetry.value) return;
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
    return {busy, canRetry, taskKeys, retry, openDraft, sceneText, sceneTagType, beijingTime, analysisValue};
  },
  template: `<section v-if="record.processing_origin === 'unconfigured' && (record.ai_tasks?.length || record.unconfigured_analysis)" class="block-section mail-analysis-panel">
    <div class="block-head"><span>{{ $t('discovery.analysis') }}</span><div class="toolbar-actions">
      <ui-button v-if="record.supplier_draft_id" link type="primary" @click="openDraft">{{ $t('discovery.viewDraft') }}</ui-button>
      <ui-action icon="Refresh" :disabled="busy" @click="$emit('changed')" :label="$t('common.refresh')"></ui-action>
    </div></div>
    <p class="field-hint">{{ $t('discovery.analysisHint') }}</p>
    <div v-for="task in record.ai_tasks || []" :key="task.task_type" class="mail-analysis-task">
      <span>{{ $t('discovery.'+taskKeys[task.task_type]) }}</span><ui-tag :type="task.status === 'failed' ? 'danger' : 'info'">{{ $t('discovery.'+task.status) }}</ui-tag>
      <span v-if="task.last_error" class="warn-text">{{ task.last_error }}</span><ui-button v-if="task.status === 'failed'" :disabled="!canRetry" :loading="busy" @click="retry(task)">{{ $t('discovery.retry') }}</ui-button>
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
