/* Mail Listen 管理台 · Vue 3 + Naive UI 视图组件
 * 依赖加载顺序：vendor → admin-shared.js → 本文件 → admin.js
 * 注意：模板为运行时编译的字符串模板，自定义元素无自闭合坑，但仍统一显式闭合。
 */
const { createApp, defineComponent, ref, reactive, computed, onMounted, onUnmounted, watch, nextTick, markRaw } = Vue;

// ==================== 工作台登录 ====================
const ViewLogin = defineComponent({
  name: "ViewLogin",
  setup() {
    const keyInput = ref("");
    const loginMode = ref('user');
    const username = ref('');
    const password = ref('');
    const submitting = ref(false);
    const errorMessage = ref("");
    const errorField = ref('');
    const usernameControl = ref(null);
    const passwordControl = ref(null);
    const keyControl = ref(null);

    // 界面语言：选项名固定为各语言自称，与系统配置页保持一致
    const currentLang = computed(() => i18n.global.locale.value);
    const langOptions = [
      { value: "zh-CN", label: "简体中文" },
      { value: "en", label: "English" },
      { value: "zh-HK", label: "繁體中文（香港）" },
    ];
    function changeLang(value) {
      setLocale(value);
      errorMessage.value = '';
      errorField.value = '';
    }

    async function changeMode(value) {
      if (submitting.value || loginMode.value === value) return;
      loginMode.value = value;
      keyInput.value = password.value = errorMessage.value = errorField.value = '';
      await nextTick();
      (value === 'admin' ? keyControl : usernameControl).value?.focus();
    }

    function showFieldError(field, message, control) {
      errorField.value = field;
      errorMessage.value = tt(message);
      control.value?.focus();
    }

    async function submitLogin() {
      if (submitting.value) return;
      const key = keyInput.value.trim();
      if (loginMode.value === 'admin' && !key) {
        return showFieldError('key', 'login.keyEmpty', keyControl);
      }
      if (loginMode.value === 'user' && !username.value.trim()) {
        return showFieldError('username', 'login.usernameEmpty', usernameControl);
      }
      if (loginMode.value === 'user' && !password.value) {
        return showFieldError('password', 'login.passwordEmpty', passwordControl);
      }
      submitting.value = true;
      errorMessage.value = "";
      errorField.value = '';
      try {
        if (loginMode.value === 'admin') await checkApiKey(key);
        else await loginSession({username: username.value.trim(), password: password.value});
        keyInput.value = password.value = '';
        NocMessage.success(tt("login.success"));
      } catch (error) {
        errorMessage.value = error.status === 401
          ? tt(loginMode.value === 'admin' ? 'login.keyInvalid' : 'login.userInvalid')
          : error.message || tt('common.requestFailed');
      } finally {
        submitting.value = false;
      }
    }

    onMounted(() => usernameControl.value?.focus());
    return { keyInput, loginMode, username, password, submitting, errorMessage, errorField,
      usernameControl, passwordControl, keyControl, currentLang, langOptions, changeLang, changeMode, submitLogin };
  },
  template: `
    <div class="login-screen">
      <ui-select class="login-lang" size="small" :model-value="currentLang" @change="changeLang">
        <ui-option v-for="option in langOptions" :key="option.value"
                   :label="option.label" :value="option.value"></ui-option>
      </ui-select>

      <main class="login-card">
        <aside class="login-intro">
          <div class="login-brand">
            <div class="brand-mark login-brand-mark">NOC</div>
            <div><h1>{{ $t('common.brandName') }}</h1><p>NETWORK OPERATIONS CENTER</p></div>
          </div>
          <div class="login-intro-copy">
            <span class="login-eyebrow">MAIL · TASK · DISPATCH</span>
            <h2>{{ $t('login.introTitle') }}</h2>
            <p>{{ $t('login.introDescription') }}</p>
            <ol class="login-workflow">
              <li><span>01</span>{{ $t('login.receive') }}</li>
              <li><span>02</span>{{ $t('login.review') }}</li>
              <li><span>03</span>{{ $t('login.report') }}</li>
            </ol>
          </div>
          <p class="login-intro-footer">{{ $t('common.brandTagline') }}</p>
        </aside>
        <section class="login-form-panel">
          <header>
            <div class="login-access-label" aria-hidden="true"><ui-icon><Lock></Lock></ui-icon><span>{{ loginMode === 'admin' ? 'ADMIN ACCESS' : 'WORKSPACE ACCESS' }}</span></div>
            <h2 id="login-title" class="login-title">{{ $t(loginMode === 'admin' ? 'login.adminSignIn' : 'login.welcome') }}</h2>
            <p class="login-subtitle">{{ $t(loginMode === 'admin' ? 'login.adminSubtitle' : 'login.subtitle') }}</p></header>
          <form id="login-panel" class="login-form" aria-labelledby="login-title"
                :aria-busy="submitting" @submit.prevent="submitLogin">
            <div class="login-fields">
              <template v-if="loginMode === 'user'">
                <div class="login-field"><label for="login-username">{{ $t('login.username') }}</label>
                  <ui-input id="login-username" ref="usernameControl" v-model="username" size="large"
                    :aria-label="$t('login.username')" :placeholder="$t('login.usernamePlaceholder')" autocomplete="username"
                    :disabled="submitting" :aria-invalid="errorField === 'username'" aria-describedby="login-error">
                    <template #prefix><ui-icon aria-hidden="true"><User></User></ui-icon></template>
                  </ui-input>
                </div>
                <div class="login-field"><label for="login-password">{{ $t('login.password') }}</label>
                  <ui-input id="login-password" ref="passwordControl" v-model="password" type="password" show-password size="large"
                    :aria-label="$t('login.password')" :placeholder="$t('login.passwordPlaceholder')" autocomplete="current-password"
                    :disabled="submitting" :aria-invalid="errorField === 'password'" aria-describedby="login-error">
                    <template #prefix><ui-icon aria-hidden="true"><Lock></Lock></ui-icon></template>
                  </ui-input>
                </div>
              </template>
              <template v-else>
                <div class="login-field"><label for="login-key">API Key</label>
                  <ui-input id="login-key" ref="keyControl" v-model="keyInput" type="password" show-password size="large"
                    :placeholder="$t('login.keyPlaceholder')" aria-label="API Key" autocomplete="off"
                    :disabled="submitting" :aria-invalid="errorField === 'key'" aria-describedby="login-error">
                    <template #prefix><ui-icon aria-hidden="true"><Key></Key></ui-icon></template>
                  </ui-input>
                </div>
                <p class="login-admin-note">{{ $t('login.adminScope') }}</p>
              </template>
            </div>
            <div class="login-feedback"><p v-if="errorMessage" id="login-error" class="login-error" role="alert">{{ errorMessage }}</p></div>
            <ui-button class="login-submit" type="primary" size="large" native-type="submit"
                       :aria-label="$t('login.submit')" :loading="submitting" :disabled="submitting"><span>{{ $t('login.submit') }}</span><ui-icon aria-hidden="true"><ArrowRight></ArrowRight></ui-icon></ui-button>
          </form>
          <p class="login-hint">{{ $t(loginMode === 'admin' ? 'login.adminHint' : 'login.userHint') }}</p>
          <footer class="login-footer">
            <button class="login-mode-switch" type="button" :disabled="submitting" aria-controls="login-panel"
                    @click="changeMode(loginMode === 'user' ? 'admin' : 'user')">
              <ui-icon aria-hidden="true"><Key v-if="loginMode === 'user'"></Key><ArrowLeft v-else></ArrowLeft></ui-icon>
              <span>{{ $t(loginMode === 'user' ? 'login.adminSignIn' : 'login.backToUser') }}</span>
            </button>
          </footer>
        </section>
      </main>
    </div>
  `,
});

// ==================== 供应商配置 ====================
const ViewSuppliers = defineComponent({
  name: "ViewSuppliers",
  setup() {
    const activeTab = ref(new URLSearchParams(window.location.search).has('draft') ? 'drafts' : 'formal');
    const suppliers = ref([]);
    const loading = ref(false);

    async function loadSuppliers() {
      loading.value = true;
      try {
        suppliers.value = await requestJson("/api/suppliers");
        appStore.supplierCount = suppliers.value.length;
        setStatusKey("suppliers.synced");
      } catch (error) {
        suppliers.value = [];
        setStatus(error.message, "error");
      } finally {
        loading.value = false;
      }
    }

    async function removeSupplier(supplier) {
      try {
        await NocDialog.confirm(
          tt("suppliers.deleteConfirm", { name: supplier.name }),
          tt("suppliers.deleteTitle"),
          { confirmButtonText: tt("common.confirmDelete"), cancelButtonText: tt("common.cancel"), type: "warning" },
        );
      } catch {
        return;
      }
      try {
        await requestJson(`/api/suppliers/${supplier.id}`, { method: "DELETE" });
        NocMessage.success(tt("suppliers.deleted"));
        await loadSuppliers();
      } catch (error) {
        NocMessage.error(error.message);
      }
    }

    function goCreate() {
      openSupplierForm(null);
    }

    function goEdit(row) {
      openSupplierForm(row.id);
    }

    onMounted(() => {
      if (appStore.apiKey) {
        loadSuppliers();
      }
    });

    return {
      suppliers, loading, loadSuppliers, removeSupplier, goCreate, goEdit, activeTab,
      icons: ElementPlusIconsVue,
    };
  },
  template: `
    <div class="view-body supplier-config-view">
      <ui-tabs v-model="activeTab" class="supplier-config-tabs"><ui-tab-pane :label="$t('discovery.formal')" name="formal"></ui-tab-pane><ui-tab-pane :label="$t('discovery.drafts')" name="drafts"></ui-tab-pane></ui-tabs>
      <supplier-drafts-table v-if="activeTab === 'drafts'"></supplier-drafts-table>
      <ui-card v-else shadow="never" class="table-card">
        <template #header>
          <div class="card-header">
            <h2 class="card-title">{{ $t('suppliers.listTitle') }}</h2>
            <div class="toolbar-actions">
              <ui-action icon="Refresh" :label="$t('common.refresh')" :loading="loading" @click="loadSuppliers"></ui-action>
              <ui-button type="primary" :icon="icons.Plus" @click="goCreate">{{ $t('suppliers.create') }}</ui-button>
            </div>
          </div>
        </template>
        <ui-table v-loading="loading" :data="suppliers" :empty-text="$t('suppliers.empty')" stripe>
          <ui-table-column prop="name" :label="$t('suppliers.name')" min-width="160">
            <template #default="{ row }">
              <span class="cell-main">{{ row.name }}</span>
            </template>
          </ui-table-column>
          <ui-table-column prop="email" :label="$t('common.email')" min-width="220"></ui-table-column>
          <ui-table-column prop="reply_email" :label="$t('suppliers.replyEmail')" min-width="220"></ui-table-column>
          <ui-table-column prop="update_time" :label="$t('common.updateTime')" width="180">
            <template #default="{ row }">
              <span class="mono muted">{{ (row.update_time || '').slice(0, 19).replace('T', ' ') }}</span>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('common.actions')" width="112" align="center" fixed="right">
            <template #default="{ row }">
              <div class="row-actions">
                <ui-action type="primary" @click="goEdit(row)" icon="Edit" :label="$t('common.edit')"></ui-action>
                <ui-action type="danger" @click="removeSupplier(row)" icon="Delete" :label="$t('common.delete')"></ui-action>
              </div>
            </template>
          </ui-table-column>
        </ui-table>
      </ui-card>
    </div>
  `,
});

// ==================== 供应商表单页（新增/编辑） ====================
// 提取预览字段标签：运行时按当前语言取值，无词典条目时回退字段名
function extractFieldLabel(key) {
  const i18nKey = `supplierForm.extractFields.${key}`;
  return hasI18nKey(i18nKey) ? tt(i18nKey) : key;
}

// 从 AI 返回文本中提取所有顶层 JSON 对象（容忍 ``` 围栏与 --- 分隔）
function extractJsonObjects(text) {
  const objects = [];
  let index = 0;
  while (index < text.length) {
    const start = text.indexOf("{", index);
    if (start === -1) {
      break;
    }
    let depth = 0;
    let inString = false;
    let escaped = false;
    let end = -1;
    for (let j = start; j < text.length; j += 1) {
      const ch = text[j];
      if (inString) {
        if (escaped) {
          escaped = false;
        } else if (ch === "\\") {
          escaped = true;
        } else if (ch === '"') {
          inString = false;
        }
        continue;
      }
      if (ch === '"') {
        inString = true;
      } else if (ch === "{") {
        depth += 1;
      } else if (ch === "}") {
        depth -= 1;
        if (depth === 0) {
          end = j;
          break;
        }
      }
    }
    if (end === -1) {
      break;
    }
    const raw = text.slice(start, end + 1);
    try {
      objects.push(JSON.parse(raw));
    } catch {
      objects.push({ __raw: raw });
    }
    index = end + 1;
  }
  return objects;
}

// 将提取预览结果解析为结构化展示块
function buildExtractPreviewView(text) {
  if (!text || !text.trim()) {
    return { blocks: [], raw: "" };
  }
  const cleaned = text.replace(/```json|```/g, "");
  const objects = extractJsonObjects(cleaned);
  if (!objects.length) {
    return { blocks: [], raw: text };
  }
  const blocks = [];
  let hasStructured = false;
  for (const obj of objects) {
    if (obj && obj.__raw) {
      blocks.push({ kind: "raw", text: obj.__raw });
      continue;
    }
    if (obj && obj.mail_type && Object.keys(obj).length <= 3) {
      blocks.push({ kind: "classify", mailType: obj.mail_type });
      hasStructured = true;
      continue;
    }
    if (!obj || typeof obj !== "object") {
      continue;
    }
    const fields = [];
    let tags = [];
    let lines = [];
    let lineColumns = [];
    for (const [key, value] of Object.entries(obj)) {
      if (key === "line_query_keywords") {
        tags = Array.isArray(value) ? value.filter(Boolean) : [];
        hasStructured = true;
        continue;
      }
      if (key === "line_array") {
        lines = Array.isArray(value) ? value.filter((row) => row && typeof row === "object") : [];
        lineColumns = lines.length ? Object.keys(lines[0]) : [];
        hasStructured = true;
        continue;
      }
      const display = value == null ? "" : String(value);
      if (!display.trim()) {
        // 空字段不展示，减少干扰
        continue;
      }
      let timeRange = null;
      if (key.endsWith("_time") && display.includes("/")) {
        const [startTime, endTime] = display.split("/").map((part) => part.trim());
        timeRange = { startTime, endTime };
      }
      fields.push({
        key,
        label: extractFieldLabel(key),
        value: display,
        timeRange,
      });
      hasStructured = true;
    }
    blocks.push({ kind: "extract", fields, tags, lines, lineColumns });
  }
  return { blocks, raw: hasStructured ? "" : text };
}

const ViewSupplierForm = defineComponent({
  name: "ViewSupplierForm",
  components: {MailAttachmentList, MailAttachmentPreview},
  props: {
    supplierId: { type: Number, default: null },
    draftId: { type: Number, default: null },
  },
  emits: ['close', 'published'],
  setup(props, {emit}) {
    const isEdit = computed(() => props.supplierId != null);
    const isDraft = computed(() => props.draftId != null);
    const draftRecord = ref(null);
    const draftReadOnly = computed(() => isDraft.value && draftRecord.value?.status !== 'review');
    const retryingDraft = ref(false);
    const supplierNameInput = ref(null);
    const loading = ref(false);
    const saving = ref(false);
    const loadFailed = ref(false);

    const form = reactive({
      name: "",
      email: "",
      reply_email: "",
      extra_instructions: "",
    });
    watch(() => form.email, (email, previousEmail) => {
      if (!form.reply_email || form.reply_email === previousEmail) {
        form.reply_email = email;
      }
    });
    const fixedDefaults = ref(null); // { top_fields: [], line_fields: [] }
    const fixedFields = ref([]); // [{ name, required, description, value, customized, isLineField }]
    const selectedFixedFieldName = ref("");
    const selectedFixedField = computed(() => (
      fixedFields.value.find((field) => field.name === selectedFixedFieldName.value)
      || fixedFields.value[0]
      || null
    ));
    function isFixedFieldCustomized(field) {
      const value = field.value.trim();
      return Boolean(value && value !== field.description.trim());
    }
    const customizedFixedFieldCount = computed(() => fixedFields.value.filter((field) => {
      return isFixedFieldCustomized(field);
    }).length);
    const defaultFixedFieldCount = computed(() => (
      Math.max(fixedFields.value.length - customizedFixedFieldCount.value, 0)
    ));
    const sectionActiveNames = ref(['mailTypes', 'fixed', 'custom', 'topCustom', 'prompt']);
    const showAdvancedPrompt = ref(false);
    const mailTypes = ref([]); // [{ name, subject, content, contentInAttachment }]
    const configuredSamplesRestricted = ref(false);
    const reviewSampleMode = ref('configured');
    const samplesRestricted = computed(() => configuredSamplesRestricted.value
      && (!isDraft.value || reviewSampleMode.value !== 'collected'));
    const samplesReadOnly = ref(false);
    const mailTypeOptions = ref([]);
    const mailTypeDialogVisible = ref(false);
    const mailTypeName = ref('');
    const mailTypeNameError = ref('');
    const mailTypeNameInput = ref(null);
    const sampleEditor = ref(null);
    const loadingOriginalSample = ref(false);
    const configuredMailTypeCount = computed(() => mailTypes.value.filter((item) => {
      return item.subject.trim() || item.content.trim();
    }).length);
    const lineFields = ref([]); // [{ name, description, keyword }]
    const topCustomFields = ref([]); // [{ name, description }] 顶层自定义字段（提取结果顶层输出，供特殊规则判断等）
    const reviewMetadata = ref({questions:[], confirmations:{}});
    const legacyPrompt = ref("");
    const promptPreview = ref("");
    const extractPreview = ref("");
    const extractPreviewView = computed(() => buildExtractPreviewView(extractPreview.value));
    const previewing = ref(false);
    const extracting = ref(false);
    const extractFiles = ref([]); // ui-upload 文件列表，提取预览时随请求上传

    const editorTitle = computed(() => tt(isDraft.value ? (draftReadOnly.value ? (draftRecord.value?.status==='published' ? 'supplierReview.viewRecord' : 'supplierReview.viewMails') : 'draftReview.title') : isEdit.value ? 'supplierOperator.editTitle' : 'supplierOperator.createTitle'));
    const usesManualPrompt = computed(() => Boolean(legacyPrompt.value.trim() && !lineFields.value.some(row => row.name.trim() || row.description.trim())));
    function supplierFieldLabel(name) {
      // Custom fields use their literal output key everywhere in the editor.
      if (!fixedFields.value.some(field => field.name === name)) return name;
      return hasI18nKey(`draftReview.fields.${name}`) ? tt(`draftReview.fields.${name}`) : extractFieldLabel(name);
    }
    const review = useSupplierReview({form, isDraft, isEdit, draftRecord, draftReadOnly, mailTypes, fixedFields, lineFields,
      topCustomFields, legacyPrompt, usesManualPrompt, extractFiles, extractPreview, extractPreviewView, reviewMetadata,
      samplesRestricted, samplesReadOnly, reviewSampleMode, supplierFieldLabel});
    async function openSupplierSection(key) {
      if (key === 'basic') { supplierNameInput.value?.focus(); return; }
      review.showAdvanced.value = true;
      const names = key === 'rules' ? ['fixed', 'custom'] : [key];
      sectionActiveNames.value = [...new Set([...sectionActiveNames.value, ...names])];
      await nextTick();
      const element = document.getElementById(`${isDraft.value ? 'draft' : 'supplier'}-section-${names[0]}`);
      element?.scrollIntoView({block:'start'});
      element?.querySelector('input:not(:disabled), textarea, button[role="tab"]')?.focus({preventScroll:true});
    }

    async function ensureFixedDefaults() {
      if (!fixedDefaults.value) {
        fixedDefaults.value = await requestJson("/api/suppliers/field-defaults");
      }
      return fixedDefaults.value;
    }

    async function ensureMailTypeOptions() {
      if (!mailTypeOptions.value.length) {
        mailTypeOptions.value = await requestJson("/api/suppliers/mail-types");
      }
      return mailTypeOptions.value;
    }

    async function fillMailTypes(supplier) {
      const options = await ensureMailTypeOptions();
      const samples = (supplier && supplier.email_type_samples) || {};
      const names = [...new Set([...options, ...Object.keys(samples)])];
      mailTypes.value = names.map((name) => {
        const sample = samples[name] || {};
        return {
          name,
          isCustom: !options.includes(name),
          subject: sample.subject || "",
          content: sample.content || "",
          contentInAttachment: Boolean(sample.content_in_attachment),
          source_email_records_id: sample.source_email_records_id || null,
        };
      });
    }

    function openMailTypeDialog() {
      mailTypeName.value = '';
      mailTypeNameError.value = '';
      mailTypeDialogVisible.value = true;
    }

    function addMailType() {
      const name = mailTypeName.value.trim();
      if (!name || Array.from(name).length > 32 || /[\u0000-\u001f\u007f-\u009f]/u.test(name)) {
        mailTypeNameError.value = tt('supplierForm.mailTypeNameInvalid');
        return;
      }
      if (name === '其它') {
        mailTypeNameError.value = tt('supplierForm.mailTypeNameReserved');
        return;
      }
      if (mailTypes.value.some(item => item.name === name)) {
        mailTypeNameError.value = tt('supplierForm.mailTypeNameDuplicate');
        return;
      }
      mailTypes.value.push({name, isCustom:true, subject:'', content:'', contentInAttachment:false});
      if (!sectionActiveNames.value.includes('mailTypes')) sectionActiveNames.value.push('mailTypes');
      mailTypeDialogVisible.value = false;
    }

    function removeMailType(item) {
      if (item.isCustom) mailTypes.value = mailTypes.value.filter(value => value !== item);
    }

    async function fillFromSupplier(supplier) {
      reviewMetadata.value = {questions:supplier?.review_metadata?.questions || draftRecord.value?.draft?.unresolved_questions || [],
        confirmations:{...(supplier?.review_metadata?.confirmations || {})}};
      configuredSamplesRestricted.value = Boolean(supplier?.samples_restricted);
      samplesReadOnly.value = Boolean(supplier?.samples_read_only);
      form.name = supplier ? supplier.name || "" : "";
      form.email = supplier ? supplier.email : "";
      form.reply_email = supplier ? supplier.reply_email || supplier.email : "";
      form.extra_instructions = supplier ? supplier.extra_instructions || "" : "";
      legacyPrompt.value = "";
      promptPreview.value = "";
      extractPreview.value = "";
      extractFiles.value = [];
      lineFields.value = [];
      topCustomFields.value = [];

      try {
        const defaults = await ensureFixedDefaults();
        const overrides = (supplier && supplier.fixed_field_rules) || {};
        const allFields = [...(defaults.top_fields || []), ...(defaults.line_fields || [])];
        fixedFields.value = allFields.map((field) => {
          const override = overrides[field.name] || "";
          return {
            name: field.name,
            required: Boolean(field.required),
            description: field.description || "",
            value: override || field.description || "",
            customized: Boolean(override),
            isLineField: (defaults.line_fields || []).some((item) => item.name === field.name),
          };
        });
      } catch (error) {
        fixedFields.value = [];
        setStatus(error.message, "error");
      }
      selectedFixedFieldName.value = (
        fixedFields.value.find((field) => isFixedFieldCustomized(field))
        || fixedFields.value[0]
        || { name: "" }
      ).name;

      try {
        await fillMailTypes(supplier);
      } catch (error) {
        mailTypes.value = [];
        setStatus(error.message, "error");
      }

      if (supplier) {
        const customFields = Array.isArray(supplier.line_custom_fields) ? supplier.line_custom_fields : [];
        const topFields = Array.isArray(supplier.custom_fields) ? supplier.custom_fields : [];
        topCustomFields.value = topFields.map((field) => ({
          name: field.name || "",
          description: field.description || "",
        }));
        const keywords = Array.isArray(supplier.line_query_keywords) ? supplier.line_query_keywords : [];
        if (supplier.prompt_mode === "manual") {
          legacyPrompt.value = supplier.cutover_extract_prompt || "";
          lineFields.value = [{ name: "", description: "", keyword: false }];
        } else if (customFields.length) {
          lineFields.value = customFields.map((field) => ({
            name: field.name || "",
            description: field.description || "",
            keyword: keywords.includes(field.name),
          }));
        } else {
          lineFields.value = [{ name: "", description: "", keyword: false }];
        }
      } else {
        lineFields.value = [{ name: "", description: "", keyword: false }];
      }
    }

    async function loadForm() {
      loading.value = true;
      loadFailed.value = false;
      try {
        draftRecord.value = isDraft.value ? await requestJson(`/api/supplier-drafts/${props.draftId}`) : null;
        const supplier = isDraft.value ? (draftRecord.value.draft?.config || {email:draftRecord.value.sender}) : isEdit.value
          ? await requestJson(`/api/suppliers/${props.supplierId}`)
          : null;
        await fillFromSupplier(supplier);
      } catch (error) {
        loadFailed.value = true;
        setStatus(error.message, "error");
      } finally {
        loading.value = false;
      }
    }

    async function retryDraft() {
      if (retryingDraft.value || draftRecord.value?.status !== 'generation_failed') return;
      retryingDraft.value = true;
      try {
        await requestJson(`/api/supplier-drafts/${props.draftId}/retry`, {method:'POST'});
        await loadForm();
        NocMessage.success(tt('discovery.retryAccepted'));
      } catch (error) { NocMessage.error(error.message); }
      finally { retryingDraft.value = false; }
    }
    function editPublishedSupplier() {
      if (draftRecord.value?.published_supplier_id) openSupplierForm(draftRecord.value.published_supplier_id);
    }

    async function loadOriginalSample(item) {
      const sourceId = draftRecord.value?.source_email_records_id;
      if (!sourceId || loadingOriginalSample.value) return;
      loadingOriginalSample.value = true;
      try {
        const source = await requestJson(`/api/emails/${sourceId}/source`);
        item.source_email_records_id = source.id;
        item.subject = source.subject || '';
        item.content = source.html_content || source.content || '';
        NocMessage.success(tt('supplierForm.originalSampleLoaded'));
      } catch (error) { NocMessage.error(error.message); }
      finally { loadingOriginalSample.value = false; }
    }

    function addLineField() {
      lineFields.value.push({ name: "", description: "", keyword: false });
    }

    function removeLineField(index) {
      lineFields.value.splice(index, 1);
    }

    function addTopCustomField() {
      topCustomFields.value.push({ name: "", description: "" });
    }

    function removeTopCustomField(index) {
      topCustomFields.value.splice(index, 1);
    }

    function collectTopCustomFields() {
      const fields = [];
      for (const row of topCustomFields.value) {
        const name = row.name.trim();
        const description = row.description.trim();
        if (!name && !description) {
          continue;
        }
        fields.push({ name, description });
      }
      return fields;
    }

    function selectFixedField(field) {
      selectedFixedFieldName.value = field.name;
    }

    function moveFixedFieldSelection(offset) {
      if (!fixedFields.value.length) {
        return;
      }
      const currentIndex = fixedFields.value.findIndex(
        (field) => field.name === selectedFixedFieldName.value,
      );
      const nextIndex = (currentIndex + offset + fixedFields.value.length) % fixedFields.value.length;
      selectedFixedFieldName.value = fixedFields.value[nextIndex].name;
      nextTick(() => {
        document.getElementById(`fixed-field-tab-${selectedFixedFieldName.value}`)?.focus();
      });
    }

    function restoreSelectedFixedField() {
      if (selectedFixedField.value) {
        selectedFixedField.value.value = selectedFixedField.value.description;
      }
    }

    function collectFixedFieldRules() {
      const rules = {};
      for (const field of fixedFields.value) {
        const value = field.value.trim();
        if (value && value !== field.description.trim()) {
          rules[field.name] = value;
        }
      }
      return rules;
    }

    function collectLineConfig() {
      const lineCustomFields = [];
      const lineQueryKeywords = [];
      for (const row of lineFields.value) {
        const name = row.name.trim();
        const description = row.description.trim();
        if (!name && !description) {
          continue;
        }
        lineCustomFields.push({ name, description });
        if (row.keyword && name) {
          lineQueryKeywords.push(name);
        }
      }
      return { lineCustomFields, lineQueryKeywords };
    }

    function isMailTypeItemConfigured(item) {
      return Boolean(item.subject.trim() || item.content.trim() || item.contentInAttachment);
    }

    function collectMailTypeSamples() {
      const requiredType = mailTypes.value.find((item) => item.name === "割接通知");
      if (!requiredType) {
        throw new Error(tt("supplierForm.mailTypeNotLoaded"));
      }
      if (!requiredType.subject.trim()) {
        throw new Error(tt("supplierForm.subjectSampleRequired"));
      }
      if (!requiredType.content.trim()) {
        throw new Error(tt("supplierForm.contentSampleRequired"));
      }
      const emailTypeSamples = Object.create(null);
      for (const item of mailTypes.value) {
        if (!item.isCustom && item.name !== "割接通知" && !isMailTypeItemConfigured(item)) {
          continue;
        }
        emailTypeSamples[item.name] = {
          subject: item.subject.trim(),
          content: item.content.trim(),
          content_in_attachment: item.contentInAttachment,
          source_email_records_id: item.source_email_records_id || null,
        };
      }
      return emailTypeSamples;
    }

    function buildSupplierPayload() {
      const { lineCustomFields, lineQueryKeywords } = collectLineConfig();
      const legacy = legacyPrompt.value.trim();
      const payload = {
        name: form.name.trim(),
        email: form.email.trim(),
        reply_email: form.reply_email.trim() || form.email.trim(),
        extra_instructions: form.extra_instructions.trim(),
      };
      if (!samplesReadOnly.value) {
        payload.review_metadata = review.reviewMetadataPayload();
        payload.email_type_samples = isDraft.value ? collectCurrentMailTypeSamples() : collectMailTypeSamples();
      }
      if (lineCustomFields.length || !legacy) {
        payload.prompt_mode = "auto";
        payload.line_custom_fields = lineCustomFields;
        payload.line_query_keywords = lineQueryKeywords;
        payload.fixed_field_rules = collectFixedFieldRules();
        payload.custom_fields = collectTopCustomFields();
        payload.cutover_extract_prompt = "";
      } else {
        payload.prompt_mode = "manual";
        payload.line_custom_fields = [];
        payload.line_query_keywords = [];
        payload.fixed_field_rules = {};
        payload.custom_fields = [];
        payload.cutover_extract_prompt = legacy;
      }
      if (!isDraft.value && !lineCustomFields.length && !legacy) {
        throw new Error(tt("supplierForm.lineFieldRequired"));
      }
      return payload;
    }

    async function previewPrompt() {
      showAdvancedPrompt.value = true;
      await openSupplierSection('prompt');
      previewing.value = true;
      try {
        promptPreview.value = await resolveCurrentPrompt();
        setStatusKey("supplierForm.promptPreviewReady");
      } catch (error) {
        promptPreview.value = "";
        setStatus(error.message, "error");
      } finally {
        previewing.value = false;
      }
    }

    function collectPromptConfig() {
      const { lineCustomFields, lineQueryKeywords } = collectLineConfig();
      return {
        line_custom_fields: lineCustomFields,
        line_query_keywords: lineQueryKeywords,
        fixed_field_rules: collectFixedFieldRules(),
        custom_fields: collectTopCustomFields(),
        extra_instructions: form.extra_instructions.trim(),
      };
    }

    async function resolveCurrentPrompt(config = collectPromptConfig(), manual = usesManualPrompt.value ? legacyPrompt.value.trim() : "") {
      if (manual) {
        return manual;
      }
      const data = await requestJson("/api/suppliers/preview-prompt", {
        method: "POST",
        body: JSON.stringify(config),
      });
      return data.cutover_extract_prompt;
    }

    function collectCurrentMailTypeSamples() {
      // 预览用，不做必填校验，空样本由后端提示词生成时自动跳过
      const samples = Object.create(null);
      for (const item of mailTypes.value) {
        samples[item.name] = {
          subject: item.subject.trim(),
          content: item.content.trim(),
          content_in_attachment: item.contentInAttachment,
          source_email_records_id: item.source_email_records_id || null,
        };
      }
      return samples;
    }

    async function uploadExtractFiles(files = [...extractFiles.value]) {
      const attachments = [];
      for (const item of files) {
        const formData = new FormData();
        formData.append("file", item.raw);
        const response = await fetch("/api/suppliers/preview-attachments", {
          method: "POST",
          headers: { 'X-CSRF-Token': appStore.csrfToken },
          body: formData,
        });
        const payload = await response.json();
        if (!response.ok || payload.success === false) {
          throw new Error(payload.message || tt("supplierForm.attachmentUploadFailed", { name: item.name }));
        }
        attachments.push(payload.data.relative_path);
      }
      return attachments;
    }

    async function previewExtract() {
      if (extracting.value || samplesRestricted.value || draftReadOnly.value || review.sourceBusy.value || review.collectedBusy.value) return;
      const sample = review.activeSample.value;
      if (review.reviewMailType.value !== '割接通知') return;
      if (!sample) {
        NocMessage.error(tt("supplierForm.mailTypeNotLoaded"));
        return;
      }
      if (!sample.subject.trim() && !sample.content.trim()) {
        NocMessage.error(tt("supplierForm.previewNeedsSample"));
        return;
      }
      if (!await review.closeCorrection()) return;
      const fingerprint = review.reviewFingerprint.value;
      const ruleSnapshot = review.ruleSnapshot();
      const config = collectPromptConfig();
      const manual = usesManualPrompt.value ? legacyPrompt.value.trim() : '';
      const files = [...extractFiles.value];
      const sourceAttachments = review.attachments.value.filter(item => !item.raw && item.path)
        .map(item => decodeURIComponent(item.path.slice('/api/email/attachments/'.length)));
      const payload = {
        subject:sample.subject.trim(), content:sample.content.trim(), content_in_attachment:sample.contentInAttachment,
        sender:form.email.trim(), supplier_name:form.name.trim(), email_type_samples:collectCurrentMailTypeSamples()
      };
      review.showAdvanced.value = false;
      review.reviewStage.value = 'review';
      review.reviewError.value = '';
      extracting.value = true;
      try {
        const attachments = [...sourceAttachments, ...await uploadExtractFiles(files)];
        const cutoverExtractPrompt = await resolveCurrentPrompt(config, manual);
        const data = await requestJson('/api/suppliers/preview-extract', {
          method:'POST', body:JSON.stringify({...payload, attachments, cutover_extract_prompt:cutoverExtractPrompt})
        });
        extractPreview.value = typeof data.extract_result === 'string' ? data.extract_result : JSON.stringify(data.extract_result ?? '');
        review.resultFingerprint.value = fingerprint;
        review.resultRuleSnapshot.value = ruleSnapshot;
        setStatusKey('supplierForm.extractPreviewReady');
      } catch (error) {
        review.reviewError.value = error.message;
        setStatus(error.message, 'error');
      } finally {
        extracting.value = false;
      }
    }

    async function saveSupplier() {
      if (!await review.closeCorrection()) return;
      if (!isDraft.value && !form.name.trim()) {
        await openSupplierSection('basic');
        NocMessage.error(tt('supplierOperator.nameRequired'));
        supplierNameInput.value?.focus();
        return;
      }
      let payload;
      try {
        payload = buildSupplierPayload();
      } catch (error) {
        NocMessage.error(error.message);
        return;
      }
      saving.value = true;
      try {
        if (isDraft.value) {
          draftRecord.value = await requestJson(`/api/supplier-drafts/${props.draftId}`, {
            method: 'PUT', body: JSON.stringify({revision: draftRecord.value.revision, config: payload}),
          });
          NocMessage.success(tt('discovery.draftSaved'));
          return true;
        }
        const path = isEdit.value ? `/api/suppliers/${props.supplierId}` : "/api/suppliers";
        await requestJson(path, {
          method: isEdit.value ? "PATCH" : "POST",
          body: JSON.stringify(payload),
        });
        NocMessage.success(isEdit.value ? tt("supplierForm.saved") : tt("supplierForm.created"));
        navigateTo("suppliers");
      } catch (error) {
        NocMessage.error(error.message);
        setStatus(error.message, "error");
      } finally {
        saving.value = false;
      }
    }

    async function publishDraft() {
      if (!form.name.trim()) {
        if (!sectionActiveNames.value.includes('basic')) sectionActiveNames.value.push('basic');
        NocMessage.error(tt('discovery.nameRequiredForPublish'));
        await nextTick();
        supplierNameInput.value?.focus();
        return;
      }
      try {
        collectMailTypeSamples();
      } catch (error) {
        await openSupplierSection('mailTypes');
        NocMessage.error(error.message);
        return;
      }
      if (!(await saveSupplier())) return;
      try {
        await NocDialog.confirm(tt('discovery.publishConfirm'), tt('discovery.publish'), {type: 'warning', confirmButtonText: tt('discovery.publish'), cancelButtonText: tt('common.cancel')});
      } catch { return; }
      saving.value = true;
      try {
        await requestJson(`/api/supplier-drafts/${props.draftId}/publish`, {method:'POST', body:JSON.stringify({revision:draftRecord.value.revision})});
        draftRecord.value.status = 'published';
        NocMessage.success(tt('discovery.publishedMessage'));
        emit('published');
      } catch (error) { NocMessage.error(error.message); }
      finally { saving.value = false; }
    }

    onMounted(() => {
      if (appStore.apiKey) {
        loadForm();
      }
    });

    return {
      isEdit, isDraft, draftRecord, draftReadOnly, retryingDraft, retryDraft, loadForm, editPublishedSupplier, supplierNameInput, publishDraft, loading, saving, loadFailed, form,
      ...review, editorTitle, usesManualPrompt, supplierFieldLabel, openSupplierSection, showAdvancedPrompt,
      fixedFields, selectedFixedField, selectedFixedFieldName,
      customizedFixedFieldCount, defaultFixedFieldCount,
      mailTypes, configuredMailTypeCount, samplesRestricted, samplesReadOnly,
      sampleEditor, loadingOriginalSample, loadOriginalSample,
      mailTypeDialogVisible, mailTypeName, mailTypeNameError, mailTypeNameInput,
      openMailTypeDialog, addMailType, removeMailType,
      sectionActiveNames, lineFields, topCustomFields, legacyPrompt, promptPreview, previewing,
      extractPreview, extracting, extractFiles, extractPreviewView,
      isFixedFieldCustomized, selectFixedField, moveFixedFieldSelection,
      restoreSelectedFixedField, addLineField, removeLineField,
      addTopCustomField, removeTopCustomField, previewPrompt,
      previewExtract, saveSupplier,
    };
  },
  methods: {
    async goBack() {
      if (!await this.closeCorrection()) return;
      if (this.isDraft) { this.$emit('close'); return; }
      navigateTo("suppliers");
    },
  },
  computed: {
    icons() {
      return ElementPlusIconsVue;
    },
  },
  template: `
    <div class="view-body supplier-form-view supplier-operator-form supplier-form" :class="{'draft-operator-form':isDraft}" v-loading="loading">
      <header class="draft-editor-head">
        <div><p>{{ editorTitle }}</p><h2>{{ form.name.trim() || $t('draftReview.unnamed') }}</h2><span>{{ form.email }}</span></div>
        <div class="supplier-section-actions">
          <ui-button v-if="reviewStage === 'review' && (!draftReadOnly || draftRecord?.draft)" size="small" :aria-expanded="showAdvanced" @click="toggleReviewAdvanced">{{ $t(showAdvanced ? 'supplierReview.back' : 'supplierReview.advanced') }}</ui-button>
          <ui-button size="small" @click="goBack">{{ $t(isDraft ? 'supplierReview.backToList' : 'common.cancel') }}</ui-button>
          <ui-button v-if="isDraft && draftRecord?.status === 'review'" size="small" :loading="saving" :disabled="loading || loadFailed" @click="saveSupplier">{{ $t('discovery.saveDraft') }}</ui-button>
          <ui-button v-if="isDraft && draftRecord?.status === 'review'" size="small" type="primary" :loading="saving" :disabled="loading || loadFailed" @click="publishDraft">{{ $t('discovery.publish') }}</ui-button>
          <ui-button v-if="!isDraft && reviewStage === 'review'" size="small" type="primary" :loading="saving" :disabled="loading || loadFailed" @click="saveSupplier">{{ $t('supplierForm.saveConfig') }}</ui-button>
        </div>
      </header>
      ${SUPPLIER_REVIEW_TEMPLATE}

      <p v-if="!loading && loadFailed" class="empty-inline">{{ $t('common.loadFailedBack') }}</p>

      <div v-if="showAdvanced && !loadFailed" class="supplier-advanced-config">
      <p class="field-hint">{{ $t('supplierReview.advancedHint') }}</p>
      <details v-if="isDraft && draftRecord?.draft?.evidence?.length" class="review-generation-evidence"><summary>{{ $t('discovery.evidence') }}</summary><ul><li v-for="(text,index) in draftRecord.draft.evidence" :key="index">{{ text }}</li></ul></details>
      <details v-if="draftReadOnly && draftRecord?.draft?.config" class="review-config-snapshot"><summary>{{ $t('supplierReview.snapshot') }}</summary><pre>{{ JSON.stringify(draftRecord.draft.config,null,2) }}</pre></details>
      <ui-collapse v-if="!draftReadOnly"
                   v-model="sectionActiveNames"
                   class="supplier-form-page supplier-section-collapse">
        <!-- 邮件类型样本 -->
        <ui-collapse-item name="mailTypes" :id="isDraft ? 'draft-section-mailTypes' : 'supplier-section-mailTypes'" class="supplier-section supplier-section--mail-types">
          <template #title>
            <div class="supplier-section-head">
              <strong>{{ $t('draftReview.samples') }}</strong>
              <div class="supplier-section-actions" :aria-label="$t('supplierForm.mailTypesStatsLabel')">
                <span class="is-configured">{{ $t('supplierForm.configuredCount', { count: configuredMailTypeCount, total: mailTypes.length }) }}</span>
                <ui-button size="small" :icon="icons.Plus" :disabled="samplesReadOnly || !mailTypes.length" @click.stop="openMailTypeDialog">{{ $t('supplierForm.addMailType') }}</ui-button>
              </div>
            </div>
          </template>
          <p class="field-hint">{{ $t('draftReview.sampleHint') }}</p>
          <ui-alert v-if="samplesRestricted" type="info" :closable="false" title="邮件样本未获来源邮箱授权，已隐藏；其他配置仍可维护。"></ui-alert>
          <div v-else-if="!mailTypes.length" class="empty-inline">{{ $t('supplierForm.mailTypesLoadFailed') }}</div>
          <div v-else class="mail-type-list" :aria-label="$t('supplierForm.mailTypesListLabel')">
            <div v-for="item in mailTypes" :key="item.name" class="mail-type-item">
              <div class="mail-type-heading">
                <span class="form-label mail-type-name">{{ item.name }}<span v-if="item.name === '割接通知'" class="required-mark"> *</span></span>
                <div class="toolbar-actions">
                  <ui-button v-if="isDraft && draftRecord?.source_email_records_id && item.name === '割接通知'" size="small" :loading="loadingOriginalSample" @click="loadOriginalSample(item)">{{ $t('supplierForm.loadOriginalSample') }}</ui-button>
                  <ui-button size="small" :disabled="samplesReadOnly" @click="sampleEditor=item">{{ $t('supplierForm.expandSample') }}</ui-button>
                  <ui-action v-if="item.isCustom" :disabled="samplesReadOnly" type="danger" @click="removeMailType(item)" icon="Delete" :label="$t('supplierForm.removeMailType')"></ui-action>
                </div>
              </div>
              <ui-input v-model="item.subject" :disabled="samplesReadOnly" :placeholder="$t('supplierForm.subjectPlaceholder')"
                        :aria-label="$t('supplierForm.categorySubjectLabel', {name:item.name})"
                        style="margin-bottom: 8px"></ui-input>
              <ui-input v-model="item.content" :disabled="samplesReadOnly" type="textarea" :rows="6" resize="vertical"
                        :aria-label="$t('supplierForm.categoryContentLabel', {name:item.name})"
                        :placeholder="$t('supplierForm.contentPlaceholder', { name: item.name })"></ui-input>
              <ui-checkbox v-if="item.name === '割接通知'" :disabled="samplesReadOnly" v-model="item.contentInAttachment"
                           class="mail-type-attachment-flag">{{ $t('supplierForm.contentInAttachment') }}</ui-checkbox>
            </div>
          </div>

        </ui-collapse-item>

        <!-- 固定字段提取规则 -->
        <ui-collapse-item name="fixed" :id="isDraft ? 'draft-section-fixed' : 'supplier-section-fixed'" class="supplier-section supplier-section--fixed">
          <template #title>
            <div class="supplier-section-head">
              <strong>{{ $t('draftReview.fixedTitle') }}</strong>
              <div class="fixed-field-summary" :aria-label="$t('supplierForm.fixedStatsLabel')">
                <span class="is-configured">{{ $t('supplierForm.customizedCount', { count: customizedFixedFieldCount }) }}</span>
                <span class="is-default">{{ $t('supplierForm.defaultCount', { count: defaultFixedFieldCount }) }}</span>
              </div>
            </div>
          </template>
          <p class="field-hint">{{ $t('draftReview.fixedHint') }}</p>
          <div v-if="fixedFields.length" class="fixed-field-workbench">
            <div class="fixed-field-tabs" role="tablist" :aria-label="$t('supplierForm.fixedTabsLabel')">
              <button
                v-for="field in fixedFields"
                :id="'fixed-field-tab-' + field.name"
                :key="field.name"
                type="button"
                role="tab"
                class="fixed-field-tab"
                :class="{
                  'is-active': selectedFixedFieldName === field.name,
                  'is-configured': isFixedFieldCustomized(field),
                }"
                :aria-selected="selectedFixedFieldName === field.name"
                :aria-controls="'fixed-field-panel-' + field.name"
                :tabindex="selectedFixedFieldName === field.name ? 0 : -1"
                @click="selectFixedField(field)"
                @keydown.left.prevent="moveFixedFieldSelection(-1)"
                @keydown.up.prevent="moveFixedFieldSelection(-1)"
                @keydown.right.prevent="moveFixedFieldSelection(1)"
                @keydown.down.prevent="moveFixedFieldSelection(1)"
              >
                <span class="fixed-field-tab-main">
                  <span class="fixed-field-tab-name">{{ supplierFieldLabel(field.name) }}</span>
                  <span class="fixed-field-tab-meta">{{ field.required ? $t('supplierForm.required') : (field.isLineField ? $t('supplierForm.lineField') : $t('supplierForm.optional')) }}</span>
                </span>
                <span
                  class="fixed-field-tab-status"
                  :class="isFixedFieldCustomized(field) ? 'is-configured' : 'is-default'"
                >{{ isFixedFieldCustomized(field) ? $t('supplierForm.customized') : $t('supplierForm.useDefault') }}</span>
              </button>
            </div>

            <section
              v-if="selectedFixedField"
              :id="'fixed-field-panel-' + selectedFixedField.name"
              class="fixed-field-editor"
              role="tabpanel"
              :aria-labelledby="'fixed-field-tab-' + selectedFixedField.name"
            >
              <div class="fixed-field-editor-head">
                <div>
                  <div class="fixed-field-editor-title">
                    <strong>{{ supplierFieldLabel(selectedFixedField.name) }}</strong>
                    <ui-tag size="small" effect="plain">
                      {{ selectedFixedField.required ? $t('supplierForm.requiredField') : (selectedFixedField.isLineField ? $t('supplierForm.lineField') : $t('supplierForm.optionalField')) }}
                    </ui-tag>
                    <ui-tag
                      size="small"
                      :type="isFixedFieldCustomized(selectedFixedField) ? 'success' : 'info'"
                      effect="plain"
                    >{{ isFixedFieldCustomized(selectedFixedField) ? $t('supplierForm.customized') : $t('supplierForm.useDefault') }}</ui-tag>
                  </div>
                  <p>{{ $t('supplierForm.editorHint') }}</p>
                </div>
                <ui-button
                  size="small"
                  :disabled="!isFixedFieldCustomized(selectedFixedField)"
                  @click="restoreSelectedFixedField"
                >{{ $t('supplierForm.restoreDefault') }}</ui-button>
              </div>
              <ui-input
                v-model="selectedFixedField.value"
                type="textarea"
                :rows="7"
                resize="vertical"
                :placeholder="selectedFixedField.description"
                :aria-label="supplierFieldLabel(selectedFixedField.name)"
              ></ui-input>
            </section>
          </div>
        </ui-collapse-item>

        <!-- line_array 自定义字段 -->
        <ui-collapse-item name="custom" :id="isDraft ? 'draft-section-custom' : 'supplier-section-custom'" class="supplier-section supplier-section--custom">
          <template #title>
            <div class="supplier-section-head">
              <strong>{{ $t('draftReview.lineTitle') }}</strong>
              <div class="supplier-section-actions">
                <span v-if="lineFields.length" class="muted">{{ $t('supplierForm.fieldCount', { count: lineFields.length }) }}</span>
                <ui-button size="small" :icon="icons.Plus" @click.stop="addLineField">{{ $t('supplierForm.addField') }}</ui-button>
              </div>
            </div>
          </template>
          <p class="field-hint">{{ $t('draftReview.lineHint') }}</p>
          <div v-if="!lineFields.length" class="empty-inline">{{ $t('supplierForm.noCustomFields') }}</div>
          <div v-else class="custom-field-list" :aria-label="$t('supplierForm.customListLabel')">
            <div v-for="(row, index) in lineFields" :key="index" :id="(isDraft ? 'draft' : 'supplier')+'-line-field-'+index" class="extract-field-row">
              <strong v-if="row.name.trim()" class="draft-line-field-label">{{ supplierFieldLabel(row.name.trim()) }}</strong>
              <div class="line-field-top">
                <label class="form-label">{{ $t('draftReview.fieldCode') }}</label>
                <ui-input v-model="row.name" :aria-label="$t('draftReview.fieldCode')" :placeholder="$t('supplierForm.fieldNamePlaceholder')" style="width: 220px"></ui-input>
                <ui-checkbox v-model="row.keyword">{{ $t('draftReview.queryUse') }}</ui-checkbox>
                <ui-action type="danger" @click="removeLineField(index)" icon="Delete" :label="$t('common.delete')"></ui-action>
              </div>
              <p class="field-hint">{{ $t('draftReview.fieldCodeHint') }}</p>
              <label class="form-label">{{ $t('draftReview.extractRule') }}</label>
              <ui-input v-model="row.description" type="textarea" :rows="2"
                        :aria-label="$t('draftReview.extractRule')"
                        :placeholder="$t('supplierForm.fieldDescPlaceholder')"></ui-input>
            </div>
          </div>
        </ui-collapse-item>

        <!-- 顶层自定义字段（提取结果顶层输出，供特殊规则判断等） -->
        <ui-collapse-item name="topCustom" class="supplier-section supplier-section--custom">
          <template #title>
            <div class="supplier-section-head">
              <strong>{{ $t('draftReview.otherTitle') }}</strong>
              <div class="supplier-section-actions">
                <span v-if="topCustomFields.length" class="muted">{{ $t('supplierForm.fieldCount', { count: topCustomFields.length }) }}</span>
                <ui-button size="small" :icon="icons.Plus" @click.stop="addTopCustomField">{{ $t('supplierForm.addField') }}</ui-button>
              </div>
            </div>
          </template>
          <p class="field-hint">{{ $t('draftReview.otherHint') }}</p>
          <div v-if="!topCustomFields.length" class="empty-inline">{{ $t('supplierForm.noTopCustomFields') }}</div>
          <div v-else class="custom-field-list" :aria-label="$t('supplierForm.customListLabel')">
            <div v-for="(row, index) in topCustomFields" :key="index" class="extract-field-row">
              <div class="line-field-top">
                <ui-input v-model="row.name" :placeholder="$t('supplierForm.topCustomFieldNamePlaceholder')" style="width: 220px"></ui-input>
                <ui-action type="danger" @click="removeTopCustomField(index)" icon="Delete" :label="$t('common.delete')"></ui-action>
              </div>
              <ui-input v-model="row.description" type="textarea" :rows="2"
                        :placeholder="$t('supplierForm.topCustomFieldDescPlaceholder')"></ui-input>
            </div>
          </div>
        </ui-collapse-item>

        <!-- 提示词 -->
        <ui-collapse-item name="prompt" :id="isDraft ? 'draft-section-prompt' : 'supplier-section-prompt'" class="supplier-section supplier-section--prompt">
          <template #title>
            <div class="supplier-section-head">
              <strong>{{ $t('draftReview.test') }}</strong>
              <div class="supplier-section-actions">
                <ui-button size="small" :loading="previewing" @click.stop="previewPrompt">{{ $t('supplierForm.previewPrompt') }}</ui-button>
                <ui-button size="small" type="primary" :loading="extracting" :disabled="loading || samplesRestricted" @click.stop="previewExtract">{{ $t('supplierForm.previewExtract') }}</ui-button>
              </div>
            </div>
          </template>
          <p class="field-hint">{{ $t(isDraft ? 'draftReview.testHint' : 'supplierOperator.testHint') }}</p>
          <div class="form-field">
            <label class="form-label">{{ $t('supplierForm.extraInstructionsLabel') }}</label>
            <ui-input v-model="form.extra_instructions" type="textarea" :rows="2"
                      :placeholder="$t('supplierForm.extraInstructionsPlaceholder')"></ui-input>
            <p class="field-hint">{{ $t('draftReview.extraHint') }}</p>
          </div>
          <div class="form-field">
            <label class="form-label">{{ $t('supplierForm.extractFilesLabel') }}</label>
            <ui-upload v-model:file-list="extractFiles" :auto-upload="false" multiple
                       class="extract-preview-upload">
              <ui-button size="small" :icon="icons.Paperclip">{{ $t('supplierForm.chooseAttachment') }}</ui-button>
            </ui-upload>
            <p class="field-hint extract-preview-upload-hint">{{ $t('supplierForm.extractFilesHint') }}</p>
          </div>
          <ui-button class="draft-advanced-toggle" size="small" :aria-expanded="showAdvancedPrompt" @click="showAdvancedPrompt=!showAdvancedPrompt">{{ $t('draftReview.advanced') }}</ui-button>
          <div v-if="showAdvancedPrompt" class="form-field">
            <label class="form-label">{{ $t('supplierForm.promptPreviewLabel') }}</label>
            <ui-input v-model="promptPreview" type="textarea" :rows="6" readonly
                      :placeholder="$t('supplierForm.promptPreviewPlaceholder')"></ui-input>
          </div>
          <div class="form-field">
            <label class="form-label">{{ $t('supplierForm.extractPreviewLabel') }}</label>
            <div v-if="!extractPreview" class="extract-preview-empty">
              {{ $t('supplierForm.extractPreviewEmpty') }}
            </div>
            <ui-button v-else link type="primary" @click="showAdvanced=false">
              {{ $t('supplierForm.viewLastExtract') }}
            </ui-button>
          </div>

          <ui-collapse v-if="showAdvancedPrompt || legacyPrompt" class="legacy-prompt-collapse">
            <ui-collapse-item name="legacy">
              <template #title>
                <span class="muted">{{ $t('supplierForm.legacyTitle') }}</span>
              </template>
              <ui-input v-model="legacyPrompt" type="textarea" :rows="6"
                        :placeholder="$t('supplierForm.legacyPlaceholder')"></ui-input>
            </ui-collapse-item>
          </ui-collapse>
        </ui-collapse-item>
      </ui-collapse>

      </div>
          <ui-dialog :model-value="!!sampleEditor" :title="sampleEditor ? $t('supplierForm.fullSampleTitle', {name:sampleEditor.name}) : ''" class="mail-sample-editor-dialog" width="1040px" @close="sampleEditor=null">
            <template v-if="sampleEditor">
              <p class="field-hint">{{ $t('supplierForm.fullSampleHint') }}</p>
              <ui-input v-model="sampleEditor.subject" :aria-label="$t('supplierForm.categorySubjectLabel', {name:sampleEditor.name})" :placeholder="$t('supplierForm.subjectPlaceholder')"></ui-input>
              <ui-input v-model="sampleEditor.content" type="textarea" :rows="16" :aria-label="$t('supplierForm.categoryContentLabel', {name:sampleEditor.name})" :placeholder="$t('supplierForm.contentPlaceholder', {name:sampleEditor.name})"></ui-input>
            </template>
            <template #footer><ui-button @click="sampleEditor=null">{{ $t('common.close') }}</ui-button></template>
          </ui-dialog>

      <ui-dialog v-model="mailTypeDialogVisible" :title="$t('supplierForm.addMailTypeTitle')" width="440px" @opened="mailTypeNameInput?.focus()">
        <form @submit.prevent="addMailType">
          <label class="form-label" for="supplier-mail-type-name">{{ $t('supplierForm.mailTypeName') }}</label>
          <ui-input id="supplier-mail-type-name" ref="mailTypeNameInput" v-model="mailTypeName" :aria-label="$t('supplierForm.mailTypeName')"
                    @input="mailTypeNameError=''"
                    :placeholder="$t('supplierForm.mailTypeNamePlaceholder')" :aria-invalid="!!mailTypeNameError" :aria-describedby="mailTypeNameError ? 'supplier-mail-type-error' : undefined"></ui-input>
          <p class="field-hint">{{ $t('supplierForm.mailTypeNameHint') }}</p>
          <p v-if="mailTypeNameError" id="supplier-mail-type-error" class="warn-text" role="alert">{{ mailTypeNameError }}</p>
        </form>
        <template #footer><ui-button @click="mailTypeDialogVisible=false">{{ $t('common.cancel') }}</ui-button><ui-button type="primary" @click="addMailType">{{ $t('supplierForm.addMailType') }}</ui-button></template>
      </ui-dialog>

    </div>
  `,
});

// ==================== 邮件记录 ====================
const ViewEmails = defineComponent({
  name: "ViewEmails",
  setup() {
    const items = ref([]);
    const loading = ref(false);
    const senderFilter = ref("");
    const receiverFilter = ref("");
    const mailboxOptions = ref([]);

    async function loadEmails() {
      loading.value = true;
      const params = new URLSearchParams({ pageSize: "50" });
      if (senderFilter.value.trim()) {
        params.set("sender", senderFilter.value.trim());
      }
      if (receiverFilter.value) {
        params.set("receiver", receiverFilter.value);
      }
      try {
        const data = await requestJson(`/api/email-records?${params.toString()}`);
        items.value = data.items || [];
        appStore.emailCount = data.total || 0;
        setStatusKey("emails.synced");
      } catch (error) {
        items.value = [];
        setStatus(error.message, "error");
      } finally {
        loading.value = false;
      }
    }

    onMounted(async () => {
      if (appStore.apiKey) {
        mailboxOptions.value = await loadMailAccountOptions();
        loadEmails();
      }
    });

    return { items, loading, senderFilter, receiverFilter, mailboxOptions, loadEmails, shortText, mailboxLabel };
  },
  template: `
    <div class="view-body">
      <ui-card shadow="never" class="table-card">
        <template #header>
          <div class="card-header">
            <div class="filter-bar">
              <ui-select v-model="receiverFilter" :placeholder="$t('common.allMailboxes')" clearable filterable style="width: 220px">
                <ui-option v-for="option in mailboxOptions" :key="option.value"
                           :label="option.label" :value="option.value"></ui-option>
              </ui-select>
              <ui-input v-model="senderFilter" :placeholder="$t('emails.senderFilterPlaceholder')" clearable style="width: 260px"
                        @keyup.enter="loadEmails"></ui-input>
              <ui-button type="primary" @click="loadEmails">{{ $t('common.query') }}</ui-button>
            </div>
          </div>
        </template>
        <ui-table v-loading="loading" :data="items" :empty-text="$t('emails.empty')" stripe>
          <ui-table-column type="expand"><template #default="{row}">
            <mail-analysis-panel :record="row" @changed="loadEmails"></mail-analysis-panel>
            <pre class="email-content-block">{{ row.content }}</pre>
          </template></ui-table-column>
          <ui-table-column prop="email_id" :label="$t('emails.uid')" width="100">
            <template #default="{ row }">
              <span class="mono">{{ row.email_id }}</span>
            </template>
          </ui-table-column>
          <ui-table-column prop="sender" :label="$t('common.sender')" min-width="200"></ui-table-column>
          <ui-table-column :label="$t('common.receiverMailbox')" min-width="180">
            <template #default="{ row }">
              <span class="muted">{{ mailboxLabel(row.receiver) }}</span>
            </template>
          </ui-table-column>
          <ui-table-column prop="subject" :label="$t('common.subject')" min-width="240">
            <template #default="{ row }">
              <span class="cell-main">{{ row.subject }}</span>
            </template>
          </ui-table-column>
          <ui-table-column prop="create_time" :label="$t('common.receiveTime')" width="170">
            <template #default="{ row }">
              <span class="mono muted">{{ row.create_time }}</span>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('emails.contentSummary')" min-width="240">
            <template #default="{ row }">
              <span class="muted">{{ shortText(row.content) }}</span>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('emails.attachments')" width="140">
            <template #default="{ row }">
              <div v-if="(row.attachment_urls || []).length" class="attachment-list">
                <a v-for="(url, index) in row.attachment_urls" :key="url" :href="url"
                   target="_blank" rel="noopener noreferrer">{{ $t('common.attachment', { index: index + 1 }) }}</a>
              </div>
              <span v-else class="muted">-</span>
            </template>
          </ui-table-column>
        </ui-table>
      </ui-card>
    </div>
  `,
});

// ==================== 工单记录 ====================
const ViewTickets = defineComponent({
  name: "ViewTickets",
  setup() {
    const items = ref([]);
    const loading = ref(false);
    const statusFilter = ref("");

    async function loadTickets() {
      loading.value = true;
      const status = encodeURIComponent(statusFilter.value.trim());
      const query = status ? `?status=${status}&pageSize=50` : "?pageSize=50";
      try {
        const data = await requestJson(`/api/tickets${query}`);
        items.value = data.items || [];
        appStore.ticketCount = data.total || 0;
        setStatusKey("tickets.synced");
      } catch (error) {
        items.value = [];
        setStatus(error.message, "error");
      } finally {
        loading.value = false;
      }
    }

    onMounted(() => {
      if (appStore.apiKey) {
        loadTickets();
      }
    });

    return { items, loading, statusFilter, loadTickets, mailboxLabel };
  },
  template: `
    <div class="view-body">
      <ui-card shadow="never" class="table-card">
        <template #header>
          <div class="card-header">
            <div class="filter-bar">
              <ui-input v-model="statusFilter" :placeholder="$t('tickets.statusFilterPlaceholder')" clearable style="width: 260px"
                        @keyup.enter="loadTickets"></ui-input>
              <ui-button type="primary" @click="loadTickets">{{ $t('common.query') }}</ui-button>
            </div>
          </div>
        </template>
        <ui-table v-loading="loading" :data="items" :empty-text="$t('tickets.empty')" stripe>
          <ui-table-column prop="id" label="ID" width="90">
            <template #default="{ row }">
              <span class="mono">{{ row.id }}</span>
            </template>
          </ui-table-column>
          <ui-table-column prop="carrier_ticket_no" :label="$t('common.carrierTicketNo')" min-width="200">
            <template #default="{ row }">
              <span class="cell-main">{{ row.carrier_ticket_no }}</span>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('common.status')" width="120">
            <template #default="{ row }">
              <span>{{ row.status || $t('common.unset') }}</span>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('tickets.cutoverWindow')" min-width="280">
            <template #default="{ row }">
              <span class="mono muted">{{ $t('common.timeRange', { start: row.cut_start_time || '', end: row.cut_end_time || '' }) }}</span>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('tickets.subjectOrSender')" min-width="240">
            <template #default="{ row }">
              <span class="muted">{{ row.subject || row.sender || '' }}</span>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('common.receiverMailbox')" min-width="160">
            <template #default="{ row }">
              <span class="muted">{{ mailboxLabel(row.receiver) }}</span>
            </template>
          </ui-table-column>
        </ui-table>
      </ui-card>
    </div>
  `,
});

// ==================== 割接任务列表（邮件维度） ====================
async function confirmDeleteCutoverEmail(email) {
  try {
    await NocDialog.confirm(
      tt("cutover.delete.message", {subject: email.subject || tt("cutover.detail.emailFallback", {id: email.id})}),
      tt("cutover.delete.title"),
      {
        confirmButtonText: tt("cutover.delete.confirm"),
        cancelButtonText: tt("common.cancel"),
        confirmButtonClass: "noc-danger",
        customClass: "cutover-delete-confirm",
        type: "warning",
      },
    );
  } catch (error) {
    if (error === "cancel" || error === "close") return false;
    throw error;
  }
  await requestJson(`/api/cutover/emails/${email.id}`, {method: "DELETE"});
  return true;
}

const ViewCutoverTasks = defineComponent({
  name: "ViewCutoverTasks",
  setup() {
    const savedState = history.state?.cutoverListState;
    const items = ref([]);
    const total = ref(0);
    const loading = ref(false);
    const readStateBusyIds = ref([]);
    const deleteBusyIds = ref([]);
    const page = ref(savedState?.page ?? 1);
    const pageSize = ref(savedState?.pageSize ?? 20);
    const showAdvanced = ref(savedState?.showAdvanced ?? false);
    let latestRequest = 0;
    const initialQuery = new URLSearchParams(window.location.search);
    const filters = reactive({
      status: initialQuery.get("status") || "",
      read_status: "",
      keyword: "",
      tag: "",
      supplier: "",
      receiver: "",
      sender: "",
      start: "",
      end: "",
      ...savedState?.filters,
    });
    const appliedFilters = ref({ ...(savedState?.appliedFilters ?? filters) });
    const advancedFilterCount = computed(() =>
      ["read_status", "tag", "receiver", "sender", "start", "end"].filter(key => filters[key]).length
    );
    const displayItems = computed(() => items.value.map(row => ({
      ...row, displayTags: cutoverEmailTags(row), displayStates: cutoverEmailStates(row),
    })));
    const statusOptions = computed(() => cutoverStatusOptions().concat(
      [{value:'analysis_failed', label:tt('discovery.failed')}, {value:'needs_review', label:tt('discovery.needs_review')}],
      ["unmatched_lines", "reply_pending", "rule_skipped", "rejected_closed", "duplicate_ignored", "no_task"].map(value => ({
        value, label: tt(`cutover.list.emailStatus.${value}`),
      }))
    ));
    // 标签选项 = 固定场景标签 + 动态邮件类型（mail_type: 前缀区分，查询时拆为 mail_type 参数）
    const mailTypeOptions = ref([]);
    const tagOptions = computed(() =>
      cutoverTagOptions().concat(
        mailTypeOptions.value.map((name) => ({ value: `mail_type:${name}`, label: name }))
      )
    );
    // 供应商下拉选项：来自供应商配置，与列表供应商列的显示口径一致
    const supplierOptions = ref([]);
    // 接收邮箱下拉选项：来自邮箱账号配置
    const mailboxOptions = ref([]);

    async function loadSupplierOptions() {
      try {
        const suppliers = await requestJson("/api/me/suppliers");
        supplierOptions.value = (suppliers || []).map((supplier) => supplier.name);
      } catch (error) {
        supplierOptions.value = [];
      }
    }

    async function loadMailTypeOptions() {
      try {
        mailTypeOptions.value = (await requestJson("/api/cutover/emails/mail-types")) || [];
      } catch (error) {
        mailTypeOptions.value = [];
      }
    }

    async function loadTasks() {
      const requestId = ++latestRequest;
      loading.value = true;
      const params = new URLSearchParams({ page: String(page.value), pageSize: String(pageSize.value) });
      for (const [key, value] of Object.entries(appliedFilters.value)) {
        if (!value) {
          continue;
        }
        if (key === "tag" && value.startsWith("mail_type:")) {
          params.set("mail_type", value.slice("mail_type:".length));
          continue;
        }
        params.set(key, value);
      }
      try {
        const data = await requestJson(`/api/cutover/emails?${params.toString()}`);
        if (requestId !== latestRequest) return;
        if (page.value > 1 && !(data.items || []).length && data.total > 0) {
          page.value = Math.max(1, Math.ceil(data.total / pageSize.value));
          return loadTasks();
        }
        items.value = data.items || [];
        total.value = data.total || 0;
        if (!total.value) page.value = 1;
        setStatusKey("cutover.list.synced");
        loadMailTypeOptions();
      } catch (error) {
        if (requestId !== latestRequest) return;
        items.value = [];
        total.value = 0;
        setStatus(error.message, "error");
      } finally {
        if (requestId === latestRequest) loading.value = false;
      }
    }

    async function toggleReadState(row) {
      if (readStateBusyIds.value.includes(row.id) || deleteBusyIds.value.includes(row.id)) {
        return;
      }
      readStateBusyIds.value = [...readStateBusyIds.value, row.id];
      try {
        const data = await requestJson(`/api/cutover/emails/${row.id}/read-state`, {
          method: "PATCH",
          body: JSON.stringify({ is_read: !row.is_read }),
        });
        const source = items.value.find(item => item.id === row.id);
        if (source) source.is_read = Boolean(data.is_read);
        NocMessage.success(tt("common.readStateUpdated"));
        if (appliedFilters.value.read_status) {
          await loadTasks();
        }
      } catch (error) {
        NocMessage.error(error.message);
      } finally {
        readStateBusyIds.value = readStateBusyIds.value.filter((id) => id !== row.id);
      }
    }

    async function deleteEmail(row) {
      if (deleteBusyIds.value.includes(row.id) || readStateBusyIds.value.includes(row.id)) return;
      deleteBusyIds.value = [...deleteBusyIds.value, row.id];
      try {
        if (!await confirmDeleteCutoverEmail(row)) return;
        NocMessage.success(tt("cutover.delete.succeeded"));
        await Promise.all([loadTasks(), loadOperationsSummary()]);
      } catch (error) {
        NocMessage.error(error.message);
      } finally {
        deleteBusyIds.value = deleteBusyIds.value.filter(id => id !== row.id);
      }
    }

    function searchTasks() {
      appliedFilters.value = { ...filters };
      if (page.value !== 1) page.value = 1;
      loadTasks();
    }

    function changePageSize() {
      page.value = 1;
      loadTasks();
    }

    function resetFilters() {
      filters.status = "";
      filters.read_status = "";
      filters.keyword = "";
      filters.tag = "";
      filters.supplier = "";
      filters.receiver = "";
      filters.sender = "";
      filters.start = "";
      filters.end = "";
      searchTasks();
    }

    function openDetail(row) {
      if (deleteBusyIds.value.includes(row.id)) return;
      openCutoverEmailDetail(row.id, {
        filters: { ...filters },
        appliedFilters: { ...appliedFilters.value },
        page: page.value,
        pageSize: pageSize.value,
        showAdvanced: showAdvanced.value,
      });
    }

    onMounted(async () => {
      if (appStore.apiKey) {
        mailboxOptions.value = await loadMailAccountOptions();
        loadTasks();
        loadSupplierOptions();
        loadMailTypeOptions();
      }
    });

    return {
      items: displayItems, total, loading, readStateBusyIds, deleteBusyIds, filters, statusOptions, tagOptions, supplierOptions, mailboxOptions,
      page, pageSize, showAdvanced, advancedFilterCount, searchTasks, changePageSize,
      loadTasks, resetFilters, openDetail, toggleReadState, deleteEmail, shortText,
      sceneText, sceneTagType, isRejectedScene, mailboxLabel, canOperateMailbox,
    };
  },
  template: `
    <div class="view-body cutover-list-view">
      <ui-card shadow="never" class="table-card cutover-list-card">
        <template #header>
          <div class="list-heading"><h2>{{ $t('cutover.list.title') }}</h2><span class="list-total">{{ $t('cutover.list.totalEmails', { total }) }}</span></div>
          <form @submit.prevent="searchTasks">
            <div class="cutover-main-filters">
              <ui-input v-model="filters.keyword" :placeholder="$t('cutover.list.keywordSearch')" :aria-label="$t('cutover.list.keywordSearch')" clearable></ui-input>
              <ui-select v-model="filters.status" :placeholder="$t('cutover.list.allStatus')" :aria-label="$t('cutover.list.processingStatus')" clearable>
                <ui-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value"></ui-option>
              </ui-select>
              <ui-select v-model="filters.supplier" :placeholder="$t('cutover.list.allSupplier')" :aria-label="$t('common.supplier')" clearable filterable>
                <ui-option v-for="name in supplierOptions" :key="name" :label="name" :value="name"></ui-option>
              </ui-select>
              <ui-button type="primary" native-type="submit" :loading="loading">{{ $t('common.query') }}</ui-button>
              <ui-button @click="resetFilters">{{ $t('common.reset') }}</ui-button>
              <ui-button text @click="showAdvanced = !showAdvanced" :aria-expanded="showAdvanced" aria-controls="cutover-advanced-filters">
                {{ $t('cutover.list.moreFilters') }}{{ advancedFilterCount ? ' (' + advancedFilterCount + ')' : '' }} {{ showAdvanced ? '−' : '+' }}
              </ui-button>
            </div>
            <div v-if="showAdvanced" id="cutover-advanced-filters" class="cutover-advanced-filters">
              <ui-select v-model="filters.read_status" :placeholder="$t('common.allReadStates')" :aria-label="$t('common.readState')" clearable>
                <ui-option :label="$t('common.unread')" value="unread"></ui-option><ui-option :label="$t('common.read')" value="read"></ui-option>
              </ui-select>
              <ui-select v-model="filters.tag" :placeholder="$t('cutover.list.allTag')" :aria-label="$t('cutover.list.tags')" clearable>
                <ui-option v-for="item in tagOptions" :key="item.value" :label="item.label" :value="item.value"></ui-option>
              </ui-select>
              <ui-select v-model="filters.receiver" :placeholder="$t('common.allMailboxes')" :aria-label="$t('common.receiverMailbox')" clearable filterable>
                <ui-option v-for="option in mailboxOptions" :key="option.value" :label="option.label" :value="option.value"></ui-option>
              </ui-select>
              <ui-input v-model="filters.sender" :placeholder="$t('common.sender')" :aria-label="$t('common.sender')" clearable></ui-input>
              <ui-date-picker v-model="filters.start" type="date" :placeholder="$t('cutover.list.receiveStart')" value-format="YYYY-MM-DD"></ui-date-picker>
              <ui-date-picker v-model="filters.end" type="date" :placeholder="$t('cutover.list.receiveEnd')" value-format="YYYY-MM-DD"></ui-date-picker>
            </div>
          </form>
        </template>
        <ui-table v-loading="loading" :data="items" :empty-text="$t('cutover.list.empty')" height="100%" row-key="id" @row-click="openDetail" class="clickable-table cutover-six-table">
          <ui-table-column :label="$t('cutover.list.mailContent')" min-width="280">
            <template #default="{ row }">
              <div class="cutover-mail" :class="{ 'is-unread': !row.is_read }" :aria-busy="readStateBusyIds.includes(row.id)">
                <div class="cutover-mail-heading"><span class="cutover-unread-dot" :class="{ 'is-read': row.is_read }" :title="row.is_read ? $t('common.read') : $t('common.unread')" :aria-label="row.is_read ? $t('common.read') : $t('common.unread')" role="img"></span>
                  <ui-tooltip :trigger="['hover', 'focus']" effect="light" placement="bottom-start" :show-after="300" popper-class="cutover-text-tooltip">
                    <template #content><div class="cutover-tooltip-heading">{{ row.subject || '-' }}</div><div class="cutover-tooltip-meta">UID {{ row.email_id }}</div></template>
                    <button class="cutover-subject" @click.stop="openDetail(row)">{{ row.subject || '-' }}</button>
                  </ui-tooltip>
                </div>
                <div v-if="row.displayTags.length" class="cutover-mail-tags">
                  <ui-tag v-for="tag in row.displayTags.slice(0, 3)" :key="tag.key" :type="tag.type" size="small" effect="plain">{{ tag.label }}</ui-tag>
                  <ui-popover v-if="row.displayTags.length > 3" trigger="hover" :width="280" popper-class="cutover-text-tooltip">
                    <template #reference><button class="cutover-extra-tags" @click.stop :aria-label="$t('cutover.list.allTags')">+{{ row.displayTags.length - 3 }}</button></template>
                    <div class="cutover-all-tags"><ui-tag v-for="tag in row.displayTags" :key="tag.key" :type="tag.type" size="small" effect="plain">{{ tag.label }}</ui-tag></div>
                  </ui-popover>
                </div>
                <ui-tooltip :trigger="['hover', 'focus']" effect="light" placement="bottom-start" :show-after="300" :disabled="!row.content_summary" popper-class="cutover-text-tooltip">
                  <template #content><div class="cutover-tooltip-meta">{{ $t('cutover.list.contentSummary') }}</div><div class="cutover-tooltip-body">{{ row.content_summary }}</div></template>
                  <div class="cutover-snippet" tabindex="0">{{ row.content_summary || '-' }}</div>
                </ui-tooltip>
              </div>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('common.supplier')" width="85"><template #default="{ row }"><span class="cutover-supplier" :title="row.suppliers || ''">{{ row.suppliers || '-' }}</span></template></ui-table-column>
          <ui-table-column :label="$t('cutover.list.mailAddresses')" width="210">
            <template #default="{ row }"><div class="cutover-address"><span>{{ $t('cutover.list.from') }}</span><ui-tooltip :trigger="['hover', 'focus']" :content="row.sender || '-'" effect="light" placement="bottom-start" :show-after="300" popper-class="cutover-text-tooltip"><span tabindex="0">{{ row.sender || '-' }}</span></ui-tooltip></div><div class="cutover-address"><span>{{ $t('cutover.list.to') }}</span><ui-tooltip :trigger="['hover', 'focus']" :content="mailboxLabel(row.receiver)" effect="light" placement="bottom-start" :show-after="300" popper-class="cutover-text-tooltip"><span tabindex="0">{{ mailboxLabel(row.receiver) }}</span></ui-tooltip></div></template>
          </ui-table-column>
          <ui-table-column :label="$t('cutover.list.processingStatus')" width="155">
            <template #default="{ row }">
              <div class="cutover-processing">
                <ui-tag v-if="row.unmatched_line_count && !row.manual_completion" class="cutover-line-warning" type="warning" size="small" effect="light" :title="$t('cutover.list.unmatchedLinesHint')">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m12 3 10 18H2Z"/><path d="M12 9v4m0 4h.01"/></svg>
                  <span>{{ $t('cutover.list.unmatchedLines', { count: row.unmatched_line_count }) }}</span>
                </ui-tag>
                <div v-for="state in row.displayStates" :key="state.key" class="cutover-state" :class="'is-' + state.type"><span>{{ state.label }}</span><span v-if="state.count" class="cutover-state-count">{{ state.count }}</span></div>
                <span v-if="row.task_count || row.displayStates[0].key !== 'no_task'" class="cutover-task-count">{{ row.task_count ? $t('cutover.list.taskCount', { count: row.task_count }) : $t('cutover.list.noTask') }}</span>
              </div>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('common.receiveTime')" width="115"><template #default="{ row }"><time class="cutover-receive-time" :datetime="(row.create_time || '').slice(0, 19).replace(' ', 'T')">{{ (row.create_time || '').slice(0, 10) }}<span>{{ (row.create_time || '').slice(11, 19) }}</span></time></template></ui-table-column>
          <ui-table-column :label="$t('common.actions')" width="112" align="center" fixed="right">
            <template #default="{ row }">
              <div class="cutover-row-actions" @click.stop>
                <ui-action class="cutover-read-action" :class="{ 'is-read': row.is_read }"
                           :icon="row.is_read ? 'MessageBox' : 'Message'" :type="row.is_read ? 'default' : 'primary'"
                           :label="row.is_read ? $t('common.markAsUnread') : $t('common.markAsRead')"
                           :loading="readStateBusyIds.includes(row.id)" :disabled="!canOperateMailbox(row.receiver) || readStateBusyIds.includes(row.id) || deleteBusyIds.includes(row.id)"
                           @click.stop="toggleReadState(row)"></ui-action>
                <ui-action icon="Delete" type="danger" class="cutover-delete-action" :label="$t('cutover.delete.rowAction')"
                           :loading="deleteBusyIds.includes(row.id)" :disabled="!canOperateMailbox(row.receiver) || deleteBusyIds.includes(row.id) || readStateBusyIds.includes(row.id)"
                           @click.stop="deleteEmail(row)"></ui-action>
              </div>
            </template>
          </ui-table-column>
        </ui-table>
        <div class="cutover-pagination"><span>{{ $t('cutover.list.pageRange', { start: total ? (page - 1) * pageSize + 1 : 0, end: Math.min(page * pageSize, total), total }) }}</span><ui-pagination v-model:current-page="page" v-model:page-size="pageSize" :page-sizes="[20, 50, 100]" :total="total" :pager-count="5" layout="sizes, prev, pager, next" :disabled="loading" @current-change="loadTasks" @size-change="changePageSize"></ui-pagination></div>
      </ui-card>
    </div>
  `,
});

// ==================== 割接模板列顺序（缓存） ====================
let cutoverTemplateColumns = null;

async function ensureCutoverTemplateColumns() {
  // 旧后端可能只返回列名；不把缺少默认结构的响应或请求失败永久缓存。
  if (!cutoverTemplateColumns?.defaults?.backbone) {
    try {
      cutoverTemplateColumns = await requestJson("/api/cutover/template-columns");
    } catch (error) {
      return cutoverTemplateColumns || {};
    }
  }
  return cutoverTemplateColumns;
}

function orderSheetColumns(kind, columns) {
  const template = cutoverTemplateColumns || {};
  const order = kind === "circuit" ? template.circuit : template.reason;
  if (!Array.isArray(order) || !order.length) {
    return columns;
  }
  return [
    ...order.filter((column) => columns.includes(column)),
    ...columns.filter((column) => !order.includes(column)),
  ];
}

// ==================== 骨干表单分组/字段顺序常量 ====================
const BACKBONE_SECTION_ORDER = ["基本信息", "割接对象", "人员信息", "其他", "确认项"];

const BACKBONE_CONFIRMATION_FIELDS = [
  "该割接已按照集团相关文件要求经过省公司领导审批。",
  "为避免省内跨专业的割接冲突影响CN2网，经和省数据专业确认，此割接操作不会与数据割接冲突。",
  "生成多张独立通道割接方案。",
];

const BACKBONE_ENUM_OPTIONS = {
  "中断类型": ["不中断", "中断", "瞬断"],
};

const CUSTOMER_CIRCUIT_ENUM_OPTIONS = {
  "客户电路在割接段是否有保护": ["无保护", "有保护"],
  "预计影响客户业务时长": ["不中断", "瞬断"],
};

const BACKBONE_FIELD_ORDER = {
  "基本信息": [
    "标题", "割接分类", "割接原因分类", "涉及系统（网络）", "操作厂家", "设备名称",
    "割接省份", "变更操作内容", "变更操作等级", "调度方式", "中断类型", "中断原因", "中断时间 (分钟)", "需要配合的省",
    "是否涉及集团维护设备或业务影响超出本省范围",
    "是否有回退应急预案和舆情应对方案", "割接地点", "是否跨专业",
  ],
  "割接对象": [
    "割接类型", "割接对象所属机构", "割接对象类型", "系统名称",
    "割接开始时间", "割接结束时间",
  ],
  "其他": [
    "影响军队", "是否变更网管中网元管理对象配置", "是否增加、删除或更改光开关(OLP)",
    "是否影响联通", "是否需要集团网管配置操作", "割接原因", "风险操作影响范围",
    "是否为境外运营商割接或联通割接(跳过变更操作方案校验)",
  ],
  "确认项": BACKBONE_CONFIRMATION_FIELDS,
};

const BACKBONE_WIDE_FIELDS = new Set([
  "标题", "系统名称", "中断原因", "割接原因", "风险操作影响范围",
  ...BACKBONE_CONFIRMATION_FIELDS,
]);

// 这些字段通常只有一句话，始终用单行输入框
const BACKBONE_SINGLE_LINE_FIELDS = new Set(["割接原因"]);

function orderedBackboneSections(circuit) {
  const names = Object.keys(circuit || {});
  return [
    ...BACKBONE_SECTION_ORDER.filter((name) => names.includes(name)),
    ...names.filter((name) => !BACKBONE_SECTION_ORDER.includes(name)),
  ];
}

function orderedBackboneFields(sectionName, fields) {
  const order = BACKBONE_FIELD_ORDER[sectionName] || [];
  const names = Object.keys(fields || {});
  return [
    ...order.filter((name) => names.includes(name)),
    ...names.filter((name) => !order.includes(name)),
  ].filter((name) => name !== "中断时间 (分钟)");
}

// Report screenshots share a bounded thumbnail layout and a full-resolution viewer.
const ReportScreenshotGallery = defineComponent({
  name: "ReportScreenshotGallery",
  components: { NImageGroup: naive.NImageGroup },
  props: { reportId: [String, Number], steps: { type: Array, default: () => [] },
    imageUrls: Object, loadingKeys: Object },
  setup(props) {
    const previewVisible = ref(false);
    const previewIndex = ref(0);
    const brokenUrls = reactive({});
    let trigger = null;
    const entries = computed(() => props.steps.map((step, index) => {
      const key = `${props.reportId}-${index}`;
      const url = props.imageUrls[key] || '';
      return { ...step, key, index, url, failed: !!brokenUrls[url], loading: props.loadingKeys.has(key) };
    }));
    const available = computed(() => entries.value.filter(item => item.url && !item.failed));
    function openPreview(entry, event) {
      previewIndex.value = available.value.findIndex(item => item.key === entry.key);
      if (previewIndex.value < 0) return;
      trigger = event.currentTarget;
      previewVisible.value = true;
    }
    function updatePreview(show) {
      previewVisible.value = show;
      if (!show) nextTick(() => { if (trigger?.isConnected) trigger.focus(); });
    }
    return { entries, available, previewVisible, previewIndex, brokenUrls, openPreview, updatePreview,
      icons: ElementPlusIconsVue };
  },
  template: `
    <section class="report-gallery" :aria-label="$t('cutover.task.operationScreenshots')">
      <header class="report-gallery-heading">
        <strong>{{ $t('cutover.task.operationScreenshots') }} <span>{{ steps.length }}</span></strong>
        <span>{{ $t('cutover.task.screenshotPreviewHint') }}</span>
      </header>
      <div class="report-operation-grid">
        <article v-for="entry in entries" :key="entry.key" class="report-operation-card">
          <button v-if="entry.url && !entry.failed" type="button" class="report-thumbnail"
                  :aria-label="$t('cutover.task.viewScreenshot', { name: entry.label || entry.step || entry.index + 1 })"
                  @click="openPreview(entry, $event)">
            <img :src="entry.url" :alt="entry.label || entry.step || ''" @error="brokenUrls[entry.url] = true">
            <span class="report-thumbnail-action"><ui-icon><component :is="icons.ZoomIn"/></ui-icon>{{ $t('cutover.task.viewFullScreenshot') }}</span>
          </button>
          <div v-else class="report-image-missing" role="status" :aria-busy="entry.loading">
            <ui-icon><component :is="entry.loading ? icons.Loading : icons.Picture"/></ui-icon>
            <span>{{ $t(entry.loading ? 'cutover.task.screenshotLoading' : 'cutover.task.screenshotUnavailable') }}</span>
          </div>
          <div class="report-operation-caption">
            <span class="report-step-number">{{ String(entry.index + 1).padStart(2, '0') }}</span>
            <div><strong>{{ entry.label || entry.step || $t('cutover.task.operationScreenshots') }}</strong>
              <time v-if="entry.captured_at" :datetime="entry.captured_at">{{ entry.captured_at.replace('T', ' ').slice(0, 19) }}</time>
            </div>
          </div>
        </article>
      </div>
      <n-image-group :src-list="available.map(item => item.url)" :show="previewVisible"
                     v-model:current="previewIndex" show-toolbar show-toolbar-tooltip
                     @update:show="updatePreview"/>
    </section>
  `,
});

// ==================== 割接任务详情面板 ====================
const TaskDetailPanel = defineComponent({
  name: "TaskDetailPanel",
  components: { ReportScreenshotGallery },
  props: {
    task: { type: Object, required: true },
    operatorMode: Boolean,
    historyOnly: Boolean,
  },
  emits: ["changed", "collapse", "dirty-change"],
  setup(props, { emit }) {
    const localTask = ref(props.task);
    const busy = ref(false);
    const fillExpanded = ref(false);
    const formSnapshot = ref('');
    const formState = () => JSON.stringify({type: localTask.value.line_type,
      circuits: collectRows(circuitRows.value, circuitColumns.value), reasons: collectRows(reasonRows.value, reasonColumns.value),
      backbone: collectBackboneCircuits()});
    const formDirty = computed(() => !!formSnapshot.value && formState() !== formSnapshot.value);
    const reportImageUrls = reactive({});
    const reportProgressVisible = ref(false);
    const activeReport = ref(null);
    const reportProgressError = ref("");
    const reportImageLoadingKeys = reactive(new Set());
    let reportImageVersion = 0;
    const notifiedReportIds = new Set();
    let reportPollTimer = null;
    let disposed = false;

    const isBackbone = computed(() => localTask.value.line_type === "backbone");
    const fill = computed(() => localTask.value.fill_result || {});
    const validationMessages = computed(() => fill.value.validation_messages || []);
    const reportSummary = computed(() => {
      const text = value => Array.isArray(value) ? value.join('、') : value == null || value === '' ? '—' : String(value);
      if (isBackbone.value) return (fill.value.backbone_circuits || []).map(card => {
        const target = card['割接对象'] || {}, basic = card['基本信息'] || {};
        return {name:text(target['系统名称']), window:[target['割接开始时间'],target['割接结束时间']].map(text).join(' — '),
          impact:[basic['中断类型'],basic['中断时间 (分钟)'] != null ? basic['中断时间 (分钟)']+' min' : ''].filter(Boolean).join(' · ') || '—',
          reason:text(card['其他']?.['割接原因'])};
      });
      return (fill.value.circuits || []).map(row => {
        const reason = (fill.value.reasons || []).find(item => item['割接线路/设备名称'] === row['电路代号']);
        return {name:text(row['电路代号']), window:text(row['割接时间']),
          impact:text(row['预计影响客户业务时长']), reason:text(reason?.['割接原因'])};
      });
    });

    // ---------- 客户线路可编辑表格 ----------
    const circuitColumns = ref([]);
    const circuitRows = ref([]);
    const reasonColumns = ref([]);
    const reasonRows = ref([]);

    function normalizeRow(row, columns) {
      const out = {};
      for (const column of columns) {
        const value = row[column];
        out[column] = value === null || value === undefined ? "" : String(value);
      }
      return out;
    }

    function collectRows(rows, columns) {
      return rows.map((row) => {
        const out = {};
        for (const column of columns) {
          out[column] = row[column] === "" ? null : row[column];
        }
        return out;
      });
    }

    function customerEnumOptions(column, row) {
      const options = CUSTOMER_CIRCUIT_ENUM_OPTIONS[column];
      if (!options) {
        return null;
      }
      const current = row[column];
      return current && !options.includes(current) ? [...options, current] : options;
    }

    function customerColumnClass(column) {
      if (column === "客户电路在割接段是否有保护") {
        return "customer-protection-column";
      }
      if (column === "预计影响客户业务时长") {
        return "customer-impact-duration-column";
      }
      return "";
    }

    function addSheetRow(kind) {
      const columns = kind === "circuit" ? circuitColumns.value : reasonColumns.value;
      if (!columns.length) {
        NocMessage.error(tt("cutover.task.noEditableColumn"));
        return;
      }
      const rows = kind === "circuit" ? circuitRows.value : reasonRows.value;
      const defaults = (cutoverTemplateColumns || {}).defaults || {};
      const source = rows.length ? rows[rows.length - 1] : (defaults[kind] || {});
      rows.push(normalizeRow(source, columns));
    }

    function removeSheetRow(kind, index) {
      (kind === "circuit" ? circuitRows : reasonRows).value.splice(index, 1);
    }

    // ---------- 骨干线路卡片表单 ----------
    const backboneCards = ref([]);
    const backboneInterruptionMinutes = ref([]);
    // 各卡片展开的分组名列表（与 backboneCards 平行），默认仅展开第一个分组
    const backboneActive = ref([]);
    // 控件类型在表单初始化时按初值决定，避免输入过程中 input/textarea 来回切换
    const backboneKinds = ref({});

    function kindKey(cardIndex, sectionName, fieldName) {
      return `${cardIndex}|${sectionName}|${fieldName}`;
    }

    function rebuildBackboneKinds() {
      const kinds = {};
      backboneCards.value.forEach((card, cardIndex) => {
        for (const sectionName of orderedBackboneSections(card)) {
          const fields = card[sectionName];
          if (!fields || typeof fields !== "object" || Array.isArray(fields)) {
            continue;
          }
          for (const fieldName of orderedBackboneFields(sectionName, fields)) {
            const text = fields[fieldName] == null ? "" : String(fields[fieldName]);
            const kind = BACKBONE_SINGLE_LINE_FIELDS.has(fieldName) || text.length <= 40
              ? "input" : "textarea";
            kinds[kindKey(cardIndex, sectionName, fieldName)] = kind;
          }
        }
      });
      backboneKinds.value = kinds;
    }

    function controlKind(cardIndex, sectionName, fieldName) {
      return backboneKinds.value[kindKey(cardIndex, sectionName, fieldName)] || "input";
    }

    function isBackboneSystemField(sectionName, fieldName) {
      return sectionName === "割接对象" && fieldName === "系统名称";
    }

    function isBackboneConfirmationField(fieldName) {
      return BACKBONE_CONFIRMATION_FIELDS.includes(fieldName);
    }

    function backboneEnumOptions(fieldName) {
      return BACKBONE_ENUM_OPTIONS[fieldName] || null;
    }

    function impactMinutesFromLine(line) {
      const durationText = String((line && line.ImpactDuration) || "").trim();
      const digits = (durationText.match(/\d+/) || [""])[0];
      if (!digits) {
        return null;
      }
      const rawCount = Number((line && line.InteruptionsCounts) || 1);
      const count = Number.isFinite(rawCount) ? Math.trunc(rawCount) : 1;
      const duration = Number(digits);
      return durationText.toLowerCase().includes("h")
        ? duration * 60 * count
        : duration * count;
    }

    function payloadInterruptionMinutes(task, cards) {
      const payload = task.fill_payload || {};
      const nestedLines = payload.line_array_info && payload.line_array_info.data;
      const lines = Array.isArray(payload.line_array)
        ? payload.line_array
        : (Array.isArray(nestedLines) ? nestedLines : []);
      const backboneLines = lines.filter((line) =>
        ["骨干", "backbone"].includes(String((line && line.line_type) || "").trim().toLowerCase())
      );
      const candidates = backboneLines.length ? backboneLines : lines;
      if (candidates.length === cards.length) {
        return candidates.map(impactMinutesFromLine);
      }
      return cards.map((card, cardIndex) =>
        impactMinutesFromLine(candidates[cardIndex] || candidates[0])
      );
    }

    function handleBackboneEnumChange(card, cardIndex, sectionName, fieldName, value) {
      if (sectionName !== "基本信息" || fieldName !== "中断类型") {
        return;
      }
      if (value === "中断") {
        if (!("中断原因" in card[sectionName])) {
          const payload = localTask.value.fill_payload || {};
          card[sectionName]["中断原因"] = `${card[sectionName]["标题"] || ""}--Location: ${payload.location || ""} Reason: ${payload.cutover_reason || ""}`;
        }
        if (!("中断时间 (分钟)" in card[sectionName])) {
          card[sectionName]["中断时间 (分钟)"] = backboneInterruptionMinutes.value[cardIndex] ?? "";
        }
      } else {
        delete card[sectionName]["中断原因"];
        delete card[sectionName]["中断时间 (分钟)"];
      }
      rebuildBackboneKinds();
    }

    function isWideField(cardIndex, sectionName, fieldName) {
      return BACKBONE_WIDE_FIELDS.has(fieldName)
        || controlKind(cardIndex, sectionName, fieldName) === "textarea";
    }

    async function addBackboneCard() {
      let source = backboneCards.value[backboneCards.value.length - 1];
      if (!source) {
        const template = await ensureCutoverTemplateColumns();
        source = (template.defaults || {}).backbone;
      }
      if (!source) {
        NocMessage.error(tt("cutover.task.backboneNoStructure"));
        return;
      }
      const template = JSON.parse(JSON.stringify(source));
      const sourceIndex = backboneCards.value.length - 1;
      const minutes = sourceIndex >= 0 ? backboneInterruptionMinutes.value[sourceIndex] : null;
      backboneCards.value.push(template);
      backboneInterruptionMinutes.value.push(minutes ?? null);
      backboneActive.value.push((orderedBackboneSections(template) || [])[0] ? [orderedBackboneSections(template)[0]] : []);
      rebuildBackboneKinds();
    }

    function removeBackboneCard(index) {
      backboneCards.value.splice(index, 1);
      backboneInterruptionMinutes.value.splice(index, 1);
      backboneActive.value.splice(index, 1);
      rebuildBackboneKinds();
    }

    function expandAllBackboneSections() {
      backboneActive.value = backboneCards.value.map((card) => orderedBackboneSections(card));
    }

    function collapseAllBackboneSections() {
      backboneActive.value = backboneCards.value.map(() => []);
    }

    function collectBackboneCircuits() {
      return backboneCards.value.map((card) => {
        const circuit = {};
        for (const sectionName of orderedBackboneSections(card)) {
          const fields = card[sectionName];
          if (!fields || typeof fields !== "object" || Array.isArray(fields)) {
            continue;
          }
          const out = {};
          for (const fieldName of Object.keys(fields)) {
            const value = fields[fieldName];
            out[fieldName] = value === "" || value == null ? null : value;
          }
          circuit[sectionName] = out;
        }
        return circuit;
      });
    }

    // ---------- 初始化/重置 ----------
    async function initFromTask(task) {
      localTask.value = task;
      loadReportImages(task);
      const currentFill = task.fill_result || {};
      if (task.line_type === "backbone") {
        backboneCards.value = JSON.parse(JSON.stringify(currentFill.backbone_circuits || []));
        const savedMinutes = Array.isArray(currentFill.backbone_interruption_minutes)
          ? currentFill.backbone_interruption_minutes
          : [];
        const inferredMinutes = payloadInterruptionMinutes(task, backboneCards.value);
        backboneInterruptionMinutes.value = backboneCards.value.map((card, cardIndex) => {
          const basicInfo = card["基本信息"] || {};
          const editedMinutes = basicInfo["中断时间 (分钟)"];
          return editedMinutes === "" || editedMinutes == null
            ? (savedMinutes[cardIndex] ?? inferredMinutes[cardIndex] ?? null)
            : editedMinutes;
        });
        backboneCards.value.forEach((card, cardIndex) => {
          const basicInfo = card["基本信息"];
          if (basicInfo && typeof basicInfo === "object" && !Array.isArray(basicInfo)) {
            if (basicInfo["中断类型"] !== "中断") {
              delete basicInfo["中断原因"];
              delete basicInfo["中断时间 (分钟)"];
            } else {
              const payload = task.fill_payload || {};
              if (!("中断原因" in basicInfo)) {
                basicInfo["中断原因"] = `${basicInfo["标题"] || ""}--Location: ${payload.location || ""} Reason: ${payload.cutover_reason || ""}`;
              }
              if (!("中断时间 (分钟)" in basicInfo)) {
                basicInfo["中断时间 (分钟)"] = backboneInterruptionMinutes.value[cardIndex] ?? "";
              }
            }
          }
          const cutoverObject = card["割接对象"] || {};
          const value = cutoverObject["系统名称"];
          cutoverObject["系统名称"] = Array.isArray(value)
            ? value.filter((name) => name !== null && name !== undefined && String(name).trim())
            : (value === null || value === undefined || value === "" ? [] : [String(value)]);
          card["割接对象"] = cutoverObject;
        });
        rebuildBackboneKinds();
        // 卡片数变化（首次加载/增删）才重置展开状态，避免保存后丢失用户展开的分组
        if (backboneActive.value.length !== backboneCards.value.length) {
          backboneActive.value = backboneCards.value.map((card) => {
            const sections = orderedBackboneSections(card);
            return sections.length ? [sections[0]] : [];
          });
        }
      } else {
        backboneInterruptionMinutes.value = [];
        const template = await ensureCutoverTemplateColumns();
        const circuits = currentFill.circuits || [];
        circuitColumns.value = orderSheetColumns("circuit", circuits.length ? Object.keys(circuits[0]) : (template.circuit || []));
        circuitRows.value = circuits.map((row) => normalizeRow(row, circuitColumns.value));
        const reasons = currentFill.reasons || [];
        reasonColumns.value = orderSheetColumns("reason", reasons.length ? Object.keys(reasons[0]) : (template.reason || []));
        reasonRows.value = reasons.map((row) => normalizeRow(row, reasonColumns.value));
      }
      formSnapshot.value = formState();
      resumeReportProgress(task);
    }

    watch(formDirty, value => emit('dirty-change', value));
    watch(() => props.task, (task) => {
      if (task) {
        initFromTask(task);
      }
    }, { immediate: true });

    // ---------- 操作 ----------
    async function runAction(action) {
      busy.value = true;
      try {
        return await action();
      } catch (error) {
        NocMessage.error(error.message);
        setStatus(error.message, "error");
        return null;
      } finally {
        busy.value = false;
      }
    }

    function applyResult(payload, fallbackMessage) {
      const responseTask = payload.data || {};
      const nextTask = {
        ...localTask.value,
        ...responseTask,
        reports: responseTask.reports || localTask.value.reports || [],
      };
      localTask.value = nextTask;
      initFromTask(nextTask).catch((error) => setStatus(error.message, "error"));
      emit("changed", nextTask);
      NocMessage.success(payload.message || fallbackMessage);
      setStatus(payload.message || fallbackMessage);
    }

    async function saveEdit() {
      const body = isBackbone.value
        ? { backbone_circuits: collectBackboneCircuits() }
        : {
            circuits: collectRows(circuitRows.value, circuitColumns.value),
            reasons: collectRows(reasonRows.value, reasonColumns.value),
          };
      const payload = await runAction(() => (
        requestFull(`/api/cutover/tasks/${localTask.value.id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        })
      ));
      if (payload) {
        applyResult(payload, tt("cutover.task.savedFallback"));
      }
    }

    async function switchType(targetType) {
      if (localTask.value.line_type === targetType) {
        return;
      }
      if (formDirty.value) {
        try {
          await NocDialog.confirm(tt('cw.discardTask'), tt('cw.fillDetails'), {
            confirmButtonText: tt('cw.discard'), cancelButtonText: tt('common.cancel'), type: 'warning',
          });
        } catch { return; }
      }
      const payload = await runAction(() => (
        requestFull(`/api/cutover/tasks/${localTask.value.id}/switch-type`, {
          method: "POST",
          body: JSON.stringify({ line_type: targetType }),
        })
      ));
      if (payload) {
        applyResult(payload, tt("cutover.task.switchedFallback"));
      }
    }

    async function confirmTask() {
      if (formDirty.value) { NocMessage.warning(tt('cw.editsUnsaved')); return; }
      const payload = await runAction(() => (
        requestFull(`/api/cutover/tasks/${localTask.value.id}/confirm`, {
          method: "POST",
        })
      ));
      if (payload) {
        applyResult(payload, tt("cutover.task.confirmedFallback"));
      }
    }

    function upsertReport(report) {
      const reports = [...(localTask.value.reports || [])];
      const index = reports.findIndex((item) => item.id === report.id);
      if (index >= 0) {
        reports[index] = { ...reports[index], ...report };
      } else {
        reports.unshift(report);
      }
      localTask.value = { ...localTask.value, reports };
    }

    function reportStatusType(status) {
      return {
        pending: "info",
        running: "warning",
        success: "success",
        failed: "danger",
        paused: "info",
        waiting_login: "warning",
        interrupted: "warning",
      }[status] || "info";
    }

    function reportStatusText(status) {
      return tt(`cutover.task.reportStatus.${status || "pending"}`);
    }

    const activeReportSteps = computed(() => {
      const result = activeReport.value && activeReport.value.result;
      return (result && result.operation_log) || [];
    });

    const activeReportInProgress = computed(() => (
      activeReport.value && ["pending", "running"].includes(activeReport.value.status)
    ));

    function canControlReport(report) {
      return canOperate.value && (appStore.user?.is_admin ||
        report?.result?.execution_identity?.principal_key === `user-${appStore.user?.id}`);
    }

    async function changeReportPause(report, paused) {
      await runAction(async () => {
        const payload = await requestFull(`/api/cutover/reports/${report.id}/${paused ? 'pause' : 'resume'}`, {method: 'POST'});
        activeReport.value = payload.data;
        upsertReport(payload.data);
        NocMessage.success(payload.message);
        startReportPolling(report.id, true);
      });
    }

    function openReportLogin() { navigateTo('dispatchSession'); }

    function scheduleReportPoll(reportId, delay = 1200) {
      if (reportPollTimer) {
        clearTimeout(reportPollTimer);
      }
      reportPollTimer = setTimeout(() => pollReport(reportId), delay);
    }

    async function finishReportProgress(report) {
      if (!notifiedReportIds.has(report.id)) {
        notifiedReportIds.add(report.id);
        if (report.status === "success") {
          NocMessage.success(tt("cutover.task.reportFinished"));
          setStatus(tt("cutover.task.reportFinished"));
        } else {
          const message = (report.result && report.result.error) || tt("cutover.task.reportFailed");
          NocMessage.error(message);
          setStatus(message, "error");
        }
      }
      try {
        const refreshed = await requestJson(`/api/cutover/tasks/${localTask.value.id}`);
        await initFromTask(refreshed);
        emit("changed", refreshed);
      } catch (error) {
        reportProgressError.value = error.message || tt("cutover.task.reportPollingError");
      }
      await refreshPortalStatus();
      if (report.result && report.result.error_code === "RPA_SESSION_REQUIRED") {
        NocMessage.warning(report.result.error || tt("dispatchSession.reportBlocked"));
        navigateTo("dispatchSession");
      }
    }

    async function pollReport(reportId) {
      if (disposed) {
        return;
      }
      try {
        const report = await requestJson(`/api/cutover/reports/${reportId}`);
        const previousStatus = activeReport.value?.status;
        reportProgressError.value = "";
        activeReport.value = report;
        upsertReport(report);
        loadReportStepImages(report);
        if (["pending", "running"].includes(report.status)) {
          scheduleReportPoll(reportId);
          return;
        }
        if (['paused', 'waiting_login', 'interrupted'].includes(report.status)) {
          if (previousStatus !== report.status) await refreshPortalStatus();
          scheduleReportPoll(reportId, 2500);
          return;
        }
        await finishReportProgress(report);
      } catch (error) {
        reportProgressError.value = error.message || tt("cutover.task.reportPollingError");
        scheduleReportPoll(reportId, 2500);
      }
    }

    function startReportPolling(reportId, immediate = false) {
      scheduleReportPoll(reportId, immediate ? 0 : 1200);
    }

    function resumeReportProgress(task) {
      const active = (task.reports || []).find((report) => (
        ["pending", "running", "paused", "waiting_login", "interrupted"].includes(report.status)
      ));
      if (!active) {
        return;
      }
      activeReport.value = active;
      reportProgressVisible.value = true;
      startReportPolling(active.id, true);
    }

    async function reportTask() {
      if (formDirty.value) { NocMessage.warning(tt('cw.editsUnsaved')); return; }
      if (reportDisabled.value) return;
      activeReport.value = { status: 'pending', result: { note: tt('cutover.task.reportPreparing') } };
      reportProgressError.value = "";
      reportProgressVisible.value = true;
      let sessionError = null;
      const payload = await runAction(async () => {
        try {
          await refreshPortalStatus();
          const canQueue = appStore.portalStatus?.reporting && appStore.portalStatus?.session_version;
          if (!appStore.portalStatus?.authenticated && !canQueue) {
            reportProgressVisible.value = false;
            activeReport.value = null;
            NocMessage.warning('请先确认当前环境的个人综调账号已登录');
            navigateTo('dispatchSession');
            return null;
          }
          return await requestFull(`/api/cutover/tasks/${localTask.value.id}/report`, {
            method: "POST",
            body: JSON.stringify({
              environment: appStore.portalEnvironment || undefined,
              session_version: appStore.portalStatus.session_version,
            }),
          });
        } catch (error) {
          if (error.status === 409 && error.code === "RPA_SESSION_REQUIRED") {
            sessionError = error;
            reportProgressVisible.value = false;
            activeReport.value = null;
            return null;
          }
          reportProgressError.value = error.message || tt('cutover.task.reportFailed');
          activeReport.value = { status: 'failed', result: { note: reportProgressError.value } };
          throw error;
        }
      });
      if (sessionError) {
        NocMessage.warning(sessionError.message || tt("dispatchSession.reportBlocked"));
        setStatus(sessionError.message || tt("dispatchSession.reportBlocked"), "error");
        navigateTo("dispatchSession");
        return;
      }
      if (!payload) {
        return;
      }
      const response = payload.data || {};
      const report = {
        id: response.report_id,
        task_id: localTask.value.id,
        report_type: localTask.value.line_type,
        status: response.report_status || "pending",
        result: response.result || {},
        create_time: new Date().toLocaleString(),
      };
      localTask.value = { ...localTask.value, status: response.task_status || "reporting" };
      upsertReport(report);
      activeReport.value = report;
      reportProgressError.value = "";
      reportProgressVisible.value = true;
      emit("changed", localTask.value);
      NocMessage.success(payload.message || tt("cutover.task.reportSubmitted"));
      setStatus(payload.message || tt("cutover.task.reportSubmitted"));
      startReportPolling(report.id);
      // The durable job now owns this account; checking returns its execution state.
      refreshPortalStatus();
    }

    async function resolveReport(report, resolution) {
      let note;
      try {
        note = await NocDialog.prompt(tt('manualCutover.reportHint'), resolution === 'success' ? tt('manualCutover.markReported') : '核对后标记失败', {inputPlaceholder: tt('manualCutover.reason'), validationMessage: tt('manualCutover.required'), confirmButtonText: tt('manualCutover.confirm'), cancelButtonText: tt('common.cancel')});
      } catch { return; }
      await runAction(async () => {
        await requestFull(`/api/cutover/reports/${report.id}/resolve`, {method: 'POST', body: JSON.stringify({
          resolution, note})});
        const task = await requestJson(`/api/cutover/tasks/${localTask.value.id}`);
        await initFromTask(task);
        activeReport.value = (task.reports || []).find(item => item.id === report.id) || null;
        emit('changed', task);
        NocMessage.success(tt('manualCutover.resolved'));
        await refreshPortalStatus();
      });
    }

    function reportSummaryText(value) {
      return String(value || '').split(/[；;]\s*失败截图[：:]/)[0];
    }

    function canUndoReport(report) {
      return canOperate.value && report.id === localTask.value.reports?.[0]?.id &&
        report.result?.resolved_by && ['failed', 'interrupted'].includes(report.result?.original_status);
    }

    async function undoReport(report) {
      let note;
      try { note = await NocDialog.prompt(tt('manualCutover.undoReportHint'), tt('manualCutover.undoReport'), {
        inputPlaceholder: tt('manualCutover.reason'), validationMessage: tt('manualCutover.required'),
        confirmButtonText: tt('manualCutover.confirm'), cancelButtonText: tt('common.cancel')}); }
      catch { return; }
      await runAction(async () => {
        await requestFull(`/api/cutover/reports/${report.id}/resolve/undo`, {method:'POST',
          body:JSON.stringify({note, expected_at:report.result.resolved_at})});
        const task = await requestJson(`/api/cutover/tasks/${localTask.value.id}`);
        await initFromTask(task);
        activeReport.value = task.reports.find(item => item.id === report.id) || null;
        emit('changed', task);
        NocMessage.success(tt('manualCutover.undone'));
        await refreshPortalStatus();
      });
    }

    function downloadExcel() {
      window.open(`/api/cutover/tasks/${localTask.value.id}/excel`, "_blank");
    }

    // 按钮禁用规则与旧版一致
    const canOperate = computed(() => canOperateMailbox(localTask.value.email?.receiver));
    const taskCompleted = computed(() => localTask.value.status === 'completed');
    const saveDisabled = computed(() => !canOperate.value || taskCompleted.value || busy.value || localTask.value.status === "reporting");
    const confirmDisabled = computed(() => !canOperate.value || busy.value || localTask.value.status !== "draft" || formDirty.value);
    const reportDisabled = computed(() => {
      const status = localTask.value.status;
      return appStore.user?.is_admin || !canOperate.value || busy.value || formDirty.value || !(status === "confirmed" || status === "report_failed");
    });
    const excelDisabled = computed(() => !localTask.value.customer_excel_filename);
    function clearReportImageUrls() {
      reportImageVersion += 1;
      reportImageLoadingKeys.clear();
      Object.values(reportImageUrls).forEach((url) => URL.revokeObjectURL(url));
      Object.keys(reportImageUrls).forEach((key) => delete reportImageUrls[key]);
    }

    function operationImageKey(reportId, index) {
      return `${reportId}-${index}`;
    }

    async function loadReportImages(task) {
      clearReportImageUrls();
      await Promise.all((task.reports || []).map(loadReportStepImages));
    }

    async function loadReportStepImages(report) {
      const version = reportImageVersion;
      const steps = (report.result && report.result.operation_log) || [];
      await Promise.all(steps.map(async (step, index) => {
        if (!step.screenshot_filename) return;
        const key = operationImageKey(report.id, index);
        if (reportImageUrls[key] || reportImageLoadingKeys.has(key)) return;
        const artifactPath = String(step.screenshot_filename)
          .split("/")
          .map((segment) => encodeURIComponent(segment))
          .join("/");
        reportImageLoadingKeys.add(key);
        try {
          const url = await requestBlobUrl(`/api/rpa/report-artifacts/${artifactPath}`);
          if (disposed || version !== reportImageVersion) URL.revokeObjectURL(url);
          else reportImageUrls[key] = url;
        } catch {
          return;
        } finally {
          if (version === reportImageVersion) reportImageLoadingKeys.delete(key);
        }
      }));
    }

    onUnmounted(() => {
      disposed = true;
      if (reportPollTimer) {
        clearTimeout(reportPollTimer);
      }
      clearReportImageUrls();
    });

    return {
      localTask, busy, fillExpanded, formDirty, isBackbone, fill, validationMessages, reportSummary, appStore, canOperate,
      circuitColumns, circuitRows, reasonColumns, reasonRows,
      addSheetRow, removeSheetRow, customerEnumOptions, customerColumnClass,
      backboneCards, backboneActive, addBackboneCard, removeBackboneCard,
      expandAllBackboneSections, collapseAllBackboneSections,
      orderedBackboneSections, orderedBackboneFields, controlKind, isWideField,
      isBackboneSystemField, isBackboneConfirmationField, backboneEnumOptions,
      handleBackboneEnumChange,
      saveEdit, switchType, confirmTask, reportTask, downloadExcel, resolveReport,
      canControlReport, changeReportPause, openReportLogin, undoReport, canUndoReport, reportSummaryText,
      saveDisabled, confirmDisabled, reportDisabled, excelDisabled, taskCompleted,
      reportImageUrls, reportImageLoadingKeys, reportProgressVisible, activeReport, activeReportSteps,
      activeReportInProgress, reportProgressError, reportStatusType, reportStatusText,
      statusTagType, statusText, lineTypeText, taskLineCount,
      icons: ElementPlusIconsVue,
    };
  },
  template: `
    <div class="task-detail-panel" :class="{'cw-task-detail':operatorMode}">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">Cutover Task</p>
          <h3>{{ $t('cutover.task.heading', { id: localTask.id }) }}<span v-if="localTask.title"> - {{ localTask.title }}</span></h3>
        </div>
        <div class="panel-heading-tools">
          <ui-tag v-if="localTask.cutover_scene === 'emergency'" type="danger" effect="dark" size="small">
            {{ $t('cutover.task.emergencyRejected') }}
          </ui-tag>
          <ui-button size="small" plain class="task-toolbar-button" :icon="icons.ArrowUp" @click="$emit('collapse')">{{ $t('cutover.task.collapse') }}</ui-button>
        </div>
      </div>

      <ui-drawer v-model="reportProgressVisible"
                 :title="$t('cutover.task.reportProgressTitle')"
                 size="520px" direction="rtl" append-to-body
                 :modal="false" modal-penetrable :lock-scroll="false"
                 class="report-progress-drawer">
        <div v-if="activeReport" class="report-progress-content">
          <section class="report-progress-summary">
            <div class="report-progress-status-row">
              <ui-tag v-if="activeReport.id || activeReport.status === 'failed'" :type="reportStatusType(activeReport.status)" effect="dark">
                {{ reportStatusText(activeReport.status) }}
              </ui-tag>
              <span v-if="activeReport.id" class="mono muted">#{{ activeReport.id }}</span>
            </div>
            <div class="report-progress-current">
              <ui-icon v-if="activeReportInProgress" class="is-loading"><component :is="icons.Loading"></component></ui-icon>
              <ui-icon v-else-if="activeReport.status === 'success'" class="report-progress-success"><component :is="icons.CircleCheck"></component></ui-icon>
              <ui-icon v-else-if="['paused','waiting_login','interrupted'].includes(activeReport.status)"><component :is="icons.WarningFilled"></component></ui-icon>
              <ui-icon v-else class="report-progress-danger"><component :is="icons.CircleClose"></component></ui-icon>
              <div>
                <span>{{ $t('cutover.task.reportCurrentStep') }}</span>
                <strong>
                  {{ (activeReport.result && (activeReport.result.current_step_label || activeReport.result.note)) || $t('cutover.task.reportPreparing') }}
                </strong>
              </div>
            </div>
            <p>{{ $t('cutover.task.reportStepCount', { count: activeReportSteps.length }) }}</p>
          </section>

          <div v-if="canControlReport(activeReport)" class="panel-actions">
            <ui-button v-if="['pending','waiting_login'].includes(activeReport.status)" :loading="busy"
                       @click="changeReportPause(activeReport, true)">{{ $t('cutover.task.pauseReport') }}</ui-button>
            <ui-button v-if="activeReport.status === 'paused'" type="primary" :loading="busy"
                       @click="changeReportPause(activeReport, false)">{{ $t('cutover.task.resumeReport') }}</ui-button>
            <ui-button v-if="activeReport.status === 'waiting_login' || activeReport.result?.error_code === 'RPA_SESSION_REQUIRED_AFTER_SUBMIT'"
                       type="primary" @click="openReportLogin">{{ $t('cutover.task.loginForQueue') }}</ui-button>
          </div>

          <ui-alert v-if="reportProgressError" type="warning" :closable="false" show-icon
                    :title="reportProgressError"></ui-alert>

          <div v-if="activeReport.id && !activeReportSteps.length && activeReportInProgress" class="report-progress-empty">
            <ui-icon class="is-loading"><component :is="icons.Loading"></component></ui-icon>
            <span>{{ $t(activeReport.status === 'pending' ? 'cutover.task.reportWaitingInQueue' : 'cutover.task.reportWaitingForStep') }}</span>
          </div>
          <report-screenshot-gallery v-else-if="activeReportSteps.length" :report-id="activeReport.id" :steps="activeReportSteps"
                                     :image-urls="reportImageUrls" :loading-keys="reportImageLoadingKeys"/>


          <p v-if="activeReport.id" class="report-progress-hint">{{ $t('cutover.task.reportProgressHint') }}</p>
        </div>
      </ui-drawer>

      <div v-show="!historyOnly" class="task-meta-grid">
        <div class="task-meta-item">
          <span>{{ $t('common.status') }}</span>
          <ui-tag :type="statusTagType(localTask.status)" effect="dark">
            {{ statusText(localTask.status, localTask.status_label) }}
          </ui-tag>
        </div>
        <div class="task-meta-item">
          <span>{{ $t('cutover.task.lineTypeLabel') }}</span>
          <strong>{{ lineTypeText(localTask) }}</strong>
        </div>
        <div class="task-meta-item">
          <span>{{ $t('cutover.task.filledLines') }}</span>
          <strong>{{ $t('cutover.task.lineCount', { count: taskLineCount(localTask) }) }}</strong>
        </div>
        <div class="task-meta-item">
          <span>{{ $t('common.supplier') }}</span>
          <strong>{{ localTask.supplier || '-' }}</strong>
        </div>
        <div class="task-meta-item">
          <span>{{ $t('common.carrierTicketNo') }}</span>
          <strong>{{ localTask.carrier_ticket_no || '-' }}</strong>
        </div>
        <div class="task-meta-item">
          <span>{{ $t('cutover.task.cutoverWindow') }}</span>
          <strong>{{ $t('common.timeRange', { start: fill.cutStartTime || '-', end: fill.cutEndTime || '-' }) }}</strong>
        </div>
        <div class="task-meta-item">
          <span>{{ $t('common.confirmTime') }}</span>
          <strong>{{ String(localTask.confirmed_at || '-').replace('T', ' ').slice(0, 19) }}</strong>
        </div>
        <div class="task-meta-item">
          <span>{{ $t('common.createTime') }}</span>
          <strong>{{ String(localTask.create_time || '-').replace('T', ' ').slice(0, 19) }}</strong>
        </div>
        <div class="task-meta-item">
          <span>{{ $t('common.updateTime') }}</span>
          <strong>{{ String(localTask.update_time || '-').replace('T', ' ').slice(0, 19) }}</strong>
        </div>
      </div>

      <div v-if="operatorMode && !historyOnly" class="cw-report-summary">
        <h3>{{ $t('cw.savedReport') }}</h3>
        <div class="cw-report-table"><table><thead><tr><th>{{ $t('cw.internalLine') }}</th><th>{{ $t('cutover.task.cutoverWindow') }}</th><th>{{ $t('cw.impact') }}</th><th>{{ $t('cw.reason') }}</th></tr></thead><tbody><tr v-for="(row,index) in reportSummary" :key="index"><td>{{ row.name }}</td><td>{{ row.window }}</td><td>{{ row.impact }}</td><td>{{ row.reason }}</td></tr></tbody></table></div>
        <p v-if="!reportSummary.length" class="cw-hint">{{ $t('cw.noReportLines') }}</p>
      </div>

      <div v-if="operatorMode && !historyOnly" class="cw-task-controls"><ui-button @click="fillExpanded=!fillExpanded" :aria-expanded="fillExpanded">{{ $t('cw.fillDetails') }} {{ fillExpanded ? '−' : '+' }}</ui-button><span v-if="validationMessages.length" class="warn-text">{{ $t('cutover.task.validationTitle',{count:validationMessages.length}) }}</span><span v-if="formDirty" class="warn-text">{{ $t('cw.editsUnsaved') }}</span></div>
      <div v-show="!historyOnly && (!operatorMode || fillExpanded)" class="cw-full-form">
      <div class="task-type-switch">
        <span class="muted">{{ $t('cutover.task.fillTypeLabel') }}</span>
        <ui-radio-group class="task-type-options" role="radiogroup" :name="'cutover-line-type-' + localTask.id"
                        :aria-label="$t('cutover.task.fillTypeLabel')" :model-value="localTask.line_type" :disabled="!canOperate || taskCompleted || localTask.status === 'reporting'"
                        @change="switchType">
          <ui-radio-button value="customer"><span class="task-type-label"><ui-icon aria-hidden="true"><component :is="icons.Check"></component></ui-icon>{{ $t('cutover.task.fillCustomer') }}</span></ui-radio-button>
          <ui-radio-button value="backbone"><span class="task-type-label"><ui-icon aria-hidden="true"><component :is="icons.Check"></component></ui-icon>{{ $t('cutover.task.fillBackbone') }}</span></ui-radio-button>
        </ui-radio-group>
      </div>

      <div v-if="validationMessages.length" class="task-warnings">
        <strong>{{ $t('cutover.task.validationTitle', { count: validationMessages.length }) }}</strong>
        <ul>
          <li v-for="(message, index) in validationMessages" :key="index">
            {{ message.message || JSON.stringify(message) }}
          </li>
        </ul>
      </div>

      <!-- 客户线路：电路表 + 割接原因表 -->
      <template v-if="!isBackbone">
        <div class="block-section">
          <div class="block-head">
            <span>{{ $t('cutover.task.circuitSheet') }}</span>
            <ui-button size="small" type="primary" plain class="task-toolbar-button" :icon="icons.Plus" :disabled="taskCompleted" @click="addSheetRow('circuit')">{{ $t('cutover.task.addRow') }}</ui-button>
          </div>
          <p class="field-hint">{{ $t('cutover.task.sheetHint') }}</p>
          <div class="sheet-table-wrap">
            <table class="sheet-table">
              <thead>
                <tr>
                  <th v-for="column in circuitColumns" :key="column" :class="customerColumnClass(column)">
                    {{ column || $t('cutover.task.emptyColumn') }}
                  </th>
                  <th v-if="circuitColumns.length">{{ $t('common.actions') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!circuitColumns.length">
                  <td class="empty-cell">{{ $t('common.noData') }}</td>
                </tr>
                <tr v-for="(row, rowIndex) in circuitRows" :key="rowIndex">
                  <td v-for="column in circuitColumns" :key="column" :class="customerColumnClass(column)">
                    <ui-select :disabled="taskCompleted" v-if="customerEnumOptions(column, row)"
                               v-model="row[column]" size="small" :aria-label="column" style="width: 100%"
                               :filterable="column === '预计影响客户业务时长'"
                               :allow-create="column === '预计影响客户业务时长'" default-first-option>
                      <ui-option v-for="option in customerEnumOptions(column, row)" :key="option"
                                 :label="option" :value="option"></ui-option>
                    </ui-select>
                    <ui-input :disabled="taskCompleted" v-else v-model="row[column]" size="small" :aria-label="column"></ui-input>
                  </td>
                  <td>
                    <ui-action type="danger" :disabled="taskCompleted" @click="removeSheetRow('circuit', rowIndex)" icon="Delete" :label="$t('common.delete')"></ui-action>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="block-section">
          <div class="block-head">
            <span>{{ $t('cutover.task.reasonSheet') }}</span>
            <ui-button size="small" type="primary" plain class="task-toolbar-button" :icon="icons.Plus" :disabled="taskCompleted" @click="addSheetRow('reason')">{{ $t('cutover.task.addRow') }}</ui-button>
          </div>
          <div class="sheet-table-wrap">
            <table class="sheet-table">
              <thead>
                <tr>
                  <th v-for="column in reasonColumns" :key="column">{{ column || $t('cutover.task.emptyColumn') }}</th>
                  <th v-if="reasonColumns.length">{{ $t('common.actions') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!reasonColumns.length">
                  <td class="empty-cell">{{ $t('common.noData') }}</td>
                </tr>
                <tr v-for="(row, rowIndex) in reasonRows" :key="rowIndex">
                  <td v-for="column in reasonColumns" :key="column">
                    <ui-input :disabled="taskCompleted" v-model="row[column]" size="small"></ui-input>
                  </td>
                  <td>
                    <ui-action type="danger" :disabled="taskCompleted" @click="removeSheetRow('reason', rowIndex)" icon="Delete" :label="$t('common.delete')"></ui-action>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>

      <!-- 骨干线路：分组卡片表单 -->
      <div v-else class="block-section">
        <div class="block-head">
          <span>{{ $t('cutover.task.backboneForm') }}</span>
          <ui-button size="small" type="primary" plain class="task-toolbar-button" :icon="icons.Plus" :disabled="taskCompleted" @click="addBackboneCard">{{ $t('cutover.task.addBackbone') }}</ui-button>
        </div>
        <p class="field-hint">{{ $t('cutover.task.backboneHint') }}</p>
        <p v-if="!backboneCards.length" class="empty-inline">{{ $t('cutover.task.backboneEmpty') }}</p>
        <div class="backbone-cards">
          <article v-for="(card, cardIndex) in backboneCards" :key="cardIndex" class="backbone-card">
            <div class="backbone-card-head">
              <strong>{{ $t('cutover.task.backboneCard', { index: cardIndex + 1 }) }}</strong>
              <div class="backbone-card-tools">
                <div class="backbone-disclosure-tools">
                  <ui-button quaternary size="small" class="task-toolbar-button" :icon="icons.ArrowDown" @click="expandAllBackboneSections">{{ $t('cutover.task.expandAll') }}</ui-button>
                  <ui-button quaternary size="small" class="task-toolbar-button" :icon="icons.ArrowUp" @click="collapseAllBackboneSections">{{ $t('cutover.task.collapseAll') }}</ui-button>
                </div>
                <ui-button size="small" type="danger" plain class="task-toolbar-button" :icon="icons.Delete" :disabled="taskCompleted" @click="removeBackboneCard(cardIndex)">{{ $t('common.delete') }}</ui-button>
              </div>
            </div>
            <ui-collapse class="backbone-collapse"
                         :model-value="backboneActive[cardIndex] || []"
                         @update:model-value="(value) => (backboneActive[cardIndex] = value)">
              <template v-for="sectionName in orderedBackboneSections(card)" :key="sectionName">
                <ui-collapse-item v-if="card[sectionName] && !Array.isArray(card[sectionName])"
                                  :title="sectionName" :name="sectionName">
                <div class="backbone-field-grid">
                  <label v-for="fieldName in orderedBackboneFields(sectionName, card[sectionName])"
                         :key="fieldName"
                         :class="{ 'backbone-field-wide': isWideField(cardIndex, sectionName, fieldName) }">
                    <span>{{ fieldName }}</span>
                    <div v-if="sectionName === '基本信息' && fieldName === '中断类型'"
                         class="backbone-interruption-control">
                      <ui-select :disabled="taskCompleted" v-model="card[sectionName][fieldName]" class="backbone-enum-select"
                                 :aria-label="fieldName"
                                 @change="(value) => handleBackboneEnumChange(card, cardIndex, sectionName, fieldName, value)">
                        <ui-option v-for="option in backboneEnumOptions(fieldName)"
                                   :key="option" :label="option" :value="option"></ui-option>
                      </ui-select>
                      <div v-if="card[sectionName]['中断类型'] === '中断'"
                           class="backbone-interruption-duration">
                        <input :disabled="taskCompleted" v-model="card[sectionName]['中断时间 (分钟)']"
                               class="backbone-input" inputmode="numeric" autocomplete="off"
                               aria-label="中断时间 (分钟)">
                        <span class="backbone-interruption-unit" aria-hidden="true">分钟</span>
                      </div>
                    </div>
                    <ui-select :disabled="taskCompleted" v-else-if="isBackboneSystemField(sectionName, fieldName)"
                               v-model="card[sectionName][fieldName]" multiple filterable allow-create
                               default-first-option class="backbone-system-select"
                               placeholder="输入系统名称后回车">
                      <ui-option v-for="systemName in card[sectionName][fieldName]"
                                 :key="systemName" :label="systemName" :value="systemName"></ui-option>
                    </ui-select>
                    <ui-checkbox :disabled="taskCompleted" v-else-if="isBackboneConfirmationField(fieldName)"
                                 v-model="card[sectionName][fieldName]"
                                 true-label="是" false-label="否" class="backbone-confirmation-checkbox">
                      {{ card[sectionName][fieldName] === '是' ? '已选中' : '未选中' }}
                    </ui-checkbox>
                    <ui-select :disabled="taskCompleted" v-else-if="backboneEnumOptions(fieldName)"
                               v-model="card[sectionName][fieldName]" class="backbone-enum-select"
                               :aria-label="fieldName"
                               @change="(value) => handleBackboneEnumChange(card, cardIndex, sectionName, fieldName, value)">
                      <ui-option v-for="option in backboneEnumOptions(fieldName)"
                                 :key="option" :label="option" :value="option"></ui-option>
                    </ui-select>
                    <textarea :disabled="taskCompleted" v-else-if="controlKind(cardIndex, sectionName, fieldName) === 'textarea'"
                              v-model="card[sectionName][fieldName]" :rows="2" class="backbone-input"></textarea>
                    <input :disabled="taskCompleted" v-else v-model="card[sectionName][fieldName]" class="backbone-input">
                  </label>
                </div>
                </ui-collapse-item>
              </template>
            </ui-collapse>
          </article>
        </div>
      </div>

      </div>
      <!-- 上报记录 -->
      <div class="block-section">
        <div class="block-head">
          <span>{{ $t('cutover.task.reports') }}</span>
          <ui-button v-if="activeReport" size="small" :type="activeReportInProgress ? 'primary' : 'default'"
                     @click="reportProgressVisible = true">
            {{ $t('cutover.task.reportViewProgress') }}
          </ui-button>
        </div>
        <ui-table :data="localTask.reports || []" size="small" :empty-text="$t('cutover.task.reportsEmpty')">
          <ui-table-column type="expand" width="48">
            <template #default="{ row }">
              <div class="report-operation-detail">
                <ui-alert v-if="row.result && row.result.manual_intervention_required"
                          type="error" :closable="false" show-icon
                          :title="$t('cutover.task.manualIntervention')"></ui-alert>
                <div v-if="row.result && row.result.portal_task_number" class="report-task-number">
                  <span>{{ $t('cutover.task.portalTaskNumber') }}</span>
                  <strong class="mono">{{ row.result.portal_task_number }}</strong>
                </div>
                <div class="report-review-bar">
                  <div class="report-review-summary">
                    <strong>{{ row.result?.resolved_by ? $t('manualCutover.reviewed') : $t('manualCutover.errorSummary') }}</strong>
                    <p v-if="row.result?.error" class="report-error">{{ reportSummaryText(row.result.error) }}</p>
                    <p v-else class="muted">{{ reportSummaryText(row.result?.note) }}</p>
                  </div>
                  <div v-if="canOperate" class="report-review-actions">
                    <ui-button v-if="row.status === 'failed' && row.id === localTask.reports[0]?.id" size="small" type="primary" :icon="icons.EditPen" :loading="busy" @click="resolveReport(row, 'success')">{{ $t('manualCutover.markReported') }}</ui-button>
                    <ui-button v-if="canUndoReport(row)" size="small" :icon="icons.RefreshLeft" :loading="busy" @click="undoReport(row)">{{ $t('manualCutover.undoReport') }}</ui-button>
                    <template v-if="canControlReport(row)">
                      <ui-button v-if="['pending','waiting_login'].includes(row.status)" size="small" :loading="busy" @click="changeReportPause(row, true)">{{ $t('cutover.task.pauseReport') }}</ui-button>
                      <ui-button v-if="row.status === 'paused'" size="small" :loading="busy" @click="changeReportPause(row, false)">{{ $t('cutover.task.resumeReport') }}</ui-button>
                    </template>
                    <template v-if="['pending','running','interrupted'].includes(row.status)">
                      <ui-button size="small" :loading="busy" @click="resolveReport(row, 'success')">核对后标记成功</ui-button>
                      <ui-button size="small" :loading="busy" @click="resolveReport(row, 'failed')">核对后标记失败</ui-button>
                    </template>
                  </div>
                </div>
                <div v-if="row.result?.resolved_by" class="manual-report-audit">
                  <div class="manual-audit-heading"><span class="manual-mark-badge"><ui-icon><component :is="icons.User" /></ui-icon>{{ $t('manualCutover.manualBadge') }}</span><strong>{{ row.result.resolved_by }}</strong><time>{{ row.result.resolved_at?.slice(0,19).replace('T',' ') }}</time></div>
                  <p>{{ row.result.note }}</p>
                  <details v-if="row.result.original_result"><summary>{{ $t('manualCutover.original') }}</summary><pre class="detail-content">{{ JSON.stringify(row.result.original_result, null, 2) }}</pre></details>
                </div>
                <details v-if="row.result?.error" class="report-error-details"><summary>{{ $t('manualCutover.errorDetails') }}</summary><pre>{{ row.result.error }}</pre></details>
                <details v-if="row.manual_history?.length" class="manual-action-history"><summary>{{ $t('manualCutover.history') }} · {{ row.manual_history.length }}</summary><ol><li v-for="(event, index) in row.manual_history" :key="index"><div><strong>{{ $t('manualCutover.actions.' + event.action) }}</strong><span>{{ event.by }}</span><time>{{ event.at?.slice(0,19).replace('T',' ') }}</time></div><p>{{ event.note }}</p></li></ol></details>
                <report-screenshot-gallery v-if="row.result && row.result.operation_log && row.result.operation_log.length"
                                           :report-id="row.id" :steps="row.result.operation_log"
                                           :image-urls="reportImageUrls" :loading-keys="reportImageLoadingKeys"/>

              </div>
            </template>
          </ui-table-column>
          <ui-table-column prop="id" label="ID" width="80">
            <template #default="{ row }">
              <span class="mono">{{ row.id }}</span>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('common.type')" width="100">
            <template #default="{ row }">
              <span>{{ lineTypeText({line_type: row.report_type}) }}</span>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('common.status')" width="120">
            <template #default="{ row }">
              <ui-tag :type="reportStatusType(row.status)" size="small">
                {{ reportStatusText(row.status) }}
              </ui-tag>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('cutover.task.reportNote')" min-width="260">
            <template #default="{ row }">
              <div v-if="row.result?.execution_identity" class="report-identity">
                <span class="report-environment" :class="{'is-production': row.result.execution_identity.environment === 'production'}">
                  {{ row.result.execution_identity.environment === 'production' ? '生产环境' : '测试环境' }}
                </span>
                <span class="report-account"><span>综调账号</span><strong>{{ row.result.execution_identity.username || '未记录' }}</strong></span>
                <span class="report-account"><span>工作台用户</span><strong>{{ row.result.execution_identity.workbench_username || '未记录' }}</strong></span>
              </div>
              <div v-else class="muted">历史记录 · 未记录执行账号</div>
              <div v-if="row.result?.resolved_by" class="report-manual-summary">
                <div><span class="manual-mark-badge"><ui-icon><component :is="icons.User" /></ui-icon>{{ $t('manualCutover.manualBadge') }}</span><strong>{{ row.result.resolved_by }}</strong><time>{{ row.result.resolved_at?.slice(0,19).replace('T',' ') }}</time></div>
                <p>{{ row.result.note?.replace(/^人工核对：/, '') }}</p>
              </div>
              <span v-else class="muted report-result-note">{{ reportSummaryText(row.result?.note || row.result?.error || row.result?.portal_task_number) || '-' }}</span>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('common.time')" width="170">
            <template #default="{ row }">
              <span class="mono muted">{{ row.create_time || '' }}</span>
            </template>
          </ui-table-column>
        </ui-table>
      </div>

      <div v-show="!historyOnly" class="panel-actions">
        <ui-button v-if="!isBackbone" :disabled="excelDisabled" @click="downloadExcel">{{ $t('cutover.task.downloadExcel') }}</ui-button>
        <ui-button :disabled="saveDisabled" @click="saveEdit">{{ $t('cutover.task.saveEdit') }}</ui-button>
        <ui-button :disabled="confirmDisabled" @click="confirmTask">{{ $t('cutover.task.manualConfirm') }}</ui-button>
        <span v-if="appStore.user?.is_admin" class="muted report-permission-hint">综调上报请使用普通用户账号</span>
        <ui-button type="primary" :disabled="reportDisabled" @click="reportTask">{{ $t('cutover.task.reportSubmit') }}</ui-button>
      </div>
    </div>
  `,
});

// ==================== 割接邮件详情页 ====================
const ViewCutoverEmailDetail = defineComponent({
  name: "ViewCutoverEmailDetail",
  components: {MailAttachmentList, MailAttachmentPreview},
  props: {
    emailRecordId: { type: Number, required: true },
  },
  setup(props) {
    const email = ref(null);
    const loading = ref(false);
    const contentCollapsed = ref([]);
    const contentFrame = ref(null);
    const expandedKeys = ref([]);
    const detailTask = ref(null);
    // 待确认回复草稿：可人工编辑后再确认发送；收件人支持修改与多个
    const replyDraft = ref("");
    const replyRecipients = ref([]);
    const replyCcRecipients = ref([]);
    const replyBusy = ref(false);
    const apiForwardBusy = ref(false);
    const readStateBusy = ref(false);
    const deleteBusy = ref(false);
    const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    const extractionDraft = ref("");
    const savedExtractionDraft = ref("");
    const extractionBusy = ref(false);
    const manualBindings = reactive({});
    const manualBindingTypes = reactive({});
    const editingLineBindings = reactive({});
    const workbench = useCutoverWorkbench({email, extractionDraft, savedExtractionDraft, extractionBusy,
      replyBusy, apiForwardBusy, deleteBusy, saveExtraction});
    async function completeEmail() {
      if (taskFormDirty.value || extractionDraft.value !== savedExtractionDraft.value) {
        NocMessage.warning(tt('cw.editsUnsaved')); return;
      }
      let note;
      try { note = await NocDialog.prompt(tt('manualCutover.completeHint'), tt('manualCutover.complete'), {
        inputPlaceholder: tt('manualCutover.reason'), validationMessage: tt('manualCutover.required'),
        confirmButtonText: tt('manualCutover.confirm'), cancelButtonText: tt('common.cancel')}); }
      catch { return; }
      workbench.completionBusy.value = true;
      try {
        await requestFull(`/api/cutover/emails/${email.value.id}/complete`, {method: 'POST', body: JSON.stringify({note})});
        detailTask.value = null;
        await loadDetail();
        NocMessage.success(tt('manualCutover.completed'));
      } catch (error) { NocMessage.error(error.message); }
      finally { workbench.completionBusy.value = false; }
    }
    async function undoEmailCompletion() {
      const expected_at = email.value.manual_completion.at;
      let note;
      try { note = await NocDialog.prompt(tt('manualCutover.undoCompleteHint'), tt('manualCutover.undoComplete'), {
        inputPlaceholder: tt('manualCutover.reason'), validationMessage: tt('manualCutover.required'),
        confirmButtonText: tt('manualCutover.confirm'), cancelButtonText: tt('common.cancel')}); }
      catch { return; }
      workbench.completionBusy.value = true;
      try {
        await requestFull(`/api/cutover/emails/${email.value.id}/complete/undo`, {method:'POST',body:JSON.stringify({note, expected_at})});
        detailTask.value = null;
        await loadDetail();
        NocMessage.success(tt('manualCutover.undone'));
      } catch (error) { NocMessage.error(error.message); }
      finally { workbench.completionBusy.value = false; }
    }
    const requestedTaskId = ref(null);
    const taskFormDirty = ref(false);
    let taskRequest = 0;
    let detailRequest = 0;
    let replySnapshot = '';
    const replySignature = () => JSON.stringify([replyDraft.value, replyRecipients.value, replyCcRecipients.value]);
    onUnmounted(() => { taskRequest++; detailRequest++; });
    const extractionDirty = computed(() => {
      try {
        return JSON.stringify(JSON.parse(extractionDraft.value)) !== JSON.stringify(JSON.parse(savedExtractionDraft.value));
      } catch {
        return extractionDraft.value !== savedExtractionDraft.value;
      }
    });
    const unsavedLineBindings = computed(() => (email.value?.line_table?.lines || []).some((entry, index) =>
      (!isAutomaticLineMatch(entry) || editingLineBindings[index]) && (
        (manualBindings[index] || "").trim() !== (entry.line?.bound_circuit_id || "").trim() ||
        (manualBindingTypes[index] || "") !== (entry.line?.bound_line_type || entry.circuits?.[0]?.line_type || "客户")
      ),
    ));
    function isAutomaticLineMatch(line) {
      return !line.line?.bound_circuit_id && line.circuits?.length === 1 && !line.task_generation_blocked;
    }
    function selectCircuitCandidate(line, index, circuitId) {
      const candidates = (line.circuits || []).filter((circuit) => circuit.circuit_id === circuitId);
      if (candidates.length === 1) {
        const type = candidates[0].line_type || "";
        manualBindingTypes[index] = type.includes("客户") ? "客户" : type.includes("骨干") ? "骨干" : "";
      } else if (!circuitId) {
        manualBindingTypes[index] = "客户";
      }
    }
    function toggleLineBindingEditor(line, index) {
      editingLineBindings[index] = !editingLineBindings[index];
      manualBindings[index] = editingLineBindings[index] ? (line.circuits[0]?.circuit_id || "") : "";
      manualBindingTypes[index] = line.circuits[0]?.line_type || "客户";
    }

    const hasSavedManualBinding = computed(() => (email.value?.line_table?.lines || []).some(
      (entry) => entry.line?.bound_circuit_id?.trim() && entry.circuits?.length === 1,
    ));
    const matchedTypeCounts = computed(() => {
      const counts = {customer: 0, backbone: 0};
      for (const entry of email.value?.line_table?.lines || []) {
        if (entry.circuits?.length !== 1) continue;
        const type = entry.circuits[0].line_type || "";
        if (type.includes("客户")) counts.customer += 1;
        else if (type.includes("骨干")) counts.backbone += 1;
      }
      return counts;
    });

    function extractionPayload() {
      const payload = JSON.parse(extractionDraft.value);
      if (!payload || Array.isArray(payload) || typeof payload !== "object") {
        throw new Error(tt("cutover.detail.extractionObjectRequired"));
      }
      payload.email_records_id = props.emailRecordId;
      return payload;
    }

    async function confirmTaskRegeneration() {
      if (!email.value?.tasks?.length) return true;
      try {
        await NocDialog.confirm(
          tt("cutover.detail.regenerateConfirmMessage"), tt("cutover.detail.regenerateTasks"),
          {confirmButtonText: tt("cutover.detail.regenerateConfirm"), cancelButtonText: tt("common.cancel"), type: "warning"},
        );
        return true;
      } catch {
        return false;
      }
    }

    async function saveExtraction(generate = false) {
      if (!workbench.canEditMail.value) return false;
      extractionBusy.value = true;
      try {
        const payload = extractionPayload();
        if (generate && !(await confirmTaskRegeneration())) return false;
        const saved = await requestJson(`/api/cutover/emails/${props.emailRecordId}/extraction`, {
          method: "PUT", body: JSON.stringify(payload),
        });
        email.value.line_table = saved.line_table;
        email.value.fill_payload = saved.fill_payload;
        Object.keys(editingLineBindings).forEach((key) => delete editingLineBindings[key]);
        Object.keys(manualBindings).forEach((key) => delete manualBindings[key]);
        Object.keys(manualBindingTypes).forEach((key) => delete manualBindingTypes[key]);
        (saved.line_table?.lines || []).forEach((entry, index) => {
          manualBindings[index] = entry.line.bound_circuit_id || "";
          manualBindingTypes[index] = entry.line.bound_line_type || entry.circuits?.[0]?.line_type || "客户";
        });
        email.value.extract_result = JSON.stringify(cleanExtraction(saved.fill_payload), null, 2);
        extractionDraft.value = email.value.extract_result;
        savedExtractionDraft.value = extractionDraft.value;
        if (generate) {
          const result = await requestJson("/api/cutover/tasks/generate", {method: "POST", body: JSON.stringify(saved.fill_payload)});
          closeTask();
          await loadDetail();
          if (!result.tasks?.length) {
            throw new Error((result.validation_messages || []).map((item) => item.message).join("；") || result.msg);
          }
        }
        workbench.tasksStale.value = !generate && !!email.value?.tasks?.length;
        NocMessage.success(tt(generate ? "cutover.detail.tasksGenerated" : "cutover.detail.extractionSaved"));
        return true;
      } catch (error) {
        NocMessage.error(error.message);
        return false;
      } finally {
        extractionBusy.value = false;
      }
    }

    function cleanExtraction(payload) {
      const result = JSON.parse(JSON.stringify(payload));
      delete result.supplier;
      delete result.supplier_name;
      delete result.email_records_id;
      if (Object.prototype.hasOwnProperty.call(result, "line_array")) delete result.line_array_info;
      for (const line of result.line_array || result.line_array_info?.data || []) {
        delete line.bound_circuit_id;
        delete line.bound_line_type;
      }
      return result;
    }

    async function bindLine(lineIndex) {
      if (!workbench.canEditMail.value) return;
      if (extractionDirty.value) { NocMessage.warning(tt('cw.editsUnsaved')); return; }
      extractionBusy.value = true;
      try {
        const saved = await requestJson(`/api/cutover/emails/${props.emailRecordId}/line-bindings`, {
          method: "PUT",
          body: JSON.stringify({line_index: lineIndex, circuit_id: manualBindings[lineIndex] || "", line_type: manualBindingTypes[lineIndex] || "客户"}),
        });
        email.value.line_table = saved.line_table;
        email.value.fill_payload = saved.fill_payload;
        editingLineBindings[lineIndex] = false;
        workbench.tasksStale.value = !!email.value.tasks?.length;
        NocMessage.success(tt("cutover.detail.bindingSaved"));
      } catch (error) {
        NocMessage.error(error.message);
      } finally {
        extractionBusy.value = false;
      }
    }

    async function regenerateTasks() {
      if (!workbench.canEditMail.value) return;
      if (extractionDirty.value || unsavedLineBindings.value) {
        NocMessage.warning(tt("cutover.detail.unsavedGenerationInputs"));
        return;
      }
      extractionBusy.value = true;
      try {
        if (!(await confirmTaskRegeneration())) return;
        const result = await requestJson("/api/cutover/tasks/generate", {
          method: "POST", body: JSON.stringify({...email.value.fill_payload, email_records_id: props.emailRecordId}),
        });
        closeTask();
        await loadDetail();
        if (!result.tasks?.length) {
          throw new Error((result.validation_messages || []).map((item) => item.message).join("；") || result.msg);
        }
        workbench.tasksStale.value = false;
        NocMessage.success(tt("cutover.detail.tasksGenerated"));
      } catch (error) {
        NocMessage.error(error.message);
      } finally {
        extractionBusy.value = false;
      }
    }

    const recipientOptions = computed(() => {
      if (!email.value) {
        return [];
      }
      const candidates = [email.value.supplier_reply_email, email.value.reply_to, email.value.sender];
      return [...new Set(candidates.filter((address) => address))];
    });
    // 提取解析结果：从 FastGPT 返回文本中解析各顶层 JSON 对象，直接展示格式化 JSON
    const extractResultBlocks = computed(() => {
      const text = (email.value && email.value.extract_result) || "";
      if (!text.trim()) {
        return [];
      }
      const objects = extractJsonObjects(text);
      if (!objects.length) {
        return [text];
      }
      return objects.map((obj) => JSON.stringify(obj, null, 2));
    });

    async function loadDetail() {
      const request = ++detailRequest;
      const recordId = props.emailRecordId;
      const preserveReply = email.value?.id === recordId && replySnapshot && replySignature() !== replySnapshot;
      loading.value = true;
      try {
        const record = await requestJson(`/api/cutover/emails/${recordId}`);
        if (request !== detailRequest) return;
        if (email.value?.id !== recordId || !record.tasks?.some(task=>task.id===detailTask.value?.id)) closeTask();
        email.value = record;
        if (email.value.processing_origin === 'unconfigured') contentCollapsed.value = ['content'];
        const extracted = Object.assign({}, ...extractJsonObjects(email.value.extract_result || ""));
        const saved = email.value.fill_payload || {};
        const payload = Object.keys(saved).length ? saved : extracted;
        extractionDraft.value = JSON.stringify(cleanExtraction(payload), null, 2);
        savedExtractionDraft.value = extractionDraft.value;
        Object.keys(editingLineBindings).forEach((key) => delete editingLineBindings[key]);
        Object.keys(manualBindings).forEach((key) => delete manualBindings[key]);
        Object.keys(manualBindingTypes).forEach((key) => delete manualBindingTypes[key]);
        (email.value.line_table?.lines || []).forEach((entry, index) => {
          manualBindings[index] = entry.line.bound_circuit_id || "";
          manualBindingTypes[index] = entry.line.bound_line_type || entry.circuits?.[0]?.line_type || "客户";
        });
        if (!preserveReply || record.reply_status !== 'pending') {
          replyDraft.value = (email.value && email.value.pending_reply_content) || "";
          replyRecipients.value = recipientOptions.value.slice(0, 1);
          replyCcRecipients.value = (email.value.reply_cc_recipients || []).slice();
          replySnapshot = replySignature();
        }
      } catch (error) {
        if (request !== detailRequest) return;
        email.value = null;
        replyDraft.value = "";
        replyRecipients.value = [];
        replyCcRecipients.value = [];
        setStatus(error.message, "error");
      } finally {
        if (request === detailRequest) loading.value = false;
      }
    }

    // 人工确认发送待确认回复（发送前二次确认，内容与收件人可在页面上修改）
    async function confirmReply() {
      if (!workbench.canReply.value || email.value.reply_status !== 'pending') return;
      if (!replyDraft.value.trim()) {
        NocMessage.error(tt("cutover.detail.replyContentRequired"));
        return;
      }
      const recipients = replyRecipients.value.map((address) => String(address).trim()).filter(Boolean);
      if (!recipients.length) {
        NocMessage.error(tt("cutover.detail.replyRecipientsRequired"));
        return;
      }
      const invalid = recipients.find((address) => !EMAIL_PATTERN.test(address));
      if (invalid) {
        NocMessage.error(tt("cutover.detail.replyRecipientsInvalid", { address: invalid }));
        return;
      }
      const ccRecipients = replyCcRecipients.value.map((address) => String(address).trim()).filter(Boolean);
      const invalidCc = ccRecipients.find((address) => !EMAIL_PATTERN.test(address));
      if (invalidCc) {
        NocMessage.error(tt("cutover.detail.replyCcInvalid", { address: invalidCc }));
        return;
      }
      try {
        await NocDialog.confirm(
          ccRecipients.length
            ? tt("cutover.detail.replyConfirmMessageWithCc", {
                recipients: recipients.join("、"),
                ccRecipients: ccRecipients.join("、"),
              })
            : tt("cutover.detail.replyConfirmMessage", { recipients: recipients.join("、") }),
          tt("cutover.detail.replyConfirmTitle"),
          {
            confirmButtonText: tt("cutover.detail.replyConfirmSend"),
            cancelButtonText: tt("common.cancel"),
            type: "warning",
          },
        );
      } catch {
        return;
      }
      replyBusy.value = true;
      try {
        await requestJson("/api/cutover/reply/confirm", {
          method: "POST",
          body: JSON.stringify({
            email_records_id: props.emailRecordId,
            reply_content: replyDraft.value,
            recipients,
            cc_recipients: ccRecipients,
          }),
        });
        NocMessage.success(tt("cutover.detail.replySent"));
        await loadDetail();
      } catch (error) {
        NocMessage.error(error.message);
      } finally {
        replyBusy.value = false;
      }
    }

    // 放弃待确认回复（不发送，不写入割接场景）
    async function cancelReply() {
      if (!workbench.canReply.value || email.value.reply_status !== 'pending') return;
      try {
        await NocDialog.confirm(
          tt("cutover.detail.replyCancelMessage"),
          tt("cutover.detail.replyCancelTitle"),
          {
            confirmButtonText: tt("cutover.detail.replyCancel"),
            cancelButtonText: tt("common.cancel"),
            type: "warning",
          },
        );
      } catch {
        return;
      }
      replyBusy.value = true;
      try {
        await requestJson("/api/cutover/reply/cancel", {
          method: "POST",
          body: JSON.stringify({ email_records_id: props.emailRecordId }),
        });
        NocMessage.success(tt("cutover.detail.replyCancelled"));
        await loadDetail();
      } catch (error) {
        NocMessage.error(error.message);
      } finally {
        replyBusy.value = false;
      }
    }

    async function retryApiForward() {
      apiForwardBusy.value = true;
      try {
        const data = await requestJson(
          `/api/cutover/emails/${props.emailRecordId}/forward-attempts`,
          { method: "POST" },
        );
        if (email.value && data && data.api_forward) {
          email.value.api_forward = data.api_forward;
        }
        NocMessage.success(tt("cutover.detail.apiForwardRetrySucceeded"));
        await loadDetail();
      } catch (error) {
        if (email.value && error.data && error.data.api_forward) {
          email.value.api_forward = error.data.api_forward;
        }
        NocMessage.error(error.message);
      } finally {
        apiForwardBusy.value = false;
      }
    }

    async function toggleReadState() {
      if (!email.value || deleteBusy.value) {
        return;
      }
      readStateBusy.value = true;
      try {
        const data = await requestJson(`/api/cutover/emails/${props.emailRecordId}/read-state`, {
          method: "PATCH",
          body: JSON.stringify({ is_read: !email.value.is_read }),
        });
        email.value.is_read = Boolean(data.is_read);
        NocMessage.success(tt("common.readStateUpdated"));
      } catch (error) {
        NocMessage.error(error.message);
      } finally {
        readStateBusy.value = false;
      }
    }

    async function deleteEmail() {
      if (!email.value || deleteBusy.value || replyBusy.value || extractionBusy.value || apiForwardBusy.value || readStateBusy.value) return;
      deleteBusy.value = true;
      try {
        if (!await confirmDeleteCutoverEmail(email.value)) return;
        NocMessage.success(tt("cutover.delete.succeeded"));
        // Replace the deleted detail in history; the destination reloads the list and summary.
        history.replaceState({
          view: "cutoverTasks",
          cutoverListState: history.state?.cutoverListState,
        }, "", VIEW_ROUTES.cutoverTasks);
        applyRoute(parseRoute());
      } catch (error) {
        NocMessage.error(error.message);
      } finally {
        deleteBusy.value = false;
      }
    }

    watch(() => props.emailRecordId, () => loadDetail());

    onMounted(async () => {
      if (appStore.apiKey) {
        await loadDetail();
        // 任务详情链接直达（generate/fill 接口 msg 中的链接带 taskId 参数）：自动展开对应任务
        const directTaskId = Number(new URLSearchParams(window.location.search).get("taskId"));
        if (directTaskId) {
          openTask(directTaskId);
        }
      }
    });

    function onIframeLoad(event) {
      const frame = event.target;
      try {
        const height = frame.contentDocument.documentElement.scrollHeight + 24;
        frame.style.height = `${Math.min(height, 640)}px`;
      } catch (error) {
        frame.style.height = "480px";
      }
    }

    // 收起状态下 iframe 高度无法测量，展开后重新计算一次
    watch(contentCollapsed, (names) => {
      if (!names.includes("content") || !email.value || !email.value.html_content) {
        return;
      }
      nextTick(() => {
        if (contentFrame.value) {
          onIframeLoad({ target: contentFrame.value });
        }
      });
    });

    // ---------- 任务展开行（单例面板，变更后仅局部更新对应行） ----------
    async function openTask(taskId, tab = 'report') {
      if (!email.value?.tasks?.some(task=>task.id===taskId)) return;
      if (detailTask.value?.id !== taskId && !(await confirmLeaveTask())) return;
      workbench.activeTab.value = tab;
      if (detailTask.value?.id === taskId) return;
      const request = ++taskRequest;
      requestedTaskId.value = taskId;
      workbench.taskLoading.value = true;
      workbench.taskError.value = '';
      try {
        const task = await requestJson(`/api/cutover/tasks/${taskId}`);
        if (request !== taskRequest) return;
        taskFormDirty.value = false;
        detailTask.value = task;
        expandedKeys.value = [taskId];
      } catch (error) {
        if (request !== taskRequest) return;
        detailTask.value = null;
        expandedKeys.value = [];
        workbench.taskError.value = error.message || tt('cw.taskLoadFailed');
        setStatus(error.message, "error");
      } finally {
        if (request === taskRequest) workbench.taskLoading.value = false;
      }
    }

    function closeTask() {
      taskRequest++;
      taskFormDirty.value = false;
      workbench.taskLoading.value = false;
      workbench.taskError.value = '';
      expandedKeys.value = [];
      detailTask.value = null;
    }

    async function confirmLeaveTask() {
      if (!taskFormDirty.value) return true;
      try {
        await NocDialog.confirm(tt('cw.discardTask'), tt('cw.fillDetails'), {
          confirmButtonText: tt('cw.discard'), cancelButtonText: tt('common.cancel'), type: 'warning',
        });
        return true;
      } catch { return false; }
    }
    async function requestCloseTask() {
      if (await confirmLeaveTask()) closeTask();
    }

    function toggleTask(task) {
      if (expandedKeys.value[0] === task.id) {
        closeTask();
      } else {
        openTask(task.id);
      }
    }

    function onExpandChange(row, expandedRows) {
      const isExpanded = expandedRows.some((item) => item.id === row.id);
      if (isExpanded) {
        openTask(row.id);
      } else if (expandedKeys.value.includes(row.id)) {
        closeTask();
      }
    }

    function onTaskChanged(task) {
      if (!email.value) {
        return;
      }
      const tasks = email.value.tasks || [];
      const index = tasks.findIndex((item) => item.id === task.id);
      if (index >= 0) {
        tasks.splice(index, 1, task);
      }
    }

    return {
      ...workbench, requestedTaskId, openTask, taskFormDirty, requestCloseTask,
      email, loading, contentCollapsed, contentFrame, expandedKeys, detailTask, canOperateMailbox,
      replyDraft, replyRecipients, replyBusy, recipientOptions, replyCcRecipients, confirmReply, cancelReply,
      apiForwardBusy, retryApiForward,
      readStateBusy, toggleReadState, deleteBusy, deleteEmail,
      extractResultBlocks, extractionDraft, extractionBusy, manualBindings, manualBindingTypes, editingLineBindings, isAutomaticLineMatch, toggleLineBindingEditor, selectCircuitCandidate, hasSavedManualBinding, matchedTypeCounts, saveExtraction, bindLine, regenerateTasks,
      loadDetail, onIframeLoad, toggleTask, closeTask, onExpandChange, onTaskChanged,
      statusTagType, statusText, mailboxLabel, completeEmail, undoEmailCompletion,
    };
  },
  template: CUTOVER_WORKBENCH_TEMPLATE,
  computed: {
    icons() {
      return ElementPlusIconsVue;
    },
    lineTypeText() {
      return lineTypeText;
    },
    taskLineCount() {
      return taskLineCount;
    },
    sceneText() {
      return sceneText;
    },
    sceneTagType() {
      return sceneTagType;
    },
    isRejectedScene() {
      return isRejectedScene;
    },
  },
});

// ==================== 线路管理 ====================
const CIRCUIT_PAGE_SIZE = 20;

const ViewCircuits = defineComponent({
  name: "ViewCircuits",
  components: { CircuitImportMenu: naive.NDropdown },
  setup() {
    const rows = ref([]);
    const total = ref(0);
    const page = ref(1);
    const loading = ref(false);
    const filters = reactive({ supplier: "", lineType: "", lineStatus: "", keyword: "" });
    const options = reactive({ suppliers: [], line_types: [], line_statuses: [] });

    async function loadCircuits() {
      loading.value = true;
      const params = new URLSearchParams();
      if (filters.supplier) params.set("supplier", filters.supplier);
      if (filters.lineType) params.set("line_type", filters.lineType);
      if (filters.lineStatus) params.set("line_status", filters.lineStatus);
      if (filters.keyword.trim()) params.set("keyword", filters.keyword.trim());
      params.set("page", String(page.value));
      params.set("page_size", String(CIRCUIT_PAGE_SIZE));
      try {
        const data = await requestJson(`/api/circuits?${params.toString()}`);
        rows.value = data.rows || [];
        total.value = data.total || 0;
        page.value = data.page || page.value;
        Object.assign(options, {
          suppliers: (data.options && data.options.suppliers) || [],
          line_types: (data.options && data.options.line_types) || [],
          line_statuses: (data.options && data.options.line_statuses) || [],
        });
      } catch (error) {
        setStatus(error.message, "error");
      } finally {
        loading.value = false;
      }
    }

    function queryCircuits() {
      page.value = 1;
      loadCircuits();
    }

    function resetFilters() {
      filters.supplier = "";
      filters.lineType = "";
      filters.lineStatus = "";
      filters.keyword = "";
      page.value = 1;
      loadCircuits();
    }

    function filtersActive() {
      return Boolean(filters.supplier || filters.lineType || filters.lineStatus || filters.keyword.trim());
    }

    function onPageChange(nextPage) {
      page.value = nextPage;
      loadCircuits();
    }

    // ---------- 新增/编辑弹窗 ----------
    const dialogVisible = ref(false);
    const saving = ref(false);
    const editingId = ref(null);
    const formRef = ref(null);
    const formAlert = ref(false);
    const form = reactive({
      supplier: "",
      supplier_circuit_id: "",
      circuit_id: "",
      line_type: "",
      line_status: "",
      remark: "",
    });
    const rules = computed(() => ({
      supplier: [{ required: true, message: tt("circuits.supplierRequired"), trigger: "blur" }],
      supplier_circuit_id: [{ required: true, message: tt("circuits.supplierCircuitIdRequired"), trigger: "blur" }],
    }));

    function openDialog(circuit = null) {
      editingId.value = circuit ? circuit.id : null;
      form.supplier = circuit ? circuit.supplier || "" : "";
      form.supplier_circuit_id = circuit ? circuit.supplier_circuit_id || "" : "";
      form.circuit_id = circuit ? circuit.circuit_id || "" : "";
      form.line_type = circuit ? circuit.line_type || "" : "";
      form.line_status = circuit ? circuit.line_status || "" : "";
      form.remark = circuit ? circuit.remark || "" : "";
      formAlert.value = false;
      dialogVisible.value = true;
      nextTick(() => formRef.value && formRef.value.clearValidate());
    }

    async function saveCircuit() {
      try {
        await formRef.value.validate();
      } catch (error) {
        formAlert.value = true;
        return;
      }
      formAlert.value = false;
      saving.value = true;
      const payload = {
        supplier: form.supplier.trim(),
        supplier_circuit_id: form.supplier_circuit_id.trim(),
        circuit_id: form.circuit_id.trim(),
        line_type: form.line_type.trim(),
        line_status: form.line_status.trim(),
        remark: form.remark.trim(),
      };
      try {
        if (editingId.value) {
          await requestJson(`/api/circuits/${editingId.value}`, {
            method: "PATCH",
            body: JSON.stringify(payload),
          });
          NocMessage.success(tt("circuits.updated"));
        } else {
          await requestJson("/api/circuits", {
            method: "POST",
            body: JSON.stringify(payload),
          });
          NocMessage.success(tt("circuits.added"));
          if (!filtersActive()) {
            // 新记录按 id 追加在末尾，无筛选时跳到最后一页使其可见
            const probe = await requestJson(`/api/circuits?page=1&page_size=${CIRCUIT_PAGE_SIZE}`);
            page.value = Math.max(Math.ceil((probe.total || 0) / CIRCUIT_PAGE_SIZE), 1);
          }
        }
        dialogVisible.value = false;
        await loadCircuits();
      } catch (error) {
        NocMessage.error(error.message);
        setStatus(error.message, "error");
      } finally {
        saving.value = false;
      }
    }

    async function deleteCircuit(circuit) {
      const label = circuit.supplier_circuit_id || circuit.circuit_id || circuit.id;
      try {
        await NocDialog.confirm(
          tt("circuits.deleteConfirm", { label }),
          tt("circuits.deleteTitle"),
          { confirmButtonText: tt("common.confirmDelete"), cancelButtonText: tt("common.cancel"), type: "warning" },
        );
      } catch {
        return;
      }
      try {
        await requestJson(`/api/circuits/${circuit.id}`, { method: "DELETE" });
        NocMessage.success(tt("circuits.deleted"));
        await loadCircuits();
      } catch (error) {
        NocMessage.error(error.message);
      }
    }

    // 建议列表（ui-autocomplete）
    function makeSuggest(source) {
      return (query, callback) => {
        const values = source().filter((value) => !query || value.toLowerCase().includes(query.toLowerCase()));
        callback(values.map((value) => ({ value })));
      };
    }
    const suggestSupplier = makeSuggest(() => options.suppliers);
    const suggestLineType = makeSuggest(() => options.line_types);
    const suggestLineStatus = makeSuggest(() => options.line_statuses);

    // ---------- 导入 ----------
    const circuitImport = useCircuitImport(async () => {
      page.value = 1;
      await loadCircuits();
    });

    function exportCircuits() {
      window.open("/api/circuits/export", "_blank");
    }

    onMounted(() => {
      if (appStore.apiKey) {
        loadCircuits();
      }
    });

    return {
      rows, total, page, loading, filters, options, CIRCUIT_PAGE_SIZE,
      queryCircuits, resetFilters, onPageChange,
      dialogVisible, saving, editingId, formRef, formAlert, form, rules,
      openDialog, saveCircuit, deleteCircuit,
      suggestSupplier, suggestLineType, suggestLineStatus,
      ...circuitImport, exportCircuits,
    };
  },
  template: `
    <div class="view-body circuits-list-view">
      <ui-card shadow="never" class="table-card circuits-list-card">
        <template #header>
          <div class="list-heading">
            <h2>{{ $t('circuits.listTitle') }}</h2>
            <span class="list-total">{{ $t('common.totalItems', { total }) }}</span>
            <div class="toolbar-actions list-actions">
              <div class="circuit-import-split">
                <ui-button :icon="icons.Upload" @click="openImportDialog('append')">{{ $t('circuits.appendImport') }}</ui-button>
                <circuit-import-menu trigger="click" :options="[{ label: $t('circuits.replaceImport'), key: 'replace' }]" @select="openImportDialog">
                  <ui-button :icon="icons.ArrowDown" :aria-label="$t('circuits.importOptions')"></ui-button>
                </circuit-import-menu>
              </div>
              <ui-button :icon="icons.Download" :loading="downloadingTemplate" @click="downloadImportTemplate">{{ $t('circuits.downloadTemplate') }}</ui-button>
              <ui-button :icon="icons.Download" @click="exportCircuits">{{ $t('common.export') }}</ui-button>
              <ui-button type="primary" :icon="icons.Plus" @click="openDialog()">{{ $t('circuits.add') }}</ui-button>
            </div>
          </div>
          <form class="filter-bar circuits-filters" @submit.prevent="queryCircuits">
            <ui-input v-model="filters.keyword" :placeholder="$t('circuits.keywordPlaceholder')" :aria-label="$t('circuits.keywordPlaceholder')" clearable></ui-input>
            <ui-select v-model="filters.supplier" :placeholder="$t('circuits.allSuppliers')" :aria-label="$t('common.supplier')" clearable filterable>
              <ui-option v-for="value in options.suppliers" :key="value" :label="value" :value="value"></ui-option>
            </ui-select>
            <ui-select v-model="filters.lineType" :placeholder="$t('circuits.allTypes')" :aria-label="$t('circuits.lineType')" clearable filterable>
              <ui-option v-for="value in options.line_types" :key="value" :label="value" :value="value"></ui-option>
            </ui-select>
            <ui-select v-model="filters.lineStatus" :placeholder="$t('circuits.allStatuses')" :aria-label="$t('circuits.lineStatus')" clearable filterable>
              <ui-option v-for="value in options.line_statuses" :key="value" :label="value" :value="value"></ui-option>
            </ui-select>
            <ui-button type="primary" native-type="submit" :loading="loading">{{ $t('common.query') }}</ui-button>
            <ui-button @click="resetFilters">{{ $t('common.reset') }}</ui-button>
          </form>
        </template>
        <ui-table v-loading="loading" :data="rows" :empty-text="$t('circuits.empty')" height="100%" class="circuits-table">
          <ui-table-column :label="$t('common.supplier')" width="104">
            <template #default="{ row }">
              <span class="cell-main">{{ row.supplier || '-' }}</span>
            </template>
          </ui-table-column>
          <ui-table-column label="Supplier Circuit ID" width="148">
            <template #default="{ row }">
              <ui-tooltip v-if="row.supplier_circuit_id" :trigger="['hover', 'focus']" :show-after="300" placement="top-start" popper-class="cell-preview-tooltip" :content="row.supplier_circuit_id">
                <span class="cell-preview mono" tabindex="0">{{ row.supplier_circuit_id }}</span>
              </ui-tooltip>
              <span v-else class="muted">—</span>
            </template>
          </ui-table-column>
          <ui-table-column label="Circuit ID" min-width="200">
            <template #default="{ row }">
              <ui-tooltip v-if="row.circuit_id" :trigger="['hover', 'focus']" :show-after="300" placement="top-start" popper-class="cell-preview-tooltip" :content="row.circuit_id">
                <span class="cell-preview mono" tabindex="0">{{ row.circuit_id }}</span>
              </ui-tooltip>
              <span v-else class="muted">—</span>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('circuits.lineType')" width="88">
            <template #default="{ row }">
              <span>{{ row.line_type || '-' }}</span>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('circuits.lineStatus')" width="84">
            <template #default="{ row }">
              <span>{{ row.line_status || '-' }}</span>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('common.remark')" min-width="180">
            <template #default="{ row }">
              <ui-tooltip v-if="row.remark" :trigger="['hover', 'focus']" :show-after="300" placement="top-start" popper-class="cell-preview-tooltip" :content="row.remark">
                <span class="cell-preview muted" tabindex="0">{{ row.remark }}</span>
              </ui-tooltip>
              <span v-else class="muted">—</span>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('common.actions')" width="112" align="center" fixed="right">
            <template #default="{ row }">
              <div class="row-actions">
                <ui-action type="primary" @click="openDialog(row)" icon="Edit" :label="$t('common.edit')"></ui-action>
                <ui-action type="danger" @click="deleteCircuit(row)" icon="Delete" :label="$t('common.delete')"></ui-action>
              </div>
            </template>
          </ui-table-column>
        </ui-table>
        <div class="pagination-bar">
          <span class="muted">{{ $t('common.totalItems', { total }) }}</span>
          <ui-pagination layout="prev, pager, next" :total="total" :page-size="CIRCUIT_PAGE_SIZE"
                         :current-page="page" @current-change="onPageChange"></ui-pagination>
        </div>
      </ui-card>

      <!-- 新增/编辑弹窗 -->
      <ui-dialog v-model="dialogVisible" :title="editingId ? $t('circuits.dialogEdit') : $t('circuits.dialogAdd')"
                 width="640px" :close-on-click-modal="false" destroy-on-close>
        <ui-alert v-if="formAlert" type="error" :closable="false"
                  :title="$t('circuits.formAlert')" class="form-alert"></ui-alert>
        <ui-form ref="formRef" :model="form" :rules="rules" label-position="top">
          <ui-form-item label="Supplier" prop="supplier">
            <ui-autocomplete v-model="form.supplier" :fetch-suggestions="suggestSupplier"
                             :placeholder="$t('circuits.supplierPlaceholder')" clearable style="width: 100%"></ui-autocomplete>
          </ui-form-item>
          <div class="field-grid-2">
            <ui-form-item :label="$t('circuits.lineType')">
              <ui-autocomplete v-model="form.line_type" :fetch-suggestions="suggestLineType"
                               :placeholder="$t('circuits.typePlaceholder')" clearable style="width: 100%"></ui-autocomplete>
            </ui-form-item>
            <ui-form-item :label="$t('circuits.lineStatus')">
              <ui-autocomplete v-model="form.line_status" :fetch-suggestions="suggestLineStatus"
                               :placeholder="$t('circuits.statusPlaceholder')" clearable style="width: 100%"></ui-autocomplete>
            </ui-form-item>
          </div>
          <ui-form-item label="Supplier Circuit ID" prop="supplier_circuit_id">
            <ui-input v-model="form.supplier_circuit_id" type="textarea" :rows="3" class="mono-input"
                      :placeholder="$t('circuits.supplierCircuitIdPlaceholder')"></ui-input>
            <div class="field-hint">{{ $t('circuits.supplierCircuitIdHint') }}</div>
          </ui-form-item>
          <ui-form-item label="Circuit ID">
            <ui-input v-model="form.circuit_id" type="textarea" :rows="4" class="mono-input"
                      :placeholder="$t('circuits.circuitIdPlaceholder')"></ui-input>
            <div class="field-hint">{{ $t('circuits.circuitIdHint') }}</div>
          </ui-form-item>
          <ui-form-item :label="$t('common.remark')">
            <ui-input v-model="form.remark" type="textarea" :rows="2"
                      :placeholder="$t('circuits.remarkPlaceholder')"></ui-input>
          </ui-form-item>
        </ui-form>
        <template #footer>
          <ui-button @click="dialogVisible = false">{{ $t('common.cancel') }}</ui-button>
          <ui-button type="primary" :loading="saving" @click="saveCircuit">{{ $t('circuits.saveCircuit') }}</ui-button>
        </template>
      </ui-dialog>

      <!-- 导入弹窗 -->
      <ui-dialog v-model="importDialogVisible" :title="$t(importMode === 'append' ? 'circuits.appendTitle' : 'circuits.importTitle')" width="1000px"
                 class="circuits-import-dialog" :close-on-click-modal="false" :closable="!importBusy" :close-on-esc="!importBusy" destroy-on-close>
        <ol class="circuit-import-steps" :aria-label="$t('circuits.importProgress')">
          <li v-for="(label, index) in ['uploadStep', 'previewStep', 'resultStep']" :key="label" :class="{ active: importStep === index + 1 }" :aria-current="importStep === index + 1 ? 'step' : undefined">
            <span>{{ index + 1 }}</span>{{ $t('circuits.' + label) }}
          </li>
        </ol>
        <div v-if="!importResult" class="import-hint-panel">
          <div class="circuit-import-template-row">
            <p class="import-hint-text">{{ $t('circuits.importHint') }}</p>
            <ui-button text type="primary" :loading="downloadingTemplate" @click="downloadImportTemplate">{{ $t('circuits.downloadTemplate') }}</ui-button>
          </div>
          <ui-alert :type="importMode === 'append' ? 'info' : 'warning'" :closable="false" show-icon
                    :title="$t(importMode === 'append' ? 'circuits.appendHint' : 'circuits.importReplaceAlert')"></ui-alert>
        </div>
        <template v-if="!importResult">
          <ui-upload class="import-upload" :class="{ 'is-previewed': importPreview }" drag :auto-upload="false" :limit="1" accept=".xlsx" :disabled="importBusy"
                     :file-list="importFileList" :on-change="onImportFileChange"
                     :on-remove="onImportFileRemove" :on-exceed="onImportFileExceed">
            <template v-if="!importPreview">
              <ui-icon class="import-upload-icon"><UploadFilled /></ui-icon>
              <p class="import-upload-text">{{ $t('circuits.uploadText') }}</p>
              <p class="import-upload-sub">{{ $t('circuits.importFileLimit') }}</p>
            </template>
            <p v-else class="import-upload-text">{{ $t('circuits.changeFile') }}</p>
          </ui-upload>
          <div v-if="!importPreview" class="import-actions">
            <ui-button type="primary" :icon="icons.View" :loading="parsing" :disabled="!importFile || importBusy" @click="parseImport">{{ $t('circuits.parsePreview') }}</ui-button>
          </div>
        </template>
        <div v-if="!importData" class="import-empty">
          <p>{{ importFile ? $t('circuits.notParsed') : $t('circuits.noFile') }}</p>
          <span>{{ importFile ? $t('circuits.notParsedHint') : $t('circuits.noFileHint') }}</span>
        </div>
        <template v-else>
          <ui-alert v-if="importResult" type="success" :closable="false" show-icon
                    :title="$t('circuits.appendSuccess', { inserted: importResult.inserted, skipped: importResult.counts.skipped })"></ui-alert>
          <div class="import-summary" aria-live="polite">
            <div class="import-summary-item"><span class="import-summary-value">{{ importData.total }}</span><span class="import-summary-label">{{ $t('circuits.summaryTotal') }}</span></div>
            <template v-if="importMode === 'append'">
              <div class="import-summary-item"><span class="import-summary-value">{{ importData.counts.new }}</span><span class="import-summary-label">{{ $t(importResult ? 'circuits.insertedCount' : 'circuits.newCount') }}</span></div>
              <div class="import-summary-item"><span class="import-summary-value">{{ importData.counts.skipped }}</span><span class="import-summary-label">{{ $t('circuits.skippedCount') }}</span></div>
              <div class="import-summary-item"><span class="import-summary-value">{{ importData.counts.errors }}</span><span class="import-summary-label">{{ $t('circuits.errorCount') }}</span></div>
              <div class="import-summary-item"><span class="import-summary-value">{{ importData.counts.review }}</span><span class="import-summary-label">{{ $t('circuits.reviewCount') }}</span></div>
            </template>
          </div>
          <ui-alert v-if="importMode === 'append' && importData.counts.errors" type="error" :closable="false" show-icon :title="$t('circuits.errorsBlockImport')"></ui-alert>
          <ui-alert v-else-if="importMode === 'append' && !importData.counts.new && !importResult" type="info" :closable="false" :title="$t('circuits.noNewRows')"></ui-alert>
          <div v-if="(importData.warnings || []).length" class="import-warnings">
            <p v-for="(warning, index) in importData.warnings" :key="index" class="warn-text">{{ warning }}</p>
          </div>
          <div v-if="importMode === 'append'" class="circuit-import-filters">
            <ui-select v-model="importFilter" :aria-label="$t('circuits.resultFilter')">
              <ui-option v-for="key in ['all', 'new', 'skipped', 'error', 'review']" :key="key" :value="key" :label="$t('circuits.filter_' + key)"></ui-option>
            </ui-select>
            <span class="muted">{{ $t('circuits.previewRowsHint', { total: importFilteredRows.length }) }}</span>
          </div>
          <ui-table :data="importVisibleRows" size="small" max-height="360" :row-key="importMode === 'append' ? 'row_number' : undefined">
            <ui-table-column v-if="importMode === 'append'" prop="row_number" :label="$t('circuits.sourceRow')" width="64"></ui-table-column>
            <ui-table-column prop="supplier" label="Supplier" width="88"></ui-table-column>
            <ui-table-column label="Supplier Circuit ID" min-width="150"><template #default="{ row }"><span class="mono pre-wrap">{{ row.supplier_circuit_id || '—' }}</span></template></ui-table-column>
            <ui-table-column label="Circuit ID" min-width="150"><template #default="{ row }"><span class="mono pre-wrap">{{ row.circuit_id || '—' }}</span></template></ui-table-column>
            <ui-table-column :label="$t('circuits.lineType')" width="80" prop="line_type"></ui-table-column>
            <ui-table-column :label="$t('circuits.lineStatus')" width="88" prop="line_status"></ui-table-column>
            <ui-table-column v-if="importMode === 'append'" :label="$t('circuits.rowResult')" width="102">
              <template #default="{ row }"><ui-tag :type="importStatusType(row)">{{ $t('circuits.status_' + row.status) }}</ui-tag></template>
            </ui-table-column>
            <ui-table-column v-if="importMode === 'append'" :label="$t('circuits.rowReason')" min-width="210">
              <template #default="{ row }"><span class="pre-wrap">{{ row.reason || '—' }}</span></template>
            </ui-table-column>
            <ui-table-column :label="$t('common.remark')" min-width="140"><template #default="{ row }"><span class="muted pre-wrap">{{ row.remark || '—' }}</span></template></ui-table-column>
          </ui-table>
          <div v-if="importFilteredRows.length > 50" class="pagination-bar">
            <ui-pagination v-model:current-page="importPage" :page-size="50" :total="importFilteredRows.length" layout="prev, pager, next"></ui-pagination>
          </div>
        </template>
        <template #footer>
          <ui-button :disabled="importBusy" @click="importDialogVisible = false">{{ $t(importResult ? 'common.close' : 'common.cancel') }}</ui-button>
          <ui-button v-if="importResult" type="primary" :icon="icons.Download" @click="downloadImportResult">{{ $t('circuits.downloadResult') }}</ui-button>
          <ui-button v-else :type="importMode === 'append' ? 'primary' : 'danger'" :loading="importing" :disabled="!canConfirmImport" @click="confirmImport">
            {{ importMode === 'append' ? $t('circuits.confirmAppend', { total: importPreview?.counts?.new || 0 }) : $t('circuits.confirmImport') }}
          </ui-button>
        </template>
      </ui-dialog>
    </div>
  `,
  computed: {
    icons() {
      return ElementPlusIconsVue;
    },
  },
});

const ViewDispatchSession = defineComponent({
  name: "ViewDispatchSession",
  setup() {
    let disposed = false;
    let statusRequest = 0;
    const checking = ref(false);
    const action = ref("");
    const environment = ref(appStore.portalEnvironment || "");
    const mode = ref("password");
    const smsRequested = ref(false);
    const status = reactive({
      state: "checking",
      authenticated: false,
      checked_at: "",
      message: tt("dispatchSession.checkingMessage"),
      configured: true,
      password_login_url: "",
      mobile_login_url: "",
      state_path: "",
    });
    const attempt = reactive({
      attempt_id: "",
      captcha_data_url: "",
      expires_at: "",
    });
    const form = reactive({
      account: "",
      password: "",
      captcha: "",
      sms_code: "",
    });

    const statusTitle = computed(() => {
      const key = `dispatchSession.state.${status.state}`;
      return hasI18nKey(key) ? tt(key) : tt("dispatchSession.state.unavailable");
    });
    const statusTone = computed(() => {
      if (status.state === "authenticated") return "is-authenticated";
      if (status.state === "unavailable") return "is-unavailable";
      if (status.state === "checking") return "is-checking";
      return "is-login-required";
    });
    const statusIcon = computed(() => {
      if (status.state === "authenticated") return ElementPlusIconsVue.CircleCheckFilled;
      if (status.state === "unavailable") return ElementPlusIconsVue.CircleCloseFilled;
      if (status.state === "checking") return ElementPlusIconsVue.Loading;
      return ElementPlusIconsVue.WarningFilled;
    });
    const modeLabel = computed(() => tt(`dispatchSession.mode.${mode.value}`));
    const environmentLabel = computed(() => environment.value
      ? tt(`dispatchSession.environment.${environment.value}`)
      : tt("common.unset"));
    const loginUrl = computed(() => (
      mode.value === "password"
        ? status.password_login_url
        : status.mobile_login_url
    ) || tt("dispatchSession.notConfigured"));
    const lastChecked = computed(() => status.checked_at
      ? String(status.checked_at).replace("T", " ").slice(0, 19)
      : tt("common.unset"));
    const attemptExpires = computed(() => attempt.expires_at
      ? String(attempt.expires_at).replace("T", " ").slice(0, 19)
      : tt("common.unset"));
    const canSubmit = computed(() => Boolean(
      attempt.attempt_id
      && form.account.trim()
      && form.password
      && form.captcha.trim()
      && (mode.value === "password" || (smsRequested.value && form.sms_code.trim()))
    ));

    function statusResponseGuard() {
      const requestId = ++statusRequest;
      const authVersion = appStore.authVersion;
      const requestedEnvironment = environment.value;
      return () => !disposed && requestId === statusRequest && authVersion === appStore.authVersion
        && requestedEnvironment === environment.value && requestedEnvironment === appStore.portalEnvironment;
    }

    function assignStatus(data) {
      if (data.environment && data.environment !== environment.value) return false;
      status.state = data.state || "login_required";
      status.authenticated = Boolean(data.authenticated);
      status.checked_at = data.checked_at || "";
      status.message = data.message || "";
      status.configured = data.configured !== false;
      status.password_login_url = data.password_login_url || "";
      status.mobile_login_url = data.mobile_login_url || "";
      status.state_path = data.state_path || "";
      // A completed login/check supersedes any earlier header status request.
      portalStatusRequest += 1;
      appStore.portalStatus = data;
      return true;
    }

    function resetAttempt() {
      attempt.attempt_id = "";
      attempt.captcha_data_url = "";
      attempt.expires_at = "";
      smsRequested.value = false;
      form.captcha = "";
      form.sms_code = "";
    }

    function clearSensitiveForm() {
      form.account = "";
      form.password = "";
      form.captcha = "";
      form.sms_code = "";
      resetAttempt();
    }

    function showError(error) {
      NocMessage.error(error.message || tt("common.requestFailed"));
      setStatus(error.message || tt("common.requestFailed"), "error");
    }

    async function beginAttempt() {
      if (checking.value || action.value || disposed) return;
      action.value = "begin";
      resetAttempt();
      try {
        const data = await requestJson("/api/rpa/session/attempts", {
          method: "POST",
          body: JSON.stringify({
            mode: mode.value,
            environment: environment.value || undefined,
          }),
        });
        Object.assign(attempt, data);
      } catch (error) {
        showError(error);
      } finally {
        action.value = "";
      }
    }

    async function loadStatus(startLoginWhenRequired = false) {
      if (checking.value || action.value || disposed) return;
      const isCurrent = statusResponseGuard();
      checking.value = true;
      status.state = "checking";
      status.message = tt("dispatchSession.checkingMessage");
      try {
        const data = await getPortalSessionStatus(environment.value);
        if (!isCurrent() || !assignStatus(data)) return;
        checking.value = false;
        if (startLoginWhenRequired && !status.authenticated && status.configured) {
          await beginAttempt();
        }
      } catch (error) {
        if (!isCurrent()) return;
        status.state = "unavailable";
        status.authenticated = false;
        status.message = error.message || tt("common.requestFailed");
        showError(error);
      } finally {
        if (isCurrent()) checking.value = false;
      }
    }

    async function refreshCaptcha() {
      if (checking.value || action.value || disposed) return;
      if (!attempt.attempt_id) {
        await beginAttempt();
        return;
      }
      action.value = "captcha";
      try {
        const data = await requestJson(
          `/api/rpa/session/attempts/${attempt.attempt_id}/captcha`,
          { method: "POST" },
        );
        Object.assign(attempt, data);
        form.captcha = "";
      } catch (error) {
        showError(error);
      } finally {
        action.value = "";
      }
    }

    async function changeMode(value) {
      if (checking.value || action.value || mode.value === value) return;
      mode.value = value;
      clearSensitiveForm();
      if (status.configured) {
        await beginAttempt();
      }
    }

    async function changeEnvironment(value) {
      if (checking.value || action.value || environment.value === value) return;
      environment.value = value;
      persistPortalEnvironment(value);
      clearSensitiveForm();
      await loadStatus(true);
    }

    function requireBaseFields() {
      if (!form.account.trim() || !form.password || !form.captcha.trim()) {
        NocMessage.warning(tt("dispatchSession.completeFields"));
        return false;
      }
      return true;
    }

    async function requestSmsCode() {
      if (checking.value || action.value || disposed) return;
      if (!attempt.attempt_id || !requireBaseFields()) return;
      action.value = "sms";
      try {
        await requestJson(`/api/rpa/session/attempts/${attempt.attempt_id}/sms`, {
          method: "POST",
          body: JSON.stringify({
            phone: form.account.trim(),
            password: form.password,
            captcha: form.captcha.trim(),
          }),
        });
        smsRequested.value = true;
        NocMessage.success(tt("dispatchSession.smsSent"));
      } catch (error) {
        showError(error);
      } finally {
        action.value = "";
      }
    }

    async function submitLogin() {
      if (checking.value || action.value || disposed) return;
      if (!canSubmit.value) {
        NocMessage.warning(tt("dispatchSession.completeFields"));
        return;
      }
      action.value = "login";
      const isCurrent = statusResponseGuard();
      try {
        const path = mode.value === "password"
          ? `/api/rpa/session/attempts/${attempt.attempt_id}/password`
          : `/api/rpa/session/attempts/${attempt.attempt_id}/sms/verify`;
        const body = mode.value === "password"
          ? {
              username: form.account.trim(),
              password: form.password,
              captcha: form.captcha.trim(),
            }
          : { sms_code: form.sms_code.trim() };
        const data = await requestJson(path, {
          method: "POST",
          body: JSON.stringify(body),
        });
        if (!isCurrent() || !assignStatus(data)) return;
        clearSensitiveForm();
        NocMessage.success(tt("dispatchSession.loginSuccess"));
        setStatusKey("dispatchSession.loginSuccess");
      } catch (error) {
        if (!isCurrent()) return;
        showError(error);
        if (error.code === "LOGIN_FAILED") {
          action.value = "";
          await refreshCaptcha();
        }
      } finally {
        if (isCurrent()) {
          action.value = "";
          checking.value = false;
        }
      }
    }

    onMounted(() => loadStatus(true));
    onUnmounted(() => { disposed = true; });

    return {
      checking, action, environment, mode, smsRequested, status, attempt, form,
      statusTitle, statusTone, statusIcon, environmentLabel, modeLabel, loginUrl,
      lastChecked, attemptExpires, canSubmit,
      loadStatus, beginAttempt, refreshCaptcha, changeEnvironment, changeMode,
      requestSmsCode, submitLogin, clearSensitiveForm,
    };
  },
  template: `
    <div class="view-body dispatch-session-view">
      <section class="dispatch-status-panel" :class="statusTone" aria-live="polite">
        <div class="dispatch-status-icon">
          <ui-icon :class="{ 'is-spinning': checking }"><component :is="statusIcon" /></ui-icon>
        </div>
        <div class="dispatch-status-copy">
          <span class="dispatch-status-environment">{{ environmentLabel }}</span>
          <h4>{{ statusTitle }}</h4>
          <p>{{ status.message }}</p>
        </div>
        <div class="dispatch-status-actions">
          <ui-button :loading="checking" :disabled="action !== ''" @click="loadStatus(false)">
            <ui-icon><Refresh /></ui-icon>{{ $t('dispatchSession.checkNow') }}
          </ui-button>
          <ui-button type="primary" :loading="action === 'begin'" :disabled="!status.configured || checking || action !== ''" @click="beginAttempt">
            <ui-icon><Key /></ui-icon>{{ $t('dispatchSession.relogin') }}
          </ui-button>
        </div>
      </section>

      <div class="dispatch-session-grid">
        <section class="dispatch-session-panel dispatch-login-panel">
          <header class="dispatch-panel-head">
            <div>
              <h4>{{ $t('dispatchSession.loginMethod') }}</h4>
              <p>{{ $t('dispatchSession.loginMethodHint') }}</p>
            </div>
          </header>

          <div class="dispatch-environment-section">
            <div class="dispatch-section-label">
              <strong>{{ $t('dispatchSession.environmentTitle') }}</strong>
              <span>{{ $t('dispatchSession.environmentHint') }}</span>
            </div>
            <ui-select class="dispatch-environment-select" :model-value="environment"
                       :aria-label="$t('dispatchSession.environmentTitle')"
                       :disabled="checking || action !== ''" @change="changeEnvironment">
              <ui-option :label="$t('dispatchSession.environment.test')" value="test"></ui-option>
              <ui-option :label="$t('dispatchSession.environment.production')" value="production"></ui-option>
            </ui-select>
          </div>

          <div class="dispatch-mode-switch" role="radiogroup" :aria-label="$t('dispatchSession.loginMethod')">
            <button type="button" :class="{ 'is-active': mode === 'password' }"
                    role="radio" :aria-checked="mode === 'password'" :disabled="!status.configured || checking || action !== ''" @click="changeMode('password')">
              <strong>{{ $t('dispatchSession.mode.password') }}</strong>
              <span>{{ $t('dispatchSession.mode.passwordHint') }}</span>
            </button>
            <button type="button" :class="{ 'is-active': mode === 'mobile' }"
                    role="radio" :aria-checked="mode === 'mobile'" :disabled="!status.configured || checking || action !== ''" @click="changeMode('mobile')">
              <strong>{{ $t('dispatchSession.mode.mobile') }}</strong>
              <span>{{ $t('dispatchSession.mode.mobileHint') }}</span>
            </button>
          </div>

          <dl class="dispatch-login-meta">
            <dt>{{ $t('dispatchSession.loginUrl') }}</dt><dd>{{ loginUrl }}</dd>
            <dt>{{ $t('dispatchSession.credentialHandling') }}</dt><dd>{{ $t('dispatchSession.credentialHint') }}</dd>
          </dl>

          <form class="dispatch-login-form" :class="{ 'is-password': mode === 'password' }" @submit.prevent="submitLogin">
            <div class="dispatch-form-head">
              <h5>{{ $t('dispatchSession.formTitle') }}</h5>
              <span>{{ $t('dispatchSession.formHint') }}</span>
            </div>
            <div class="dispatch-field-grid">
              <label class="dispatch-field">
                <span>{{ mode === 'password' ? $t('dispatchSession.username') : $t('dispatchSession.phone') }}</span>
                <ui-input v-model="form.account" :placeholder="mode === 'password' ? $t('dispatchSession.usernamePlaceholder') : $t('dispatchSession.phonePlaceholder')"
                          :autocomplete="mode === 'password' ? 'username' : 'tel'" clearable></ui-input>
              </label>
              <label class="dispatch-field">
                <span>{{ $t('dispatchSession.password') }}</span>
                <ui-input v-model="form.password" type="password" show-password autocomplete="current-password"
                          :placeholder="$t('dispatchSession.passwordPlaceholder')"></ui-input>
              </label>
              <label class="dispatch-field dispatch-field--captcha">
                <span>{{ $t('dispatchSession.captcha') }}</span>
                <div class="dispatch-inline-field">
                  <ui-input v-model="form.captcha" autocomplete="off" :placeholder="$t('dispatchSession.captchaPlaceholder')"></ui-input>
                  <button class="dispatch-captcha-button" type="button" :disabled="!status.configured || checking || action !== ''" @click="refreshCaptcha">
                    <img v-if="attempt.captcha_data_url" :src="attempt.captcha_data_url" width="144" height="44"
                         :alt="$t('dispatchSession.captchaAlt')">
                    <span v-else>{{ $t('dispatchSession.loadCaptcha') }}</span>
                  </button>
                </div>
              </label>
              <label v-if="mode === 'mobile'" class="dispatch-field">
                <span>{{ $t('dispatchSession.smsCode') }}</span>
                <div class="dispatch-inline-field">
                  <ui-input v-model="form.sms_code" autocomplete="one-time-code" :disabled="!smsRequested"
                            :placeholder="$t('dispatchSession.smsPlaceholder')"></ui-input>
                  <ui-button class="dispatch-sms-button" type="primary" plain :loading="action === 'sms'" :disabled="checking || action !== ''" @click="requestSmsCode">
                    {{ smsRequested ? $t('dispatchSession.resendSms') : $t('dispatchSession.sendSms') }}
                  </ui-button>
                </div>
              </label>
            </div>
            <p class="dispatch-form-note">{{ $t('dispatchSession.captchaHint') }}</p>
            <div class="dispatch-form-actions">
              <ui-button :disabled="checking || action !== ''" @click="clearSensitiveForm">{{ $t('dispatchSession.clear') }}</ui-button>
              <ui-button type="primary" native-type="submit" :loading="action === 'login'" :disabled="!canSubmit || checking || action !== ''">
                {{ $t('dispatchSession.loginSubmit') }}
              </ui-button>
            </div>
          </form>
        </section>

        <aside class="dispatch-session-panel dispatch-session-info">
          <header class="dispatch-panel-head">
            <div><h4>{{ $t('dispatchSession.sessionInfo') }}</h4><p>{{ $t('dispatchSession.sessionInfoHint') }}</p></div>
          </header>
          <dl>
            <div><dt>{{ $t('dispatchSession.currentState') }}</dt><dd :class="{ 'is-valid': status.authenticated }">{{ statusTitle }}</dd></div>
            <div><dt>{{ $t('dispatchSession.currentEnvironment') }}</dt><dd>{{ environmentLabel }}</dd></div>
            <div><dt>{{ $t('dispatchSession.currentMode') }}</dt><dd>{{ modeLabel }}</dd></div>
            <div><dt>{{ $t('dispatchSession.lastChecked') }}</dt><dd>{{ lastChecked }}</dd></div>
            <div><dt>{{ $t('dispatchSession.attemptExpires') }}</dt><dd>{{ attemptExpires }}</dd></div>
            <div><dt>{{ $t('dispatchSession.sessionStorage') }}</dt><dd class="dispatch-mono">{{ status.state_path || $t('common.unset') }}</dd></div>
          </dl>
        </aside>
      </div>
    </div>
  `,
});

// ==================== 系统配置 ====================
const ViewSettings = defineComponent({
  name: "ViewSettings",
  setup() {
    const loading = ref(false);
    const saving = ref(false);
    const guardStart = ref("");
    const guardEnd = ref("");
    const nocPhone = ref("");
    const provinceReviewerName = ref("");
    const provinceReviewerPhone = ref("");

    async function loadSettings() {
      loading.value = true;
      try {
        const data = await requestJson("/api/system/settings");
        guardStart.value = data.guard_start_time || "";
        guardEnd.value = data.guard_end_time || "";
        nocPhone.value = data.backbone_noc_phone || "";
        provinceReviewerName.value = data.backbone_province_reviewer_name || "";
        provinceReviewerPhone.value = data.backbone_province_reviewer_phone || "";
        setStatusKey("settings.loaded");
      } catch (error) {
        setStatus(error.message, "error");
      } finally {
        loading.value = false;
      }
    }

    async function saveSettings() {
      if (!nocPhone.value.trim() || !provinceReviewerName.value.trim() || !provinceReviewerPhone.value.trim()) {
        NocMessage.warning(tt("settings.backbonePersonnelRequired"));
        return;
      }
      saving.value = true;
      try {
        const data = await requestJson("/api/system/settings", {
          method: "PUT",
          body: JSON.stringify({
            guard_start_time: guardStart.value || null,
            guard_end_time: guardEnd.value || null,
            backbone_noc_phone: nocPhone.value.trim(),
            backbone_province_reviewer_name: provinceReviewerName.value.trim(),
            backbone_province_reviewer_phone: provinceReviewerPhone.value.trim(),
          }),
        });
        guardStart.value = data.guard_start_time || "";
        guardEnd.value = data.guard_end_time || "";
        nocPhone.value = data.backbone_noc_phone || "";
        provinceReviewerName.value = data.backbone_province_reviewer_name || "";
        provinceReviewerPhone.value = data.backbone_province_reviewer_phone || "";
        NocMessage.success(tt("settings.saved"));
        setStatusKey("settings.saved");
      } catch (error) {
        NocMessage.error(error.message);
        setStatus(error.message, "error");
      } finally {
        saving.value = false;
      }
    }

    onMounted(() => {
      if (appStore.apiKey) {
        loadSettings();
      }
    });

    // 界面语言：选项名固定为各语言自称，不随当前语言翻译
    const currentLang = computed(() => i18n.global.locale.value);
    const langOptions = [
      { value: "zh-CN", label: "简体中文" },
      { value: "en", label: "English" },
      { value: "zh-HK", label: "繁體中文（香港）" },
    ];
    function changeLang(value) {
      setLocale(value);
    }

    return {
      loading,
      saving,
      guardStart,
      guardEnd,
      nocPhone,
      provinceReviewerName,
      provinceReviewerPhone,
      loadSettings,
      saveSettings,
      currentLang,
      langOptions,
      changeLang,
    };
  },
  template: `
    <div class="view-body settings-view" v-loading="loading">
      <discovery-settings></discovery-settings>
      <div class="block-section">
        <div class="block-head">
          <span>{{ $t('settings.guardTitle') }}</span>
        </div>
        <p class="field-hint">{{ $t('settings.guardHint') }}</p>
        <ui-form label-position="top">
          <ui-form-item :label="$t('settings.guardStart')">
            <ui-date-picker v-model="guardStart" type="datetime" format="YYYY-MM-DD HH:mm:ss"
                            value-format="YYYY-MM-DD HH:mm:ss" :placeholder="$t('settings.guardStartPlaceholder')"
                            clearable class="settings-field"></ui-date-picker>
          </ui-form-item>
          <ui-form-item :label="$t('settings.guardEnd')">
            <ui-date-picker v-model="guardEnd" type="datetime" format="YYYY-MM-DD HH:mm:ss"
                            value-format="YYYY-MM-DD HH:mm:ss" :placeholder="$t('settings.guardEndPlaceholder')"
                            clearable class="settings-field"></ui-date-picker>
          </ui-form-item>
          <div class="settings-actions">
            <ui-button type="primary" :loading="saving" @click="saveSettings">{{ $t('common.save') }}</ui-button>
          </div>
        </ui-form>
      </div>

      <div class="block-section">
        <div class="block-head">
          <span>{{ $t('settings.backbonePersonnelTitle') }}</span>
        </div>
        <p class="field-hint">{{ $t('settings.backbonePersonnelHint') }}</p>
        <ui-form label-position="top">
          <ui-form-item :label="$t('settings.nocPhone')">
            <ui-input v-model="nocPhone" :placeholder="$t('settings.nocPhonePlaceholder')"
                      class="settings-field"></ui-input>
          </ui-form-item>
          <ui-form-item :label="$t('settings.provinceReviewerName')">
            <ui-input v-model="provinceReviewerName" :placeholder="$t('settings.provinceReviewerNamePlaceholder')"
                      class="settings-field"></ui-input>
          </ui-form-item>
          <ui-form-item :label="$t('settings.provinceReviewerPhone')">
            <ui-input v-model="provinceReviewerPhone" :placeholder="$t('settings.provinceReviewerPhonePlaceholder')"
                      class="settings-field"></ui-input>
          </ui-form-item>
          <div class="settings-actions">
            <ui-button type="primary" :loading="saving" @click="saveSettings">{{ $t('common.save') }}</ui-button>
          </div>
        </ui-form>
      </div>

      <div class="block-section settings-language">
        <div class="block-head">
          <span>{{ $t('settings.languageTitle') }}</span>
        </div>
        <p class="field-hint">{{ $t('settings.languageHint') }}</p>
        <ui-form label-position="top">
          <ui-form-item :label="$t('settings.languageLabel')">
            <ui-select :model-value="currentLang" @change="changeLang" class="settings-field">
              <ui-option v-for="option in langOptions" :key="option.value"
                         :label="option.label" :value="option.value"></ui-option>
            </ui-select>
          </ui-form-item>
        </ui-form>
      </div>
    </div>
  `,
});

// ==================== 邮箱账号配置 ====================
const ViewMailAccounts = defineComponent({
  name: "ViewMailAccounts",
  setup() {
    const loading = ref(false);
    const rows = ref([]);
    const dialogVisible = ref(false);
    const saving = ref(false);
    const editingId = ref(null);
    const formRef = ref(null);
    const formAlert = ref(false);
    const testingId = ref(null);
    const togglingId = ref(null);
    const previewing = ref(false);
    // 监听状态：{[accountId]: {running, error, last_email_at}}
    const statusMap = ref({});
    let statusTimer = null;

    const form = reactive({
      name: "",
      email_address: "",
      email_password: "",
      imap_server: "",
      imap_port: 993,
      imap_use_ssl: true,
      smtp_server: "",
      smtp_port: 465,
      smtp_use_ssl: true,
      smtp_use_tls: false,
    });

    const rules = computed(() => ({
      name: [{ required: true, message: tt("mailAccounts.nameRequired"), trigger: "blur" }],
      email_address: [{ required: true, message: tt("mailAccounts.addressRequired"), trigger: "blur" }],
      email_password: editingId.value
        ? []
        : [{ required: true, message: tt("mailAccounts.passwordRequired"), trigger: "blur" }],
      imap_server: [{ required: true, message: tt("mailAccounts.imapServerRequired"), trigger: "blur" }],
    }));

    async function loadAccounts() {
      loading.value = true;
      try {
        const data = await requestJson("/api/system/mail-accounts");
        rows.value = Array.isArray(data) ? data : [];
        // 同步刷新其它页面共用的邮箱选项缓存（筛选下拉/接收邮箱列）
        loadMailAccountOptions(true);
        // 账号变更后立即刷新监听状态，不等下一轮轮询
        loadStatus();
        setStatusKey("mailAccounts.loaded");
      } catch (error) {
        setStatus(error.message, "error");
      } finally {
        loading.value = false;
      }
    }

    async function loadStatus() {
      try {
        const data = await requestJson("/api/system/mail-accounts/status");
        statusMap.value = data && typeof data === "object" ? data : {};
      } catch (error) {
        // 状态轮询失败不阻断页面，保持旧数据
      }
    }

    function accountStatus(row) {
      if (!row.enabled) {
        return { type: "info", text: tt("mailAccounts.statusDisabled") };
      }
      const status = statusMap.value[row.id] || {};
      if (status.running) {
        return { type: "success", text: tt("mailAccounts.statusRunning") };
      }
      return { type: "danger", text: tt("mailAccounts.statusFailed"), error: status.error || "" };
    }

    function lastEmailAt(row) {
      const status = statusMap.value[row.id] || {};
      return (status.last_email_at || "").slice(0, 19).replace("T", " ");
    }

    function openDialog(account = null) {
      editingId.value = account ? account.id : null;
      form.name = account ? account.name || "" : "";
      form.email_address = account ? account.email_address || "" : "";
      form.email_password = "";
      form.imap_server = account ? account.imap_server || "" : "";
      form.imap_port = account ? account.imap_port || 993 : 993;
      form.imap_use_ssl = account ? Boolean(account.imap_use_ssl) : true;
      form.smtp_server = account ? account.smtp_server || "" : "";
      form.smtp_port = account ? account.smtp_port || 465 : 465;
      form.smtp_use_ssl = account ? Boolean(account.smtp_use_ssl) : true;
      form.smtp_use_tls = account ? Boolean(account.smtp_use_tls) : false;
      formAlert.value = false;
      dialogVisible.value = true;
      nextTick(() => formRef.value && formRef.value.clearValidate());
    }

    async function saveAccount() {
      try {
        await formRef.value.validate();
      } catch (error) {
        formAlert.value = true;
        return;
      }
      formAlert.value = false;
      saving.value = true;
      const payload = {
        name: form.name.trim(),
        email_address: form.email_address.trim(),
        email_password: form.email_password,
        imap_server: form.imap_server.trim(),
        imap_port: form.imap_port,
        imap_use_ssl: form.imap_use_ssl,
        smtp_server: form.smtp_server.trim(),
        smtp_port: form.smtp_port,
        smtp_use_ssl: form.smtp_use_ssl,
        smtp_use_tls: form.smtp_use_tls,
      };
      try {
        if (editingId.value) {
          await requestJson(`/api/system/mail-accounts/${editingId.value}`, {
            method: "PUT",
            body: JSON.stringify(payload),
          });
          NocMessage.success(tt("mailAccounts.updated"));
        } else {
          await requestJson("/api/system/mail-accounts", {
            method: "POST",
            body: JSON.stringify(payload),
          });
          NocMessage.success(tt("mailAccounts.created"));
        }
        dialogVisible.value = false;
        await loadAccounts();
      } catch (error) {
        NocMessage.error(error.message);
        setStatus(error.message, "error");
      } finally {
        saving.value = false;
      }
    }

    async function removeAccount(account) {
      try {
        await NocDialog.confirm(
          tt("mailAccounts.deleteConfirm", { address: account.email_address }),
          tt("mailAccounts.deleteTitle"),
          { confirmButtonText: tt("common.confirmDelete"), cancelButtonText: tt("common.cancel"), type: "warning" },
        );
      } catch {
        return;
      }
      try {
        await requestJson(`/api/system/mail-accounts/${account.id}`, { method: "DELETE" });
        NocMessage.success(tt("mailAccounts.deleted"));
        await loadAccounts();
      } catch (error) {
        NocMessage.error(error.message);
      }
    }

    async function toggleEnabled(account) {
      togglingId.value = account.id;
      try {
        await requestJson(`/api/system/mail-accounts/${account.id}`, {
          method: "PUT",
          body: JSON.stringify({ enabled: !account.enabled }),
        });
        await loadAccounts();
      } catch (error) {
        NocMessage.error(error.message);
      } finally {
        togglingId.value = null;
      }
    }

    async function testConnection(account) {
      testingId.value = account.id;
      try {
        const data = await requestJson(`/api/system/mail-accounts/${account.id}/test`, { method: "POST" });
        NocMessage.success(data && data.message ? data.message : tt("mailAccounts.testSuccess"));
      } catch (error) {
        NocMessage.error(error.message);
      } finally {
        testingId.value = null;
      }
    }

    async function testPreview() {
      // 保存前用当前表单配置测试连接（编辑时密码留空无法测试）
      if (!form.email_address.trim() || !form.imap_server.trim() || !form.email_password) {
        NocMessage.warning(tt("mailAccounts.testPreviewRequire"));
        return;
      }
      previewing.value = true;
      try {
        const data = await requestJson("/api/system/mail-accounts/test-preview", {
          method: "POST",
          body: JSON.stringify({
            name: form.name.trim(),
            email_address: form.email_address.trim(),
            email_password: form.email_password,
            imap_server: form.imap_server.trim(),
            imap_port: form.imap_port,
            imap_use_ssl: form.imap_use_ssl,
          }),
        });
        NocMessage.success(data && data.message ? data.message : tt("mailAccounts.testSuccess"));
      } catch (error) {
        NocMessage.error(error.message);
      } finally {
        previewing.value = false;
      }
    }

    function imapLabel(account) {
      return `${account.imap_server}:${account.imap_port}${account.imap_use_ssl ? " (SSL)" : ""}`;
    }

    onMounted(() => {
      if (appStore.apiKey) {
        loadAccounts();
        loadStatus();
        statusTimer = setInterval(loadStatus, 10000);
      }
    });

    onUnmounted(() => {
      if (statusTimer) {
        clearInterval(statusTimer);
        statusTimer = null;
      }
    });

    return {
      loading, rows, dialogVisible, saving, editingId, formRef, formAlert,
      testingId, togglingId, previewing, statusMap, form, rules,
      loadAccounts, openDialog, saveAccount, removeAccount, toggleEnabled,
      testConnection, testPreview, imapLabel, accountStatus, lastEmailAt,
    };
  },
  template: `
    <div class="view-body" v-loading="loading">
      <div class="block-section mail-accounts-panel">
        <div class="block-head">
          <h2 class="card-title">{{ $t('mailAccounts.title') }}</h2>
          <ui-button type="primary" :icon="icons.Plus" @click="openDialog()">{{ $t('mailAccounts.add') }}</ui-button>
        </div>
        <p class="field-hint">{{ $t('mailAccounts.hint') }}</p>

        <ui-table :data="rows" class="data-table" :empty-text="$t('common.noData')">
          <ui-table-column prop="name" :label="$t('mailAccounts.name')" min-width="100"></ui-table-column>
          <ui-table-column prop="email_address" :label="$t('mailAccounts.address')" min-width="190" show-overflow-tooltip></ui-table-column>
          <ui-table-column :label="$t('mailAccounts.imapTitle')" min-width="160">
            <template #default="{ row }">
              <span class="mono">{{ imapLabel(row) }}</span>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('mailAccounts.statusColumn')" width="100">
            <template #default="{ row }">
              <ui-tooltip v-if="accountStatus(row).error" :content="accountStatus(row).error" placement="top">
                <ui-tag :type="accountStatus(row).type" size="small">{{ accountStatus(row).text }}</ui-tag>
              </ui-tooltip>
              <ui-tag v-else :type="accountStatus(row).type" size="small">{{ accountStatus(row).text }}</ui-tag>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('mailAccounts.lastEmailAt')" width="142">
            <template #default="{ row }">
              <span v-if="lastEmailAt(row)" class="cell-timestamp" :title="lastEmailAt(row)">
                {{ lastEmailAt(row).slice(0, 10) }}<span>{{ lastEmailAt(row).slice(11) }}</span>
              </span>
              <span v-else class="muted">{{ $t('mailAccounts.neverReceived') }}</span>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('mailAccounts.enabledColumn')" width="110">
            <template #default="{ row }">
              <ui-switch :model-value="row.enabled" :loading="togglingId === row.id"
                         :active-text="$t('mailAccounts.enabledText')" :inactive-text="$t('mailAccounts.disabledText')"
                         inline-prompt @change="toggleEnabled(row)"></ui-switch>
            </template>
          </ui-table-column>
          <ui-table-column :label="$t('common.actions')" width="152" align="center" fixed="right">
            <template #default="{ row }">
              <div class="row-actions">
                <ui-action type="primary" :loading="testingId === row.id"
                           @click="testConnection(row)" icon="Connection" :label="$t('mailAccounts.test')"></ui-action>
                <ui-action type="primary" @click="openDialog(row)" icon="Edit" :label="$t('common.edit')"></ui-action>
                <ui-action type="danger" @click="removeAccount(row)" icon="Delete" :label="$t('common.delete')"></ui-action>
              </div>
            </template>
          </ui-table-column>
        </ui-table>
      </div>

      <!-- 新建/编辑邮箱弹窗 -->
      <ui-dialog v-model="dialogVisible" :title="editingId ? $t('mailAccounts.dialogEdit') : $t('mailAccounts.dialogAdd')"
                 width="640px" :close-on-click-modal="false" destroy-on-close>
        <ui-alert v-if="formAlert" type="error" :closable="false"
                  :title="$t('mailAccounts.formAlert')" class="form-alert"></ui-alert>
        <ui-form ref="formRef" :model="form" :rules="rules" label-position="top">
          <div class="field-grid-2">
            <ui-form-item :label="$t('mailAccounts.name')" prop="name">
              <ui-input v-model="form.name" :placeholder="$t('mailAccounts.namePlaceholder')" clearable></ui-input>
            </ui-form-item>
            <ui-form-item :label="$t('mailAccounts.address')" prop="email_address">
              <ui-input v-model="form.email_address" :placeholder="$t('mailAccounts.addressPlaceholder')" clearable></ui-input>
            </ui-form-item>
          </div>
          <ui-form-item :label="$t('mailAccounts.password')" prop="email_password">
            <ui-input v-model="form.email_password" type="password" show-password
                      :placeholder="editingId ? $t('mailAccounts.passwordKeep') : $t('mailAccounts.passwordPlaceholder')"></ui-input>
          </ui-form-item>

          <p class="field-hint">{{ $t('mailAccounts.imapTitle') }}</p>
          <div class="field-grid-2">
            <ui-form-item :label="$t('mailAccounts.imapServer')" prop="imap_server">
              <ui-input v-model="form.imap_server" :placeholder="$t('mailAccounts.imapServerPlaceholder')" clearable></ui-input>
            </ui-form-item>
            <ui-form-item :label="$t('mailAccounts.imapPort')">
              <ui-input-number v-model="form.imap_port" :min="1" :max="65535" style="width: 100%"></ui-input-number>
            </ui-form-item>
          </div>
          <ui-form-item :label="$t('mailAccounts.imapSsl')">
            <ui-switch v-model="form.imap_use_ssl"></ui-switch>
          </ui-form-item>

          <p class="field-hint">{{ $t('mailAccounts.smtpTitle') }}</p>
          <div class="field-grid-2">
            <ui-form-item :label="$t('mailAccounts.smtpServer')">
              <ui-input v-model="form.smtp_server" :placeholder="$t('mailAccounts.smtpServerPlaceholder')" clearable></ui-input>
            </ui-form-item>
            <ui-form-item :label="$t('mailAccounts.smtpPort')">
              <ui-input-number v-model="form.smtp_port" :min="1" :max="65535" style="width: 100%"></ui-input-number>
            </ui-form-item>
          </div>
          <div class="field-grid-2">
            <ui-form-item :label="$t('mailAccounts.smtpSsl')">
              <ui-switch v-model="form.smtp_use_ssl"></ui-switch>
            </ui-form-item>
            <ui-form-item :label="$t('mailAccounts.smtpTls')">
              <ui-switch v-model="form.smtp_use_tls"></ui-switch>
            </ui-form-item>
          </div>
        </ui-form>
        <template #footer>
          <ui-button @click="dialogVisible = false">{{ $t('common.cancel') }}</ui-button>
          <ui-button :loading="previewing" :disabled="Boolean(editingId) && !form.email_password"
                     @click="testPreview">{{ $t('mailAccounts.test') }}</ui-button>
          <ui-button type="primary" :loading="saving" @click="saveAccount">{{ $t('common.save') }}</ui-button>
        </template>
      </ui-dialog>
    </div>
  `,
  computed: {
    icons() {
      return ElementPlusIconsVue;
    },
  },
});
