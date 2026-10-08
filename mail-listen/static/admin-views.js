/* Mail Listen 管理台 · Vue 3 + Element Plus 视图组件
 * 依赖加载顺序：vendor → admin-shared.js → 本文件 → admin.js
 * 注意：模板为运行时编译的字符串模板，自定义元素无自闭合坑，但仍统一显式闭合。
 */
const { createApp, defineComponent, ref, reactive, computed, onMounted, onUnmounted, watch, nextTick, markRaw } = Vue;

// ==================== 登录页（密码即 API Key） ====================
const ViewLogin = defineComponent({
  name: "ViewLogin",
  setup() {
    const keyInput = ref("");
    const submitting = ref(false);
    const errorMessage = ref("");

    // 界面语言：选项名固定为各语言自称，与系统配置页保持一致
    const currentLang = computed(() => i18n.global.locale.value);
    const langOptions = [
      { value: "zh-CN", label: "简体中文" },
      { value: "en", label: "English" },
      { value: "zh-HK", label: "繁體中文（香港）" },
    ];
    function changeLang(value) {
      setLocale(value);
    }

    async function submitLogin() {
      const key = keyInput.value.trim();
      if (!key) {
        errorMessage.value = tt("login.keyEmpty");
        return;
      }
      submitting.value = true;
      errorMessage.value = "";
      try {
        await checkApiKey(key);
        persistApiKey(key);
        ElMessage.success(tt("login.success"));
      } catch (error) {
        errorMessage.value = error.message || tt("login.keyInvalid");
      } finally {
        submitting.value = false;
      }
    }

    return { keyInput, submitting, errorMessage, currentLang, langOptions, changeLang, submitLogin };
  },
  template: `
    <div class="login-screen">
      <el-select class="login-lang" size="small" :model-value="currentLang" @change="changeLang">
        <el-option v-for="option in langOptions" :key="option.value"
                   :label="option.label" :value="option.value"></el-option>
      </el-select>

      <div class="login-card">
        <div class="login-brand">
          <div class="brand-mark login-brand-mark">NOC</div>
          <div>
            <h1>{{ $t('common.brandName') }}</h1>
            <p>{{ $t('common.brandTagline') }}</p>
          </div>
        </div>
        <h2 class="login-title">{{ $t('login.title') }}</h2>
        <p class="login-subtitle">{{ $t('login.subtitle') }}</p>
        <el-input v-model="keyInput" type="password" show-password size="large"
                  :placeholder="$t('login.keyPlaceholder')"
                  aria-label="API Key"
                  @keyup.enter="submitLogin"></el-input>
        <p v-if="errorMessage" class="login-error" role="alert">{{ errorMessage }}</p>
        <el-button class="login-submit" type="primary" size="large"
                   :loading="submitting" @click="submitLogin">{{ $t('login.submit') }}</el-button>
        <p class="login-hint">{{ $t('login.hint') }}</p>
      </div>
    </div>
  `,
});

// ==================== 供应商配置 ====================
const ViewSuppliers = defineComponent({
  name: "ViewSuppliers",
  setup() {
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
        await ElMessageBox.confirm(
          tt("suppliers.deleteConfirm", { name: supplier.name }),
          tt("suppliers.deleteTitle"),
          { confirmButtonText: tt("common.confirmDelete"), cancelButtonText: tt("common.cancel"), type: "warning" },
        );
      } catch {
        return;
      }
      try {
        await requestJson(`/api/suppliers/${supplier.id}`, { method: "DELETE" });
        ElMessage.success(tt("suppliers.deleted"));
        await loadSuppliers();
      } catch (error) {
        ElMessage.error(error.message);
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
      suppliers, loading, loadSuppliers, removeSupplier, goCreate, goEdit,
      icons: ElementPlusIconsVue,
    };
  },
  template: `
    <div class="view-body">
      <el-card shadow="never" class="table-card">
        <template #header>
          <div class="card-header">
            <span class="card-title">{{ $t('suppliers.listTitle') }}</span>
            <div>
              <el-button :icon="icons.Refresh" @click="loadSuppliers">{{ $t('common.refresh') }}</el-button>
              <el-button type="primary" :icon="icons.Plus" @click="goCreate">{{ $t('suppliers.create') }}</el-button>
            </div>
          </div>
        </template>
        <el-table v-loading="loading" :data="suppliers" :empty-text="$t('suppliers.empty')" stripe>
          <el-table-column prop="name" :label="$t('suppliers.name')" min-width="160">
            <template #default="{ row }">
              <span class="cell-main">{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="email" :label="$t('common.email')" min-width="220"></el-table-column>
          <el-table-column prop="reply_email" :label="$t('suppliers.replyEmail')" min-width="220"></el-table-column>
          <el-table-column prop="update_time" :label="$t('common.updateTime')" width="180">
            <template #default="{ row }">
              <span class="mono muted">{{ row.update_time }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.actions')" width="150" align="right" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" :icon="icons.Edit" @click="goEdit(row)">{{ $t('common.edit') }}</el-button>
              <el-button link type="danger" :icon="icons.Delete" @click="removeSupplier(row)">{{ $t('common.delete') }}</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
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
  props: {
    supplierId: { type: Number, default: null },
  },
  setup(props) {
    const isEdit = computed(() => props.supplierId != null);
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
    const sectionActiveNames = ref(["basic", "mailTypes", "fixed", "custom", "topCustom", "prompt"]);
    const mailTypes = ref([]); // [{ name, subject, content, contentInAttachment }]
    const mailTypeOptions = ref([]);
    const configuredMailTypeCount = computed(() => mailTypes.value.filter((item) => {
      return item.subject.trim() || item.content.trim();
    }).length);
    const lineFields = ref([]); // [{ name, description, keyword }]
    const topCustomFields = ref([]); // [{ name, description }] 顶层自定义字段（提取结果顶层输出，供特殊规则判断等）
    const legacyPrompt = ref("");
    const promptPreview = ref("");
    const extractPreview = ref("");
    const extractPreviewView = computed(() => buildExtractPreviewView(extractPreview.value));
    const previewing = ref(false);
    const extracting = ref(false);
    const extractFiles = ref([]); // el-upload 文件列表，提取预览时随请求上传
    const extractResultVisible = ref(false); // 提取结果弹窗，避免结果藏在页面底部

    // 影响线路列宽：按表头与内容长度估算，减少横向滚动
    function lineColumnWidth(col, lines) {
      let length = col.length;
      for (const row of lines) {
        const value = row[col];
        if (value != null && value !== "") {
          length = Math.max(length, String(value).length);
        }
      }
      return Math.max(90, Math.min(length * 8 + 28, 400));
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
      mailTypes.value = options.map((name) => {
        const sample = samples[name] || {};
        return {
          name,
          subject: sample.subject || "",
          content: sample.content || "",
          contentInAttachment: Boolean(sample.content_in_attachment),
        };
      });
    }

    async function fillFromSupplier(supplier) {
      form.name = supplier ? supplier.name : "";
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
        const supplier = isEdit.value
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
      const emailTypeSamples = {};
      for (const item of mailTypes.value) {
        if (item.name !== "割接通知" && !isMailTypeItemConfigured(item)) {
          continue;
        }
        emailTypeSamples[item.name] = {
          subject: item.subject.trim(),
          content: item.content.trim(),
          content_in_attachment: item.contentInAttachment,
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
        email_type_samples: collectMailTypeSamples(),
      };
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
      if (!lineCustomFields.length && !legacy) {
        throw new Error(tt("supplierForm.lineFieldRequired"));
      }
      return payload;
    }

    async function previewPrompt() {
      previewing.value = true;
      try {
        const data = await requestJson("/api/suppliers/preview-prompt", {
          method: "POST",
          body: JSON.stringify(collectPromptConfig()),
        });
        promptPreview.value = data.cutover_extract_prompt;
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

    async function resolveCurrentPrompt() {
      const legacy = legacyPrompt.value.trim();
      if (legacy) {
        return legacy;
      }
      const data = await requestJson("/api/suppliers/preview-prompt", {
        method: "POST",
        body: JSON.stringify(collectPromptConfig()),
      });
      return data.cutover_extract_prompt;
    }

    function collectCurrentMailTypeSamples() {
      // 预览用，不做必填校验，空样本由后端提示词生成时自动跳过
      const samples = {};
      for (const item of mailTypes.value) {
        samples[item.name] = {
          subject: item.subject.trim(),
          content: item.content.trim(),
          content_in_attachment: item.contentInAttachment,
        };
      }
      return samples;
    }

    async function uploadExtractFiles() {
      const attachments = [];
      for (const item of extractFiles.value) {
        const formData = new FormData();
        formData.append("file", item.raw);
        const response = await fetch("/api/suppliers/preview-attachments", {
          method: "POST",
          headers: { Authorization: `Bearer ${appStore.apiKey}` },
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
      const sample = mailTypes.value.find((item) => item.name === "割接通知");
      if (!sample) {
        ElMessage.error(tt("supplierForm.mailTypeNotLoaded"));
        return;
      }
      if (!sample.subject.trim() && !sample.content.trim()) {
        ElMessage.error(tt("supplierForm.previewNeedsSample"));
        return;
      }
      extracting.value = true;
      try {
        const attachments = await uploadExtractFiles();
        const cutoverExtractPrompt = await resolveCurrentPrompt();
        const data = await requestJson("/api/suppliers/preview-extract", {
          method: "POST",
          body: JSON.stringify({
            subject: sample.subject.trim(),
            content: sample.content.trim(),
            content_in_attachment: sample.contentInAttachment,
            attachments,
            sender: form.email.trim(),
            supplier_name: form.name.trim(),
            email_type_samples: collectCurrentMailTypeSamples(),
            cutover_extract_prompt: cutoverExtractPrompt,
          }),
        });
        extractPreview.value = data.extract_result || "";
        extractResultVisible.value = true;
        setStatusKey("supplierForm.extractPreviewReady");
      } catch (error) {
        extractPreview.value = "";
        extractResultVisible.value = false;
        setStatus(error.message, "error");
        ElMessage.error(error.message);
      } finally {
        extracting.value = false;
      }
    }

    async function saveSupplier() {
      let payload;
      try {
        payload = buildSupplierPayload();
      } catch (error) {
        ElMessage.error(error.message);
        return;
      }
      saving.value = true;
      try {
        const path = isEdit.value ? `/api/suppliers/${props.supplierId}` : "/api/suppliers";
        await requestJson(path, {
          method: isEdit.value ? "PATCH" : "POST",
          body: JSON.stringify(payload),
        });
        ElMessage.success(isEdit.value ? tt("supplierForm.saved") : tt("supplierForm.created"));
        navigateTo("suppliers");
      } catch (error) {
        ElMessage.error(error.message);
        setStatus(error.message, "error");
      } finally {
        saving.value = false;
      }
    }

    onMounted(() => {
      if (appStore.apiKey) {
        loadForm();
      }
    });

    return {
      isEdit, loading, saving, loadFailed, form,
      fixedFields, selectedFixedField, selectedFixedFieldName,
      customizedFixedFieldCount, defaultFixedFieldCount,
      mailTypes, configuredMailTypeCount,
      sectionActiveNames, lineFields, topCustomFields, legacyPrompt, promptPreview, previewing,
      extractPreview, extracting, extractFiles, extractPreviewView, extractResultVisible,
      lineColumnWidth,
      isFixedFieldCustomized, selectFixedField, moveFixedFieldSelection,
      restoreSelectedFixedField, addLineField, removeLineField,
      addTopCustomField, removeTopCustomField, previewPrompt,
      previewExtract, saveSupplier,
    };
  },
  methods: {
    goBack() {
      navigateTo("suppliers");
    },
  },
  computed: {
    icons() {
      return ElementPlusIconsVue;
    },
  },
  template: `
    <div class="view-body supplier-form-view" v-loading="loading">
      <nav class="supplier-context-bar" :aria-label="$t('common.pageLocation')">
        <el-button link class="supplier-back-link" :icon="icons.ArrowLeft" @click="goBack">{{ $t('suppliers.listTitle') }}</el-button>
        <span class="supplier-context-separator" aria-hidden="true">/</span>
        <span class="supplier-context-current">{{ isEdit ? $t('nav.supplierEdit') : $t('nav.supplierCreate') }}</span>
      </nav>

      <p v-if="!loading && loadFailed" class="empty-inline">{{ $t('common.loadFailedBack') }}</p>

      <el-collapse v-if="!loadFailed"
                   v-model="sectionActiveNames"
                   class="supplier-form supplier-form-page supplier-section-collapse">
        <!-- 基本信息 -->
        <el-collapse-item name="basic" class="supplier-section supplier-section--basic">
          <template #title>
            <div class="supplier-section-head">
              <strong>{{ $t('supplierForm.basicInfo') }}</strong>
              <div class="supplier-section-actions">
                <el-button size="small" @click.stop="goBack">{{ $t('common.cancel') }}</el-button>
                <el-button size="small" type="primary" :loading="saving" @click.stop="saveSupplier">{{ $t('supplierForm.saveConfig') }}</el-button>
              </div>
            </div>
          </template>
          <div class="field-grid-2">
            <div class="form-field">
              <label class="form-label">{{ $t('supplierForm.nameLabel') }} <span class="required-mark">*</span></label>
              <el-input v-model="form.name" :placeholder="$t('supplierForm.namePlaceholder')"></el-input>
            </div>
            <div class="form-field">
              <label class="form-label">{{ $t('supplierForm.emailLabel') }} <span class="required-mark">*</span></label>
              <el-input v-model="form.email" type="email" :placeholder="$t('supplierForm.emailPlaceholder')"></el-input>
            </div>
            <div class="form-field">
              <label class="form-label">{{ $t('supplierForm.replyEmailLabel') }}</label>
              <el-input v-model="form.reply_email" type="email" :placeholder="$t('supplierForm.replyEmailPlaceholder')"></el-input>
              <p class="field-hint">{{ $t('supplierForm.replyEmailHint') }}</p>
            </div>
          </div>
        </el-collapse-item>

        <!-- 邮件类型样本 -->
        <el-collapse-item name="mailTypes" class="supplier-section supplier-section--mail-types">
          <template #title>
            <div class="supplier-section-head">
              <strong>{{ $t('supplierForm.mailTypesTitle') }}</strong>
              <div class="fixed-field-summary" :aria-label="$t('supplierForm.mailTypesStatsLabel')">
                <span class="is-configured">{{ $t('supplierForm.configuredCount', { count: configuredMailTypeCount, total: mailTypes.length }) }}</span>
              </div>
            </div>
          </template>
          <p class="field-hint">{{ $t('supplierForm.mailTypesHint') }}</p>
          <div v-if="!mailTypes.length" class="empty-inline">{{ $t('supplierForm.mailTypesLoadFailed') }}</div>
          <div v-else class="mail-type-list" :aria-label="$t('supplierForm.mailTypesListLabel')">
            <div v-for="item in mailTypes" :key="item.name" class="mail-type-item">
              <label class="form-label mail-type-name">
                {{ item.name }}
                <span v-if="item.name === '割接通知'" class="required-mark">*</span>
              </label>
              <el-input v-model="item.subject" :placeholder="$t('supplierForm.subjectPlaceholder')"
                        style="margin-bottom: 8px"></el-input>
              <el-input v-model="item.content" type="textarea" :rows="4" resize="vertical"
                        :placeholder="$t('supplierForm.contentPlaceholder', { name: item.name })"></el-input>
              <el-checkbox v-if="item.name === '割接通知'" v-model="item.contentInAttachment"
                           class="mail-type-attachment-flag">{{ $t('supplierForm.contentInAttachment') }}</el-checkbox>
            </div>
          </div>
        </el-collapse-item>

        <!-- 固定字段提取规则 -->
        <el-collapse-item name="fixed" class="supplier-section supplier-section--fixed">
          <template #title>
            <div class="supplier-section-head">
              <strong>{{ $t('supplierForm.fixedTitle') }}</strong>
              <div class="fixed-field-summary" :aria-label="$t('supplierForm.fixedStatsLabel')">
                <span class="is-configured">{{ $t('supplierForm.customizedCount', { count: customizedFixedFieldCount }) }}</span>
                <span class="is-default">{{ $t('supplierForm.defaultCount', { count: defaultFixedFieldCount }) }}</span>
              </div>
            </div>
          </template>
          <p class="field-hint">{{ $t('supplierForm.fixedHint') }}</p>
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
                  <span class="fixed-field-tab-name">{{ field.name }}</span>
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
                    <strong>{{ selectedFixedField.name }}</strong>
                    <el-tag size="small" effect="plain">
                      {{ selectedFixedField.required ? $t('supplierForm.requiredField') : (selectedFixedField.isLineField ? $t('supplierForm.lineField') : $t('supplierForm.optionalField')) }}
                    </el-tag>
                    <el-tag
                      size="small"
                      :type="isFixedFieldCustomized(selectedFixedField) ? 'success' : 'info'"
                      effect="plain"
                    >{{ isFixedFieldCustomized(selectedFixedField) ? $t('supplierForm.customized') : $t('supplierForm.useDefault') }}</el-tag>
                  </div>
                  <p>{{ $t('supplierForm.editorHint') }}</p>
                </div>
                <el-button
                  size="small"
                  :disabled="!isFixedFieldCustomized(selectedFixedField)"
                  @click="restoreSelectedFixedField"
                >{{ $t('supplierForm.restoreDefault') }}</el-button>
              </div>
              <el-input
                v-model="selectedFixedField.value"
                type="textarea"
                :rows="7"
                resize="vertical"
                :placeholder="selectedFixedField.description"
              ></el-input>
            </section>
          </div>
        </el-collapse-item>

        <!-- line_array 自定义字段 -->
        <el-collapse-item name="custom" class="supplier-section supplier-section--custom">
          <template #title>
            <div class="supplier-section-head">
              <strong>{{ $t('supplierForm.customTitle') }}</strong>
              <div class="supplier-section-actions">
                <span v-if="lineFields.length" class="muted">{{ $t('supplierForm.fieldCount', { count: lineFields.length }) }}</span>
                <el-button size="small" :icon="icons.Plus" @click.stop="addLineField">{{ $t('supplierForm.addField') }}</el-button>
              </div>
            </div>
          </template>
          <p class="field-hint">{{ $t('supplierForm.customHint') }}</p>
          <div v-if="!lineFields.length" class="empty-inline">{{ $t('supplierForm.noCustomFields') }}</div>
          <div v-else class="custom-field-list" :aria-label="$t('supplierForm.customListLabel')">
            <div v-for="(row, index) in lineFields" :key="index" class="extract-field-row">
              <div class="line-field-top">
                <el-input v-model="row.name" :placeholder="$t('supplierForm.fieldNamePlaceholder')" style="width: 220px"></el-input>
                <el-checkbox v-model="row.keyword">{{ $t('supplierForm.asKeyword') }}</el-checkbox>
                <el-button link type="danger" :icon="icons.Delete" @click="removeLineField(index)">{{ $t('common.delete') }}</el-button>
              </div>
              <el-input v-model="row.description" type="textarea" :rows="2"
                        :placeholder="$t('supplierForm.fieldDescPlaceholder')"></el-input>
            </div>
          </div>
        </el-collapse-item>

        <!-- 顶层自定义字段（提取结果顶层输出，供特殊规则判断等） -->
        <el-collapse-item name="topCustom" class="supplier-section supplier-section--custom">
          <template #title>
            <div class="supplier-section-head">
              <strong>{{ $t('supplierForm.topCustomTitle') }}</strong>
              <div class="supplier-section-actions">
                <span v-if="topCustomFields.length" class="muted">{{ $t('supplierForm.fieldCount', { count: topCustomFields.length }) }}</span>
                <el-button size="small" :icon="icons.Plus" @click.stop="addTopCustomField">{{ $t('supplierForm.addField') }}</el-button>
              </div>
            </div>
          </template>
          <p class="field-hint">{{ $t('supplierForm.topCustomHint') }}</p>
          <div v-if="!topCustomFields.length" class="empty-inline">{{ $t('supplierForm.noTopCustomFields') }}</div>
          <div v-else class="custom-field-list" :aria-label="$t('supplierForm.customListLabel')">
            <div v-for="(row, index) in topCustomFields" :key="index" class="extract-field-row">
              <div class="line-field-top">
                <el-input v-model="row.name" :placeholder="$t('supplierForm.topCustomFieldNamePlaceholder')" style="width: 220px"></el-input>
                <el-button link type="danger" :icon="icons.Delete" @click="removeTopCustomField(index)">{{ $t('common.delete') }}</el-button>
              </div>
              <el-input v-model="row.description" type="textarea" :rows="2"
                        :placeholder="$t('supplierForm.topCustomFieldDescPlaceholder')"></el-input>
            </div>
          </div>
        </el-collapse-item>

        <!-- 提示词 -->
        <el-collapse-item name="prompt" class="supplier-section supplier-section--prompt">
          <template #title>
            <div class="supplier-section-head">
              <strong>{{ $t('supplierForm.promptTitle') }}</strong>
              <div class="supplier-section-actions">
                <el-button size="small" :loading="previewing" @click.stop="previewPrompt">{{ $t('supplierForm.previewPrompt') }}</el-button>
                <el-button size="small" type="primary" :loading="extracting" @click.stop="previewExtract">{{ $t('supplierForm.previewExtract') }}</el-button>
              </div>
            </div>
          </template>
          <p class="field-hint">{{ $t('supplierForm.promptHint') }}</p>
          <div class="form-field">
            <label class="form-label">{{ $t('supplierForm.extraInstructionsLabel') }}</label>
            <el-input v-model="form.extra_instructions" type="textarea" :rows="2"
                      :placeholder="$t('supplierForm.extraInstructionsPlaceholder')"></el-input>
          </div>
          <div class="form-field">
            <label class="form-label">{{ $t('supplierForm.extractFilesLabel') }}</label>
            <el-upload v-model:file-list="extractFiles" :auto-upload="false" multiple
                       class="extract-preview-upload">
              <el-button size="small" :icon="icons.Paperclip">{{ $t('supplierForm.chooseAttachment') }}</el-button>
            </el-upload>
            <p class="field-hint extract-preview-upload-hint">{{ $t('supplierForm.extractFilesHint') }}</p>
          </div>
          <div class="form-field">
            <label class="form-label">{{ $t('supplierForm.promptPreviewLabel') }}</label>
            <el-input v-model="promptPreview" type="textarea" :rows="6" readonly
                      :placeholder="$t('supplierForm.promptPreviewPlaceholder')"></el-input>
          </div>
          <div class="form-field">
            <label class="form-label">{{ $t('supplierForm.extractPreviewLabel') }}</label>
            <div v-if="!extractPreview" class="extract-preview-empty">
              {{ $t('supplierForm.extractPreviewEmpty') }}
            </div>
            <el-button v-else link type="primary" @click="extractResultVisible = true">
              {{ $t('supplierForm.viewLastExtract') }}
            </el-button>
          </div>
          <el-dialog v-model="extractResultVisible" :title="$t('supplierForm.extractResultTitle')" top="8vh"
                     class="extract-result-dialog" append-to-body>
            <div class="extract-preview-result">
              <template v-for="(block, blockIndex) in extractPreviewView.blocks" :key="blockIndex">
                <div v-if="block.kind === 'classify'" class="extract-preview-classify">
                  <span class="extract-preview-block-label">{{ $t('supplierForm.classifyResult') }}</span>
                  <el-tag type="primary" effect="dark">{{ block.mailType }}</el-tag>
                </div>
                <div v-else-if="block.kind === 'extract'" class="extract-preview-extract">
                  <div v-for="field in block.fields" :key="field.key" class="extract-preview-field">
                    <span class="extract-preview-field-label">{{ field.label }}</span>
                    <div v-if="field.timeRange" class="extract-preview-time-range">
                      <span class="mono">{{ $t('supplierForm.timeStart', { time: field.timeRange.startTime }) }}</span>
                      <span class="mono">{{ $t('supplierForm.timeEnd', { time: field.timeRange.endTime }) }}</span>
                    </div>
                    <span v-else class="mono extract-preview-field-value">{{ field.value || '-' }}</span>
                  </div>
                  <div v-if="block.tags.length" class="extract-preview-field">
                    <span class="extract-preview-field-label">{{ $t('supplierForm.lineKeywordsLabel') }}</span>
                    <div class="extract-preview-tags">
                      <el-tag v-for="tag in block.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag>
                    </div>
                  </div>
                  <div v-if="block.lines.length" class="extract-preview-lines">
                    <div class="extract-preview-block-label">{{ $t('supplierForm.affectedLines', { count: block.lines.length }) }}</div>
                    <el-table :data="block.lines" size="small" border>
                      <el-table-column v-for="col in block.lineColumns" :key="col" :prop="col" :label="col" :min-width="lineColumnWidth(col, block.lines)">
                        <template #default="{ row }">
                          <span class="mono">{{ row[col] === '' || row[col] == null ? '-' : row[col] }}</span>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </div>
                <pre v-else class="extract-preview-raw">{{ block.text }}</pre>
              </template>
              <pre v-if="extractPreviewView.raw" class="extract-preview-raw">{{ extractPreviewView.raw }}</pre>
            </div>
          </el-dialog>
          <el-collapse class="legacy-prompt-collapse">
            <el-collapse-item name="legacy">
              <template #title>
                <span class="muted">{{ $t('supplierForm.legacyTitle') }}</span>
              </template>
              <el-input v-model="legacyPrompt" type="textarea" :rows="6"
                        :placeholder="$t('supplierForm.legacyPlaceholder')"></el-input>
            </el-collapse-item>
          </el-collapse>
        </el-collapse-item>
      </el-collapse>

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
      <el-card shadow="never" class="table-card">
        <template #header>
          <div class="card-header">
            <div class="filter-bar">
              <el-select v-model="receiverFilter" :placeholder="$t('common.allMailboxes')" clearable filterable style="width: 220px">
                <el-option v-for="option in mailboxOptions" :key="option.value"
                           :label="option.label" :value="option.value"></el-option>
              </el-select>
              <el-input v-model="senderFilter" :placeholder="$t('emails.senderFilterPlaceholder')" clearable style="width: 260px"
                        @keyup.enter="loadEmails"></el-input>
              <el-button type="primary" @click="loadEmails">{{ $t('common.query') }}</el-button>
            </div>
          </div>
        </template>
        <el-table v-loading="loading" :data="items" :empty-text="$t('emails.empty')" stripe>
          <el-table-column prop="email_id" :label="$t('emails.uid')" width="100">
            <template #default="{ row }">
              <span class="mono">{{ row.email_id }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="sender" :label="$t('common.sender')" min-width="200"></el-table-column>
          <el-table-column :label="$t('common.receiverMailbox')" min-width="180">
            <template #default="{ row }">
              <span class="muted">{{ mailboxLabel(row.receiver) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="subject" :label="$t('common.subject')" min-width="240">
            <template #default="{ row }">
              <span class="cell-main">{{ row.subject }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="create_time" :label="$t('common.receiveTime')" width="170">
            <template #default="{ row }">
              <span class="mono muted">{{ row.create_time }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('emails.contentSummary')" min-width="240">
            <template #default="{ row }">
              <span class="muted">{{ shortText(row.content) }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('emails.attachments')" width="140">
            <template #default="{ row }">
              <div v-if="(row.attachment_urls || []).length" class="attachment-list">
                <a v-for="(url, index) in row.attachment_urls" :key="url" :href="url"
                   target="_blank" rel="noopener noreferrer">{{ $t('common.attachment', { index: index + 1 }) }}</a>
              </div>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
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
      <el-card shadow="never" class="table-card">
        <template #header>
          <div class="card-header">
            <div class="filter-bar">
              <el-input v-model="statusFilter" :placeholder="$t('tickets.statusFilterPlaceholder')" clearable style="width: 260px"
                        @keyup.enter="loadTickets"></el-input>
              <el-button type="primary" @click="loadTickets">{{ $t('common.query') }}</el-button>
            </div>
          </div>
        </template>
        <el-table v-loading="loading" :data="items" :empty-text="$t('tickets.empty')" stripe>
          <el-table-column prop="id" label="ID" width="90">
            <template #default="{ row }">
              <span class="mono">{{ row.id }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="carrier_ticket_no" :label="$t('common.carrierTicketNo')" min-width="200">
            <template #default="{ row }">
              <span class="cell-main">{{ row.carrier_ticket_no }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.status')" width="120">
            <template #default="{ row }">
              <span>{{ row.status || $t('common.unset') }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('tickets.cutoverWindow')" min-width="280">
            <template #default="{ row }">
              <span class="mono muted">{{ $t('common.timeRange', { start: row.cut_start_time || '', end: row.cut_end_time || '' }) }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('tickets.subjectOrSender')" min-width="240">
            <template #default="{ row }">
              <span class="muted">{{ row.subject || row.sender || '' }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.receiverMailbox')" min-width="160">
            <template #default="{ row }">
              <span class="muted">{{ mailboxLabel(row.receiver) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>
  `,
});

// ==================== 割接任务列表（邮件维度） ====================
const ViewCutoverTasks = defineComponent({
  name: "ViewCutoverTasks",
  setup() {
    const items = ref([]);
    const total = ref(0);
    const loading = ref(false);
    const readStateBusyIds = ref([]);
    const page = ref(1);
    const pageSize = ref(20);
    const showAdvanced = ref(false);
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
    });
    const appliedFilters = ref({ ...filters });
    const advancedFilterCount = computed(() =>
      ["read_status", "tag", "receiver", "sender", "start", "end"].filter(key => filters[key]).length
    );
    const displayItems = computed(() => items.value.map(row => ({
      ...row, displayTags: cutoverEmailTags(row), displayStates: cutoverEmailStates(row),
    })));
    const statusOptions = computed(() => cutoverStatusOptions().concat(
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
        const suppliers = await requestJson("/api/suppliers");
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
      if (readStateBusyIds.value.includes(row.id)) {
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
        ElMessage.success(tt("common.readStateUpdated"));
        if (appliedFilters.value.read_status) {
          await loadTasks();
        }
      } catch (error) {
        ElMessage.error(error.message);
      } finally {
        readStateBusyIds.value = readStateBusyIds.value.filter((id) => id !== row.id);
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
      openCutoverEmailDetail(row.id);
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
      items: displayItems, total, loading, readStateBusyIds, filters, statusOptions, tagOptions, supplierOptions, mailboxOptions,
      page, pageSize, showAdvanced, advancedFilterCount, searchTasks, changePageSize,
      loadTasks, resetFilters, openDetail, toggleReadState, shortText,
      sceneText, sceneTagType, isRejectedScene, mailboxLabel,
    };
  },
  template: `
    <div class="view-body cutover-list-view">
      <el-card shadow="never" class="table-card cutover-list-card">
        <template #header>
          <form @submit.prevent="searchTasks">
            <div class="cutover-main-filters">
              <el-input v-model="filters.keyword" :placeholder="$t('cutover.list.keywordSearch')" :aria-label="$t('cutover.list.keywordSearch')" clearable></el-input>
              <el-select v-model="filters.status" :placeholder="$t('cutover.list.allStatus')" :aria-label="$t('cutover.list.processingStatus')" clearable>
                <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value"></el-option>
              </el-select>
              <el-select v-model="filters.supplier" :placeholder="$t('cutover.list.allSupplier')" :aria-label="$t('common.supplier')" clearable filterable>
                <el-option v-for="name in supplierOptions" :key="name" :label="name" :value="name"></el-option>
              </el-select>
              <el-button type="primary" native-type="submit" :loading="loading">{{ $t('common.query') }}</el-button>
              <el-button @click="resetFilters">{{ $t('common.reset') }}</el-button>
              <el-button text @click="showAdvanced = !showAdvanced" :aria-expanded="showAdvanced" aria-controls="cutover-advanced-filters">
                {{ $t('cutover.list.moreFilters') }}{{ advancedFilterCount ? ' (' + advancedFilterCount + ')' : '' }} {{ showAdvanced ? '−' : '+' }}
              </el-button>
            </div>
            <div v-if="showAdvanced" id="cutover-advanced-filters" class="cutover-advanced-filters">
              <el-select v-model="filters.read_status" :placeholder="$t('common.allReadStates')" :aria-label="$t('common.readState')" clearable>
                <el-option :label="$t('common.unread')" value="unread"></el-option><el-option :label="$t('common.read')" value="read"></el-option>
              </el-select>
              <el-select v-model="filters.tag" :placeholder="$t('cutover.list.allTag')" :aria-label="$t('cutover.list.tags')" clearable>
                <el-option v-for="item in tagOptions" :key="item.value" :label="item.label" :value="item.value"></el-option>
              </el-select>
              <el-select v-model="filters.receiver" :placeholder="$t('common.allMailboxes')" :aria-label="$t('common.receiverMailbox')" clearable filterable>
                <el-option v-for="option in mailboxOptions" :key="option.value" :label="option.label" :value="option.value"></el-option>
              </el-select>
              <el-input v-model="filters.sender" :placeholder="$t('common.sender')" :aria-label="$t('common.sender')" clearable></el-input>
              <el-date-picker v-model="filters.start" type="date" :placeholder="$t('cutover.list.receiveStart')" value-format="YYYY-MM-DD"></el-date-picker>
              <el-date-picker v-model="filters.end" type="date" :placeholder="$t('cutover.list.receiveEnd')" value-format="YYYY-MM-DD"></el-date-picker>
            </div>
          </form>
        </template>
        <div class="cutover-list-meta"><span>{{ $t('cutover.list.totalEmails', { total }) }}</span></div>
        <el-table v-loading="loading" :data="items" :empty-text="$t('cutover.list.empty')" height="100%" row-key="id" @row-click="openDetail" class="clickable-table cutover-six-table">
          <el-table-column :label="$t('cutover.list.mailContent')" min-width="320">
            <template #default="{ row }">
              <div class="cutover-mail" :class="{ 'is-unread': !row.is_read }" :aria-busy="readStateBusyIds.includes(row.id)">
                <div class="cutover-mail-heading"><span class="cutover-unread-dot" :class="{ 'is-read': row.is_read }" :title="row.is_read ? $t('common.read') : $t('common.unread')" :aria-label="row.is_read ? $t('common.read') : $t('common.unread')" role="img"></span>
                  <el-tooltip :trigger="['hover', 'focus']" effect="light" placement="bottom-start" :show-after="300" popper-class="cutover-text-tooltip">
                    <template #content><div class="cutover-tooltip-heading">{{ row.subject || '-' }}</div><div class="cutover-tooltip-meta">UID {{ row.email_id }}</div></template>
                    <button class="cutover-subject" @click.stop="openDetail(row)">{{ row.subject || '-' }}</button>
                  </el-tooltip>
                </div>
                <div class="cutover-mail-tags">
                  <el-tag v-for="tag in row.displayTags.slice(0, 3)" :key="tag.key" :type="tag.type" size="small" effect="plain">{{ tag.label }}</el-tag>
                  <el-popover v-if="row.displayTags.length > 3" trigger="hover" :width="280" popper-class="cutover-text-tooltip">
                    <template #reference><button class="cutover-extra-tags" @click.stop :aria-label="$t('cutover.list.allTags')">+{{ row.displayTags.length - 3 }}</button></template>
                    <div class="cutover-all-tags"><el-tag v-for="tag in row.displayTags" :key="tag.key" :type="tag.type" size="small" effect="plain">{{ tag.label }}</el-tag></div>
                  </el-popover>
                </div>
                <el-tooltip :trigger="['hover', 'focus']" effect="light" placement="bottom-start" :show-after="300" :disabled="!row.content_summary" popper-class="cutover-text-tooltip">
                  <template #content><div class="cutover-tooltip-meta">{{ $t('cutover.list.contentSummary') }}</div><div class="cutover-tooltip-body">{{ row.content_summary }}</div></template>
                  <div class="cutover-snippet" tabindex="0">{{ row.content_summary || '-' }}</div>
                </el-tooltip>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.supplier')" width="85"><template #default="{ row }"><span class="cutover-supplier" :title="row.suppliers || ''">{{ row.suppliers || '-' }}</span></template></el-table-column>
          <el-table-column :label="$t('cutover.list.mailAddresses')" width="240">
            <template #default="{ row }"><div class="cutover-address"><span>{{ $t('cutover.list.from') }}</span><el-tooltip :trigger="['hover', 'focus']" :content="row.sender || '-'" effect="light" placement="bottom-start" :show-after="300" popper-class="cutover-text-tooltip"><span tabindex="0">{{ row.sender || '-' }}</span></el-tooltip></div><div class="cutover-address"><span>{{ $t('cutover.list.to') }}</span><el-tooltip :trigger="['hover', 'focus']" :content="mailboxLabel(row.receiver)" effect="light" placement="bottom-start" :show-after="300" popper-class="cutover-text-tooltip"><span tabindex="0">{{ mailboxLabel(row.receiver) }}</span></el-tooltip></div></template>
          </el-table-column>
          <el-table-column :label="$t('cutover.list.processingStatus')" width="155">
            <template #default="{ row }">
              <div class="cutover-processing">
                <el-tag v-if="row.unmatched_line_count" class="cutover-line-warning" type="warning" size="small" effect="light" :title="$t('cutover.list.unmatchedLinesHint')">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m12 3 10 18H2Z"/><path d="M12 9v4m0 4h.01"/></svg>
                  <span>{{ $t('cutover.list.unmatchedLines', { count: row.unmatched_line_count }) }}</span>
                </el-tag>
                <div v-for="state in row.displayStates" :key="state.key" class="cutover-state" :class="'is-' + state.type"><span>{{ state.label }}</span><span v-if="state.count" class="cutover-state-count">{{ state.count }}</span></div>
                <span v-if="row.task_count || row.displayStates[0].key !== 'no_task'" class="cutover-task-count">{{ row.task_count ? $t('cutover.list.taskCount', { count: row.task_count }) : $t('cutover.list.noTask') }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.receiveTime')" width="115"><template #default="{ row }"><time class="cutover-receive-time" :datetime="(row.create_time || '').slice(0, 19).replace(' ', 'T')">{{ (row.create_time || '').slice(0, 10) }}<span>{{ (row.create_time || '').slice(11, 19) }}</span></time></template></el-table-column>
          <el-table-column :label="$t('common.readState')" width="80" align="center" fixed="right">
            <template #default="{ row }">
              <div class="cutover-row-actions" @click.stop>
                <el-tooltip :trigger="['hover', 'focus']" :content="row.is_read ? $t('common.markAsUnread') : $t('common.markAsRead')" effect="light" popper-class="cutover-text-tooltip" :show-after="200">
                  <el-button text class="cutover-read-action" :class="{ 'is-read': row.is_read }" :type="row.is_read ? 'info' : 'primary'"
                             :aria-label="row.is_read ? $t('common.markAsUnread') : $t('common.markAsRead')"
                             :loading="readStateBusyIds.includes(row.id)" :disabled="readStateBusyIds.includes(row.id)"
                             @click.stop="toggleReadState(row)">
                    <svg v-if="!readStateBusyIds.includes(row.id)" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                      <template v-if="row.is_read"><path d="m3 9 9-6 9 6v11H3Z"/><path d="m3 9 9 6 9-6M3 20l6-7m12 7-6-7"/></template>
                      <template v-else><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 6 9 7 9-7"/></template>
                    </svg>
                  </el-button>
                </el-tooltip>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div class="cutover-pagination"><span>{{ $t('cutover.list.pageRange', { start: total ? (page - 1) * pageSize + 1 : 0, end: Math.min(page * pageSize, total), total }) }}</span><el-pagination v-model:current-page="page" v-model:page-size="pageSize" :page-sizes="[20, 50, 100]" :total="total" :pager-count="5" layout="sizes, prev, pager, next" :disabled="loading" @current-change="loadTasks" @size-change="changePageSize"></el-pagination></div>
      </el-card>
    </div>
  `,
});

// ==================== 割接模板列顺序（缓存） ====================
let cutoverTemplateColumns = null;

async function ensureCutoverTemplateColumns() {
  if (cutoverTemplateColumns === null) {
    try {
      cutoverTemplateColumns = await requestJson("/api/cutover/template-columns");
    } catch (error) {
      cutoverTemplateColumns = {};
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

// ==================== 割接任务详情面板 ====================
const TaskDetailPanel = defineComponent({
  name: "TaskDetailPanel",
  props: {
    task: { type: Object, required: true },
  },
  emits: ["changed", "collapse"],
  setup(props, { emit }) {
    const localTask = ref(props.task);
    const busy = ref(false);
    const reportImageUrls = reactive({});
    const reportProgressVisible = ref(false);
    const activeReport = ref(null);
    const reportProgressError = ref("");
    const reportImageLoadingKeys = new Set();
    const notifiedReportIds = new Set();
    let reportPollTimer = null;
    let disposed = false;

    const isBackbone = computed(() => localTask.value.line_type === "backbone");
    const fill = computed(() => localTask.value.fill_result || {});
    const validationMessages = computed(() => fill.value.validation_messages || []);

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
        ElMessage.error(tt("cutover.task.noEditableColumn"));
        return;
      }
      const row = {};
      for (const column of columns) {
        row[column] = "";
      }
      (kind === "circuit" ? circuitRows : reasonRows).value.push(row);
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

    function addBackboneCard() {
      if (!backboneCards.value.length) {
        ElMessage.error(tt("cutover.task.backboneNoStructure"));
        return;
      }
      const template = JSON.parse(JSON.stringify(backboneCards.value[0]));
      for (const fields of Object.values(template)) {
        for (const key of Object.keys(fields)) {
          fields[key] = null;
        }
      }
      template["割接对象"]["系统名称"] = [];
      backboneCards.value.push(template);
      backboneInterruptionMinutes.value.push(null);
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
        await ensureCutoverTemplateColumns();
        const circuits = currentFill.circuits || [];
        circuitColumns.value = orderSheetColumns("circuit", circuits.length ? Object.keys(circuits[0]) : []);
        circuitRows.value = circuits.map((row) => normalizeRow(row, circuitColumns.value));
        const reasons = currentFill.reasons || [];
        reasonColumns.value = orderSheetColumns("reason", reasons.length ? Object.keys(reasons[0]) : []);
        reasonRows.value = reasons.map((row) => normalizeRow(row, reasonColumns.value));
      }
      resumeReportProgress(task);
    }

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
        ElMessage.error(error.message);
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
      ElMessage.success(payload.message || fallbackMessage);
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
          ElMessage.success(tt("cutover.task.reportFinished"));
          setStatus(tt("cutover.task.reportFinished"));
        } else {
          const message = (report.result && report.result.error) || tt("cutover.task.reportFailed");
          ElMessage.error(message);
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
      if (report.result && report.result.error_code === "RPA_SESSION_REQUIRED") {
        ElMessage.warning(report.result.error || tt("dispatchSession.reportBlocked"));
        navigateTo("dispatchSession");
      }
    }

    async function pollReport(reportId) {
      if (disposed) {
        return;
      }
      try {
        const report = await requestJson(`/api/cutover/reports/${reportId}`);
        reportProgressError.value = "";
        activeReport.value = report;
        upsertReport(report);
        loadReportStepImages(report);
        if (["pending", "running"].includes(report.status)) {
          scheduleReportPoll(reportId);
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
        ["pending", "running"].includes(report.status)
      ));
      if (!active) {
        return;
      }
      activeReport.value = active;
      reportProgressVisible.value = true;
      startReportPolling(active.id, true);
    }

    async function reportTask() {
      let sessionError = null;
      const payload = await runAction(async () => {
        try {
          return await requestFull(`/api/cutover/tasks/${localTask.value.id}/report`, {
            method: "POST",
            body: JSON.stringify({
              environment: appStore.portalEnvironment || undefined,
            }),
          });
        } catch (error) {
          if (error.status === 409 && error.code === "RPA_SESSION_REQUIRED") {
            sessionError = error;
            return null;
          }
          throw error;
        }
      });
      if (sessionError) {
        ElMessage.warning(sessionError.message || tt("dispatchSession.reportBlocked"));
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
      ElMessage.success(payload.message || tt("cutover.task.reportSubmitted"));
      setStatus(payload.message || tt("cutover.task.reportSubmitted"));
      startReportPolling(report.id);
    }

    function downloadExcel() {
      window.open(`/api/cutover/tasks/${localTask.value.id}/excel`, "_blank");
    }

    // 按钮禁用规则与旧版一致
    const saveDisabled = computed(() => busy.value || localTask.value.status === "reporting");
    const confirmDisabled = computed(() => busy.value || localTask.value.status !== "draft");
    const reportDisabled = computed(() => {
      const status = localTask.value.status;
      return busy.value || !(status === "confirmed" || status === "report_failed");
    });
    const excelDisabled = computed(() => !localTask.value.customer_excel_filename);
    function clearReportImageUrls() {
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
          reportImageUrls[key] = await requestBlobUrl(`/api/rpa/report-artifacts/${artifactPath}`);
        } catch {
          return;
        } finally {
          reportImageLoadingKeys.delete(key);
        }
      }));
    }

    function reportImageUrl(reportId, index) {
      return reportImageUrls[operationImageKey(reportId, index)] || "";
    }

    onUnmounted(() => {
      disposed = true;
      if (reportPollTimer) {
        clearTimeout(reportPollTimer);
      }
      clearReportImageUrls();
    });

    return {
      localTask, busy, isBackbone, fill, validationMessages,
      circuitColumns, circuitRows, reasonColumns, reasonRows,
      addSheetRow, removeSheetRow, customerEnumOptions, customerColumnClass,
      backboneCards, backboneActive, addBackboneCard, removeBackboneCard,
      expandAllBackboneSections, collapseAllBackboneSections,
      orderedBackboneSections, orderedBackboneFields, controlKind, isWideField,
      isBackboneSystemField, isBackboneConfirmationField, backboneEnumOptions,
      handleBackboneEnumChange,
      saveEdit, switchType, confirmTask, reportTask, downloadExcel,
      saveDisabled, confirmDisabled, reportDisabled, excelDisabled,
      reportImageUrl, reportProgressVisible, activeReport, activeReportSteps,
      activeReportInProgress, reportProgressError, reportStatusType, reportStatusText,
      statusTagType, statusText, lineTypeText, taskLineCount,
      icons: ElementPlusIconsVue,
    };
  },
  template: `
    <div class="task-detail-panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">Cutover Task</p>
          <h3>{{ $t('cutover.task.heading', { id: localTask.id }) }}<span v-if="localTask.title"> - {{ localTask.title }}</span></h3>
        </div>
        <div class="panel-heading-tools">
          <el-tag v-if="localTask.cutover_scene === 'emergency'" type="danger" effect="dark" size="small">
            {{ $t('cutover.task.emergencyRejected') }}
          </el-tag>
          <el-button size="small" :icon="icons.ArrowUp" @click="$emit('collapse')">{{ $t('cutover.task.collapse') }}</el-button>
        </div>
      </div>

      <el-drawer v-model="reportProgressVisible"
                 :title="$t('cutover.task.reportProgressTitle')"
                 size="520px" direction="rtl" append-to-body
                 :modal="false" modal-penetrable :lock-scroll="false"
                 class="report-progress-drawer">
        <div v-if="activeReport" class="report-progress-content">
          <section class="report-progress-summary">
            <div class="report-progress-status-row">
              <el-tag :type="reportStatusType(activeReport.status)" effect="dark">
                {{ reportStatusText(activeReport.status) }}
              </el-tag>
              <span class="mono muted">#{{ activeReport.id }}</span>
            </div>
            <div class="report-progress-current">
              <el-icon v-if="activeReportInProgress" class="is-loading"><component :is="icons.Loading"></component></el-icon>
              <el-icon v-else-if="activeReport.status === 'success'" class="report-progress-success"><component :is="icons.CircleCheck"></component></el-icon>
              <el-icon v-else class="report-progress-danger"><component :is="icons.CircleClose"></component></el-icon>
              <div>
                <span>{{ $t('cutover.task.reportCurrentStep') }}</span>
                <strong>
                  {{ (activeReport.result && (activeReport.result.current_step_label || activeReport.result.note)) || $t('cutover.task.reportPreparing') }}
                </strong>
              </div>
            </div>
            <p>{{ $t('cutover.task.reportStepCount', { count: activeReportSteps.length }) }}</p>
          </section>

          <el-alert v-if="reportProgressError" type="warning" :closable="false" show-icon
                    :title="reportProgressError"></el-alert>

          <div v-if="!activeReportSteps.length" class="report-progress-empty">
            <el-icon class="is-loading"><component :is="icons.Loading"></component></el-icon>
            <span>{{ $t('cutover.task.reportWaitingForStep') }}</span>
          </div>
          <el-timeline v-else class="report-progress-timeline">
            <el-timeline-item v-for="(step, index) in activeReportSteps"
                              :key="activeReport.id + '-' + index"
                              :timestamp="step.captured_at || ''" placement="top"
                              type="primary">
              <article class="report-progress-step">
                <strong>{{ step.label || step.step }}</strong>
                <el-image v-if="reportImageUrl(activeReport.id, index)"
                          :src="reportImageUrl(activeReport.id, index)"
                          :preview-src-list="[reportImageUrl(activeReport.id, index)]"
                          fit="cover" preview-teleported></el-image>
                <div v-else class="report-progress-image-loading">
                  {{ $t('cutover.task.screenshotLoading') }}
                </div>
              </article>
            </el-timeline-item>
          </el-timeline>

          <p class="report-progress-hint">{{ $t('cutover.task.reportProgressHint') }}</p>
        </div>
      </el-drawer>

      <div class="task-meta-grid">
        <div class="task-meta-item">
          <span>{{ $t('common.status') }}</span>
          <el-tag :type="statusTagType(localTask.status)" effect="dark">
            {{ statusText(localTask.status, localTask.status_label) }}
          </el-tag>
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
          <strong>{{ localTask.confirmed_at || '-' }}</strong>
        </div>
        <div class="task-meta-item">
          <span>{{ $t('common.createTime') }}</span>
          <strong>{{ localTask.create_time || '-' }}</strong>
        </div>
        <div class="task-meta-item">
          <span>{{ $t('common.updateTime') }}</span>
          <strong>{{ localTask.update_time || '-' }}</strong>
        </div>
      </div>

      <div class="task-type-switch">
        <span class="muted">{{ $t('cutover.task.fillTypeLabel') }}</span>
        <el-radio-group :model-value="localTask.line_type" :disabled="localTask.status === 'reporting'"
                        @change="switchType">
          <el-radio-button value="customer">{{ $t('cutover.task.fillCustomer') }}</el-radio-button>
          <el-radio-button value="backbone">{{ $t('cutover.task.fillBackbone') }}</el-radio-button>
        </el-radio-group>
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
            <el-button size="small" @click="addSheetRow('circuit')">{{ $t('cutover.task.addRow') }}</el-button>
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
                    <el-select v-if="customerEnumOptions(column, row)"
                               v-model="row[column]" size="small" :aria-label="column" style="width: 100%"
                               :filterable="column === '预计影响客户业务时长'"
                               :allow-create="column === '预计影响客户业务时长'" default-first-option>
                      <el-option v-for="option in customerEnumOptions(column, row)" :key="option"
                                 :label="option" :value="option"></el-option>
                    </el-select>
                    <el-input v-else v-model="row[column]" size="small" :aria-label="column"></el-input>
                  </td>
                  <td>
                    <el-button link type="danger" size="small" @click="removeSheetRow('circuit', rowIndex)">{{ $t('common.delete') }}</el-button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="block-section">
          <div class="block-head">
            <span>{{ $t('cutover.task.reasonSheet') }}</span>
            <el-button size="small" @click="addSheetRow('reason')">{{ $t('cutover.task.addRow') }}</el-button>
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
                    <el-input v-model="row[column]" size="small"></el-input>
                  </td>
                  <td>
                    <el-button link type="danger" size="small" @click="removeSheetRow('reason', rowIndex)">{{ $t('common.delete') }}</el-button>
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
          <el-button size="small" @click="addBackboneCard">{{ $t('cutover.task.addBackbone') }}</el-button>
        </div>
        <p class="field-hint">{{ $t('cutover.task.backboneHint') }}</p>
        <p v-if="!backboneCards.length" class="empty-inline">{{ $t('cutover.task.backboneEmpty') }}</p>
        <div class="backbone-cards">
          <article v-for="(card, cardIndex) in backboneCards" :key="cardIndex" class="backbone-card">
            <div class="backbone-card-head">
              <strong>{{ $t('cutover.task.backboneCard', { index: cardIndex + 1 }) }}</strong>
              <div class="backbone-card-tools">
                <el-button link size="small" @click="expandAllBackboneSections">{{ $t('cutover.task.expandAll') }}</el-button>
                <el-button link size="small" @click="collapseAllBackboneSections">{{ $t('cutover.task.collapseAll') }}</el-button>
                <el-button size="small" @click="removeBackboneCard(cardIndex)">{{ $t('common.delete') }}</el-button>
              </div>
            </div>
            <el-collapse class="backbone-collapse"
                         :model-value="backboneActive[cardIndex] || []"
                         @update:model-value="(value) => (backboneActive[cardIndex] = value)">
              <template v-for="sectionName in orderedBackboneSections(card)" :key="sectionName">
                <el-collapse-item v-if="card[sectionName] && !Array.isArray(card[sectionName])"
                                  :title="sectionName" :name="sectionName">
                <div class="backbone-field-grid">
                  <label v-for="fieldName in orderedBackboneFields(sectionName, card[sectionName])"
                         :key="fieldName"
                         :class="{ 'backbone-field-wide': isWideField(cardIndex, sectionName, fieldName) }">
                    <span>{{ fieldName }}</span>
                    <div v-if="sectionName === '基本信息' && fieldName === '中断类型'"
                         class="backbone-interruption-control">
                      <el-select v-model="card[sectionName][fieldName]" class="backbone-enum-select"
                                 :aria-label="fieldName"
                                 @change="(value) => handleBackboneEnumChange(card, cardIndex, sectionName, fieldName, value)">
                        <el-option v-for="option in backboneEnumOptions(fieldName)"
                                   :key="option" :label="option" :value="option"></el-option>
                      </el-select>
                      <div v-if="card[sectionName]['中断类型'] === '中断'"
                           class="backbone-interruption-duration">
                        <input v-model="card[sectionName]['中断时间 (分钟)']"
                               class="backbone-input" inputmode="numeric" autocomplete="off"
                               aria-label="中断时间 (分钟)">
                        <span class="backbone-interruption-unit" aria-hidden="true">分钟</span>
                      </div>
                    </div>
                    <el-select v-else-if="isBackboneSystemField(sectionName, fieldName)"
                               v-model="card[sectionName][fieldName]" multiple filterable allow-create
                               default-first-option class="backbone-system-select"
                               placeholder="输入系统名称后回车">
                      <el-option v-for="systemName in card[sectionName][fieldName]"
                                 :key="systemName" :label="systemName" :value="systemName"></el-option>
                    </el-select>
                    <el-checkbox v-else-if="isBackboneConfirmationField(fieldName)"
                                 v-model="card[sectionName][fieldName]"
                                 true-label="是" false-label="否" class="backbone-confirmation-checkbox">
                      已选中
                    </el-checkbox>
                    <el-select v-else-if="backboneEnumOptions(fieldName)"
                               v-model="card[sectionName][fieldName]" class="backbone-enum-select"
                               :aria-label="fieldName"
                               @change="(value) => handleBackboneEnumChange(card, cardIndex, sectionName, fieldName, value)">
                      <el-option v-for="option in backboneEnumOptions(fieldName)"
                                 :key="option" :label="option" :value="option"></el-option>
                    </el-select>
                    <textarea v-else-if="controlKind(cardIndex, sectionName, fieldName) === 'textarea'"
                              v-model="card[sectionName][fieldName]" :rows="2" class="backbone-input"></textarea>
                    <input v-else v-model="card[sectionName][fieldName]" class="backbone-input">
                  </label>
                </div>
                </el-collapse-item>
              </template>
            </el-collapse>
          </article>
        </div>
      </div>

      <!-- 上报记录 -->
      <div class="block-section">
        <div class="block-head">
          <span>{{ $t('cutover.task.reports') }}</span>
          <el-button v-if="activeReport" size="small" :type="activeReportInProgress ? 'primary' : 'default'"
                     @click="reportProgressVisible = true">
            {{ $t('cutover.task.reportViewProgress') }}
          </el-button>
        </div>
        <el-table :data="localTask.reports || []" size="small" :empty-text="$t('cutover.task.reportsEmpty')">
          <el-table-column type="expand" width="48">
            <template #default="{ row }">
              <div class="report-operation-detail">
                <el-alert v-if="row.result && row.result.manual_intervention_required"
                          type="error" :closable="false" show-icon
                          :title="$t('cutover.task.manualIntervention')"></el-alert>
                <div v-if="row.result && row.result.portal_task_number" class="report-task-number">
                  <span>{{ $t('cutover.task.portalTaskNumber') }}</span>
                  <strong class="mono">{{ row.result.portal_task_number }}</strong>
                </div>
                <p v-if="row.result && row.result.error" class="report-error">{{ row.result.error }}</p>
                <div v-if="row.result && row.result.operation_log && row.result.operation_log.length"
                     class="report-operation-grid">
                  <article v-for="(step, index) in row.result.operation_log"
                           :key="row.id + '-' + index" class="report-operation-card">
                    <el-image v-if="reportImageUrl(row.id, index)"
                              :src="reportImageUrl(row.id, index)"
                              :preview-src-list="[reportImageUrl(row.id, index)]"
                              fit="cover" preview-teleported></el-image>
                    <div v-else class="report-image-missing">{{ $t('cutover.task.screenshotUnavailable') }}</div>
                    <strong>{{ step.label || step.step }}</strong>
                    <span class="mono muted">{{ step.captured_at || '' }}</span>
                  </article>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="id" label="ID" width="80">
            <template #default="{ row }">
              <span class="mono">{{ row.id }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.type')" width="100">
            <template #default="{ row }">
              <span>{{ row.report_type || 'all' }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.status')" width="120">
            <template #default="{ row }">
              <el-tag :type="reportStatusType(row.status)" size="small">
                {{ reportStatusText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="$t('cutover.task.reportNote')" min-width="260">
            <template #default="{ row }">
              <span class="muted">
                {{ (row.result && (row.result.note || row.result.error || row.result.portal_task_number)) || '-' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.time')" width="170">
            <template #default="{ row }">
              <span class="mono muted">{{ row.create_time || '' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="panel-actions">
        <el-button v-if="!isBackbone" :disabled="excelDisabled" @click="downloadExcel">{{ $t('cutover.task.downloadExcel') }}</el-button>
        <el-button :disabled="saveDisabled" @click="saveEdit">{{ $t('cutover.task.saveEdit') }}</el-button>
        <el-button :disabled="confirmDisabled" @click="confirmTask">{{ $t('cutover.task.manualConfirm') }}</el-button>
        <el-button type="primary" :disabled="reportDisabled" @click="reportTask">{{ $t('cutover.task.reportSubmit') }}</el-button>
      </div>
    </div>
  `,
});

// ==================== 割接邮件详情页 ====================
const ViewCutoverEmailDetail = defineComponent({
  name: "ViewCutoverEmailDetail",
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
    const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    const extractionDraft = ref("");
    const extractionBusy = ref(false);
    const manualBindings = reactive({});
    const manualBindingTypes = reactive({});
    const editingLineBindings = reactive({});
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

    async function saveExtraction(generate = false) {
      if (extractionBusy.value) return;
      extractionBusy.value = true;
      try {
        const payload = extractionPayload();
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
        email.value.extract_result = JSON.stringify(cleanExtraction(payload), null, 2);
        extractionDraft.value = email.value.extract_result;
        if (generate) {
          const result = await requestJson("/api/cutover/tasks/generate", {method: "POST", body: JSON.stringify(saved.fill_payload)});
          await loadDetail();
          if (!result.tasks?.length) {
            throw new Error((result.validation_messages || []).map((item) => item.message).join("；") || result.msg);
          }
        }
        ElMessage.success(tt(generate ? "cutover.detail.tasksGenerated" : "cutover.detail.extractionSaved"));
      } catch (error) {
        ElMessage.error(error.message);
      } finally {
        extractionBusy.value = false;
      }
    }

    function cleanExtraction(payload) {
      const result = JSON.parse(JSON.stringify(payload));
      for (const line of result.line_array || result.line_array_info?.data || []) {
        delete line.bound_circuit_id;
        delete line.bound_line_type;
      }
      return result;
    }

    async function bindLine(lineIndex) {
      if (extractionBusy.value) return;
      extractionBusy.value = true;
      try {
        const saved = await requestJson(`/api/cutover/emails/${props.emailRecordId}/line-bindings`, {
          method: "PUT",
          body: JSON.stringify({line_index: lineIndex, circuit_id: manualBindings[lineIndex] || "", line_type: manualBindingTypes[lineIndex] || "客户"}),
        });
        email.value.line_table = saved.line_table;
        email.value.fill_payload = saved.fill_payload;
        ElMessage.success(tt("cutover.detail.bindingSaved"));
      } catch (error) {
        ElMessage.error(error.message);
      } finally {
        extractionBusy.value = false;
      }
    }

    async function regenerateTasks() {
      if (extractionBusy.value) return;
      extractionBusy.value = true;
      try {
        const draft = extractionDraft.value;
        const result = await requestJson("/api/cutover/tasks/generate", {
          method: "POST", body: JSON.stringify({...email.value.fill_payload, email_records_id: props.emailRecordId}),
        });
        await loadDetail();
        extractionDraft.value = draft;
        if (!result.tasks?.length) {
          throw new Error((result.validation_messages || []).map((item) => item.message).join("；") || result.msg);
        }
        ElMessage.success(tt("cutover.detail.tasksGenerated"));
      } catch (error) {
        ElMessage.error(error.message);
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
      loading.value = true;
      expandedKeys.value = [];
      detailTask.value = null;
      try {
        email.value = await requestJson(`/api/cutover/emails/${props.emailRecordId}`);
        const extracted = Object.assign({}, ...extractJsonObjects(email.value.extract_result || ""));
        const payload = Object.keys(extracted).length ? extracted : (email.value.fill_payload || {});
        extractionDraft.value = JSON.stringify(cleanExtraction(payload), null, 2);
        Object.keys(editingLineBindings).forEach((key) => delete editingLineBindings[key]);
        Object.keys(manualBindings).forEach((key) => delete manualBindings[key]);
        Object.keys(manualBindingTypes).forEach((key) => delete manualBindingTypes[key]);
        (email.value.line_table?.lines || []).forEach((entry, index) => {
          manualBindings[index] = entry.line.bound_circuit_id || "";
          manualBindingTypes[index] = entry.line.bound_line_type || entry.circuits?.[0]?.line_type || "客户";
        });
        replyDraft.value = (email.value && email.value.pending_reply_content) || "";
        replyRecipients.value = recipientOptions.value.slice(0, 1);
        replyCcRecipients.value = (email.value.reply_cc_recipients || []).slice();
      } catch (error) {
        email.value = null;
        replyDraft.value = "";
        replyRecipients.value = [];
        replyCcRecipients.value = [];
        setStatus(error.message, "error");
      } finally {
        loading.value = false;
      }
    }

    // 人工确认发送待确认回复（发送前二次确认，内容与收件人可在页面上修改）
    async function confirmReply() {
      if (!replyDraft.value.trim()) {
        ElMessage.error(tt("cutover.detail.replyContentRequired"));
        return;
      }
      const recipients = replyRecipients.value.map((address) => String(address).trim()).filter(Boolean);
      if (!recipients.length) {
        ElMessage.error(tt("cutover.detail.replyRecipientsRequired"));
        return;
      }
      const invalid = recipients.find((address) => !EMAIL_PATTERN.test(address));
      if (invalid) {
        ElMessage.error(tt("cutover.detail.replyRecipientsInvalid", { address: invalid }));
        return;
      }
      const ccRecipients = replyCcRecipients.value.map((address) => String(address).trim()).filter(Boolean);
      const invalidCc = ccRecipients.find((address) => !EMAIL_PATTERN.test(address));
      if (invalidCc) {
        ElMessage.error(tt("cutover.detail.replyCcInvalid", { address: invalidCc }));
        return;
      }
      try {
        await ElMessageBox.confirm(
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
        ElMessage.success(tt("cutover.detail.replySent"));
        await loadDetail();
      } catch (error) {
        ElMessage.error(error.message);
      } finally {
        replyBusy.value = false;
      }
    }

    // 放弃待确认回复（不发送，不写入割接场景）
    async function cancelReply() {
      try {
        await ElMessageBox.confirm(
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
        ElMessage.success(tt("cutover.detail.replyCancelled"));
        await loadDetail();
      } catch (error) {
        ElMessage.error(error.message);
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
        ElMessage.success(tt("cutover.detail.apiForwardRetrySucceeded"));
        await loadDetail();
      } catch (error) {
        if (email.value && error.data && error.data.api_forward) {
          email.value.api_forward = error.data.api_forward;
        }
        ElMessage.error(error.message);
      } finally {
        apiForwardBusy.value = false;
      }
    }

    async function toggleReadState() {
      if (!email.value) {
        return;
      }
      readStateBusy.value = true;
      try {
        const data = await requestJson(`/api/cutover/emails/${props.emailRecordId}/read-state`, {
          method: "PATCH",
          body: JSON.stringify({ is_read: !email.value.is_read }),
        });
        email.value.is_read = Boolean(data.is_read);
        ElMessage.success(tt("common.readStateUpdated"));
      } catch (error) {
        ElMessage.error(error.message);
      } finally {
        readStateBusy.value = false;
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
    async function openTask(taskId) {
      try {
        detailTask.value = await requestJson(`/api/cutover/tasks/${taskId}`);
        expandedKeys.value = [taskId];
      } catch (error) {
        detailTask.value = null;
        expandedKeys.value = [];
        setStatus(error.message, "error");
      }
    }

    function closeTask() {
      expandedKeys.value = [];
      detailTask.value = null;
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
      email, loading, contentCollapsed, contentFrame, expandedKeys, detailTask,
      replyDraft, replyRecipients, replyBusy, recipientOptions, replyCcRecipients, confirmReply, cancelReply,
      apiForwardBusy, retryApiForward,
      readStateBusy, toggleReadState,
      extractResultBlocks, extractionDraft, extractionBusy, manualBindings, manualBindingTypes, editingLineBindings, isAutomaticLineMatch, toggleLineBindingEditor, selectCircuitCandidate, hasSavedManualBinding, matchedTypeCounts, saveExtraction, bindLine, regenerateTasks,
      loadDetail, onIframeLoad, toggleTask, closeTask, onExpandChange, onTaskChanged,
      statusTagType, statusText, mailboxLabel,
    };
  },
  template: `
    <div class="view-body" v-loading="loading">
      <nav class="supplier-context-bar" :aria-label="$t('common.pageLocation')">
        <el-button link class="supplier-back-link" :icon="icons.ArrowLeft" @click="goBack">{{ $t('cutover.detail.breadcrumbList') }}</el-button>
        <span class="supplier-context-separator" aria-hidden="true">/</span>
        <span class="supplier-context-current">{{ $t('cutover.detail.breadcrumbTitle') }}</span>
        <span v-if="email" class="supplier-context-detail">{{ email.subject || $t('cutover.detail.emailFallback', { id: email.email_id || email.id }) }}</span>
      </nav>

      <p v-if="!loading && !email" class="empty-inline">{{ $t('common.loadFailedBack') }}</p>

      <template v-if="email">
        <!-- 邮件 meta -->
        <div class="task-meta-grid">
          <div class="task-meta-item">
            <span>{{ $t('cutover.detail.emailUid') }}</span>
            <strong class="mono">{{ email.email_id || '-' }}</strong>
          </div>
          <div class="task-meta-item">
            <span>{{ $t('common.sender') }}</span>
            <strong>{{ email.sender || '-' }}</strong>
          </div>
          <div class="task-meta-item">
            <span>{{ $t('common.receiverMailbox') }}</span>
            <strong :title="email.receiver || ''">{{ mailboxLabel(email.receiver) }}</strong>
          </div>
          <div class="task-meta-item task-meta-item--timestamp">
            <span>{{ $t('common.receiveTime') }}</span>
            <strong class="mono">{{ email.create_time || '-' }}</strong>
          </div>
          <div class="task-meta-item">
            <span>{{ $t('common.readState') }}</span>
            <div class="mail-read-state-control" :class="email.is_read ? 'is-read' : 'is-unread'"
                 role="status" aria-live="polite" :aria-busy="readStateBusy">
              <span class="read-state-indicator">
                <span class="read-state-dot" aria-hidden="true"></span>
                <span class="read-state-text">{{ email.is_read ? $t('common.read') : $t('common.unread') }}</span>
              </span>
              <el-button class="read-state-toggle" link :loading="readStateBusy"
                         :disabled="readStateBusy"
                         @click="toggleReadState">
                {{ email.is_read ? $t('common.markAsUnread') : $t('common.markAsRead') }}
              </el-button>
            </div>
          </div>
        </div>

        <div class="api-forward-card"
             :class="'api-forward-' + (apiForwardBusy ? 'forwarding' : (email.api_forward.status || 'not_recorded'))"
             role="status" aria-live="polite" :aria-busy="apiForwardBusy">
          <div class="api-forward-main">
            <div class="api-forward-head">
              <strong>{{ $t('cutover.detail.apiForwardTitle') }}</strong>
              <el-tag :type="apiForwardBusy ? 'warning' : (email.api_forward.status === 'succeeded' ? 'success' : (email.api_forward.status === 'failed' ? 'danger' : (email.api_forward.status === 'forwarding' ? 'warning' : 'info')))"
                      size="small" effect="plain">
                {{ $t('cutover.detail.apiForwardStatus.' + (apiForwardBusy ? 'forwarding' : (email.api_forward.status || 'not_recorded'))) }}
              </el-tag>
              <span v-if="email.api_forward.updated_at" class="mono muted">
                {{ $t('cutover.detail.apiForwardTime', { time: email.api_forward.updated_at }) }}
              </span>
            </div>
            <p v-if="email.api_forward.error && !apiForwardBusy" class="api-forward-error" role="alert">
              <span>{{ $t('cutover.detail.apiForwardReason') }}</span>
              {{ email.api_forward.error }}
            </p>
          </div>
          <el-button v-if="email.api_forward.status === 'failed'" type="primary"
                     :loading="apiForwardBusy" :disabled="apiForwardBusy"
                     @click="retryApiForward">
            {{ $t('cutover.detail.apiForwardRetry') }}
          </el-button>
        </div>

        <!-- 待确认回复（FastGPT 登记草稿，人工确认后才发送） -->
        <div v-if="email.reply_status === 'pending'" class="reply-pending-card">
          <div class="reply-pending-head">
            <el-tag type="warning" effect="dark" size="small">{{ $t('cutover.detail.replyPendingTitle') }}</el-tag>
            <el-tag v-if="isRejectedScene(email.pending_reply_scene)"
                    :type="sceneTagType(email.pending_reply_scene)" effect="plain" size="small">
              {{ sceneText(email.pending_reply_scene, email.pending_reply_scene_label) }}
            </el-tag>
            <span class="muted">{{ $t('cutover.detail.replyPendingHint') }}</span>
          </div>
          <div class="reply-recipients">
            <span class="reply-recipients-label">
              <el-icon class="reply-recipients-icon"><Promotion /></el-icon>
              {{ $t('cutover.detail.replyRecipient') }}
            </span>
            <el-select v-model="replyRecipients" multiple filterable allow-create default-first-option
                       :placeholder="$t('cutover.detail.replyRecipientPlaceholder')" class="reply-recipients-select">
              <el-option v-for="addr in recipientOptions" :key="addr" :label="addr" :value="addr"></el-option>
            </el-select>
          </div>
          <div class="reply-recipients">
            <span class="reply-recipients-label">{{ $t('cutover.detail.replyCc') }}</span>
            <el-select v-model="replyCcRecipients" multiple filterable allow-create clearable default-first-option
                       :placeholder="$t('cutover.detail.replyCcPlaceholder')" class="reply-recipients-select">
              <el-option v-for="addr in replyCcRecipients" :key="addr" :label="addr" :value="addr"></el-option>
            </el-select>
          </div>
          <el-input v-model="replyDraft" type="textarea" :rows="4"
                    :placeholder="$t('cutover.detail.replyContentLabel')"></el-input>
          <div class="reply-pending-actions">
            <el-button :disabled="replyBusy" @click="cancelReply">{{ $t('cutover.detail.replyCancel') }}</el-button>
            <el-button type="primary" :loading="replyBusy" :disabled="!replyDraft.trim()" @click="confirmReply">
              {{ $t('cutover.detail.replyConfirmSend') }}
            </el-button>
          </div>
        </div>

        <!-- 割接场景提示（已回复拒绝割接时展示） -->
        <div v-if="isRejectedScene(email.cutover_scene)"
             class="scene-notice" :class="'scene-' + email.cutover_scene">
          <el-tag :type="sceneTagType(email.cutover_scene)" effect="dark" size="small">
            {{ sceneText(email.cutover_scene, email.cutover_scene_label) }}
          </el-tag>
          <span v-if="email.cutover_scene === 'emergency'">{{ $t('cutover.detail.sceneNoticeEmergency') }}</span>
          <span v-else-if="email.cutover_scene === 'major_event'">{{ $t('cutover.detail.sceneNoticeMajorEvent') }}</span>
          <span v-else-if="email.cutover_scene === 'in_window'">{{ $t('cutover.detail.sceneNoticeInWindow') }}</span>
          <span v-else-if="email.cutover_scene === 'rule_skipped'">{{ email.cutover_scene_remark || $t('cutover.detail.sceneNoticeRuleSkipped') }}</span>
          <span v-if="email.reply_time" class="mono muted">{{ email.reply_time }}</span>
        </div>

        <!-- 重复邮件提示 -->
        <div v-if="email.is_duplicate" class="scene-notice scene-duplicate">
          <el-tag type="info" effect="plain" size="small">{{ $t('cutover.tag.duplicate') }}</el-tag>
          <span>{{ $t('cutover.detail.duplicateNotice') }}</span>
        </div>

        <!-- 附件 -->
        <div v-if="(email.attachment_urls || []).length" class="attachment-list detail-attachments">
          <a v-for="(url, index) in email.attachment_urls" :key="url" :href="url"
             target="_blank" rel="noopener noreferrer">{{ $t('common.attachment', { index: index + 1 }) }}</a>
        </div>

        <!-- 邮件内容（默认收起） -->
        <el-collapse v-model="contentCollapsed" class="email-content-collapse">
          <el-collapse-item :title="$t('cutover.detail.emailContent')" name="content">
            <div class="email-content-body">
              <iframe v-if="email.html_content" ref="contentFrame" class="email-html-frame" sandbox="allow-same-origin"
                      :srcdoc="email.html_content" @load="onIframeLoad"></iframe>
              <pre v-else class="email-content-block">{{ email.content || $t('cutover.detail.noContent') }}</pre>
            </div>
          </el-collapse-item>
          <el-collapse-item :title="$t('cutover.detail.extractResult')" name="extract">
            <div class="extraction-panel">
              <div class="extraction-toolbar">
                <span class="extraction-format-label">JSON</span>
                <span>{{ $t('cutover.detail.extractionEditorHint') }}</span>
              </div>
              <el-input v-model="extractionDraft" type="textarea" :rows="16" :disabled="extractionBusy"
                        :aria-label="$t('cutover.detail.extractResult')" class="extraction-editor" spellcheck="false"></el-input>
              <div class="extraction-footer">
                <p class="extraction-footer-note">{{ $t('cutover.detail.extractionSaveHint') }}</p>
                <div class="extraction-actions">
                  <el-button :loading="extractionBusy" @click="saveExtraction()">{{ $t('cutover.detail.saveRematch') }}</el-button>
                  <el-button type="primary" :loading="extractionBusy" @click="saveExtraction(true)">{{ $t('cutover.detail.generateTasks') }}</el-button>
                </div>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>

        <!-- 线路表匹配结果 -->
        <div class="block-section">
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
            <div v-for="(line, lineIndex) in email.line_table.lines" :key="lineIndex" class="line-match-block">
              <div class="line-match-heading">
                <p class="cell-main">{{ $t('cutover.detail.lineEntry', { index: lineIndex + 1, keywords: (line.keywords || []).join('、') || '-' }) }}</p>
                <el-tooltip v-if="isAutomaticLineMatch(line)" :content="$t(editingLineBindings[lineIndex] ? 'cutover.detail.cancelMatchEdit' : 'cutover.detail.editMatch')" :trigger="['hover', 'focus']" placement="top">
                  <el-button text circle :icon="editingLineBindings[lineIndex] ? icons.Close : icons.Edit"
                             :disabled="extractionBusy" :aria-expanded="!!editingLineBindings[lineIndex]"
                             :aria-label="$t(editingLineBindings[lineIndex] ? 'cutover.detail.cancelMatchEdit' : 'cutover.detail.editMatch')"
                             @click="toggleLineBindingEditor(line, lineIndex)"></el-button>
                </el-tooltip>
              </div>
              <div v-if="!isAutomaticLineMatch(line) || editingLineBindings[lineIndex]" class="line-binding-controls">
                <el-select v-if="line.circuits && line.circuits.length > 1" v-model="manualBindings[lineIndex]"
                           class="line-binding-circuit-select" :disabled="extractionBusy" filterable allow-create clearable default-first-option
                           :placeholder="$t('cutover.detail.selectOrEnterCircuit')" aria-label="Circuit ID"
                           @change="selectCircuitCandidate(line, lineIndex, $event)">
                  <el-option v-for="(circuit, candidateIndex) in line.circuits" :key="candidateIndex"
                             :label="circuit.circuit_id || '-'" :value="circuit.circuit_id || ''" :disabled="!circuit.circuit_id">
                    <span class="line-candidate-id">{{ circuit.circuit_id || '-' }}</span>
                    <span class="line-candidate-type">{{ circuit.line_type || '-' }} · {{ circuit.line_status || '-' }}</span>
                  </el-option>
                </el-select>
                <el-input v-else v-model="manualBindings[lineIndex]" :disabled="extractionBusy"
                          :placeholder="$t('cutover.detail.bindCircuitPlaceholder')" aria-label="Circuit ID" clearable></el-input>
                <el-select v-model="manualBindingTypes[lineIndex]" :disabled="extractionBusy" class="line-binding-type"
                           :aria-label="$t('cutover.detail.bindingType')">
                  <el-option :label="$t('cutover.detail.bindCustomer')" value="客户"></el-option>
                  <el-option :label="$t('cutover.detail.bindBackbone')" value="骨干"></el-option>
                </el-select>
                <el-button :loading="extractionBusy" @click="bindLine(lineIndex)">{{ $t('cutover.detail.bindCircuit') }}</el-button>
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
              <el-table v-if="(line.circuits || []).length" :data="line.circuits" stripe>
                <el-table-column prop="supplier" label="Supplier" min-width="120">
                  <template #default="{ row }">
                    <span class="cell-main">{{ row.supplier || '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="Supplier Circuit ID" min-width="220">
                  <template #default="{ row }">
                    <span class="mono pre-wrap">{{ row.supplier_circuit_id || '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="Circuit ID" min-width="220">
                  <template #default="{ row }">
                    <span class="mono pre-wrap">{{ row.circuit_id || '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('circuits.lineType')" width="110">
                  <template #default="{ row }">
                    <span>{{ row.line_type || '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('circuits.lineStatus')" width="110">
                  <template #default="{ row }">
                    <span>{{ row.line_status || '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('common.remark')" min-width="160">
                  <template #default="{ row }">
                    <span class="muted pre-wrap">{{ row.remark || '-' }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
          <div v-if="hasSavedManualBinding" class="cutover-regenerate-footer">
            <div class="cutover-regenerate-summary">
              <span class="cell-main">{{ $t('cutover.detail.regenerateSummary', matchedTypeCounts) }}</span>
              <span class="muted">{{ $t('cutover.detail.regenerateHint') }}</span>
            </div>
            <el-button plain :loading="extractionBusy" @click="regenerateTasks">
              {{ $t('cutover.detail.regenerateTasks') }}
            </el-button>
          </div>
        </div>

        <!-- 任务列表 -->
        <div class="block-section">
          <div class="block-head">
            <span>{{ $t('cutover.detail.taskTitle', { count: (email.tasks || []).length }) }}</span>
          </div>
          <div v-if="!(email.tasks || []).length && email.cutover_scene === 'rule_skipped'"
               class="scene-notice scene-closed">
            <span>{{ $t('cutover.detail.taskRuleSkipped') }}</span>
          </div>
          <div v-else-if="!(email.tasks || []).length && isRejectedScene(email.cutover_scene)"
               class="scene-notice scene-closed">
            <span>{{ $t('cutover.detail.taskRejectedClosed', { scene: sceneText(email.cutover_scene, email.cutover_scene_label) }) }}</span>
          </div>
          <div v-else-if="!(email.tasks || []).length && email.is_duplicate"
               class="scene-notice scene-duplicate">
            <span>{{ $t('cutover.detail.taskDuplicateIgnored') }}</span>
          </div>
          <el-table v-else :data="email.tasks || []" :empty-text="$t('cutover.detail.taskEmpty')"
                    row-key="id" :expand-row-keys="expandedKeys" @expand-change="onExpandChange">
            <el-table-column type="expand">
              <template #default="{ row }">
                <task-detail-panel v-if="detailTask && detailTask.id === row.id"
                                   :task="detailTask" @changed="onTaskChanged"
                                   @collapse="closeTask"></task-detail-panel>
              </template>
            </el-table-column>
            <el-table-column prop="id" :label="$t('cutover.detail.taskId')" width="90">
              <template #default="{ row }">
                <span class="mono">{{ row.id }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('common.type')" min-width="160">
              <template #default="{ row }">
                <span class="cell-main">{{ lineTypeText(row) }} · {{ $t('cutover.task.lineCount', { count: taskLineCount(row) }) }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('common.supplier')" width="120">
              <template #default="{ row }">
                <span>{{ row.supplier || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('common.carrierTicketNo')" min-width="150">
              <template #default="{ row }">
                <span>{{ row.carrier_ticket_no || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('common.status')" width="110" align="center">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">
                  {{ statusText(row.status, row.status_label) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="$t('cutover.detail.validationColumn')" width="110">
              <template #default="{ row }">
                <span v-if="row.validation_count" class="warn-text">{{ $t('cutover.detail.validationCount', { count: row.validation_count }) }}</span>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('common.updateTime')" width="170">
              <template #default="{ row }">
                <span class="mono muted">{{ row.update_time || '' }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('common.actions')" width="110" align="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="toggleTask(row)">{{ $t('cutover.detail.taskDetail') }}</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </div>
  `,
  methods: {
    goBack() {
      navigateTo("cutoverTasks");
    },
  },
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
          ElMessage.success(tt("circuits.updated"));
        } else {
          await requestJson("/api/circuits", {
            method: "POST",
            body: JSON.stringify(payload),
          });
          ElMessage.success(tt("circuits.added"));
          if (!filtersActive()) {
            // 新记录按 id 追加在末尾，无筛选时跳到最后一页使其可见
            const probe = await requestJson(`/api/circuits?page=1&page_size=${CIRCUIT_PAGE_SIZE}`);
            page.value = Math.max(Math.ceil((probe.total || 0) / CIRCUIT_PAGE_SIZE), 1);
          }
        }
        dialogVisible.value = false;
        await loadCircuits();
      } catch (error) {
        ElMessage.error(error.message);
        setStatus(error.message, "error");
      } finally {
        saving.value = false;
      }
    }

    async function deleteCircuit(circuit) {
      const label = circuit.supplier_circuit_id || circuit.circuit_id || circuit.id;
      try {
        await ElMessageBox.confirm(
          tt("circuits.deleteConfirm", { label }),
          tt("circuits.deleteTitle"),
          { confirmButtonText: tt("common.confirmDelete"), cancelButtonText: tt("common.cancel"), type: "warning" },
        );
      } catch {
        return;
      }
      try {
        await requestJson(`/api/circuits/${circuit.id}`, { method: "DELETE" });
        ElMessage.success(tt("circuits.deleted"));
        await loadCircuits();
      } catch (error) {
        ElMessage.error(error.message);
      }
    }

    // 建议列表（el-autocomplete）
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
    const importDialogVisible = ref(false);
    const importFile = ref(null);
    const importFileList = ref([]);
    const importPreview = ref(null);
    const parsing = ref(false);
    const importing = ref(false);

    function openImportDialog() {
      importFile.value = null;
      importFileList.value = [];
      importPreview.value = null;
      importDialogVisible.value = true;
    }

    function resetImportFile() {
      importFile.value = null;
      importFileList.value = [];
      importPreview.value = null;
    }

    function onImportFileChange(uploadFile) {
      if (!uploadFile.name.toLowerCase().endsWith(".xlsx")) {
        ElMessage.warning(tt("circuits.fileInvalid"));
        resetImportFile();
        return;
      }
      importFile.value = uploadFile.raw || null;
      importPreview.value = null;
    }

    function onImportFileRemove() {
      importFile.value = null;
      importPreview.value = null;
    }

    function onImportFileExceed(files) {
      const file = (files || [])[0];
      if (!file) {
        return;
      }
      importFile.value = file;
      importFileList.value = [{ uid: Date.now(), name: file.name }];
      importPreview.value = null;
    }

    async function uploadImport(confirm) {
      if (!appStore.apiKey) {
        throw new Error(tt("common.apiKeyRequired"));
      }
      if (!importFile.value) {
        throw new Error(tt("circuits.fileRequired"));
      }
      const formData = new FormData();
      formData.append("file", importFile.value);
      if (confirm) {
        formData.append("confirm", "true");
      }
      const response = await fetch("/api/circuits/import", {
        method: "POST",
        headers: { Authorization: `Bearer ${appStore.apiKey}` },
        body: formData,
      });
      const payload = await response.json();
      if (!response.ok || payload.success === false) {
        throw new Error(payload.message || tt("circuits.importFailed"));
      }
      return payload.data;
    }

    async function parseImport() {
      parsing.value = true;
      try {
        importPreview.value = await uploadImport(false);
        ElMessage.success(tt("circuits.parsedSuccess", { total: importPreview.value.total }));
      } catch (error) {
        importPreview.value = null;
        ElMessage.error(error.message);
      } finally {
        parsing.value = false;
      }
    }

    async function confirmImport() {
      if (!importPreview.value) {
        return;
      }
      try {
        await ElMessageBox.confirm(
          tt("circuits.importConfirmMessage", { total: importPreview.value.total }),
          tt("circuits.importConfirmTitle"),
          {
            confirmButtonText: tt("circuits.confirmImport"),
            cancelButtonText: tt("common.cancel"),
            type: "warning",
          },
        );
      } catch {
        return;
      }
      importing.value = true;
      try {
        const result = await uploadImport(true);
        importDialogVisible.value = false;
        page.value = 1;
        await loadCircuits();
        ElMessage.success(tt("circuits.importSuccess", { total: result.total }));
      } catch (error) {
        ElMessage.error(error.message);
      } finally {
        importing.value = false;
      }
    }

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
      importDialogVisible, importFile, importFileList, importPreview, parsing, importing,
      openImportDialog, onImportFileChange, onImportFileRemove, onImportFileExceed,
      parseImport, confirmImport, exportCircuits,
    };
  },
  template: `
    <div class="view-body">
      <el-card shadow="never" class="table-card">
        <template #header>
          <div class="card-header">
            <div class="filter-bar">
              <el-select v-model="filters.supplier" :placeholder="$t('circuits.allSuppliers')" clearable filterable style="width: 160px">
                <el-option v-for="value in options.suppliers" :key="value" :label="value" :value="value"></el-option>
              </el-select>
              <el-select v-model="filters.lineType" :placeholder="$t('circuits.allTypes')" clearable filterable style="width: 140px">
                <el-option v-for="value in options.line_types" :key="value" :label="value" :value="value"></el-option>
              </el-select>
              <el-select v-model="filters.lineStatus" :placeholder="$t('circuits.allStatuses')" clearable filterable style="width: 140px">
                <el-option v-for="value in options.line_statuses" :key="value" :label="value" :value="value"></el-option>
              </el-select>
              <el-input v-model="filters.keyword" :placeholder="$t('circuits.keywordPlaceholder')"
                        clearable style="width: 240px" @keyup.enter="queryCircuits"></el-input>
              <el-button type="primary" @click="queryCircuits">{{ $t('common.query') }}</el-button>
              <el-button @click="resetFilters">{{ $t('common.reset') }}</el-button>
            </div>
            <div>
              <el-button :icon="icons.Upload" @click="openImportDialog">{{ $t('common.import') }}</el-button>
              <el-button :icon="icons.Download" @click="exportCircuits">{{ $t('common.export') }}</el-button>
              <el-button type="primary" :icon="icons.Plus" @click="openDialog()">{{ $t('circuits.add') }}</el-button>
            </div>
          </div>
        </template>
        <el-table v-loading="loading" :data="rows" :empty-text="$t('circuits.empty')" stripe>
          <el-table-column label="Supplier" min-width="120">
            <template #default="{ row }">
              <span class="cell-main">{{ row.supplier || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="Supplier Circuit ID" min-width="220">
            <template #default="{ row }">
              <span class="mono pre-wrap">{{ row.supplier_circuit_id || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="Circuit ID" min-width="220">
            <template #default="{ row }">
              <span class="mono pre-wrap">{{ row.circuit_id || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('circuits.lineType')" width="110">
            <template #default="{ row }">
              <span>{{ row.line_type || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('circuits.lineStatus')" width="110">
            <template #default="{ row }">
              <span>{{ row.line_status || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.remark')" min-width="160">
            <template #default="{ row }">
              <span class="muted pre-wrap">{{ row.remark || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.actions')" width="140" align="right" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDialog(row)">{{ $t('common.edit') }}</el-button>
              <el-button link type="danger" @click="deleteCircuit(row)">{{ $t('common.delete') }}</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pagination-bar">
          <span class="muted">{{ $t('common.totalItems', { total }) }}</span>
          <el-pagination layout="prev, pager, next" :total="total" :page-size="CIRCUIT_PAGE_SIZE"
                         :current-page="page" @current-change="onPageChange"></el-pagination>
        </div>
      </el-card>

      <!-- 新增/编辑弹窗 -->
      <el-dialog v-model="dialogVisible" :title="editingId ? $t('circuits.dialogEdit') : $t('circuits.dialogAdd')"
                 width="640px" :close-on-click-modal="false" destroy-on-close>
        <el-alert v-if="formAlert" type="error" :closable="false"
                  :title="$t('circuits.formAlert')" class="form-alert"></el-alert>
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
          <el-form-item label="Supplier" prop="supplier">
            <el-autocomplete v-model="form.supplier" :fetch-suggestions="suggestSupplier"
                             :placeholder="$t('circuits.supplierPlaceholder')" clearable style="width: 100%"></el-autocomplete>
          </el-form-item>
          <div class="field-grid-2">
            <el-form-item :label="$t('circuits.lineType')">
              <el-autocomplete v-model="form.line_type" :fetch-suggestions="suggestLineType"
                               :placeholder="$t('circuits.typePlaceholder')" clearable style="width: 100%"></el-autocomplete>
            </el-form-item>
            <el-form-item :label="$t('circuits.lineStatus')">
              <el-autocomplete v-model="form.line_status" :fetch-suggestions="suggestLineStatus"
                               :placeholder="$t('circuits.statusPlaceholder')" clearable style="width: 100%"></el-autocomplete>
            </el-form-item>
          </div>
          <el-form-item label="Supplier Circuit ID" prop="supplier_circuit_id">
            <el-input v-model="form.supplier_circuit_id" type="textarea" :rows="3" class="mono-input"
                      :placeholder="$t('circuits.supplierCircuitIdPlaceholder')"></el-input>
            <div class="field-hint">{{ $t('circuits.supplierCircuitIdHint') }}</div>
          </el-form-item>
          <el-form-item label="Circuit ID">
            <el-input v-model="form.circuit_id" type="textarea" :rows="4" class="mono-input"
                      :placeholder="$t('circuits.circuitIdPlaceholder')"></el-input>
            <div class="field-hint">{{ $t('circuits.circuitIdHint') }}</div>
          </el-form-item>
          <el-form-item :label="$t('common.remark')">
            <el-input v-model="form.remark" type="textarea" :rows="2"
                      :placeholder="$t('circuits.remarkPlaceholder')"></el-input>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
          <el-button type="primary" :loading="saving" @click="saveCircuit">{{ $t('circuits.saveCircuit') }}</el-button>
        </template>
      </el-dialog>

      <!-- 导入弹窗 -->
      <el-dialog v-model="importDialogVisible" :title="$t('circuits.importTitle')" width="820px"
                 class="circuits-import-dialog" :close-on-click-modal="false" destroy-on-close>
        <div class="import-hint-panel">
          <p class="import-hint-text">{{ $t('circuits.importHint') }}</p>
          <el-alert type="warning" :closable="false" show-icon :title="$t('circuits.importReplaceAlert')"
                    class="import-replace-alert"></el-alert>
        </div>
        <el-upload class="import-upload" drag :auto-upload="false" :limit="1" accept=".xlsx"
                   :file-list="importFileList" :on-change="onImportFileChange"
                   :on-remove="onImportFileRemove" :on-exceed="onImportFileExceed">
          <el-icon class="import-upload-icon"><UploadFilled /></el-icon>
          <p class="import-upload-text">{{ $t('circuits.uploadText') }}</p>
          <p class="import-upload-sub">{{ $t('circuits.uploadFormatHint') }}</p>
        </el-upload>
        <div class="import-actions">
          <el-button type="primary" :icon="icons.View" :loading="parsing" :disabled="!importFile" @click="parseImport">
            {{ $t('circuits.parsePreview') }}
          </el-button>
        </div>
        <div v-if="!importPreview" class="import-empty">
          <el-icon class="import-empty-icon"><Document /></el-icon>
          <p>{{ importFile ? $t('circuits.notParsed') : $t('circuits.noFile') }}</p>
          <span>{{ importFile ? $t('circuits.notParsedHint') : $t('circuits.noFileHint') }}</span>
        </div>
        <template v-else>
          <div class="import-summary">
            <div class="import-summary-item">
              <span class="import-summary-value">{{ importPreview.total }}</span>
              <span class="import-summary-label">{{ $t('circuits.summaryTotal') }}</span>
            </div>
            <div class="import-summary-item">
              <span class="import-summary-value">{{ (importPreview.rows || []).length }}</span>
              <span class="import-summary-label">{{ $t('circuits.summaryPreview') }}</span>
            </div>
            <div v-if="(importPreview.warnings || []).length" class="import-summary-item">
              <span class="import-summary-value import-summary-warn">{{ (importPreview.warnings || []).length }}</span>
              <span class="import-summary-label">{{ $t('circuits.summaryWarnings') }}</span>
            </div>
          </div>
          <div v-if="(importPreview.warnings || []).length" class="import-warnings">
            <p v-for="(warning, index) in importPreview.warnings" :key="index" class="warn-text">{{ warning }}</p>
          </div>
          <el-table :data="importPreview.rows || []" size="small" border max-height="360">
            <el-table-column prop="supplier" label="Supplier" min-width="100">
              <template #default="{ row }">
                <span>{{ row.supplier || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="Supplier Circuit ID" min-width="180">
              <template #default="{ row }">
                <span class="mono pre-wrap">{{ row.supplier_circuit_id || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="Circuit ID" min-width="180">
              <template #default="{ row }">
                <span class="mono pre-wrap">{{ row.circuit_id || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('circuits.lineType')" width="90">
              <template #default="{ row }">
                <span>{{ row.line_type || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('circuits.lineStatus')" width="100">
              <template #default="{ row }">
                <span>{{ row.line_status || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('common.remark')" min-width="140">
              <template #default="{ row }">
                <span class="muted pre-wrap">{{ row.remark || '-' }}</span>
              </template>
            </el-table-column>
          </el-table>
        </template>
        <template #footer>
          <el-button @click="importDialogVisible = false">{{ $t('common.cancel') }}</el-button>
          <el-button type="danger" :loading="importing" :disabled="!importPreview" @click="confirmImport">
            {{ $t('circuits.confirmImport') }}
          </el-button>
        </template>
      </el-dialog>
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

    function assignStatus(data) {
      status.state = data.state || "login_required";
      status.authenticated = Boolean(data.authenticated);
      status.checked_at = data.checked_at || "";
      status.message = data.message || "";
      status.configured = data.configured !== false;
      status.password_login_url = data.password_login_url || "";
      status.mobile_login_url = data.mobile_login_url || "";
      status.state_path = data.state_path || "";
      if (data.environment) {
        environment.value = data.environment;
        persistPortalEnvironment(data.environment);
      }
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
      ElMessage.error(error.message || tt("common.requestFailed"));
      setStatus(error.message || tt("common.requestFailed"), "error");
    }

    async function beginAttempt() {
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
      checking.value = true;
      status.state = "checking";
      status.message = tt("dispatchSession.checkingMessage");
      try {
        const query = environment.value
          ? `?environment=${encodeURIComponent(environment.value)}`
          : "";
        assignStatus(await requestJson(`/api/rpa/session${query}`));
        if (startLoginWhenRequired && !status.authenticated && status.configured) {
          await beginAttempt();
        }
      } catch (error) {
        status.state = "unavailable";
        status.authenticated = false;
        status.message = error.message || tt("common.requestFailed");
        showError(error);
      } finally {
        checking.value = false;
      }
    }

    async function refreshCaptcha() {
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
      mode.value = value;
      clearSensitiveForm();
      if (status.configured) {
        await beginAttempt();
      }
    }

    async function changeEnvironment(value) {
      if (environment.value === value) return;
      environment.value = value;
      persistPortalEnvironment(value);
      clearSensitiveForm();
      await loadStatus(true);
    }

    function requireBaseFields() {
      if (!form.account.trim() || !form.password || !form.captcha.trim()) {
        ElMessage.warning(tt("dispatchSession.completeFields"));
        return false;
      }
      return true;
    }

    async function requestSmsCode() {
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
        ElMessage.success(tt("dispatchSession.smsSent"));
      } catch (error) {
        showError(error);
      } finally {
        action.value = "";
      }
    }

    async function submitLogin() {
      if (!canSubmit.value) {
        ElMessage.warning(tt("dispatchSession.completeFields"));
        return;
      }
      action.value = "login";
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
        assignStatus(await requestJson(path, {
          method: "POST",
          body: JSON.stringify(body),
        }));
        clearSensitiveForm();
        ElMessage.success(tt("dispatchSession.loginSuccess"));
        setStatusKey("dispatchSession.loginSuccess");
      } catch (error) {
        showError(error);
        if (error.code === "LOGIN_FAILED") {
          await refreshCaptcha();
        }
      } finally {
        action.value = "";
      }
    }

    onMounted(() => loadStatus(true));

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
      <div class="dispatch-session-intro">
        <div>
          <h3>{{ $t('dispatchSession.title') }}</h3>
          <p>{{ $t('dispatchSession.subtitle') }}</p>
        </div>
      </div>

      <section class="dispatch-status-panel" :class="statusTone" aria-live="polite">
        <div class="dispatch-status-icon">
          <el-icon :class="{ 'is-spinning': checking }"><component :is="statusIcon" /></el-icon>
        </div>
        <div class="dispatch-status-copy">
          <span class="dispatch-status-environment">{{ environmentLabel }}</span>
          <h4>{{ statusTitle }}</h4>
          <p>{{ status.message }}</p>
        </div>
        <div class="dispatch-status-actions">
          <el-button :loading="checking" @click="loadStatus(false)">
            <el-icon><Refresh /></el-icon>{{ $t('dispatchSession.checkNow') }}
          </el-button>
          <el-button type="primary" :loading="action === 'begin'" :disabled="!status.configured" @click="beginAttempt">
            <el-icon><Key /></el-icon>{{ $t('dispatchSession.relogin') }}
          </el-button>
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
            <el-select class="dispatch-environment-select" :model-value="environment"
                       :aria-label="$t('dispatchSession.environmentTitle')"
                       :disabled="checking || action !== ''" @change="changeEnvironment">
              <el-option :label="$t('dispatchSession.environment.test')" value="test"></el-option>
              <el-option :label="$t('dispatchSession.environment.production')" value="production"></el-option>
            </el-select>
          </div>

          <div class="dispatch-mode-switch" role="radiogroup" :aria-label="$t('dispatchSession.loginMethod')">
            <button type="button" :class="{ 'is-active': mode === 'password' }"
                    role="radio" :aria-checked="mode === 'password'" :disabled="!status.configured" @click="changeMode('password')">
              <strong>{{ $t('dispatchSession.mode.password') }}</strong>
              <span>{{ $t('dispatchSession.mode.passwordHint') }}</span>
            </button>
            <button type="button" :class="{ 'is-active': mode === 'mobile' }"
                    role="radio" :aria-checked="mode === 'mobile'" :disabled="!status.configured" @click="changeMode('mobile')">
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
                <el-input v-model="form.account" :placeholder="mode === 'password' ? $t('dispatchSession.usernamePlaceholder') : $t('dispatchSession.phonePlaceholder')"
                          :autocomplete="mode === 'password' ? 'username' : 'tel'" clearable></el-input>
              </label>
              <label class="dispatch-field">
                <span>{{ $t('dispatchSession.password') }}</span>
                <el-input v-model="form.password" type="password" show-password autocomplete="current-password"
                          :placeholder="$t('dispatchSession.passwordPlaceholder')"></el-input>
              </label>
              <label class="dispatch-field dispatch-field--captcha">
                <span>{{ $t('dispatchSession.captcha') }}</span>
                <div class="dispatch-inline-field">
                  <el-input v-model="form.captcha" autocomplete="off" :placeholder="$t('dispatchSession.captchaPlaceholder')"></el-input>
                  <button class="dispatch-captcha-button" type="button" :disabled="action === 'captcha'" @click="refreshCaptcha">
                    <img v-if="attempt.captcha_data_url" :src="attempt.captcha_data_url" width="144" height="44"
                         :alt="$t('dispatchSession.captchaAlt')">
                    <span v-else>{{ $t('dispatchSession.loadCaptcha') }}</span>
                  </button>
                </div>
              </label>
              <label v-if="mode === 'mobile'" class="dispatch-field">
                <span>{{ $t('dispatchSession.smsCode') }}</span>
                <div class="dispatch-inline-field">
                  <el-input v-model="form.sms_code" autocomplete="one-time-code" :disabled="!smsRequested"
                            :placeholder="$t('dispatchSession.smsPlaceholder')"></el-input>
                  <el-button class="dispatch-sms-button" type="primary" plain :loading="action === 'sms'" @click="requestSmsCode">
                    {{ smsRequested ? $t('dispatchSession.resendSms') : $t('dispatchSession.sendSms') }}
                  </el-button>
                </div>
              </label>
            </div>
            <p class="dispatch-form-note">{{ $t('dispatchSession.captchaHint') }}</p>
            <div class="dispatch-form-actions">
              <el-button @click="clearSensitiveForm">{{ $t('dispatchSession.clear') }}</el-button>
              <el-button type="primary" native-type="submit" :loading="action === 'login'" :disabled="!canSubmit">
                {{ $t('dispatchSession.loginSubmit') }}
              </el-button>
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
        ElMessage.warning(tt("settings.backbonePersonnelRequired"));
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
        ElMessage.success(tt("settings.saved"));
        setStatusKey("settings.saved");
      } catch (error) {
        ElMessage.error(error.message);
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
    <div class="view-body" v-loading="loading">
      <div class="block-section">
        <div class="block-head">
          <span>{{ $t('settings.guardTitle') }}</span>
        </div>
        <p class="field-hint">{{ $t('settings.guardHint') }}</p>
        <el-form label-width="110px">
          <el-form-item :label="$t('settings.guardStart')">
            <el-date-picker v-model="guardStart" type="datetime" format="YYYY-MM-DD HH:mm:ss"
                            value-format="YYYY-MM-DD HH:mm:ss" :placeholder="$t('settings.guardStartPlaceholder')"
                            clearable style="width: 240px"></el-date-picker>
          </el-form-item>
          <el-form-item :label="$t('settings.guardEnd')">
            <el-date-picker v-model="guardEnd" type="datetime" format="YYYY-MM-DD HH:mm:ss"
                            value-format="YYYY-MM-DD HH:mm:ss" :placeholder="$t('settings.guardEndPlaceholder')"
                            clearable style="width: 240px"></el-date-picker>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="saving" @click="saveSettings">{{ $t('common.save') }}</el-button>
          </el-form-item>
        </el-form>
      </div>

      <div class="block-section">
        <div class="block-head">
          <span>{{ $t('settings.backbonePersonnelTitle') }}</span>
        </div>
        <p class="field-hint">{{ $t('settings.backbonePersonnelHint') }}</p>
        <el-form label-width="180px">
          <el-form-item :label="$t('settings.nocPhone')">
            <el-input v-model="nocPhone" :placeholder="$t('settings.nocPhonePlaceholder')"
                      style="width: 320px"></el-input>
          </el-form-item>
          <el-form-item :label="$t('settings.provinceReviewerName')">
            <el-input v-model="provinceReviewerName" :placeholder="$t('settings.provinceReviewerNamePlaceholder')"
                      style="width: 320px"></el-input>
          </el-form-item>
          <el-form-item :label="$t('settings.provinceReviewerPhone')">
            <el-input v-model="provinceReviewerPhone" :placeholder="$t('settings.provinceReviewerPhonePlaceholder')"
                      style="width: 320px"></el-input>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="saving" @click="saveSettings">{{ $t('common.save') }}</el-button>
          </el-form-item>
        </el-form>
      </div>

      <div class="block-section">
        <div class="block-head">
          <span>{{ $t('settings.languageTitle') }}</span>
        </div>
        <p class="field-hint">{{ $t('settings.languageHint') }}</p>
        <el-form label-width="110px">
          <el-form-item :label="$t('settings.languageLabel')">
            <el-select :model-value="currentLang" @change="changeLang" style="width: 240px">
              <el-option v-for="option in langOptions" :key="option.value"
                         :label="option.label" :value="option.value"></el-option>
            </el-select>
          </el-form-item>
        </el-form>
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
      return status.last_email_at || "";
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
          ElMessage.success(tt("mailAccounts.updated"));
        } else {
          await requestJson("/api/system/mail-accounts", {
            method: "POST",
            body: JSON.stringify(payload),
          });
          ElMessage.success(tt("mailAccounts.created"));
        }
        dialogVisible.value = false;
        await loadAccounts();
      } catch (error) {
        ElMessage.error(error.message);
        setStatus(error.message, "error");
      } finally {
        saving.value = false;
      }
    }

    async function removeAccount(account) {
      try {
        await ElMessageBox.confirm(
          tt("mailAccounts.deleteConfirm", { address: account.email_address }),
          tt("mailAccounts.deleteTitle"),
          { confirmButtonText: tt("common.confirmDelete"), cancelButtonText: tt("common.cancel"), type: "warning" },
        );
      } catch {
        return;
      }
      try {
        await requestJson(`/api/system/mail-accounts/${account.id}`, { method: "DELETE" });
        ElMessage.success(tt("mailAccounts.deleted"));
        await loadAccounts();
      } catch (error) {
        ElMessage.error(error.message);
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
        ElMessage.error(error.message);
      } finally {
        togglingId.value = null;
      }
    }

    async function testConnection(account) {
      testingId.value = account.id;
      try {
        const data = await requestJson(`/api/system/mail-accounts/${account.id}/test`, { method: "POST" });
        ElMessage.success(data && data.message ? data.message : tt("mailAccounts.testSuccess"));
      } catch (error) {
        ElMessage.error(error.message);
      } finally {
        testingId.value = null;
      }
    }

    async function testPreview() {
      // 保存前用当前表单配置测试连接（编辑时密码留空无法测试）
      if (!form.email_address.trim() || !form.imap_server.trim() || !form.email_password) {
        ElMessage.warning(tt("mailAccounts.testPreviewRequire"));
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
        ElMessage.success(data && data.message ? data.message : tt("mailAccounts.testSuccess"));
      } catch (error) {
        ElMessage.error(error.message);
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
      <div class="block-section">
        <div class="block-head">
          <span>{{ $t('mailAccounts.title') }}</span>
          <el-button type="primary" :icon="icons.Plus" @click="openDialog()">{{ $t('mailAccounts.add') }}</el-button>
        </div>
        <p class="field-hint">{{ $t('mailAccounts.hint') }}</p>

        <el-table :data="rows" class="data-table" :empty-text="$t('common.noData')">
          <el-table-column prop="name" :label="$t('mailAccounts.name')" min-width="140"></el-table-column>
          <el-table-column prop="email_address" :label="$t('mailAccounts.address')" min-width="200"></el-table-column>
          <el-table-column :label="$t('mailAccounts.imapTitle')" min-width="200">
            <template #default="{ row }">
              <span class="mono">{{ imapLabel(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('mailAccounts.statusColumn')" width="120">
            <template #default="{ row }">
              <el-tooltip v-if="accountStatus(row).error" :content="accountStatus(row).error" placement="top">
                <el-tag :type="accountStatus(row).type" size="small">{{ accountStatus(row).text }}</el-tag>
              </el-tooltip>
              <el-tag v-else :type="accountStatus(row).type" size="small">{{ accountStatus(row).text }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="$t('mailAccounts.lastEmailAt')" width="170">
            <template #default="{ row }">
              <span class="mono muted">{{ lastEmailAt(row) || $t('mailAccounts.neverReceived') }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('mailAccounts.enabledColumn')" width="110">
            <template #default="{ row }">
              <el-switch :model-value="row.enabled" :loading="togglingId === row.id"
                         :active-text="$t('mailAccounts.enabledText')" :inactive-text="$t('mailAccounts.disabledText')"
                         inline-prompt @change="toggleEnabled(row)"></el-switch>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.actions')" width="230" align="right" fixed="right">
            <template #default="{ row }">
              <div class="row-actions">
                <el-button link type="primary" :loading="testingId === row.id"
                           @click="testConnection(row)">{{ $t('mailAccounts.test') }}</el-button>
                <el-button link type="primary" @click="openDialog(row)">{{ $t('common.edit') }}</el-button>
                <el-button link type="danger" @click="removeAccount(row)">{{ $t('common.delete') }}</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 新建/编辑邮箱弹窗 -->
      <el-dialog v-model="dialogVisible" :title="editingId ? $t('mailAccounts.dialogEdit') : $t('mailAccounts.dialogAdd')"
                 width="640px" :close-on-click-modal="false" destroy-on-close>
        <el-alert v-if="formAlert" type="error" :closable="false"
                  :title="$t('mailAccounts.formAlert')" class="form-alert"></el-alert>
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
          <div class="field-grid-2">
            <el-form-item :label="$t('mailAccounts.name')" prop="name">
              <el-input v-model="form.name" :placeholder="$t('mailAccounts.namePlaceholder')" clearable></el-input>
            </el-form-item>
            <el-form-item :label="$t('mailAccounts.address')" prop="email_address">
              <el-input v-model="form.email_address" :placeholder="$t('mailAccounts.addressPlaceholder')" clearable></el-input>
            </el-form-item>
          </div>
          <el-form-item :label="$t('mailAccounts.password')" prop="email_password">
            <el-input v-model="form.email_password" type="password" show-password
                      :placeholder="editingId ? $t('mailAccounts.passwordKeep') : $t('mailAccounts.passwordPlaceholder')"></el-input>
          </el-form-item>

          <p class="field-hint">{{ $t('mailAccounts.imapTitle') }}</p>
          <div class="field-grid-2">
            <el-form-item :label="$t('mailAccounts.imapServer')" prop="imap_server">
              <el-input v-model="form.imap_server" :placeholder="$t('mailAccounts.imapServerPlaceholder')" clearable></el-input>
            </el-form-item>
            <el-form-item :label="$t('mailAccounts.imapPort')">
              <el-input-number v-model="form.imap_port" :min="1" :max="65535" style="width: 100%"></el-input-number>
            </el-form-item>
          </div>
          <el-form-item :label="$t('mailAccounts.imapSsl')">
            <el-switch v-model="form.imap_use_ssl"></el-switch>
          </el-form-item>

          <p class="field-hint">{{ $t('mailAccounts.smtpTitle') }}</p>
          <div class="field-grid-2">
            <el-form-item :label="$t('mailAccounts.smtpServer')">
              <el-input v-model="form.smtp_server" :placeholder="$t('mailAccounts.smtpServerPlaceholder')" clearable></el-input>
            </el-form-item>
            <el-form-item :label="$t('mailAccounts.smtpPort')">
              <el-input-number v-model="form.smtp_port" :min="1" :max="65535" style="width: 100%"></el-input-number>
            </el-form-item>
          </div>
          <div class="field-grid-2">
            <el-form-item :label="$t('mailAccounts.smtpSsl')">
              <el-switch v-model="form.smtp_use_ssl"></el-switch>
            </el-form-item>
            <el-form-item :label="$t('mailAccounts.smtpTls')">
              <el-switch v-model="form.smtp_use_tls"></el-switch>
            </el-form-item>
          </div>
        </el-form>
        <template #footer>
          <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
          <el-button :loading="previewing" :disabled="Boolean(editingId) && !form.email_password"
                     @click="testPreview">{{ $t('mailAccounts.test') }}</el-button>
          <el-button type="primary" :loading="saving" @click="saveAccount">{{ $t('common.save') }}</el-button>
        </template>
      </el-dialog>
    </div>
  `,
  computed: {
    icons() {
      return ElementPlusIconsVue;
    },
  },
});
