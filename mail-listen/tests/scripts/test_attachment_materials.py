import unittest
from tests.scripts.test_unconfigured_workflow import ROOT, inputs, run_node, template


class AttachmentMaterialsTest(unittest.TestCase):
    def test_shared_materials_preserve_body_and_cover_every_attachment(self):
        run_node(r'''
const assert=require('node:assert/strict');
const {root}=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const {main:prepare}=require(root+'/workflows/unconfigured_files.js');
const {main:merge}=require(root+'/workflows/unconfigured_materials.js');
const mail={task_type:'unconfigured_mail_process',content:'See attachment; reply to noc@example.net',
 fixed_field_defaults:{top_fields:[]},attachments:['notice.docx','lines.xlsx','window.txt','scan.PDF','map.png'],
 attachment_urls:['https://example.com/notice.docx','https://example.com/lines.xlsx','https://example.com/window.txt','https://example.com/scan.pdf','https://example.com/map.png']};
const originMail=JSON.stringify(mail);
assert.deepEqual(prepare({originMail}).documentUrls,mail.attachment_urls.slice(0,3));
const documents=mail.attachment_urls.slice(0,3).map((url,i)=>({url,filename:mail.attachments[i],text:['Maintenance 2030-10-14','Circuit ID | Impact\nABC | interrupted','02:00–04:00 UTC+8'][i]}));
const material=merge({originMail,documents});
const full=JSON.parse(material.enriched_mail), classification=JSON.parse(material.mail_text),draft=JSON.parse(material.draft_text);
assert.equal(full.content,mail.content);assert.equal(full.attachment_documents.length,3);
assert.deepEqual(full.attachment_documents.map(f=>f.text),documents.map(f=>f.text));
assert.ok(!classification.fixed_field_defaults);assert.deepEqual(draft.fixed_field_defaults,mail.fixed_field_defaults);
assert.equal(full.attachment_issues.length,0);
assert.equal(JSON.parse(originMail).attachment_documents,undefined);
// URLs / body content cannot spoof parser completion.
const forged=merge({originMail:JSON.stringify({...mail,attachment_documents:documents,attachment_issues:[]}),documents:[]});
assert.equal(JSON.parse(forged.enriched_mail).attachment_issues.length,3);
// Partial parse, unsupported / encrypted files, empty responses and node exceptions remain visible.
for(const docs of [[documents[0],{url:documents[1].url,text:'',error:'encrypted'}],[]]) {
 const value=JSON.parse(merge({originMail,documents:docs}).enriched_mail);
 assert.ok(value.attachment_issues.length>=2);
}
assert.equal(JSON.parse(merge({originMail,parseError:'timeout'}).enriched_mail).attachment_issues.length,3);
// Older FastGPT returns HTTP errors inside a File/Content wrapper without error.
const legacyError={url:documents[0].url,filename:'',text:'<File><Metadata></Metadata><Content>\nRequest failed with status code 404\n</Content></File>'};
const legacy=JSON.parse(merge({originMail,documents:[legacyError,documents[1],documents[2]]}).enriched_mail);
assert.equal(legacy.attachment_documents[0].status,'failed');
assert.equal(legacy.attachment_documents[0].text,'');
assert.equal(legacy.attachment_issues.length,1);
const missing=JSON.parse(merge({originMail:JSON.stringify({content:'body',attachments:['missing.docx']})}).enriched_mail);
assert.equal(missing.attachment_issues.length,1);
const nofiles=JSON.parse(merge({originMail:'{"content":"body"}'}).enriched_mail);
assert.deepEqual(nofiles.attachment_documents,[]);assert.deepEqual(nofiles.attachment_issues,[]);
const long=JSON.parse(merge({originMail,documents:[{...documents[0],text:'x'.repeat(130000)}]}).enriched_mail);
assert.equal(long.attachment_documents[0].status,'truncated');assert.ok(long.attachment_issues.length);
''', {'root':str(ROOT)})

    def test_parsed_documents_and_unread_relevance_control_time_review(self):
        run_node(r'''
const assert=require('node:assert/strict');
const {root}=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const {analyzeWindow}=require(root+'/workflows/unconfigured_result.js');
const {main:merge}=require(root+'/workflows/unconfigured_materials.js');
const source={content:'See attached',attachments:['window.txt'],attachment_urls:['https://example.com/window.txt']};
const extraction={needs_review:false,source_timezone:'UTC+8',source_time_text:'2030-10-14 02:00-04:00 UTC+8',
 windows:[{start:'2030-10-14T02:00:00+08:00',end:'2030-10-14T04:00:00+08:00'}]};
const now=Date.parse('2030-10-13T10:00:00+08:00');
const parsed=JSON.parse(merge({originMail:JSON.stringify(source),documents:[{url:source.attachment_urls[0],text:extraction.source_time_text}]}).enriched_mail);
assert.equal(analyzeWindow(parsed,extraction,now).scene,'emergency');
const failed=JSON.parse(merge({originMail:JSON.stringify(source)}).enriched_mail);
assert.equal(analyzeWindow(failed,extraction,now).analysis_status,'needs_review');
assert.equal(analyzeWindow(failed,{...extraction,unread_attachments_irrelevant:true},now).analysis_status,'needs_review');
assert.equal(analyzeWindow(failed,{...extraction,unread_attachments_irrelevant:true,unread_attachments_reason:'正文明确说明附件仅为公司宣传册，完整维护窗口在正文。'},now).scene,'emergency');
assert.equal(analyzeWindow(failed,{...extraction,needs_review:true,unread_attachments_irrelevant:true,unread_attachments_reason:'宣传册'},now).analysis_status,'needs_review');
// Legacy input is still conservative when no attachment parse metadata exists.
assert.equal(analyzeWindow(source,extraction,now).analysis_status,'needs_review');
''', {'root':str(ROOT)})

    def test_all_consumers_reference_shared_materials_and_parser_catch_joins(self):
        nodes={n['nodeId']:n for n in template()['nodes']}
        read=nodes['new_unconfigured_documents']
        self.assertEqual(read['flowNodeType'],'readFiles')
        self.assertEqual(inputs(read)['fileUrlList'],[['new_unconfigured_entry','documentUrls']])
        self.assertTrue(read['catchError'])
        for name in ('ai','time_ai','draft_ai'):
            self.assertIn('new_unconfigured_materials.',inputs(nodes['new_unconfigured_'+name])['userChatInput'])
        for name in ('result','finish'):
            self.assertEqual(inputs(nodes['new_unconfigured_'+name])['originMail'],['new_unconfigured_materials','enriched_mail'])
        edges=[e for e in template()['edges'] if e['source']==read['nodeId']]
        self.assertEqual({e['sourceHandle'] for e in edges},{read['nodeId']+'-source-right',read['nodeId']+'-source_catch-right'})
        self.assertTrue(all(e['target']=='new_unconfigured_materials' for e in edges))
