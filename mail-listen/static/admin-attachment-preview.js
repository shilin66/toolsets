/* Offline attachment review within the current email's mailbox permissions. */
const attachmentPreviewMessages = {
  'zh-CN': {title:'邮件附件', preview:'预览', download:'下载', body:'返回邮件正文', loading:'正在读取附件…',
    failed:'附件预览失败，请重试或下载查看。', retry:'重新预览', empty:'附件内容为空',
    partial:'当前显示部分内容，完整内容请下载原文件。', sheet:'工作表', rows:'当前显示 {count} 行',
    unavailable:'浏览器无法显示时，请下载查看。'},
  en: {title:'Email attachments',preview:'Preview',download:'Download',body:'Back to email body',loading:'Loading attachment…',
    failed:'Could not preview the attachment. Retry or download it.',retry:'Retry preview',empty:'The attachment is empty.',
    partial:'Showing partial content. Download the original for the complete file.',sheet:'Worksheet',rows:'Showing {count} rows',
    unavailable:'Download the file if your browser cannot display it.'},
  'zh-HK': {title:'郵件附件',preview:'預覽',download:'下載',body:'返回郵件正文',loading:'正在讀取附件…',
    failed:'附件預覽失敗，請重試或下載查看。',retry:'重新預覽',empty:'附件內容為空',
    partial:'目前顯示部分內容，完整內容請下載原檔案。',sheet:'工作表',rows:'目前顯示 {count} 行',
    unavailable:'瀏覽器無法顯示時，請下載查看。'},
};
for (const [locale,messages] of Object.entries(attachmentPreviewMessages)) i18n.global.mergeLocaleMessage(locale,{attachmentPreview:messages});

function useMailAttachmentPreview(email, localFiles = null) {
  const {ref,computed,watch,onUnmounted} = Vue;
  const selectedAttachment = ref(null), attachmentData = ref(null), attachmentBusy = ref(false), attachmentError = ref('');
  let request = 0, controller;
  const attachments = computed(() => (email.value?.attachment_urls || []).map((url,index) => {
    let path='', name='';
    try {
      const parsed = new URL(url, location.href);
      if (parsed.pathname.startsWith('/api/email/attachments/')) path = parsed.pathname;
      name = decodeURIComponent(parsed.pathname.split('/').pop() || '').replace(/^[a-f0-9]{32}-/i, '');
    } catch { /* Missing metadata must not prevent reading the email. */ }
    return {index,path,name:name || tt('cw.attachment',{index:index+1}),type:(name.split('.').pop() || 'FILE').toUpperCase()};
  }).concat((localFiles?.value || []).map(file => ({index:'local-'+file.uid, raw:file.raw, name:file.name, path:'', type:(file.name.split('.').pop() || 'FILE').toUpperCase()}))));
  function release() {
    if (attachmentData.value?.blobUrl) URL.revokeObjectURL(attachmentData.value.blobUrl);
    attachmentData.value = null;
  }
  function closeAttachment() {
    request++; controller?.abort(); release();
    selectedAttachment.value=null; attachmentBusy.value=false; attachmentError.value='';
  }
  async function openAttachment(item) {
    if (!item || (!item.raw && !email.value)) return;
    const current=++request, mailId=email.value?.id;
    controller?.abort(); controller=new AbortController(); release();
    selectedAttachment.value=item; attachmentBusy.value=true; attachmentError.value='';
    try {
      let data;
      if (item.raw) {
        const body=new FormData(); body.append('file',item.raw,item.name);
        data=await requestJson('/api/suppliers/preview-attachment-content',{method:'POST',body,signal:controller.signal});
      } else {
        data=await requestJson(`/api/cutover/emails/${mailId}/attachments/${item.index}/preview`,{signal:controller.signal});
      }
      if (current!==request) return;
      if (['image','pdf'].includes(data.kind)) {
        if (!item.raw && !item.path) throw new Error(tt('attachmentPreview.failed'));
        data.blobUrl=item.raw ? URL.createObjectURL(item.raw) : await requestBlobUrl(item.path);
        if (current!==request) {URL.revokeObjectURL(data.blobUrl);return;}
      }
      attachmentData.value=data;
    } catch(error) {
      if(current===request && error.name!=='AbortError') attachmentError.value=error.status===404 ? tt('attachmentPreview.failed') : error.message || tt('attachmentPreview.failed');
    } finally {if(current===request) attachmentBusy.value=false;}
  }
  watch(()=>email.value?.id,closeAttachment);
  watch(attachments,items=>{if(selectedAttachment.value && !items.some(item=>item.index===selectedAttachment.value.index)) closeAttachment();});
  onUnmounted(closeAttachment);
  return {attachments,selectedAttachment,attachmentData,attachmentBusy,attachmentError,openAttachment,closeAttachment};
}

const MailAttachmentList = Vue.defineComponent({
  props:{items:{type:Array,default:()=>[]},selected:Object,busy:Boolean},emits:['preview','remove'],
  setup() { return {downloadLocal(item) { const url=URL.createObjectURL(item.raw); const link=document.createElement('a'); link.href=url; link.download=item.name; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000); }}; },
  template:`<section v-if="items.length" class="cw-attachment-list">
    <h3>{{ $t('attachmentPreview.title') }} <span>{{ items.length }}</span></h3>
    <div v-for="item in items" :key="item.index" class="cw-attachment-row" :class="{selected:selected?.index===item.index}">
      <span class="cw-file-type">{{ item.type }}</span><span class="cw-file-name" :title="item.name">{{ item.name }}</span>
      <ui-button size="small" :loading="busy && selected?.index===item.index" :aria-label="$t('attachmentPreview.preview')+' '+item.name" @click="$emit('preview',item)">{{ $t('attachmentPreview.preview') }}</ui-button>
      <a v-if="item.path" :href="item.path" :download="item.name" :aria-label="$t('attachmentPreview.download')+' '+item.name">{{ $t('attachmentPreview.download') }}</a>
      <ui-button v-if="item.raw" text size="small" @click="downloadLocal(item)">{{ $t('attachmentPreview.download') }}</ui-button>
      <ui-button v-if="item.raw" text size="small" :aria-label="$t('common.delete')+' '+item.name" @click="$emit('remove',item)">{{ $t('common.delete') }}</ui-button>
    </div>
  </section>`,
});

const MailAttachmentPreview = Vue.defineComponent({
  props:{item:Object,data:Object,busy:Boolean,error:String},emits:['close','retry'],
  setup(props) {
    const sheet=Vue.ref(0);
    Vue.watch(()=>props.data,()=>{sheet.value=0;});
    const activeSheet=Vue.computed(()=>props.data?.sheets?.[sheet.value]);
    return {sheet,activeSheet};
  },
  template:`<section class="cw-attachment-preview" :aria-busy="busy">
    <div class="cw-preview-heading"><ui-button text size="small" @click="$emit('close')">← {{ $t('attachmentPreview.body') }}</ui-button><strong :title="item?.name">{{ item?.name }}</strong></div>
    <p v-if="busy" role="status" class="cw-preview-state">{{ $t('attachmentPreview.loading') }}</p>
    <div v-else-if="error" role="alert" class="cw-preview-state"><p>{{ error }}</p><ui-button size="small" @click="$emit('retry',item)">{{ $t('attachmentPreview.retry') }}</ui-button></div>
    <template v-else-if="data">
      <p v-if="data.truncated" class="cw-preview-note" role="status">{{ $t('attachmentPreview.partial') }}</p>
      <p v-if="data.note" class="cw-preview-note">{{ data.note }}</p>
      <div v-if="data.kind==='table'" class="cw-preview-content">
        <div class="cw-sheet-bar"><label v-if="data.sheets.length>1">{{ $t('attachmentPreview.sheet') }} <select v-model.number="sheet"><option v-for="(entry,index) in data.sheets" :key="index" :value="index">{{ entry.name }}</option></select></label><span>{{ $t('attachmentPreview.rows',{count:activeSheet?.rows?.length || 0}) }}</span></div>
        <div v-if="activeSheet?.columns.length" class="cw-attachment-table" tabindex="0"><table><thead><tr><th scope="col">#</th><th v-for="(column,index) in activeSheet.columns" :key="index" scope="col">{{ column || '—' }}</th></tr></thead><tbody><tr v-for="(row,index) in activeSheet.rows" :key="index"><th scope="row">{{ index+1 }}</th><td v-for="(_,column) in activeSheet.columns" :key="column">{{ row[column] ?? '' }}</td></tr></tbody></table></div>
        <p v-else class="cw-preview-state">{{ $t('attachmentPreview.empty') }}</p>
      </div>
      <pre v-else-if="data.kind==='text'" class="cw-preview-text">{{ data.text || $t('attachmentPreview.empty') }}</pre>
      <div v-else-if="data.kind==='document'" class="cw-preview-document"><template v-for="(block,index) in data.blocks" :key="index"><p v-if="block.kind==='text'">{{ block.text }}</p><div v-else class="cw-attachment-table" tabindex="0"><table><tbody><tr v-for="(row,rowIndex) in block.rows" :key="rowIndex"><td v-for="(cell,colIndex) in row" :key="colIndex">{{ cell }}</td></tr></tbody></table></div></template><p v-if="!data.blocks.length">{{ $t('attachmentPreview.empty') }}</p></div>
      <div v-else-if="data.kind==='image'" class="cw-preview-image"><img :src="data.blobUrl" :alt="item.name"></div>
      <object v-else-if="data.kind==='pdf'" :key="data.blobUrl" class="cw-preview-pdf" type="application/pdf" :data="data.blobUrl+'#toolbar=0&navpanes=0&view=FitH'" :aria-label="item.name"><p class="cw-preview-state">{{ $t('attachmentPreview.unavailable') }}</p></object>
    </template>
  </section>`,
});
