function strictDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return null;
  const number = Date.parse(value);
  if (Number(value.slice(11,13)) > 23 || Number(value.slice(14,16)) > 59 || Number(value.slice(17,19)) > 59) return null;
  if (!Number.isFinite(number)) return null;
  const parts = value.slice(0, 10).split('-').map(Number);
  const calendar = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
  if (calendar.getUTCFullYear() !== parts[0] || calendar.getUTCMonth() !== parts[1] - 1 || calendar.getUTCDate() !== parts[2]) return null;
  return number;
}

function formatBeijingTime(value) {
  return new Date(Date.parse(value) + 8 * 3600000).toISOString().slice(0, 19).replace('T', ' ');
}

function analyzeWindow(mail, extraction, now) {
  const base = {
    analysis_status: 'needs_review', scene: null, reply: null,
    cutover_start: null, cutover_end: null, security_window: null,
    source_timezone: extraction.source_timezone || null,
    source_time_text: extraction.source_time_text || null,
    assessed_at: new Date(now).toISOString(), hours_until_start: null,
    reason: extraction.reason || '时间或时区证据不足，请人工核对原文',
  };
  const windows = extraction.windows;
  const unread = Array.isArray(mail.attachment_issues) ? mail.attachment_issues.length > 0
    : (mail.attachments || []).some(name => !/\.(pdf|png|jpe?g|webp|gif)$/i.test(name));
  if (unread && !(extraction.unread_attachments_irrelevant === true &&
      typeof extraction.unread_attachments_reason === 'string' && extraction.unread_attachments_reason.trim())) {
    return {...base, reason:'邮件包含未完整解析的附件，尚不能排除其影响完整时间窗口，请人工核对'};
  }
  if (extraction.needs_review !== false || !Array.isArray(windows) || windows.length !== 1 || !base.source_timezone || !base.source_time_text) return base;
  const start = strictDate(windows[0].start), end = strictDate(windows[0].end);
  if (start === null || end === null || start > end) return {...base, reason:'时间格式无效或窗口倒置，请人工核对'};
  const hours = (start - now) / 3600000;
  let scene = start <= now ? 'in_window' : hours <= 72 ? 'emergency' : 'normal';
  let securityWindow = null;
  if (mail.securityTime) {
    const parts = mail.securityTime.split('/');
    if (mail.security_timezone !== 'Asia/Shanghai' || parts.length !== 2) return {...base, reason:'重保窗口配置或时区无效，请人工核对'};
    const asOffset = text => /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(text) ? text.replace(' ', 'T') + '+08:00' : text;
    const a = asOffset(parts[0]), b = asOffset(parts[1]);
    const guardStart = strictDate(a), guardEnd = strictDate(b);
    if (guardStart === null || guardEnd === null || guardStart > guardEnd) return {...base, reason:'重保窗口时间无效，请人工核对'};
    if (start <= guardEnd && end >= guardStart) {
      scene = 'major_event';
      securityWindow = {start:a, end:b};
    }
  }
  const reasons = {
    major_event:'割接窗口与重保窗口相交', in_window:end < now ? '判定时割接已开始且窗口已结束' : '判定时已进入割接窗口',
    emergency:`判定时距割接开始 ${hours.toFixed(2)} 小时，未超过 72 小时阈值`, normal:'割接时间有效，未命中紧急、重保或已开始条件',
  };
  const replies = {
    major_event:'您好，本次割接安排在重保期间，请调整割接时间，并重新发送割接通知。谢谢。',
    in_window:'您好，收到通知时已进入本次割接窗口，请确认当前实施情况，并提前提供后续割接安排。谢谢。',
    emergency:'您好，本次割接通知距离开始时间不足约定的提前通知期限，请调整割接时间，并提前发送正式通知。谢谢。',
  };
  return {...base, analysis_status:'ready', scene, cutover_start:windows[0].start, cutover_end:windows[0].end,
    hours_until_start:hours, security_window:securityWindow, reason:reasons[scene],
    reply:scene === 'normal' ? null : {content:(typeof REPLY_TEMPLATES !== 'undefined' ? REPLY_TEMPLATES[scene] : replies[scene])
      .split('__UNCONFIGURED_GUARD_START__').join(securityWindow ? formatBeijingTime(securityWindow.start) : '')
      .split('__UNCONFIGURED_GUARD_END__').join(securityWindow ? formatBeijingTime(securityWindow.end) : '')
      .split(String.fromCharCode(92) + 'n').join(String.fromCharCode(10))}};
}

function main({originMail, answer, now}) {
  const mail = JSON.parse(originMail);
  const cleaned = answer.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
  let result = JSON.parse(cleaned);
  if (mail.task_type === 'cutover_time_extract') result = analyzeWindow(mail, result, now === undefined ? Date.now() : now);
  if (!['unconfigured_mail_analyze','supplier_config_draft','cutover_time_extract'].includes(mail.task_type)) throw new Error('未知任务类型');
  const envelope = {schema_version:1, task_type:mail.task_type, request_id:mail.request_id,
    attempt_id:mail.attempt_id, email_records_id:mail.email_records_id, result};
  return {result_json:JSON.stringify(envelope), envelope};
}

if (typeof module !== 'undefined') module.exports = {main, analyzeWindow, strictDate};
