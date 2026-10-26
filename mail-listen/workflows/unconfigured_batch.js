function parseBranch(answer, error, validate) {
  if (error) return {status:'failed', error:'模型节点执行失败，请重试此分支'};
  try {
    if (typeof answer !== 'string' || !answer.trim()) throw new Error('模型没有返回结果');
    const result = JSON.parse(answer.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, ''));
    if (!result || typeof result !== 'object' || Array.isArray(result)) throw new Error('模型结果不是 JSON 对象');
    if (validate) validate(result);
    return {status:'succeeded', result};
  } catch (err) {
    return {status:'failed', error:'分支结果无效：' + String(err.message).slice(0, 300)};
  }
}

function planCombined({originMail, answer = '', error = '', now}) {
  const mail = JSON.parse(originMail);
  if (mail.task_type !== 'unconfigured_mail_process') {
    if (error) throw new Error('模型节点执行失败');
    return {...main({originMail, answer, now}), run_time:false, run_draft:false, state:{legacy:true}};
  }
  for (const key of ['should_generate_supplier_draft','should_analyze_cutover_time']) {
    if (typeof mail[key] !== 'boolean') throw new Error(key + ' 必须是布尔值');
  }
  const classification = parseBranch(answer, error, result => {
    if (!['割接通知','割接改期','割接取消','割接提醒','故障邮件','其它'].includes(result.mail_type) ||
        typeof result.needs_review !== 'boolean' || typeof result.classification_reason !== 'string') {
      throw new Error('邮件分类结构无效');
    }
  });
  const notice = classification.status === 'succeeded' && classification.result.mail_type === '割接通知';
  return {state:{classification}, run_time:notice && mail.should_analyze_cutover_time,
    run_draft:notice && mail.should_generate_supplier_draft};
}

function finishCombined({originMail, state, legacyResult, timeAnswer = '', timeError = '', draftAnswer = '', draftError = '', now}) {
  const mail = JSON.parse(originMail);
  if (mail.task_type !== 'unconfigured_mail_process') {
    return {result_json:legacyResult, envelope:JSON.parse(legacyResult)};
  }
  const result = {classification:state.classification, time_analysis:{status:'skipped'}, supplier_draft:{status:'skipped'}};
  if (state.classification.status === 'succeeded' && state.classification.result.mail_type === '割接通知') {
    if (mail.should_analyze_cutover_time === true) {
      result.time_analysis = parseBranch(timeAnswer, timeError);
      if (result.time_analysis.status === 'succeeded') {
        try {
          result.time_analysis.result = analyzeWindow(mail, result.time_analysis.result, now === undefined ? Date.now() : now);
        } catch (_) {
          result.time_analysis = {status:'failed', error:'时间分析结果无效，请重试时间分支'};
        }
      }
    }
    if (mail.should_generate_supplier_draft === true) {
      result.supplier_draft = parseBranch(draftAnswer, draftError);
    }
  }
  const envelope = {schema_version:1, task_type:mail.task_type, request_id:mail.request_id,
    attempt_id:mail.attempt_id, email_records_id:mail.email_records_id, result};
  return {result_json:JSON.stringify(envelope), envelope};
}

if (typeof module !== 'undefined') module.exports = {parseBranch, planCombined, finishCombined};
