// Native readFiles output is matched to requested URLs. Missing/failed files are
// explicit evidence gaps, not empty documents that the model may assume it read.
function main({originMail, documents = [], parseError = ''}) {
  const mail = JSON.parse(originMail);
  const names = Array.isArray(mail.attachments) ? mail.attachments : [];
  const urls = Array.isArray(mail.attachment_urls) ? mail.attachment_urls : [];
  const parsed = Array.isArray(documents) ? documents : [];
  const attachment_documents = [], attachment_issues = [];
  let remaining = 120000;
  for (let index = 0; index < Math.max(names.length, urls.length); index++) {
    const url = urls[index];
    const filename = String(names[index] || url || '未命名附件');
    if (typeof url !== 'string' || !url.trim()) {
      attachment_issues.push({filename, reason:'附件缺少下载地址，未读取'});
      continue;
    }
    // PDF pages and images remain on the existing multimodal path.
    if (/\.(pdf|png|jpe?g|webp|gif)$/i.test(filename.split('?')[0])) continue;
    const result = parsed.find(item => item && item.url === url);
    const rawText = result && typeof result.text === 'string' ? result.text : '';
    const wrapped = rawText.match(/<Content>([\s\S]*?)<\/Content>/);
    const contentText = (wrapped ? wrapped[1] : rawText).trim();
    // Older readFiles versions put transport failures in text, without error.
    const legacyError = /^(?:Request failed with status code [45]\d\d|timeout of \d+ms exceeded|(?:connect|read) (?:ECONNREFUSED|ECONNRESET|ETIMEDOUT)[^\n]*|getaddrinfo ENOTFOUND[^\n]*)$/.test(contentText);
    const readable = !parseError && result && !result.error && result.success !== false && !legacyError && contentText;
    const text = readable ? result.text.slice(0, remaining) : '';
    remaining -= text.length;
    const status = !readable ? 'failed' : text.length < result.text.length ? 'truncated' : 'parsed';
    attachment_documents.push({filename, url, status, text});
    if (status !== 'parsed') {
      attachment_issues.push({filename, reason:status === 'truncated'
        ? '附件正文超出本次处理长度，只有部分内容可读'
        : '附件未成功解析（可能下载失败、不支持、加密、空文件或超过解析限制），不得视为已阅读'});
    }
  }
  const enriched = {...mail, attachment_documents, attachment_issues,
    attachment_reading_note:attachment_issues.length
      ? '存在未完整读取的附件。结合正文判断缺失内容是否影响分类、完整割接窗口或草稿规则；不能凭文件名断言无关，也不得假装已阅读。'
      : '正文与 attachment_documents 中的附件文本均为分析材料；PDF 和图片通过图片输入提供。'};
  const enriched_mail = JSON.stringify(enriched);
  const draft_text = enriched_mail;
  if (mail.task_type === 'unconfigured_mail_process') delete enriched.fixed_field_defaults;
  return {enriched_mail, draft_text, mail_text:JSON.stringify(enriched)};
}

if (typeof module !== 'undefined') module.exports = {main};
