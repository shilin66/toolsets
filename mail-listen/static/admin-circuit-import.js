/* Circuit import state; uploads remain local until preview/confirmation. */
function useCircuitImport(onImported) {
  const { ref, computed, watch } = Vue;
  const importDialogVisible = ref(false);
  const importMode = ref('append');
  const importFile = ref(null);
  const importFileList = ref([]);
  const importPreview = ref(null);
  const importResult = ref(null);
  const parsing = ref(false);
  const importing = ref(false);
  const downloadingTemplate = ref(false);
  const importFilter = ref('all');
  const importPage = ref(1);
  let revision = 0;
  const importBusy = computed(() => parsing.value || importing.value);
  const importData = computed(() => importResult.value || importPreview.value);
  const importStep = computed(() => importResult.value ? 3 : importPreview.value ? 2 : 1);
  const importFilteredRows = computed(() => (importData.value?.rows || []).filter(row => {
    if (importFilter.value === 'all') return true;
    if (importFilter.value === 'review') return row.needs_review;
    if (importFilter.value === 'new') return ['new', 'inserted'].includes(row.status);
    return row.status === importFilter.value;
  }));
  const importVisibleRows = computed(() => importFilteredRows.value.slice((importPage.value - 1) * 50, importPage.value * 50));
  const canConfirmImport = computed(() => Boolean(importPreview.value && !importResult.value && !importBusy.value &&
    (importMode.value === 'replace' || (importPreview.value.counts?.new > 0 && importPreview.value.counts?.errors === 0))));
  watch(importFilter, () => { importPage.value = 1; });
  watch(importDialogVisible, value => { if (!value) revision += 1; });

  function clearImportPreview() {
    revision += 1;
    importPreview.value = null;
    importResult.value = null;
    importFilter.value = 'all';
    importPage.value = 1;
  }
  function resetImportFile() {
    clearImportPreview();
    importFile.value = null;
    importFileList.value = [];
  }
  function openImportDialog(mode = 'append') {
    if (importBusy.value) return;
    resetImportFile();
    importMode.value = mode;
    importDialogVisible.value = true;
  }
  function onImportFileChange(uploadFile) {
    clearImportPreview();
    const file = uploadFile.raw;
    if (!uploadFile.name.toLowerCase().endsWith('.xlsx') || !file || file.size > 10 * 1024 * 1024) {
      NocMessage.warning(tt('circuits.importFileLimit'));
      resetImportFile();
      return;
    }
    importFile.value = file;
  }
  function onImportFileExceed(files) {
    const file = (files || [])[0];
    if (!file) return;
    const uploadFile = { uid: Date.now(), name: file.name, raw: file };
    onImportFileChange(uploadFile);
    if (importFile.value) importFileList.value = [uploadFile];
  }
  async function uploadImport(confirm) {
    if (!importFile.value) throw new Error(tt('circuits.fileRequired'));
    const formData = new FormData();
    formData.append('file', importFile.value);
    formData.append('mode', importMode.value);
    if (confirm) {
      formData.append('confirm', 'true');
      if (importPreview.value?.preview_token) formData.append('preview_token', importPreview.value.preview_token);
    }
    const response = await fetch('/api/circuits/import', {
      method: 'POST', headers: { 'X-CSRF-Token': appStore.csrfToken }, body: formData,
    });
    const payload = await response.json();
    if (!response.ok || payload.success === false) {
      const error = new Error(payload.message || tt('circuits.importFailed'));
      error.preview = payload.data;
      error.stale = response.status === 409;
      throw error;
    }
    return payload.data;
  }
  async function parseImport() {
    if (importBusy.value) return;
    clearImportPreview();
    const currentRevision = revision;
    parsing.value = true;
    try {
      const data = await uploadImport(false);
      if (currentRevision === revision && importDialogVisible.value) importPreview.value = data;
    } catch (error) {
      if (currentRevision === revision) NocMessage.error(error.message);
    } finally {
      parsing.value = false;
    }
  }
  async function confirmImport() {
    if (!canConfirmImport.value) return;
    importing.value = true;
    try {
      if (importMode.value === 'replace') {
        try {
          await NocDialog.confirm(tt('circuits.importConfirmMessage', { total: importPreview.value.total }),
            tt('circuits.importConfirmTitle'), { confirmButtonText: tt('circuits.confirmImport'),
              cancelButtonText: tt('common.cancel'), type: 'warning' });
        } catch { return; }
      }
      const data = await uploadImport(true);
      if (importMode.value === 'append') {
        importResult.value = data;
        importFilter.value = 'all';
        importPage.value = 1;
        NocMessage.success(tt('circuits.appendSuccess', { inserted: data.inserted, skipped: data.counts.skipped }));
      } else {
        importDialogVisible.value = false;
        NocMessage.success(tt('circuits.importSuccess', { total: data.total }));
      }
      await onImported();
    } catch (error) {
      importPreview.value = error.preview || null;
      importFilter.value = 'all';
      importPage.value = 1;
      NocMessage.error(error.stale ? tt('circuits.previewChanged') : error.message);
    } finally {
      importing.value = false;
    }
  }
  function saveWorkbook(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function downloadImportTemplate() {
    if (downloadingTemplate.value) return;
    downloadingTemplate.value = true;
    try {
      const response = await fetch('/api/circuits/template');
      if (!response.ok) throw new Error((await response.json()).message || tt('common.requestFailed'));
      saveWorkbook(await response.blob(), '线路导入模板_v1.xlsx');
    } catch (error) { NocMessage.error(error.message); }
    finally { downloadingTemplate.value = false; }
  }
  function downloadImportResult() {
    if (!importResult.value?.report_base64) return;
    const bytes = Uint8Array.from(atob(importResult.value.report_base64), c => c.charCodeAt(0));
    saveWorkbook(new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), '线路增量导入结果.xlsx');
  }
  function importStatusType(row) {
    return row.status === 'error' ? 'danger' : row.needs_review ? 'warning' : ['new', 'inserted'].includes(row.status) ? 'success' : 'info';
  }
  return { importDialogVisible, importMode, importFile, importFileList, importPreview, importResult,
    parsing, importing, downloadingTemplate, importBusy, importData, importStep, importFilter, importPage,
    importFilteredRows, importVisibleRows, canConfirmImport, openImportDialog, onImportFileChange,
    onImportFileRemove: resetImportFile, onImportFileExceed, resetImportFile, parseImport, confirmImport,
    downloadImportTemplate, downloadImportResult, importStatusType };
}
