/* Supplier review: compare the mail actually tested with its extraction results. */
const supplierReviewMessages = {
  'zh-CN': {
    readRetry:'重试读取', viewRecord:'查看记录', viewMails:'查看邮件', configuredSample:'配置中的样本', collectedMails:'已收集的邮件（{count}）',
    selectMail:'选择邮件样本', collectedEmpty:'暂未收集到邮件样本。', sampleReadError:'邮件读取失败，请重试。', useSample:'设为此分类样本', collectedReadOnlyHint:'切换已收集的邮件，查看完整正文、表格和附件。',
    sampleUpdated:'已更新配置样本，保存草稿后生效', collectedHint:'可切换已收到的邮件核对或测试；只有“设为此分类样本”才会替换配置中的样本。切换邮件会清空本次上传的附件。',
    verify:'待核实', generalQuestions:'其他待核实事项', questionsHint:'这些是生成时留下的提醒，请结合邮件核对，修改后重新识别。',
    draftState:'配置生成状态', refreshState:'刷新状态', editFormal:'编辑正式配置', recordHint:'这是启用时保留的记录。后续调整请编辑正式配置。',
    snapshot:'启用时的配置记录', backToList:'返回列表',
    identifierName:'字段 key', identifierNameHint:'例如 CircuitId、TGN_NMS_ID', identifierSource:'从哪里提取',
    identifierSourceHint:'说明编号在正文或哪个附件、哪一列中，以及如何对应到每条线路。', identifierHint:'直接定义提取结果中的字段 key，原样用于保存和查询。',
    identifierAdd:'添加', identifierQuery:'用于查询内部线路', identifierInvalid:'key 只能包含文字、数字和下划线，且不能全部为下划线；请勿使用空格或其他标点。',
    identifierDuplicate:'该 key 已存在，请直接修改已有字段的识别方式。', identifierReserved:'此 key 已用于内置或其他字段，请使用不同的 key。',
    circuitIdentifier:'线路标识', intro:'先核对邮件和识别结果，有问题时直接修正识别方式。', advanced:'高级配置', back:'返回邮件核对',
    setupTitle:'从一封割接通知开始', setupHint:'填写供应商信息，导入 EML 邮件或粘贴一封有代表性的通知。接下来核对时间、原因和线路编号。',
    continue:'进入邮件核对', sample:'邮件样本', sampleHint:'右侧识别使用当前样本的主题、正文和附件。', editSample:'编辑样本',
    original:'查看来源邮件', restore:'使用来源邮件作为样本', sampleEmpty:'还没有邮件样本，请先添加主题和正文。',
    sampleLoading:'正在整理邮件预览…', sampleError:'邮件预览失败，可重试或编辑样本查看原文。', retry:'重试预览',
    results:'识别结果', test:'识别这封邮件', retest:'重新识别', testing:'正在识别邮件…',
    beforeTest:'先识别，再对照原文核对', beforeHint:'系统会读取当前邮件样本。识别结果和线路信息将在这里展示。',
    resultHint:'核对割接时间、时区、原因和线路编号；测试不会保存配置或发送邮件。',
    current:'本次测试结果 · 待人工核对', stale:'样本或规则已修改，以下是上次结果，请重新识别。',
    waiting:'等待识别', missing:'未识别到', correct:'修正识别方式', correctionTitle:'如何识别{label}',
    correctionHint:'用业务语言说明应从哪里读取、如何判断。此要求会用于后续同类邮件，应用后请重新识别。',
    correctionPlaceholder:'例如：读取 Reason 段落，保留设备故障及更换原因。', apply:'应用修正', applied:'已应用修正，请重新识别后核对',
    lineInfo:'线路信息', noLines:'本次未识别到线路，请核对正文、附件或识别要求。', query:'用哪些编号查询内部线路？',
    queryHint:'只选择邮件中实际出现的编号。勾选后将用于查询内部线路；完整值和前导零会保留。',
    identifiers:'添加一种线路编号', lineCount:'识别到 {count} 条线路', attachmentHint:'下方附件会与正文一并识别，可添加或移除；ICS 不参与识别。',
    noticeOnly:'此分类用于识别邮件类型。请选择“割接通知”样本测试割接信息。', noAccess:'邮件样本受来源邮箱权限保护，无法展示或测试。供应商基本信息与高级配置仍可维护。',
    advancedHint:'这里保留字段标识、完整提取规则、邮件分类样本和提示词。日常核对可返回邮件对照页完成。',
    manualHint:'当前使用已有手写规则。在结果旁提交的修正会补充到手写规则中；新增线路字段会切换为自动生成规则。',
    error:'本次识别未完成，请重试。上次结果仅供参考。', raw:'查看完整返回内容', emptyResult:'本次没有返回可核对的割接字段，请查看完整返回内容或调整识别要求后重试。',
    fixLines:'修正线路识别', generalRule:'线路识别', required:'请先填写供应商名称、发件地址和割接通知的主题、正文。',
    notes:'生成时的待核对事项', editIdentity:'供应商信息', newName:'供应商名称待填写', noSave:'填写与测试不会自动保存。正式配置保存后用于后续邮件；草稿仍需人工确认启用。'
  },
  en: {
    readRetry:'Retry loading', viewRecord:'View record', viewMails:'View emails', configuredSample:'Configured sample', collectedMails:'Collected emails ({count})',
    selectMail:'Select email sample', collectedEmpty:'No email samples collected yet.', sampleReadError:'Could not load the email. Retry.', useSample:'Use as category sample', collectedReadOnlyHint:'Switch collected emails to view their complete body, tables and attachments.',
    sampleUpdated:'Configuration sample updated. Save the draft to persist it.', collectedHint:'Switch received emails to review or test. Only “Use as category sample” replaces the configuration sample. Switching clears uploaded test attachments.',
    verify:'Please verify', generalQuestions:'Other items to verify', questionsHint:'These reminders were recorded when the draft was generated. Check the email and analyze again after changes.',
    draftState:'Configuration generation status', refreshState:'Refresh status', editFormal:'Edit active configuration', recordHint:'This record was retained at activation. Edit the active configuration for subsequent changes.',
    snapshot:'Configuration at activation', backToList:'Back to list',
    identifierName:'Field key', identifierNameHint:'For example, CircuitId or TGN_NMS_ID', identifierSource:'Where to extract it',
    identifierSourceHint:'Describe its location in the body or attachment and how it relates to each circuit.', identifierHint:'Define the extraction output key directly. It is stored and used for lookup exactly as entered.',
    identifierAdd:'Add', identifierQuery:'Use to find internal circuits', identifierInvalid:'Use letters, numbers and underscores, including at least one letter or number. Spaces and other punctuation are not allowed.',
    identifierDuplicate:'This key already exists. Edit its existing extraction rule.', identifierReserved:'This key is reserved or used by another field. Choose a different key.',
    circuitIdentifier:'Circuit identifier', intro:'Compare the email with its extracted results and correct how information is identified.', advanced:'Advanced configuration', back:'Back to email review',
    setupTitle:'Start with a maintenance notice', setupHint:'Enter the supplier details, then import an EML email or paste a representative notice. Review times, reasons and circuit identifiers next.', continue:'Review the email',
    sample:'Email sample',sampleHint:'Analysis uses this sample’s subject, body and attachments.',editSample:'Edit sample',original:'View source email',restore:'Use source email as sample',sampleEmpty:'Add a subject and body to begin.',sampleLoading:'Preparing email preview…',sampleError:'Could not preview the email. Retry or edit the sample to view its source.',retry:'Retry preview',
    results:'Extraction results',test:'Analyze this email',retest:'Analyze again',testing:'Analyzing email…',beforeTest:'Analyze, then compare with the email',beforeHint:'Results and circuit information from the current sample will appear here.',resultHint:'Check times, timezone, reason and circuit identifiers. Testing does not save settings or send emails.',current:'Test result · awaiting human review',stale:'The sample or rules have changed. These are previous results; analyze again.',waiting:'Awaiting analysis',missing:'Not identified',correct:'Correct identification',correctionTitle:'How to identify {label}',correctionHint:'Describe where to find this information and how to interpret it. This applies to future emails; analyze again after applying.',correctionPlaceholder:'For example: read the Reason paragraph and include the hardware fault and replacement reason.',apply:'Apply correction',applied:'Correction applied. Analyze again to check the result.',
    lineInfo:'Circuit information',noLines:'No circuits identified. Check the body, attachments and extraction requirements.',query:'Which identifiers should locate internal circuits?',queryHint:'Select identifiers present in the email. Preserve complete values and leading zeros.',identifiers:'Add an identifier',lineCount:'{count} circuits identified',attachmentHint:'The attachments listed below are analyzed with the body. Add or remove files as needed; ICS files are excluded.',noticeOnly:'This sample is used for classification. Choose the maintenance notice to test extraction.',noAccess:'Mailbox permissions protect this sample. Preview and analysis are unavailable; shared configuration can still be maintained.',advancedHint:'Field keys, full rules, classification samples and prompts are available here. Return to email review for everyday checks.',manualHint:'Existing manual rules are in use. Corrections are appended to them. Adding circuit fields switches to generated rules.',error:'Analysis failed. Retry; previous results are for reference only.',raw:'View full response',emptyResult:'No maintenance fields were returned. Inspect the full response or adjust the requirements and retry.',fixLines:'Correct circuit extraction',generalRule:'Circuit extraction',required:'Enter the supplier name, sender address and maintenance sample subject and body first.',notes:'Items to check from generation',editIdentity:'Supplier details',newName:'Supplier name required',noSave:'Editing and testing do not save automatically. Saved formal settings apply to future emails; drafts require human activation.'
  },
  'zh-HK': {
    readRetry:'重試讀取', viewRecord:'查看記錄', viewMails:'查看郵件', configuredSample:'配置中的樣本', collectedMails:'已收集的郵件（{count}）',
    selectMail:'選擇郵件樣本', collectedEmpty:'暫未收集到郵件樣本。', sampleReadError:'郵件讀取失敗，請重試。', useSample:'設為此分類樣本', collectedReadOnlyHint:'切換已收集的郵件，查看完整正文、表格和附件。',
    sampleUpdated:'已更新配置樣本，儲存草稿後生效', collectedHint:'可切換已收到的郵件核對或測試；只有「設為此分類樣本」才會替換配置中的樣本。切換郵件會清空本次上傳的附件。',
    verify:'待核實', generalQuestions:'其他待核實事項', questionsHint:'這些是生成時留下的提醒，請結合郵件核對，修改後重新識別。',
    draftState:'配置生成狀態', refreshState:'重新整理狀態', editFormal:'編輯正式配置', recordHint:'這是啟用時保留的記錄。後續調整請編輯正式配置。',
    snapshot:'啟用時的配置記錄', backToList:'返回清單',
    identifierName:'欄位 key', identifierNameHint:'例如 CircuitId、TGN_NMS_ID', identifierSource:'從哪裏提取',
    identifierSourceHint:'說明編號在正文或哪個附件、哪一欄中，以及如何對應每條線路。', identifierHint:'直接定義提取結果中的欄位 key，原樣用於儲存和查詢。',
    identifierAdd:'新增', identifierQuery:'用於查詢內部線路', identifierInvalid:'key 只能包含文字、數字和底線，且不能全部為底線；請勿使用空格或其他標點。',
    identifierDuplicate:'該 key 已存在，請直接修改已有欄位的識別方式。', identifierReserved:'此 key 已用於內建或其他欄位，請使用不同的 key。',
    circuitIdentifier:'線路識別碼', intro:'先核對郵件和識別結果，有問題時直接修正識別方式。',advanced:'進階配置',back:'返回郵件核對',setupTitle:'從一封割接通知開始',setupHint:'填寫供應商資訊，匯入 EML 郵件或貼上一封有代表性的通知。接下來核對時間、原因和線路編號。',continue:'進入郵件核對',sample:'郵件樣本',sampleHint:'右側識別使用目前樣本的主旨、正文和附件。',editSample:'編輯樣本',original:'查看來源郵件',restore:'使用來源郵件作為樣本',sampleEmpty:'還沒有郵件樣本，請先新增主旨和正文。',sampleLoading:'正在整理郵件預覽…',sampleError:'郵件預覽失敗，可重試或編輯樣本查看原文。',retry:'重試預覽',results:'識別結果',test:'識別這封郵件',retest:'重新識別',testing:'正在識別郵件…',beforeTest:'先識別，再對照原文核對',beforeHint:'系統會讀取目前郵件樣本，識別結果和線路資訊將在這裏展示。',resultHint:'核對割接時間、時區、原因和線路編號；測試不會儲存配置或傳送郵件。',current:'本次測試結果 · 待人工核對',stale:'樣本或規則已修改，以下是上次結果，請重新識別。',waiting:'等待識別',missing:'未識別到',correct:'修正識別方式',correctionTitle:'如何識別{label}',correctionHint:'用業務語言說明應從哪裏讀取、如何判斷。此要求會用於後續同類郵件，套用後請重新識別。',correctionPlaceholder:'例如：讀取 Reason 段落，保留設備故障及更換原因。',apply:'套用修正',applied:'已套用修正，請重新識別後核對',lineInfo:'線路資訊',noLines:'本次未識別到線路，請核對正文、附件或識別要求。',query:'用哪些編號查詢內部線路？',queryHint:'只選擇郵件中實際出現的編號。完整值和前導零會保留。',identifiers:'新增一種線路編號',lineCount:'識別到 {count} 條線路',attachmentHint:'下方附件會與正文一併識別，可新增或移除；ICS 不參與識別。',noticeOnly:'此分類用於識別郵件類型。請選擇「割接通知」樣本測試割接資訊。',noAccess:'郵件樣本受來源郵箱權限保護，無法展示或測試。供應商基本資訊與進階配置仍可維護。',advancedHint:'這裏保留欄位識別碼、完整提取規則、郵件分類樣本和提示詞。日常核對可返回郵件對照頁完成。',manualHint:'目前使用已有手寫規則。在結果旁提交的修正會補充到手寫規則中；新增線路欄位會切換為自動生成規則。',error:'本次識別未完成，請重試。上次結果僅供參考。',raw:'查看完整回傳內容',emptyResult:'本次沒有回傳可核對的割接欄位，請查看完整回傳內容或調整識別要求後重試。',fixLines:'修正線路識別',generalRule:'線路識別',required:'請先填寫供應商名稱、寄件地址和割接通知的主旨、正文。',notes:'生成時的待核對事項',editIdentity:'供應商資訊',newName:'供應商名稱待填寫',noSave:'填寫與測試不會自動儲存。正式配置儲存後用於後續郵件；草稿仍需人工確認啟用。'
  }
};
Object.assign(supplierReviewMessages['zh-CN'], {importEml:'导入 EML 邮件', importHint:'可导入一封 .eml 邮件（最多 20 MB），替换下方主题、正文和测试附件；发件地址为空时自动填入，供应商名称由人工填写。', importSuccess:'已导入邮件，带入 {count} 个附件，跳过 {skipped} 个 ICS 附件。请核对后继续。', importError:'邮件导入失败，请重试', importInvalid:'请选择不超过 20 MB 的 .eml 文件', importedAttachments:'已带入 {count} 个附件，进入邮件核对后可查看或移除。'});
Object.assign(supplierReviewMessages['zh-HK'], {importEml:'匯入 EML 郵件', importHint:'可匯入一封 .eml 郵件（最多 20 MB），替換下方主旨、正文及測試附件；寄件地址為空時自動填入，供應商名稱由人工填寫。', importSuccess:'已匯入郵件，帶入 {count} 個附件，略過 {skipped} 個 ICS 附件。請核對後繼續。', importError:'郵件匯入失敗，請重試', importInvalid:'請選擇不超過 20 MB 的 .eml 檔案', importedAttachments:'已帶入 {count} 個附件，進入郵件核對後可查看或移除。'});
Object.assign(supplierReviewMessages.en, {importEml:'Import EML email', importHint:'Import an .eml file (up to 20 MB) to replace the subject, body and test attachments. The sender is filled only if blank; enter the supplier name manually.', importSuccess:'Imported email with {count} attachments; skipped {skipped} ICS files. Review before continuing.', importError:'Email import failed. Retry.', importInvalid:'Choose an .eml file up to 20 MB', importedAttachments:'{count} attachments imported. Review or remove them on the next screen.'});
Object.assign(supplierReviewMessages['zh-CN'], {lineRules:'每条线路的识别方式', lineRulesHint:'修改下面的规则后重新识别，核对每条线路的结果，再保存配置。', editLineRule:'修改识别方式', manualLineRule:'使用完整手写规则；可补充该字段的识别要求。', currentFullRule:'查看当前完整规则'});
Object.assign(supplierReviewMessages['zh-HK'], {lineRules:'每條線路的識別方式', lineRulesHint:'修改下方規則後重新識別，核對每條線路的結果，再儲存配置。', editLineRule:'修改識別方式', manualLineRule:'使用完整手寫規則；可補充此欄位的識別要求。', currentFullRule:'查看目前完整規則'});
Object.assign(supplierReviewMessages.en, {lineRules:'How each circuit is identified', lineRulesHint:'After changing a rule, analyze again and review each circuit before saving.', editLineRule:'Edit extraction rule', manualLineRule:'Uses the full manual prompt. Add instructions for this field.', currentFullRule:'View current full prompt'});
for (const [locale, messages] of Object.entries(supplierReviewMessages)) i18n.global.mergeLocaleMessage(locale, {supplierReview:messages});

// Static assets can update before the running Python service reloads. Keep a safe
// local fallback for the caller's current sample, using the mail_preview.py policy.
function buildLocalSupplierPreview(content) {
  if (new TextEncoder().encode(content).length > 2 * 1024 * 1024) throw new Error('Sample too large');
  const template = document.createElement('template');
  template.innerHTML = content; // Inert: never attach this untrusted fragment to the document.
  const allowed = new Set('div p span font b strong i em u s strike br hr pre blockquote a ol ul li table caption colgroup col thead tbody tfoot tr th td h1 h2 h3 h4 h5 h6 img style center small sub sup address dl dt dd'.split(' '));
  const omitted = new Set('script iframe frame object embed svg math form title template'.split(' '));
  const attributes = new Set('style class title width height border cellpadding cellspacing align valign colspan rowspan bgcolor color face size dir lang'.split(' '));
  const escape = value => value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  function serialize(node) {
    if (node.nodeType === Node.TEXT_NODE) return escape(node.textContent);
    if (node.nodeType !== Node.ELEMENT_NODE || omitted.has(node.localName)) return '';
    const tag = node.localName;
    if (tag === 'img' && !/^data:image\/(?:png|jpeg|gif|webp);base64,/i.test(node.getAttribute('src') || '')) return '';
    const children = () => [...node.childNodes].map(serialize).join('');
    if (!allowed.has(tag)) return children();
    const attrs = [...node.attributes].filter(a => attributes.has(a.name) || (tag === 'img' && a.name === 'src'))
      .map(a => ' ' + a.name + '="' + escape(a.value) + '"').join('');
    if (['br', 'hr', 'col', 'img'].includes(tag)) return '<' + tag + attrs + '>';
    // A raw-text style node must never be able to close its element on reparse.
    const body = tag === 'style' ? node.textContent.replace(/</g, '\\3c ') : children();
    return '<' + tag + attrs + '>' + body + '</' + tag + '>';
  }
  return '<!doctype html><html><head><meta charset="utf-8">'
    + '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; base-uri \'none\'; form-action \'none\'">'
    + '<meta name="referrer" content="no-referrer"><style>body{margin:16px;font:14px/1.6 sans-serif;overflow-wrap:break-word}table{border-collapse:collapse}img{max-width:100%}</style>'
    + '</head><body>' + [...template.content.childNodes].map(serialize).join('') + '</body></html>';
}

function useSupplierDraftReview(ctx) {
  const {ref, computed, watch, onUnmounted} = Vue;
  const {draftRecord, draftReadOnly, mailTypes, fixedFields, lineFields, topCustomFields, extractFiles, supplierFieldLabel} = ctx;
  const sampleMode = ref('configured'), collectedPage = ref(1), collectedRequestedPage = ref(1), collectedMails = ref([]);
  const sourceMail = ref(null), sourceMailId = ref(null), sourceBusy = ref(false), sourceError = ref('');
  const collectedBusy = ref(false), collectedError = ref('');
  let sourceRequest = 0, listRequest = 0;
  async function selectCollectedMail(id) {
    const request = ++sourceRequest;
    sourceMailId.value = Number(id); sourceMail.value = null; sourceError.value = ''; extractFiles.value = [];
    sourceBusy.value = true;
    try {
      const mail = await requestJson(`/api/emails/${Number(id)}/source`);
      if (request === sourceRequest) sourceMail.value = mail;
    } catch (error) { if (request === sourceRequest) sourceError.value = error.message; }
    finally { if (request === sourceRequest) sourceBusy.value = false; }
  }
  function changeSampleMode(mode) {
    if (mode !== sampleMode.value) extractFiles.value = [];
    if (mode === 'configured') {
      ++listRequest; ++sourceRequest;
      if (sourceBusy.value) sourceMailId.value = null;
      sourceBusy.value = false; collectedBusy.value = false;
    }
    sampleMode.value = mode;
    if (mode === 'collected' && !sourceMailId.value && collectedMails.value.length) selectCollectedMail(collectedMails.value[0].id);
  }
  async function loadCollectedPage(page) {
    const request = ++listRequest;
    collectedRequestedPage.value = page;
    ++sourceRequest; sourceMail.value = null; sourceMailId.value = null; sourceBusy.value = false;
    collectedBusy.value = true; collectedError.value = ''; extractFiles.value = [];
    try {
      const data = await requestJson(`/api/supplier-drafts/${draftRecord.value.id}?page=${page}`);
      if (request !== listRequest) return;
      collectedPage.value = page; collectedMails.value = data.samples || [];
      if (collectedMails.value.length) await selectCollectedMail(collectedMails.value[0].id);
    } catch (error) { if (request === listRequest) collectedError.value = error.message; }
    finally { if (request === listRequest) collectedBusy.value = false; }
  }
  watch(() => draftRecord.value?.id, id => {
    ++listRequest; ++sourceRequest;
    collectedPage.value = 1; collectedMails.value = draftRecord.value?.samples || [];
    sourceMail.value = null; sourceMailId.value = null; sourceError.value = ''; collectedError.value = '';
    if (id && draftReadOnly.value) changeSampleMode('collected');
  });
  watch(() => draftRecord.value?.samples, samples => {
    if (collectedPage.value === 1 && Array.isArray(samples)) collectedMails.value = samples;
  });
  onUnmounted(() => { ++sourceRequest; ++listRequest; });
  const canUseCollectedSample = computed(() => !draftReadOnly.value && sourceMail.value
    && mailTypes.value.some(sample => sample.name === sourceMail.value.mail_type));
  function useCollectedSample() {
    if (!canUseCollectedSample.value) return;
    const target = mailTypes.value.find(sample => sample.name === sourceMail.value.mail_type);
    target.source_email_records_id = sourceMail.value.id;
    target.subject = sourceMail.value.subject || '';
    target.content = sourceMail.value.html_content || sourceMail.value.content || '';
    NocMessage.success(tt('supplierReview.sampleUpdated'));
  }
  const reviewQuestions = computed(() => {
    const fields = [...fixedFields.value, ...lineFields.value, ...topCustomFields.value,
      {name:'reply_email'}, {name:'name'}, {name:'line_array'}, {name:'line_query_keywords'}];
    const label = name => ({reply_email:tt('supplierForm.replyEmailLabel'), name:tt('suppliers.name'),
      line_array:tt('supplierReview.lineInfo'), line_query_keywords:tt('supplierReview.query')})[name] || supplierFieldLabel(name);
    return (draftRecord.value?.draft?.unresolved_questions || []).map(text => {
      const raw = String(text), prefix = raw.split(/[|｜:：]/, 1)[0].trim();
      const target = fields.find(field => field.name && (field.name.toLowerCase() === prefix.toLowerCase() || label(field.name) === prefix));
      let content = target ? raw.slice(prefix.length).replace(/^[\s|｜:：]+/, '') : raw;
      for (const field of fields.filter(f => f.name).sort((a,b) => b.name.length-a.name.length)) {
        if (field.name !== 'name') content = content.split(field.name).join(label(field.name));
      }
      return {key:target?.name || '', text:content.replace(/\s*[|｜]\s*/g, '；')};
    });
  });
  const questionsFor = key => reviewQuestions.value.filter(question => question.key === key);
  const generalQuestions = computed(() => questionsFor(''));
  const lineQuestions = computed(() => reviewQuestions.value.filter(question => ['line_array','line_query_keywords'].includes(question.key)));
  return {sampleMode, collectedMails, collectedPage, collectedRequestedPage, collectedBusy, collectedError, loadCollectedPage,
    sourceMail, sourceMailId, sourceBusy, sourceError, selectCollectedMail, changeSampleMode,
    canUseCollectedSample, useCollectedSample, questionsFor, generalQuestions, lineQuestions};
}

function useSupplierReview(ctx) {
  const {ref, reactive, computed, watch, onUnmounted} = Vue;
  const {form, isDraft, isEdit, mailTypes, fixedFields, lineFields, topCustomFields, legacyPrompt,
    usesManualPrompt, extractFiles, extractPreview, extractPreviewView, samplesRestricted, supplierFieldLabel} = ctx;
  const reviewStage = ref(isDraft.value || isEdit.value ? 'review' : 'intro');
  const showAdvanced = ref(false);
  const emlInput = ref(null), emlBusy = ref(false), emlError = ref('');
  let importActive = true;
  onUnmounted(() => { importActive = false; });
  async function importEml(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || emlBusy.value) return;
    emlError.value = '';
    if (!/\.eml$/i.test(file.name) || file.size > 20 * 1024 * 1024) {
      emlError.value = tt('supplierReview.importInvalid'); return;
    }
    emlBusy.value = true;
    try {
      const body = new FormData(); body.append('file', file);
      const response = await fetch('/api/suppliers/import-eml', {method:'POST', headers:{'X-CSRF-Token':appStore.csrfToken}, body});
      const result = await response.json();
      if (!response.ok || !result.success) throw new Error(result.message || tt('supplierReview.importError'));
      const data = result.data;
      const files = data.attachments.map((attachment,index) => {
        const bytes = Uint8Array.from(atob(attachment.base64), character => character.charCodeAt(0));
        const raw = new File([bytes], attachment.name, {type:attachment.type});
        return {name:raw.name, raw, uid:Date.now()+'-'+index, status:'ready'};
      });
      if (!importActive) return;
      const notice = mailTypes.value.find(sample => sample.name === '割接通知');
      notice.subject = data.subject; notice.content = data.content; notice.source_email_records_id = null;
      notice.contentInAttachment = !data.content.trim() && files.length > 0;
      if (!form.email.trim()) form.email = data.sender;
      extractFiles.value = files;
      NocMessage.success(tt('supplierReview.importSuccess', {count:files.length, skipped:data.skipped_attachments.length}));
    } catch (error) { if (importActive) emlError.value = error.message || tt('supplierReview.importError'); }
    finally { emlBusy.value = false; }
  }
  const draftReview = useSupplierDraftReview(ctx);
  const configuredAttachmentMail = ref(null), configuredAttachmentBusy = ref(false), configuredAttachmentError = ref('');
  const sampleAttachmentMail = computed(() => draftReview.sampleMode.value === 'collected' ? draftReview.sourceMail.value : configuredAttachmentMail.value);
  const sampleAttachments = useMailAttachmentPreview(sampleAttachmentMail, extractFiles);
  const removeSampleAttachment = item => { extractFiles.value = extractFiles.value.filter(file => 'local-'+file.uid !== item.index); };
  const activeSampleName = ref('割接通知');
  const activeSample = computed(() => draftReview.sampleMode.value === 'collected'
    ? (draftReview.sourceMail.value ? {subject:draftReview.sourceMail.value.subject || '',
      content:draftReview.sourceMail.value.html_content || draftReview.sourceMail.value.content || '', contentInAttachment:false} : null)
    : mailTypes.value.find(item => item.name === activeSampleName.value));
  let attachmentRequest = 0;
  async function loadConfiguredAttachments() {
    const current = ++attachmentRequest;
    configuredAttachmentMail.value = null; configuredAttachmentError.value = ''; configuredAttachmentBusy.value = false;
    if (draftReview.sampleMode.value !== 'configured' || !activeSample.value || samplesRestricted.value) return;
    const sample = activeSample.value;
    // Auto-generated legacy notice samples have a trusted draft source reference.
    const sourceId = sample.source_email_records_id || (activeSampleName.value === '割接通知' ? ctx.draftRecord.value?.source_email_records_id : null);
    configuredAttachmentBusy.value = true;
    try {
      const data = await requestJson('/api/suppliers/sample-attachment-source', {method:'POST', body:JSON.stringify({
        source_email_records_id:sourceId || null, subject:sample.subject || '', content:sample.content || ''})});
      if (current !== attachmentRequest) return;
      configuredAttachmentMail.value = data;
      if (data?.id) sample.source_email_records_id = data.id;
    } catch (error) { if (current === attachmentRequest) configuredAttachmentError.value = error.message; }
    finally { if (current === attachmentRequest) configuredAttachmentBusy.value = false; }
  }
  watch(() => [draftReview.sampleMode.value, activeSampleName.value, activeSample.value?.source_email_records_id,
    activeSample.value?.subject, activeSample.value?.content, samplesRestricted.value], loadConfiguredAttachments);
  onUnmounted(() => { ++attachmentRequest; });
  const reviewMailType = computed(() => draftReview.sampleMode.value === 'collected' ? draftReview.sourceMail.value?.mail_type : activeSampleName.value);
  const sampleIsHtml = computed(() => /<(?:html|body|div|p|table|br|span|style|h[1-6])\b/i.test(activeSample.value?.content || ''));
  const samplePreview = ref('');
  const samplePreviewBusy = ref(false);
  const samplePreviewError = ref(false);
  let sampleRequest = 0, sampleTimer;
  async function renderSample() {
    const request = ++sampleRequest;
    samplePreview.value = '';
    samplePreviewError.value = false;
    samplePreviewBusy.value = false;
    if (!sampleIsHtml.value || samplesRestricted.value || showAdvanced.value || reviewStage.value !== 'review') return;
    samplePreviewBusy.value = true;
    const content = activeSample.value.content;
    try {
      const data = await requestJson('/api/suppliers/sample-preview', {method:'POST', body:JSON.stringify({content})});
      if (typeof data?.preview_html !== 'string' || !data.preview_html) throw new Error('Empty preview');
      if (request === sampleRequest) samplePreview.value = data.preview_html;
    } catch (error) {
      if (request === sampleRequest) {
        try {
          if (!appStore.apiKey || samplesRestricted.value || [401,403].includes(error.status)) throw error;
          samplePreview.value = buildLocalSupplierPreview(content);
        } catch { samplePreviewError.value = true; }
      }
    }
    finally { if (request === sampleRequest) samplePreviewBusy.value = false; }
  }
  watch(() => [activeSample.value?.content, samplesRestricted.value, showAdvanced.value, reviewStage.value], () => {
    ++sampleRequest; clearTimeout(sampleTimer); samplePreview.value = '';
    sampleTimer = setTimeout(renderSample, 150);
  }, {immediate:true});
  onUnmounted(() => { ++sampleRequest; clearTimeout(sampleTimer); });
  const reviewFingerprint = computed(() => JSON.stringify({
    form, samples:mailTypes.value, selectedSample:activeSample.value, selectedSource:draftReview.sampleMode.value === 'collected' ? draftReview.sourceMailId.value : null,
    fixed:fixedFields.value.map(f => [f.name,f.value]), lines:lineFields.value,
    top:topCustomFields.value, legacy:legacyPrompt.value, files:extractFiles.value.map(f => [f.uid,f.name,f.size])
  }));
  const resultFingerprint = ref('');
  const reviewError = ref('');
  const hasReviewResult = computed(() => Boolean(resultFingerprint.value));
  const reviewStale = computed(() => hasReviewResult.value && resultFingerprint.value !== reviewFingerprint.value);
  const reviewFields = computed(() => {
    const extracted = extractPreviewView.value.blocks.filter(b => b.kind === 'extract').flatMap(b => b.fields);
    return [...fixedFields.value.filter(f => !f.isLineField), ...topCustomFields.value].map(f => ({
      key:f.name, label:supplierFieldLabel(f.name), value:extracted.find(v => v.key === f.name)?.value || '',
      timeRange:extracted.find(v => v.key === f.name)?.timeRange
    }));
  });
  const reviewLines = computed(() => extractPreviewView.value.blocks.filter(b => b.kind === 'extract').flatMap(b => b.lines));
  const reviewLineFields = computed(() => fixedFields.value.filter(field => field.isLineField));
  const hasStructuredReview = computed(() => reviewFields.value.some(f => f.value) || reviewLines.value.length > 0);
  const reviewColumns = computed(() => [...new Set(reviewLines.value.flatMap(row => Object.keys(row)))]);
  const configuredIdentifiers = computed(() => lineFields.value.filter(row => row.name.trim()));
  const identifierDialog = ref(false);
  const identifierForm = reactive({name:'', description:'', keyword:true});
  const identifierError = ref('');
  function openIdentifierDialog() {
    Object.assign(identifierForm, {name:'', description:'', keyword:true});
    identifierError.value = '';
    identifierDialog.value = true;
  }
  function addReviewIdentifier() {
    const name = identifierForm.name.trim();
    const description = identifierForm.description.trim();
    if (!name || !description) return;
    let error = '';
    if (!/^[\p{L}\p{N}_]+$/u.test(name) || !/[\p{L}\p{N}]/u.test(name)) error = 'identifierInvalid';
    else if (lineFields.value.some(row => row.name.trim() === name)) error = 'identifierDuplicate';
    else if ([...fixedFields.value, ...topCustomFields.value].some(row => row.name.trim() === name)
      || ['line_array','line_query_keywords','__proto__','prototype','constructor'].includes(name)) error = 'identifierReserved';
    if (error) { identifierError.value = tt('supplierReview.' + error); return; }
    const field = {name, description, keyword:identifierForm.keyword};
    const emptyIndex = lineFields.value.findIndex(row => !row.name.trim() && !row.description.trim());
    if (emptyIndex < 0) lineFields.value.push(field);
    else lineFields.value[emptyIndex] = field;
    identifierDialog.value = false;
  }
  const correction = ref(null);
  const correctionText = ref('');
  function correctResult(key) {
    const target = fixedFields.value.find(f => f.name === key) || lineFields.value.find(f => f.name === key) || topCustomFields.value.find(f => f.name === key);
    correction.value = {key, label:key ? supplierFieldLabel(key) : tt('supplierReview.generalRule'), target};
    correctionText.value = usesManualPrompt.value || !target ? '' : (target.value?.trim() ? target.value : target.description || '');
  }
  function applyCorrection() {
    const text = correctionText.value.trim();
    if (!text || !correction.value) return;
    const {target,label} = correction.value;
    if (usesManualPrompt.value) legacyPrompt.value += '\n\n' + label + '：' + text;
    else if (target && 'value' in target) target.value = text;
    else if (target) target.description = text;
    else form.extra_instructions = [form.extra_instructions.trim(), text].filter(Boolean).join('\n');
    correction.value = null;
    NocMessage.success(tt('supplierReview.applied'));
  }
  function startReview() {
    const notice = mailTypes.value.find(item => item.name === '割接通知');
    if (!form.name.trim() || !form.email.trim() || !notice?.subject.trim() || !notice?.content.trim()) {
      NocMessage.error(tt('supplierReview.required')); return;
    }
    reviewStage.value = 'review';
  }
  return {...draftReview, ...sampleAttachments, configuredAttachmentBusy, configuredAttachmentError, loadConfiguredAttachments, removeSampleAttachment, emlInput, emlBusy, emlError, importEml, reviewStage, showAdvanced, activeSampleName, activeSample, reviewMailType, sampleIsHtml, samplePreview,
    samplePreviewBusy, samplePreviewError, renderSample, reviewFingerprint, resultFingerprint, hasReviewResult,
    reviewError, reviewStale, reviewFields, reviewLineFields, reviewLines, reviewColumns, configuredIdentifiers, hasStructuredReview,
    correction, correctionText, correctResult, applyCorrection, startReview,
    identifierDialog, identifierForm, identifierError, openIdentifierDialog, addReviewIdentifier};
}

const SUPPLIER_REVIEW_TEMPLATE = `
  <section v-if="!loadFailed && (!draftReadOnly || draftRecord?.draft?.config)" class="supplier-identity" :aria-label="$t('supplierReview.editIdentity')">
    <div class="form-field"><label class="form-label">{{ $t('suppliers.name') }} <span class="required-mark">*</span></label>
      <ui-input ref="supplierNameInput" v-model="form.name" :disabled="draftReadOnly" :aria-label="$t('suppliers.name')" :placeholder="$t('supplierForm.namePlaceholder')"></ui-input><p v-for="(question,index) in questionsFor('name')" :key="index" class="review-field-question">{{ question.text }}</p></div>
    <div class="form-field"><label class="form-label">{{ $t('draftReview.senderLabel') }} <span class="required-mark">*</span></label>
      <ui-input v-model="form.email" :aria-label="$t('draftReview.senderLabel')" type="email" :disabled="isDraft" :placeholder="$t('supplierForm.emailPlaceholder')"></ui-input></div>
    <div class="form-field"><label class="form-label">{{ $t('supplierForm.replyEmailLabel') }}</label>
      <ui-input v-model="form.reply_email" :disabled="draftReadOnly" :aria-label="$t('supplierForm.replyEmailLabel')" type="email" :placeholder="$t('supplierForm.replyEmailPlaceholder')"></ui-input>
      <p v-for="(question,index) in questionsFor('reply_email')" :key="index" class="review-field-question"><strong>{{ $t('supplierReview.verify') }} · </strong>{{ question.text }}</p></div>
    <p class="supplier-identity-hint">{{ $t('draftReview.replyHint') }}</p>
  </section>
  <section v-if="reviewStage === 'intro' && !loadFailed && activeSample" class="supplier-start">
    <span class="review-eyebrow">{{ $t('supplierOperator.createTitle') }}</span><h2>{{ $t('supplierReview.setupTitle') }}</h2><p>{{ $t('supplierReview.setupHint') }}</p>
    <input ref="emlInput" type="file" accept=".eml,message/rfc822" hidden @change="importEml">
    <ui-button :loading="emlBusy" :disabled="loading" @click="emlInput?.click()">{{ $t('supplierReview.importEml') }}</ui-button>
    <p class="field-hint">{{ $t('supplierReview.importHint') }}</p>
    <p v-if="emlError" class="warn-text" role="alert">{{ emlError }}</p>
    <p v-if="extractFiles.length" class="field-hint">{{ $t('supplierReview.importedAttachments',{count:extractFiles.length}) }}</p>
    <label class="form-label">{{ $t('supplierForm.categorySubjectLabel',{name:'割接通知'}) }}</label>
    <ui-input v-model="activeSample.subject" :aria-label="$t('supplierForm.categorySubjectLabel',{name:'割接通知'})"></ui-input>
    <label class="form-label">{{ $t('supplierForm.categoryContentLabel',{name:'割接通知'}) }}</label>
    <ui-input v-model="activeSample.content" type="textarea" :rows="10" :aria-label="$t('supplierForm.categoryContentLabel',{name:'割接通知'})"></ui-input>
    <div class="supplier-start-footer"><span>{{ $t('supplierReview.noSave') }}</span><ui-button type="primary" :disabled="loading || emlBusy" @click="startReview">{{ $t('supplierReview.continue') }}</ui-button></div>
  </section>
  <section v-if="reviewStage === 'review' && !showAdvanced && !loadFailed" class="supplier-compare">
    <section class="supplier-mail-pane" :aria-label="$t('supplierReview.sample')">
      <header class="review-pane-head"><div><span class="review-eyebrow">01 / EMAIL</span><h2>{{ $t('supplierReview.sample') }}</h2></div>
        <ui-button v-if="!draftReadOnly && sampleMode === 'configured'" size="small" :disabled="samplesReadOnly || !activeSample" @click="sampleEditor=activeSample">{{ $t('supplierReview.editSample') }}</ui-button></header>
      <div v-if="isDraft" class="review-sample-modes" role="group" :aria-label="$t('discovery.samples')">
        <button v-if="draftRecord?.draft?.config" type="button" :aria-pressed="sampleMode==='configured'" @click="changeSampleMode('configured')">{{ $t('supplierReview.configuredSample') }}</button>
        <button type="button" :aria-pressed="sampleMode==='collected'" @click="changeSampleMode('collected')">{{ $t('supplierReview.collectedMails',{count:draftRecord?.sample_count || 0}) }}</button>
      </div>
      <p class="review-pane-hint">{{ $t(sampleMode==='collected' ? (draftReadOnly ? 'supplierReview.collectedReadOnlyHint' : 'supplierReview.collectedHint') : 'supplierReview.sampleHint') }}</p>
      <ui-alert v-if="samplesRestricted" type="info" :closable="false" :title="$t('supplierReview.noAccess')"></ui-alert>
      <template v-else>
        <div v-if="sampleMode === 'configured'" class="review-sample-tabs" role="tablist" :aria-label="$t('supplierForm.mailTypesTitle')">
          <button v-for="sample in mailTypes" :key="sample.name" role="tab" type="button" :aria-selected="activeSampleName===sample.name" @click="activeSampleName=sample.name">{{ sample.name }}</button>
        </div>
        <div v-if="sampleMode==='collected'" class="review-collected-picker">
          <label class="form-label" for="collected-mail-select">{{ $t('supplierReview.selectMail') }}</label>
          <ui-select filterable id="collected-mail-select" class="review-sample-select" :aria-label="$t('supplierReview.selectMail')" :model-value="sourceMailId || ''" :disabled="collectedBusy || !collectedMails.length" @change="selectCollectedMail">
            <ui-option v-if="!collectedMails.length" value="" :label="$t('supplierReview.collectedEmpty')"></ui-option>
            <ui-option v-for="mail in collectedMails" :key="mail.id" :value="mail.id" :label="mail.mail_type + ' · ' + (mail.subject || '—') + ' · ' + mail.create_time"></ui-option>
          </ui-select>
          <p v-if="collectedError" class="warn-text" role="alert">{{ collectedError }} <ui-button size="small" @click="loadCollectedPage(collectedRequestedPage)">{{ $t('supplierReview.readRetry') }}</ui-button></p>
          <ui-pagination v-if="draftRecord.sample_count > 20" :current-page="collectedPage" :total="draftRecord.sample_count" :page-size="20" layout="prev, pager, next" :disabled="collectedBusy" @current-change="loadCollectedPage"></ui-pagination>
          <div v-if="sourceMail" class="review-collected-meta"><span>{{ sourceMail.mail_type }} · {{ sourceMail.create_time }}</span><span>{{ sourceMail.sender }} → {{ sourceMail.receiver }}</span></div>
        </div>
        <div class="review-mail-subject">{{ activeSample?.subject || $t('supplierReview.sampleEmpty') }}</div>
        <mail-attachment-preview v-if="selectedAttachment" :item="selectedAttachment" :data="attachmentData" :busy="attachmentBusy" :error="attachmentError" @close="closeAttachment" @retry="openAttachment"></mail-attachment-preview>
        <div v-else class="review-mail-body">
          <p v-if="sourceBusy || collectedBusy || samplePreviewBusy" role="status">{{ $t('supplierReview.sampleLoading') }}</p>
          <div v-else-if="sourceError && sampleMode==='collected'" role="alert">{{ $t('supplierReview.sampleReadError') }} {{ sourceError }} <ui-button size="small" @click="selectCollectedMail(sourceMailId)">{{ $t('supplierReview.readRetry') }}</ui-button></div>
          <div v-else-if="samplePreviewError" role="alert">{{ $t('supplierReview.sampleError') }} <ui-button size="small" @click="renderSample">{{ $t('supplierReview.retry') }}</ui-button></div>
          <iframe v-else-if="sampleIsHtml && samplePreview" class="review-mail-frame" sandbox="" referrerpolicy="no-referrer" :title="$t('supplierReview.sample')" :srcdoc="samplePreview"></iframe>
          <pre v-else-if="!sampleIsHtml">{{ activeSample?.content || $t('supplierReview.sampleEmpty') }}</pre>
        </div>
        <div v-if="sampleMode==='collected' && sourceMail" class="review-source-actions">
          <ui-button v-if="canUseCollectedSample" size="small" @click="useCollectedSample">{{ $t('supplierReview.useSample') }}</ui-button>

        </div>
        <mail-attachment-list :items="attachments" :selected="selectedAttachment" :busy="attachmentBusy" @preview="openAttachment" @remove="removeSampleAttachment"></mail-attachment-list>
        <p v-if="sampleMode==='configured' && configuredAttachmentBusy" class="review-pane-hint" role="status">{{ $t('attachmentPreview.loading') }}</p>
        <p v-if="sampleMode==='configured' && configuredAttachmentError" class="review-pane-hint" role="alert">{{ configuredAttachmentError }} <ui-button size="small" @click="loadConfiguredAttachments">{{ $t('supplierReview.readRetry') }}</ui-button></p>
      </template>
    </section>
    <section class="supplier-results-pane" :aria-label="$t('supplierReview.results')" :aria-busy="extracting">
      <header class="review-pane-head"><div><span class="review-eyebrow">02 / REVIEW</span><h2>{{ $t(draftReadOnly ? 'supplierReview.draftState' : 'supplierReview.results') }}</h2></div>
        <ui-button v-if="!draftReadOnly" type="primary" :loading="extracting" :disabled="loading || samplesRestricted || sourceBusy || collectedBusy || configuredAttachmentBusy || configuredAttachmentError || !activeSample || reviewMailType!=='割接通知'" @click="previewExtract">{{ $t(extracting ? 'supplierReview.testing' : hasReviewResult ? 'supplierReview.retest' : 'supplierReview.test') }}</ui-button></header>
      <div v-if="draftReadOnly && draftRecord" class="review-draft-state">
        <h3>{{ $t('discovery.'+draftRecord.status) }}</h3>
        <p>{{ $t(draftRecord.status==='published' ? 'supplierReview.recordHint' : draftRecord.status==='generation_failed' ? 'draftReview.nextFailed' : draftRecord.status==='generating' ? 'draftReview.nextGenerating' : 'draftReview.nextCollecting') }}</p>
        <p v-if="draftRecord.last_error" class="warn-text" role="alert">{{ draftRecord.last_error }}</p>
        <ui-button v-if="draftRecord.status==='generation_failed'" :loading="retryingDraft" @click="retryDraft">{{ $t('discovery.retry') }}</ui-button>
        <ui-button v-if="draftRecord.status!=='published'" :loading="loading" @click="loadForm">{{ $t('supplierReview.refreshState') }}</ui-button>
        <ui-button v-if="draftRecord.published_supplier_id" type="primary" @click="editPublishedSupplier">{{ $t('supplierReview.editFormal') }}</ui-button>
      </div>
      <template v-else>
      <p class="review-pane-hint">{{ $t('supplierReview.resultHint') }}</p>
      <section v-if="generalQuestions.length" class="review-general-questions"><h3>{{ $t('supplierReview.generalQuestions') }}</h3><p>{{ $t('supplierReview.questionsHint') }}</p><ul><li v-for="(question,index) in generalQuestions" :key="index">{{ question.text }}</li></ul></section>
      <p v-if="samplesRestricted" class="review-state-message">{{ $t('supplierOperator.testRestricted') }}</p>
      <p v-else-if="reviewMailType!=='割接通知'" class="review-state-message">{{ $t('supplierReview.noticeOnly') }}</p>
      <template v-else>
        <div v-if="!hasReviewResult && !extracting" class="review-empty"><h3>{{ $t('supplierReview.beforeTest') }}</h3><p>{{ $t('supplierReview.beforeHint') }}</p></div>
        <p v-if="reviewError" class="review-warning" role="alert">{{ $t('supplierReview.error') }} {{ reviewError }}</p>
        <p v-if="hasReviewResult" class="review-result-status" :class="{'review-warning':reviewStale}" role="status">{{ $t(reviewStale ? 'supplierReview.stale' : 'supplierReview.current') }}</p>
        <p v-if="hasReviewResult && !hasStructuredReview" class="review-warning">{{ $t('supplierReview.emptyResult') }}</p>
        <p v-if="usesManualPrompt" class="review-warning">{{ $t('supplierReview.manualHint') }}</p>
        <div class="review-field-results">
          <article v-for="field in reviewFields" :key="field.key" class="review-result-row" :data-field="field.key">
            <div><h3>{{ field.label }}</h3><p v-if="hasReviewResult && field.timeRange" class="review-time-range"><span>{{ $t('supplierForm.timeStart',{time:field.timeRange.startTime}) }}</span><span>{{ $t('supplierForm.timeEnd',{time:field.timeRange.endTime}) }}</span></p><p v-else :class="{'review-value-empty':!field.value}">{{ hasReviewResult ? (field.value || $t('supplierReview.missing')) : $t('supplierReview.waiting') }}</p><p v-for="(question,index) in questionsFor(field.key)" :key="index" class="review-field-question"><strong>{{ $t('supplierReview.verify') }} · </strong>{{ question.text }}</p></div>
            <ui-button text size="small" :aria-label="$t('supplierReview.correct')+'：'+field.label" @click="correctResult(field.key)">{{ $t('supplierReview.correct') }}</ui-button>
          </article>
        </div>
        <div class="review-lines-head"><h3>{{ $t('supplierReview.lineInfo') }} <small v-if="hasReviewResult">{{ $t('supplierReview.lineCount',{count:reviewLines.length}) }}</small></h3><ui-button text size="small" @click="correctResult(null)">{{ $t('supplierReview.fixLines') }}</ui-button></div>
        <p v-for="(question,index) in lineQuestions" :key="index" class="review-field-question review-line-question"><strong>{{ $t('supplierReview.verify') }} · </strong>{{ question.text }}</p>
        <section class="review-line-rules" :aria-label="$t('supplierReview.lineRules')">
          <header><h4>{{ $t('supplierReview.lineRules') }}</h4><p>{{ $t('supplierReview.lineRulesHint') }}</p></header>
          <article v-for="field in reviewLineFields" :key="field.name" class="review-line-rule" :data-field="field.name">
            <div class="review-line-rule-head"><h4>{{ supplierFieldLabel(field.name) }}</h4><ui-button text size="small" :aria-label="$t('supplierReview.editLineRule')+'：'+supplierFieldLabel(field.name)" @click="correctResult(field.name)">{{ $t('supplierReview.editLineRule') }}</ui-button></div>
            <p class="review-line-rule-summary">{{ usesManualPrompt ? $t('supplierReview.manualLineRule') : (field.value.trim() || field.description) }}</p>
            <p v-for="(question,index) in questionsFor(field.name)" :key="index" class="review-field-question"><strong>{{ $t('supplierReview.verify') }} · </strong>{{ question.text }}</p>
          </article>
        </section>
        <div v-if="reviewLines.length && hasReviewResult" class="review-lines-scroll"><table class="review-lines-table"><thead><tr><th v-for="col in reviewColumns" :key="col">{{ supplierFieldLabel(col) }}</th></tr></thead><tbody><tr v-for="(row,index) in reviewLines" :key="index"><td v-for="col in reviewColumns" :key="col">{{ row[col] == null || row[col] === '' ? '—' : row[col] }}</td></tr></tbody></table></div>
        <p v-else-if="hasReviewResult" class="review-pane-hint">{{ $t('supplierReview.noLines') }}</p>
        <section class="review-query-options"><h3>{{ $t('supplierReview.query') }}</h3><p>{{ $t('supplierReview.queryHint') }}</p>
          <div v-for="row in configuredIdentifiers" :key="row.name" class="review-query-row"><div><ui-checkbox v-model="row.keyword">{{ supplierFieldLabel(row.name) }}</ui-checkbox><p v-for="(question,index) in questionsFor(row.name)" :key="index" class="review-field-question">{{ question.text }}</p></div><ui-button text size="small" :aria-label="$t('supplierReview.correct')+'：'+supplierFieldLabel(row.name)" @click="correctResult(row.name)">{{ $t('supplierReview.correct') }}</ui-button></div>
          <ui-button v-if="!usesManualPrompt" class="review-add-identifier" size="small" :icon="icons.Plus" @click="openIdentifierDialog">{{ $t('supplierReview.identifiers') }}</ui-button>
        </section>
        <details v-if="hasReviewResult" class="review-raw-result"><summary>{{ $t('supplierReview.raw') }}</summary><pre>{{ extractPreview }}</pre></details>
      </template>
      </template>
    </section>
  </section>
  <ui-dialog v-model="identifierDialog" :title="$t('supplierReview.identifiers')" width="600px" class="review-identifier-dialog">
    <p class="field-hint">{{ $t('supplierReview.identifierHint') }}</p>
    <label class="form-label">{{ $t('supplierReview.identifierName') }}</label>
    <ui-input v-model="identifierForm.name" :aria-label="$t('supplierReview.identifierName')" :placeholder="$t('supplierReview.identifierNameHint')" @update:model-value="identifierError=''"></ui-input>
    <label class="form-label">{{ $t('supplierReview.identifierSource') }}</label>
    <ui-input v-model="identifierForm.description" type="textarea" :rows="4" :aria-label="$t('supplierReview.identifierSource')" :placeholder="$t('supplierReview.identifierSourceHint')"></ui-input>
    <ui-checkbox v-model="identifierForm.keyword">{{ $t('supplierReview.identifierQuery') }}</ui-checkbox>
    <p v-if="identifierError" role="alert" class="review-identifier-error">{{ identifierError }}</p>
    <template #footer><ui-button @click="identifierDialog=false">{{ $t('common.cancel') }}</ui-button><ui-button type="primary" :disabled="!identifierForm.name.trim() || !identifierForm.description.trim()" @click="addReviewIdentifier">{{ $t('supplierReview.identifierAdd') }}</ui-button></template>
  </ui-dialog>
  <ui-dialog :model-value="!!correction" :title="correction ? $t('supplierReview.correctionTitle',{label:correction.label}) : ''" width="640px" class="review-correction-dialog" @close="correction=null">
    <p class="field-hint">{{ $t('supplierReview.correctionHint') }}</p>
    <details v-if="usesManualPrompt && correction?.target?.isLineField" class="review-manual-line-rule"><summary>{{ $t('supplierReview.currentFullRule') }}</summary><pre>{{ legacyPrompt }}</pre><p class="field-hint">{{ $t('supplierReview.manualLineRule') }}</p></details>
    <ui-input v-model="correctionText" type="textarea" :rows="7" :aria-label="$t('supplierReview.correct')" :placeholder="$t('supplierReview.correctionPlaceholder')"></ui-input>
    <template #footer><ui-button @click="correction=null">{{ $t('common.cancel') }}</ui-button><ui-button type="primary" :disabled="!correctionText.trim()" @click="applyCorrection">{{ $t('supplierReview.apply') }}</ui-button></template>
  </ui-dialog>
`;
