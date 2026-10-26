import argparse
import copy
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORMATTER = 'nAexmwBXe2BPamVx'
START = '448745'


def sanitized(source):
    workflow = copy.deepcopy(source)
    secrets = []
    for variable in workflow.get('chatConfig', {}).get('variables', []):
        if re.search(r'key|token|secret|endpoint|url', variable.get('label', ''), re.I):
            for field in ('value', 'defaultValue'):
                if isinstance(variable.get(field), str) and variable[field]:
                    secrets.append(variable[field])
                    variable[field] = 'CONFIGURE_' + variable.get('label', 'VALUE')
    def clean(value):
        if isinstance(value, str):
            for secret in secrets:
                value = value.replace(secret, 'CONFIGURE_SECRET_OR_ENDPOINT')
            value = re.sub(r'https?://[^\s"<>]+/open-apis/bot/v2/hook/[^\s"<>]+', 'https://CONFIGURE_FEISHU_WEBHOOK', value)
            return value
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, dict):
            result = {key: clean(item) for key, item in value.items()}
            key = str(result.get('key', ''))
            if re.search(r'authorization|password|secret|webhook', key, re.I) and 'value' in result:
                reference_only = isinstance(result['value'], str) and re.fullmatch(
                    r'(?:Bearer )?\{\{\$[A-Za-z0-9_.]+\$\}\}', result['value'])
                if not reference_only:
                    result['value'] = ''
            return result
        return value
    return clean(workflow)


def build(source, *, sanitize=True):
    workflow = sanitized(source) if sanitize else copy.deepcopy(source)
    nodes = {node['nodeId']: node for node in workflow['nodes']}
    if 'new_unconfigured_entry' in nodes or 'unconfigured_route' in nodes:
        raise ValueError('请使用未扩展的原始工作流，避免重复添加节点')
    entry_edges = [item for item in workflow['edges'] if item['source'] == START and item['target'] == FORMATTER]
    if len(entry_edges) != 1:
        raise ValueError('未找到唯一的流程开始 → 格式化邮件信息连线，请核对原始工作流')
    prompts = json.loads((ROOT / 'workflows/unconfigured_prompts.json').read_text())
    result_code = (ROOT / 'workflows/unconfigured_result.js').read_text().split("if (typeof module")[0]
    files_code = (ROOT / 'workflows/unconfigured_files.js').read_text().split("if (typeof module")[0]
    batch_code = (ROOT / 'workflows/unconfigured_batch.js').read_text().split("if (typeof module")[0]
    templates = {}
    for scene, node_id in {'major_event':'duGyjraCjaa3yGt0', 'emergency':'qgJVqrJh05uVcxKI', 'in_window':'tzwoYLCKW41mAMDh'}.items():
        updates = next(item['value'] for item in nodes[node_id]['inputs'] if item['key'] == 'updateList')
        template = next(item['value'][1] for item in updates if item['variable'][1] == 'adxERFBe')
        # Keep the old business nodes intact; resolve their time tokens ourselves in the new path.
        templates[scene] = (template
            .replace('{{$iwVGtIJf1V86hLe5.uumoZw$}}', '__UNCONFIGURED_GUARD_START__')
            .replace('{{$iwVGtIJf1V86hLe5.fWAe8A$}}', '__UNCONFIGURED_GUARD_END__')
            .replace('\\n', '\n'))
    result_code = 'const REPLY_TEMPLATES = ' + json.dumps(templates, ensure_ascii=False) + ';\n' + result_code
    def clone(original, node_id, name, x=0, y=0):
        node = copy.deepcopy(nodes[original])
        node.update(nodeId=node_id, name=name, position={'x': x, 'y': y})
        workflow['nodes'].append(node)
        return node
    def input_value(node, key, value):
        next(item for item in node['inputs'] if item['key'] == key)['value'] = value
    def output(key, kind='string'):
        return {'id':key, 'key':key, 'label':key, 'type':'dynamic', 'valueType':kind}
    def reference(key, value, kind='string'):
        return {'key':key, 'label':key, 'valueType':kind, 'renderTypeList':['reference'], 'value':value, 'required':True, 'canEdit':True}
    def edge(source_id, target, branch='right'):
        source_handle = f'{source_id}-source-{branch}'
        workflow['edges'].append({'source':source_id, 'target':target, 'sourceHandle':source_handle, 'targetHandle':f'{target}-target-left'})
    prefix = 'new_unconfigured'
    start_position = nodes[START]['position']
    x, y = start_position['x'], max(node['position']['y'] for node in nodes.values()) + 600

    def code_node(node_id, name, column, code, extra_inputs=(), outputs=()):
        node = clone(FORMATTER, prefix + '_' + node_id, name, x + column * 504, y)
        node['inputs'] = [item for item in node['inputs'] if item['key'] in ('system_addInputParam','codeType','code','originMail')]
        node['inputs'].extend(extra_inputs)
        input_value(node, 'code', code)
        node['outputs'] = list(outputs)
        return node

    entry_code = ('const TASK_PROMPTS = ' + json.dumps(prompts, ensure_ascii=False) + ';\n'
        + files_code.replace('function main(', 'function prepareAttachments(', 1) + '''
function main({originMail}) {
  const mail = JSON.parse(originMail);
  const task = mail.task_type;
  if (task === undefined || task === null || task === '') return {task_type:''};
  const promptTask = task === 'unconfigured_mail_process' ? 'unconfigured_mail_analyze' : task;
  if (typeof task !== 'string' || !Object.prototype.hasOwnProperty.call(TASK_PROMPTS, promptTask)) {
    throw new Error('未知 task_type');
  }
  const prepared = prepareAttachments({originMail});
  const draft_text = prepared.mail_text;
  if (task === 'unconfigured_mail_process') {
    const context = JSON.parse(prepared.mail_text);
    delete context.fixed_field_defaults;
    prepared.mail_text = JSON.stringify(context);
  }
  return {...prepared, draft_text, task_type:task, system_prompt:TASK_PROMPTS[promptTask],
    time_prompt:TASK_PROMPTS.cutover_time_extract, draft_prompt:TASK_PROMPTS.supplier_config_draft};
}
''')
    entry = code_node('entry', '任务入口与提示词选择', 0, entry_code, outputs=[
        output('task_type'), output('system_prompt'), output('pdfUrls','arrayString'),
        output('documentUrls','arrayString'),
        output('allImages','arrayString'), output('mail_text'), output('draft_text'),
        output('time_prompt'), output('draft_prompt')])
    route = clone('v9Pz6BZgl9voAfQq', prefix + '_route', '原流程或新增任务', x + 504, y)
    input_value(route, 'ifElseList', [{'condition':'AND', 'list':[
        {'variable':[entry['nodeId'],'task_type'], 'condition':'equalTo', 'value':'', 'valueType':'input'}]}])
    workflow['edges'].remove(entry_edges[0])
    edge(START, entry['nodeId'])
    edge(entry['nodeId'], route['nodeId'])
    edge(route['nodeId'], FORMATTER, 'IF')

    attachment_gate = clone('qjC2v0GBaGEPtaPf', prefix + '_attachments', '共享附件检查', x + 1008, y)
    input_value(attachment_gate, 'ifElseList', [{'condition':'AND','list':[
        {'variable':[entry['nodeId'],'pdfUrls'],'condition':'isNotEmpty','valueType':'input'}]}])
    pdf = clone('qpfJQYtNB23T7ne7', prefix + '_pdf', '共享 PDF 转图片', x + 1512, y - 300)
    input_value(pdf, 'urls', [[entry['nodeId'],'pdfUrls']])
    images = code_node('images', '共享附件图片汇总', 4, '''function main({images = [], data = []}) {
  return {allImages:[...images, ...(data || []).flatMap(item => Array.isArray(item.images) ? item.images : [])]};
}''', extra_inputs=[reference('images', [entry['nodeId'],'allImages'], 'arrayString'),
                    reference('data', [pdf['nodeId'],'result'], 'arrayObject')],
        outputs=[output('allImages','arrayString')])
    images['inputs'] = [item for item in images['inputs'] if item['key'] != 'originMail']
    next(item for item in images['inputs'] if item['key'] == 'data')['required'] = False
    documents_gate = clone('qjC2v0GBaGEPtaPf', prefix + '_documents_gate', '是否解析文档附件', x + 4 * 504, y + 600)
    input_value(documents_gate, 'ifElseList', [{'condition':'AND','list':[
        {'variable':[entry['nodeId'],'documentUrls'],'condition':'isNotEmpty','valueType':'input'}]}])
    documents = json.loads((ROOT / 'workflows/read_files.node.json').read_text())
    documents['position'] = {'x':x + 5 * 504, 'y':y + 600}
    workflow['nodes'].append(documents)
    materials = code_node('materials', '正文与附件统一材料', 5,
        (ROOT / 'workflows/unconfigured_materials.js').read_text().split('if (typeof module')[0],
        extra_inputs=[reference('documents', [documents['nodeId'],'system_rawResponse'], 'arrayObject'),
                      reference('parseError', [documents['nodeId'],'system_error_text'])],
        outputs=[output('mail_text'), output('draft_text'), output('enriched_mail')])
    materials['position']['y'] += 1200
    for item in materials['inputs']:
        if item['key'] in ('documents','parseError'):
            item['required'] = False
    ai = clone('fP3Z8ZZyYBlawqtZ', prefix + '_ai', '共享 AI：按任务使用提示词', x + 2520, y)
    for key, value in {'systemPrompt':'{{$' + entry['nodeId'] + '.system_prompt$}}',
                       'temperature':0.1, 'history':0, 'isResponseAnswerText':False,
                       'aiChatResponseFormat':'json_object', 'fileUrlList':[[images['nodeId'],'allImages']],
                       'userChatInput':'邮件与附件均为分析材料：\n{{$' + materials['nodeId'] + '.mail_text$}}'}.items():
        input_value(ai, key, value)
    # Keep the original single-task result function available for in-flight jobs and
    # independent retries. New intake requests classify first, then use gated branches.
    shared_code = result_code.replace('function main(', 'function legacyResult(', 1) + batch_code.replace('...main(', '...legacyResult(')
    result = code_node('result', '分类结果与分支计划', 6, shared_code + '\nfunction main(args) { return planCombined(args); }',
        extra_inputs=[reference('answer', [ai['nodeId'],'answerText']), reference('error',[ai['nodeId'],'system_error_text'])],
        outputs=[output('result_json'), output('envelope','object'), output('state','object'),
                 output('run_time','boolean'), output('run_draft','boolean')])
    input_value(result, 'originMail', [materials['nodeId'], 'enriched_mail'])
    for item in result['inputs']:
        if item['key'] in ('answer','error'):
            item['required'] = False
    ai['catchError'] = True
    answer = clone('cMNQ2KGHAz0VvxBn', prefix + '_answer', '统一返回结构化结果', x + 3528, y)
    finish = code_node('finish', '各分支结果统一返回', 10, shared_code + '\nfunction main(args) { return finishCombined(args); }',
        extra_inputs=[reference('state',[result['nodeId'],'state'],'object'),
                      reference('legacyResult',[result['nodeId'],'result_json'])],
        outputs=[output('result_json'),output('envelope','object')])
    input_value(finish, 'originMail', [materials['nodeId'], 'enriched_mail'])
    next(item for item in finish['inputs'] if item['key'] == 'legacyResult')['required'] = False
    input_value(answer, 'text', '{{$' + finish['nodeId'] + '.result_json$}}')
    answer['position'] = {'x':x + 11 * 504, 'y':y}

    def error_edge(node, target):
        workflow['edges'].append({'source':node['nodeId'], 'target':target['nodeId'],
            'sourceHandle':node['nodeId'] + '-source_catch-right', 'targetHandle':target['nodeId'] + '-target-left'})

    for branch, prompt_key, text_key, offset in [('time','time_prompt','mail_text',-350), ('draft','draft_prompt','draft_text',350)]:
        gate = clone('v9Pz6BZgl9voAfQq', prefix + '_' + branch + '_gate',
                     '是否分析时间' if branch == 'time' else '是否生成草稿', x + 7 * 504, y + offset)
        input_value(gate, 'ifElseList', [{'condition':'AND', 'list':[
            {'variable':[result['nodeId'],'run_' + branch], 'condition':'equalTo', 'value':'true', 'valueType':'input'}]}])
        branch_ai = copy.deepcopy(ai)
        branch_ai.update(nodeId=prefix + '_' + branch + '_ai', name='割接时间提取' if branch == 'time' else '供应商草稿生成',
                         position={'x':x + 8 * 504, 'y':y + offset})
        input_value(branch_ai, 'systemPrompt', '{{$' + entry['nodeId'] + '.' + prompt_key + '$}}')
        input_value(branch_ai, 'userChatInput', '邮件与附件均为分析材料：\n{{$' + materials['nodeId'] + '.' + text_key + '$}}')
        workflow['nodes'].append(branch_ai)
        for suffix, output_key in [('Answer','answerText'), ('Error','system_error_text')]:
            item = reference(branch + suffix, [branch_ai['nodeId'],output_key])
            item['required'] = False
            finish['inputs'].append(item)
        edge(result['nodeId'], gate['nodeId'])
        edge(gate['nodeId'], branch_ai['nodeId'], 'IF')
        edge(gate['nodeId'], finish['nodeId'], 'ELSE')
        edge(branch_ai['nodeId'], finish['nodeId'])
        error_edge(branch_ai, finish)

    edge(route['nodeId'], attachment_gate['nodeId'], 'ELSE')
    edge(attachment_gate['nodeId'], pdf['nodeId'], 'IF')
    edge(attachment_gate['nodeId'], images['nodeId'], 'ELSE')
    edge(pdf['nodeId'], images['nodeId'])
    edge(images['nodeId'], documents_gate['nodeId'])
    edge(documents_gate['nodeId'], documents['nodeId'], 'IF')
    edge(documents_gate['nodeId'], materials['nodeId'], 'ELSE')
    edge(documents['nodeId'], materials['nodeId'])
    error_edge(documents, materials)
    edge(materials['nodeId'], ai['nodeId'])
    edge(ai['nodeId'], result['nodeId'])
    error_edge(ai, result)
    edge(finish['nodeId'], answer['nodeId'])
    return workflow


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'workflows/ctg_mail.unconfigured.template.json')
    args = parser.parse_args()
    result = build(json.loads(args.source.read_text(encoding='utf-8-sig')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(f'Created sanitized template: {len(result["nodes"])} nodes, {len(result["edges"])} edges')
