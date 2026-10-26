from tests.scripts.test_unconfigured_workflow import inputs, run_node, template
import unittest


class CombinedWorkflowTest(unittest.TestCase):
    def test_branch_gates_failure_isolation_and_legacy_retry(self):
        nodes = {n['nodeId']: n for n in template()['nodes']}
        run_node(r'''
const assert=require('node:assert/strict');
const codes=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const load=code=>new Function(code+';return main;')();
const entry=load(codes.entry), plan=load(codes.plan), finish=load(codes.finish);
const base={schema_version:1,task_type:'unconfigured_mail_process',request_id:'r',attempt_id:'a',email_records_id:1,
 sender:'noc@example.com',content:'Maintenance',attachments:[],attachment_urls:[],securityTime:'',
 should_generate_supplier_draft:true,should_analyze_cutover_time:true,fixed_field_defaults:{top_fields:[]}};
const mail=JSON.stringify(base);
const prepared=entry({originMail:mail});
assert.ok(!JSON.parse(prepared.mail_text).fixed_field_defaults);
assert.deepEqual(JSON.parse(prepared.draft_text).fixed_field_defaults,base.fixed_field_defaults);
const classified=type=>JSON.stringify({mail_type:type,needs_review:false,classification_reason:'当前正文'});
const timeAnswer=JSON.stringify({windows:[{start:'2030-10-14T02:00:00+08:00',end:'2030-10-14T04:00:00+08:00'}],
 source_timezone:'UTC+8',source_time_text:'2030-10-14 02:00-04:00 UTC+8',needs_review:false,reason:'完整窗口'});
const draftAnswer=JSON.stringify({config:{name:'test',reply_email:'reply@example.net'},evidence:[],unresolved_questions:[]});
const now=Date.parse('2030-10-13T10:00:00+08:00');
for(const type of ['割接通知','割接取消','割接改期','割接提醒','故障邮件','其它']) {
 for(const draft of [true,false]) for(const time of [true,false]) {
  const originMail=JSON.stringify({...base,should_generate_supplier_draft:draft,should_analyze_cutover_time:time});
  const initial=plan({originMail,answer:classified(type)});
  assert.equal(initial.run_time,type==='割接通知'&&time);
  assert.equal(initial.run_draft,type==='割接通知'&&draft);
  const result=finish({originMail,state:initial.state,timeAnswer,draftAnswer,now}).envelope.result;
  assert.equal(result.time_analysis.status,initial.run_time?'succeeded':'skipped');
  assert.equal(result.supplier_draft.status,initial.run_draft?'succeeded':'skipped');
 }
}
const initial=plan({originMail:mail,answer:classified('割接通知')});
for(const bad of [{draftAnswer:'not json'}, {draftError:'upstream failed'}]) {
 const result=finish({originMail:mail,state:initial.state,timeAnswer,now,...bad}).envelope.result;
 assert.equal(result.classification.status,'succeeded');assert.equal(result.time_analysis.result.scene,'emergency');
 assert.equal(result.supplier_draft.status,'failed');
}
const badTime=finish({originMail:mail,state:initial.state,timeError:'timeout',draftAnswer,now}).envelope.result;
assert.equal(badTime.time_analysis.status,'failed');assert.equal(badTime.supplier_draft.status,'succeeded');
for(const failure of [{answer:'broken'},{error:'timeout'}]) {
 const p=plan({originMail:mail,...failure});assert.equal(p.run_time,false);assert.equal(p.run_draft,false);
 assert.equal(finish({originMail:mail,state:p.state}).envelope.result.classification.status,'failed');
}
const oldMail=JSON.stringify({...base,task_type:'supplier_config_draft'});
const retry=plan({originMail:oldMail,answer:draftAnswer});
assert.equal(retry.run_time,false);assert.equal(retry.run_draft,false);
assert.deepEqual(finish({originMail:oldMail,state:retry.state,legacyResult:retry.result_json}).envelope.result,JSON.parse(draftAnswer));
''', {key: inputs(nodes['new_unconfigured_' + node])['code'] for key, node in
      [('entry','entry'),('plan','result'),('finish','finish')]})

    def test_every_ai_error_and_skip_reaches_one_final_join(self):
        w = template()
        nodes = {n['nodeId']:n for n in w['nodes']}
        for kind in ('time','draft'):
            ai = nodes[f'new_unconfigured_{kind}_ai']
            self.assertTrue(ai['catchError'])
            outgoing = [e for e in w['edges'] if e['source'] == ai['nodeId']]
            self.assertEqual({e['sourceHandle'] for e in outgoing}, {
                ai['nodeId']+'-source-right', ai['nodeId']+'-source_catch-right'})
            self.assertTrue(all(e['target']=='new_unconfigured_finish' for e in outgoing))
        optional = {i['key']:i for i in nodes['new_unconfigured_finish']['inputs']}
        for key in ('timeAnswer','timeError','draftAnswer','draftError','legacyResult'):
            self.assertFalse(optional[key]['required'])
