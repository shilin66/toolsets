import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import api_server
import cutover_deletion
from cutover_deletion import delete_cutover_email
from database import EmailDatabase
from mail_artifacts import legacy_mailbox_storage_key, message_storage_directory
from supplier_config import SupplierConfigCreate, SupplierConfigRepository
from unconfigured_mail_repository import UnconfiguredMailRepository


class CutoverDeletionApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='/tmp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'data'
        self.root.mkdir()
        self.image_root = Path(self.tmp.name).resolve() / 'mail-listen-images'
        patcher = patch.object(cutover_deletion, 'IMAGE_DIR', self.image_root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.db = EmailDatabase(str(self.root / 'mail.db'))
        for name, value in (('email_db', self.db), ('DATA_DIR', self.root)):
            patcher = patch.object(api_server, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = api_server.app.test_client()
        self.headers = {'Authorization':'Bearer test-key'}
        self.supplier = SupplierConfigRepository(self.db).create(SupplierConfigCreate(
            name='Supplier', email='noc@example.com', prompt_mode='auto'))
        self.email_id = self.mail(100, 'inbox@example.com')
        self.url = f'/api/cutover/emails/{self.email_id}'
        self.message_root = message_storage_directory(self.root, mailbox_address='inbox@example.com', email_uid=100)

    def mail(self, uid, mailbox):
        self.assertTrue(self.db.add_email_record(uid, sender='noc@example.com', receiver=mailbox,
            subject='Cutover notice', content='private mail body'))
        return self.db.get_email_record(uid, mailbox)['id']

    def write(self, path):
        path = path if isinstance(path, Path) else self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'private file')
        return path

    def sql(self, query, parameters=()):
        with self.db.get_connection() as conn:
            result = conn.execute(query, parameters)
            rows = result.fetchall()
            conn.commit()
            return rows

    def task(self, email_id=None, line_type='customer', filename='notice.xlsx'):
        return self.db.upsert_cutover_task(email_id or self.email_id, line_type=line_type,
            customer_excel_filename=filename if line_type == 'customer' else None,
            fill_payload={'private':'payload'}, fill_result={'private':'result'})

    def report(self, task_id, path=None, status='success'):
        result = {'operation_log':[{'screenshot_filename':path}]} if path else {}
        return self.db.add_cutover_report(task_id, status=status, result=result)

    def draft(self, source, sample_ids, with_config=True):
        value = {'config':{'name':'Keep draft rules', 'fixed_field_rules':{'carrier_ticket_no':'Read Maintenance Reference'},
            'email_type_samples':{'割接通知':{'subject':'Cutover notice','content':'private mail body'}}},
            'evidence':['private mail evidence'],
            'unresolved_questions':['请确认运营商默认时区','请核对原文：private mail body']} if with_config else None
        with self.db.get_connection() as conn:
            result = conn.execute('''INSERT INTO supplier_drafts
                (candidate_key,sender,status,draft_json,source_email_records_id,create_time,update_time)
                VALUES (?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)''',
                (f'candidate-{source}', f'candidate-{source}@example.com', 'review' if value else 'generation_failed',
                    json.dumps(value), source)) if value else conn.execute('''INSERT INTO supplier_drafts
                (candidate_key,sender,status,source_email_records_id,create_time,update_time)
                VALUES (?,?,'generation_failed',?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)''',
                (f'candidate-{source}', f'candidate-{source}@example.com', source))
            draft_id = result.lastrowid
            conn.executemany('INSERT INTO supplier_draft_samples VALUES (?,?)', [(draft_id, item) for item in sample_ids])
            conn.commit()
        return draft_id

    def delete(self):
        return self.client.delete(self.url, headers=self.headers)

    def test_deletes_webp_report_and_error_only_screenshots(self):
        task = self.task()
        screenshot = self.write(self.message_root / 'cutover/reports/2030-01-01/1/1_1/step.webp')
        failure = self.write('rpa/artifacts/cutover-report-failure-test.webp')
        self.db.add_cutover_report(task, status='failed', result={
            'operation_log': [{'screenshot_filename': screenshot.relative_to(self.root).as_posix()}],
            'error': '失败截图：data/' + failure.relative_to(self.root).as_posix(),
        })
        self.assertEqual(self.delete().status_code, 200)
        self.assertFalse(screenshot.exists())
        self.assertFalse(failure.exists())

    def test_cascades_email_tasks_reports_analysis_replies_and_private_files(self):
        other = self.mail(101, 'inbox@example.com')
        customer = self.task()
        backbone = self.task(line_type='backbone')
        report_path = self.message_root / 'cutover/reports/2030-01-01' / str(self.email_id) / f'{customer}_1/report-success.png'
        self.report(customer, report_path.relative_to(self.root).as_posix())
        self.report(backbone)
        self.db.add_ticket_record(self.email_id, carrier_ticket_no='TICKET-1', cut_start_time='', cut_end_time='')
        self.sql("UPDATE email_records SET extract_result=?,line_match_payload=?,unconfigured_analysis_json=?,reply_status='pending',pending_reply_content=? WHERE id=?",
            ('private extraction','private bindings','{"reason":"private analysis"}','private reply',self.email_id))
        with self.db.get_connection() as conn:
            UnconfiguredMailRepository.enqueue(conn, 'cutover_time_extract', self.email_id, {})
            conn.commit()
        draft_id = self.draft(self.email_id, [self.email_id, other])
        paths = [self.message_root / 'source-email-100.eml', self.message_root / 'attachments/notice.pdf',
            self.message_root / 'cutover/customer/notice.xlsx', report_path,
            report_path.parent / 'unreferenced-failure.png', self.root / 'notice.xlsx',
            self.root / 'rpa/backbone-attachments/UID-100.eml',
            self.root / f'rpa/artifacts/2030-01-01/{self.email_id}/{customer}_adhoc/failed-step.png',
            self.root / 'email_attachments/100/unreferenced.pdf',
            self.image_root / ('email-100-' + 'a' * 32 + '.png'),
            self.root / 'mail_store/mailboxes' / legacy_mailbox_storage_key('inbox@example.com') / 'messages/100/source-email-100.eml']
        for path in paths:
            self.write(path)
        self.sql('UPDATE email_records SET attachments=? WHERE id=?',
            (json.dumps([(self.message_root / 'attachments/notice.pdf').relative_to(self.root).as_posix()]), self.email_id))
        supplier_before = SupplierConfigRepository(self.db).get(self.supplier['id'])
        self.db.replace_all_supplier_circuits([{'supplier':'Supplier','supplier_circuit_id':'SC-1',
            'circuit_id':'C-1','line_type':'客户','line_status':'正常','remark':''}])
        circuits_before = [dict(row) for row in self.sql('SELECT * FROM supplier_circuits')]
        response = self.delete()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['data'], {'email_records_id':self.email_id,'deleted':True})
        self.assertIsNone(self.db.get_email_record_by_id(self.email_id))
        for table, column in (('cutover_tasks','email_records_id'),('ticket_records','email_records_id'),
            ('mail_ai_jobs','email_records_id'),('supplier_draft_samples','email_records_id')):
            self.assertEqual(self.sql(f'SELECT count(*) FROM {table} WHERE {column}=?', (self.email_id,))[0][0], 0)
        self.assertEqual(self.sql('SELECT count(*) FROM cutover_reports')[0][0], 0)
        for path in paths:
            self.assertFalse(path.exists(), str(path))
        draft = dict(self.sql('SELECT * FROM supplier_drafts WHERE id=?', (draft_id,))[0])
        self.assertIsNone(draft['source_email_records_id'])
        value = json.loads(draft['draft_json'])
        self.assertEqual(value['config']['fixed_field_rules'], {'carrier_ticket_no':'Read Maintenance Reference'})
        self.assertEqual(value['config']['email_type_samples'], {})
        self.assertEqual(value['evidence'], [])
        self.assertIn('请确认运营商默认时区', value['unresolved_questions'])
        self.assertNotIn('private', draft['draft_json'])
        self.assertEqual(self.sql('SELECT email_records_id FROM supplier_draft_samples WHERE draft_id=?', (draft_id,))[0][0], other)
        self.assertIsNotNone(self.db.get_email_record_by_id(other))
        self.assertEqual(SupplierConfigRepository(self.db).get(self.supplier['id']), supplier_before)
        self.assertEqual([dict(row) for row in self.sql('SELECT * FROM supplier_circuits')], circuits_before)
        marker = dict(self.sql('SELECT * FROM mail_deletions WHERE email_records_id=?', (self.email_id,))[0])
        self.assertEqual(marker['status'], 'deleted')
        self.assertEqual(marker['cleanup_manifest'], '[]')
        self.assertNotIn('private', json.dumps(marker))

    def test_requires_auth_and_missing_is_404_while_completed_retry_is_idempotent(self):
        self.assertEqual(self.client.delete(self.url).status_code, 401)
        self.assertEqual(self.client.delete('/api/cutover/emails/99999', headers=self.headers).status_code, 404)
        self.assertEqual(self.delete().status_code, 200)
        self.assertEqual(self.delete().status_code, 200)

    def test_unconfigured_mail_without_children_ignores_other_missing_historical_absolute_report(self):
        self.sql("UPDATE email_records SET processing_origin='unconfigured', attachments=NULL WHERE id=?",
            (self.email_id,))
        other = self.mail(101, 'inbox@example.com')
        other_task = self.task(other)
        missing = Path(self.tmp.name).resolve() / 'old-installation/data/rpa/artifacts/report.png'
        self.assertFalse(missing.exists())
        other_report = self.report(other_task, str(missing))
        before = dict(self.sql('SELECT * FROM cutover_reports WHERE id=?', (other_report,))[0])
        self.assertEqual(self.sql('SELECT count(*) FROM cutover_tasks WHERE email_records_id=?',
            (self.email_id,))[0][0], 0)
        response = self.delete()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertIsNone(self.db.get_email_record_by_id(self.email_id))
        self.assertEqual(self.db.get_mail_deletion(self.email_id)['status'], 'deleted')
        self.assertIsNotNone(self.db.get_email_record_by_id(other))
        self.assertEqual(dict(self.sql('SELECT * FROM cutover_reports WHERE id=?', (other_report,))[0]), before)
        self.assertFalse(missing.exists())

    def test_configured_task_deletes_with_missing_ticket_report_and_files(self):
        task_id = self.task(filename='already-removed.xlsx')
        report_id = self.report(task_id, 'already-removed.png')
        self.sql('DELETE FROM cutover_reports WHERE id=?', (report_id,))
        self.sql('UPDATE cutover_tasks SET ticket_id=99999 WHERE id=?', (task_id,))
        self.sql('UPDATE email_records SET attachments=? WHERE id=?',
            (json.dumps(['email_attachments/100/already-removed.pdf']), self.email_id))
        remaining = self.write(self.message_root / 'source-email-100.eml')
        supplier_before = SupplierConfigRepository(self.db).get(self.supplier['id'])
        response = self.delete()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertFalse(remaining.exists())
        self.assertIsNone(self.db.get_email_record_by_id(self.email_id))
        self.assertIsNone(self.db.get_cutover_task(task_id))
        self.assertEqual(self.sql('SELECT count(*) FROM cutover_reports')[0][0], 0)
        self.assertEqual(SupplierConfigRepository(self.db).get(self.supplier['id']), supplier_before)

    def test_missing_own_external_report_is_skipped_but_existing_external_file_is_protected(self):
        task_id = self.task()
        missing = Path(self.tmp.name).resolve() / 'old-host/removed-report.png'
        self.report(task_id, str(missing))
        response = self.delete()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertIsNone(self.db.get_email_record_by_id(self.email_id))
        self.assertFalse(missing.exists())

        existing_email = self.mail(102, 'inbox@example.com')
        existing_task = self.task(existing_email)
        outside = self.write(Path(self.tmp.name).resolve() / 'existing-external-report.png')
        self.report(existing_task, str(outside))
        response = self.client.delete(f'/api/cutover/emails/{existing_email}', headers=self.headers)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(outside.read_bytes(), b'private file')
        self.assertIsNotNone(self.db.get_email_record_by_id(existing_email))
        self.assertIsNone(self.db.get_mail_deletion(existing_email))

    def test_missing_legacy_attachment_filename_does_not_block_either_mail_origin(self):
        for index, origin in enumerate(('configured', 'unconfigured')):
            with self.subTest(origin=origin):
                uid = 700 + index
                record_id = self.mail(uid, 'inbox@example.com')
                self.sql('UPDATE email_records SET processing_origin=?,attachments=? WHERE id=?',
                    (origin, json.dumps(['already-removed.pdf', f'email_attachments/{uid}/gone.pdf']), record_id))
                directory = message_storage_directory(self.root, mailbox_address='inbox@example.com', email_uid=uid)
                present = self.write(directory / f'source-email-{uid}.eml')
                response = self.client.delete(f'/api/cutover/emails/{record_id}', headers=self.headers)
                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertIsNone(self.db.get_email_record_by_id(record_id))
                self.assertFalse(present.exists())

    def test_old_container_report_path_resolves_to_current_target_mail_files(self):
        task_id = self.task()
        current = self.write(self.message_root / f'cutover/reports/2030-01-01/{self.email_id}/{task_id}_1/step.png')
        historical = '/app/data/' + current.relative_to(self.root).as_posix()
        self.report(task_id, historical)
        response = self.delete()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertFalse(current.exists())
        self.assertIsNone(self.db.get_email_record_by_id(self.email_id))

    def test_other_old_container_report_reference_preserves_current_shared_file(self):
        own_task = self.task()
        other = self.mail(101, 'inbox@example.com')
        other_task = self.task(other)
        shared = self.write(self.message_root / f'cutover/reports/2030-01-01/{self.email_id}/{own_task}_1/shared.png')
        relative = shared.relative_to(self.root).as_posix()
        self.report(own_task, relative)
        other_report = self.report(other_task, '/app/data/' + relative)
        exclusive = self.write(self.message_root / 'source-email-100.eml')
        response = self.delete()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertTrue(shared.is_file())
        self.assertFalse(exclusive.exists())
        self.assertIsNone(self.db.get_email_record_by_id(self.email_id))
        self.assertIsNotNone(self.db.get_email_record_by_id(other))
        self.assertEqual(self.sql('SELECT count(*) FROM cutover_reports WHERE id=?', (other_report,))[0][0], 1)

    def test_other_existing_external_report_cannot_block_unrelated_mail_deletion(self):
        other = self.mail(101, 'inbox@example.com')
        other_task = self.task(other)
        external = self.write(Path(self.tmp.name).resolve() / 'unrelated-existing-report.png')
        other_report = self.report(other_task, str(external))
        before = dict(self.sql('SELECT * FROM cutover_reports WHERE id=?', (other_report,))[0])
        own_file = self.write(self.message_root / 'source-email-100.eml')
        response = self.delete()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertFalse(own_file.exists())
        self.assertEqual(external.read_bytes(), b'private file')
        self.assertIsNone(self.db.get_email_record_by_id(self.email_id))
        self.assertIsNotNone(self.db.get_email_record_by_id(other))
        self.assertEqual(dict(self.sql('SELECT * FROM cutover_reports WHERE id=?', (other_report,))[0]), before)

    def test_incomplete_report_results_do_not_block_target_or_other_mail_deletion(self):
        cases = [None, '', 'null', '[]', '{damaged historical JSON', '{}',
            '{"operation_log":null}', '{"operation_log":[]}', '{"operation_log":1}',
            '{"screenshot_path":"."}']
        for index, raw_result in enumerate(cases):
            with self.subTest(raw_result=raw_result):
                target = self.mail(200 + index, 'inbox@example.com')
                target_task = self.task(target)
                report_id = self.report(target_task)
                self.sql('UPDATE cutover_reports SET result=? WHERE id=?', (raw_result, report_id))
                try:
                    # Another mail's corrupt legacy result must not block this unrelated mail.
                    unrelated = self.mail(300 + index, 'inbox@example.com')
                    response = self.client.delete(f'/api/cutover/emails/{unrelated}', headers=self.headers)
                    self.assertEqual(response.status_code, 200, response.get_json())
                    self.assertIsNone(self.db.get_email_record_by_id(unrelated))
                    self.assertEqual(self.sql('SELECT result FROM cutover_reports WHERE id=?', (report_id,))[0][0], raw_result)
                    response = self.client.delete(f'/api/cutover/emails/{target}', headers=self.headers)
                    self.assertEqual(response.status_code, 200, response.get_json())
                    self.assertIsNone(self.db.get_email_record_by_id(target))
                    self.assertEqual(self.sql('SELECT count(*) FROM cutover_reports WHERE id=?', (report_id,))[0][0], 0)
                finally:
                    # A failing subcase must not leave malformed shared metadata for the next one.
                    self.sql('DELETE FROM cutover_reports WHERE id=?', (report_id,))

    def test_null_attachments_and_missing_draft_config_samples_do_not_block_deletion(self):
        cases = [{}, {'config':None}, {'config':{}}, {'config':{'email_type_samples':None}},
            {'config':{'email_type_samples':{'割接通知':None}}}]
        for index, value in enumerate(cases):
            with self.subTest(draft=value):
                target = self.mail(400 + index, 'inbox@example.com')
                self.sql("UPDATE email_records SET processing_origin='unconfigured', attachments=NULL WHERE id=?", (target,))
                draft_id = self.draft(target, [target])
                self.sql('UPDATE supplier_drafts SET draft_json=? WHERE id=?', (json.dumps(value), draft_id))
                response = self.client.delete(f'/api/cutover/emails/{target}', headers=self.headers)
                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertIsNone(self.db.get_email_record_by_id(target))
                draft = self.sql('SELECT * FROM supplier_drafts WHERE id=?', (draft_id,))[0]
                self.assertIsNone(draft['source_email_records_id'])
                self.assertEqual(self.sql('SELECT count(*) FROM supplier_draft_samples WHERE draft_id=?', (draft_id,))[0][0], 0)
                self.assertEqual(self.db.get_mail_deletion(target)['status'], 'deleted')

    def test_optional_attachment_formats_skip_bad_items_and_keep_valid_file_reference(self):
        explicit_relative = 'email_attachments/9999/explicit-reference.pdf'
        cases = ['null', '{damaged attachment JSON', json.dumps([None, {'missing':'path'}, explicit_relative])]
        for index, attachments in enumerate(cases):
            with self.subTest(attachments=attachments):
                target = self.mail(500 + index, 'inbox@example.com')
                self.sql('UPDATE email_records SET attachments=? WHERE id=?', (attachments, target))
                canonical = message_storage_directory(self.root, mailbox_address='inbox@example.com', email_uid=500 + index)
                own_file = self.write(canonical / 'source.eml')
                explicit_file = self.write(explicit_relative) if index == 2 else None
                try:
                    response = self.client.delete(f'/api/cutover/emails/{target}', headers=self.headers)
                    self.assertEqual(response.status_code, 200, response.get_json())
                    self.assertIsNone(self.db.get_email_record_by_id(target))
                    self.assertFalse(own_file.exists())
                    if explicit_file:
                        self.assertFalse(explicit_file.exists())
                finally:
                    self.sql("UPDATE email_records SET attachments='[]' WHERE id=?", (target,))

    def test_invalid_source_draft_json_does_not_leave_deleted_source_or_sample(self):
        for index, raw in enumerate(('{broken "content":"private mail body"', '["private mail body"]', 'null')):
            with self.subTest(draft_json=raw):
                target = self.mail(600 + index, 'inbox@example.com')
                draft_id = self.draft(target, [target])
                self.sql('UPDATE supplier_drafts SET draft_json=? WHERE id=?', (raw, draft_id))
                response = self.client.delete(f'/api/cutover/emails/{target}', headers=self.headers)
                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertIsNone(self.db.get_email_record_by_id(target))
                draft = self.sql('SELECT * FROM supplier_drafts WHERE id=?', (draft_id,))[0]
                self.assertIsNone(draft['source_email_records_id'])
                self.assertIsNone(draft['draft_json'])
                self.assertEqual(draft['status'], 'collecting')
                self.assertEqual(self.sql('SELECT count(*) FROM supplier_draft_samples WHERE draft_id=?', (draft_id,))[0][0], 0)

    def test_legacy_mail_without_receiver_deletes_remaining_uid_artifacts(self):
        for index, receiver in enumerate((None, '')):
            with self.subTest(receiver=receiver):
                uid = 700 + index
                target = self.mail(uid, receiver)
                own_file = self.write(f'email_attachments/{uid}/legacy.pdf')
                response = self.client.delete(f'/api/cutover/emails/{target}', headers=self.headers)
                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertIsNone(self.db.get_email_record_by_id(target))
                self.assertFalse(own_file.exists())
                self.assertEqual(self.db.get_mail_deletion(target)['status'], 'deleted')

    def test_refuses_every_active_side_effect_before_marking_or_removing_files(self):
        task_id = self.task()
        report_id = self.report(task_id)
        with self.db.get_connection() as conn:
            UnconfiguredMailRepository.enqueue(conn, 'cutover_time_extract', self.email_id, {})
            conn.commit()
        path = self.write(self.message_root / 'source-email-100.eml')
        cases = [('cutover_tasks','status','reporting',task_id,'draft'),
            ('cutover_reports','status','pending',report_id,'success'),
            ('cutover_reports','status','running',report_id,'success'),
            ('email_records','reply_status','sending',self.email_id,''),
            ('email_records','api_forward_status','forwarding',self.email_id,''),
            ('mail_ai_jobs','status','running',self.sql('SELECT id FROM mail_ai_jobs')[0][0],'pending')]
        for table, column, value, row_id, reset in cases:
            with self.subTest(table=table, value=value):
                self.sql(f'UPDATE {table} SET {column}=? WHERE id=?', (value,row_id))
                self.assertEqual(self.delete().status_code, 409)
                self.assertTrue(path.exists())
                self.assertEqual(self.sql('SELECT count(*) FROM mail_deletions')[0][0], 0)
                self.sql(f'UPDATE {table} SET {column}=? WHERE id=?', (reset,row_id))

    def test_file_failure_keeps_row_and_manifest_for_successful_retry(self):
        path = self.write(self.message_root / 'source-email-100.eml')
        original_unlink = Path.unlink
        def fail_target(candidate, *args, **kwargs):
            if candidate == path:
                raise PermissionError('test denial')
            return original_unlink(candidate, *args, **kwargs)
        with patch.object(Path, 'unlink', fail_target):
            self.assertEqual(self.delete().status_code, 500)
        self.assertIsNotNone(self.db.get_email_record_by_id(self.email_id))
        marker = self.sql('SELECT status,cleanup_manifest FROM mail_deletions')[0]
        self.assertEqual(marker['status'], 'pending_cleanup')
        self.assertIn(path.relative_to(self.root).as_posix(), marker['cleanup_manifest'])
        self.assertTrue(path.exists())
        self.assertEqual(self.delete().status_code, 200)
        self.assertFalse(path.exists())
        self.assertIsNone(self.db.get_email_record_by_id(self.email_id))

    def test_sql_failure_after_files_is_retryable_without_losing_pending_entry(self):
        task_id = self.task()
        self.report(task_id)
        path = self.write(self.message_root / 'source-email-100.eml')
        self.sql("CREATE TRIGGER test_fail_delete BEFORE DELETE ON email_records BEGIN SELECT RAISE(ABORT,'test SQL failure'); END")
        self.assertEqual(self.delete().status_code, 500)
        self.assertIsNotNone(self.db.get_email_record_by_id(self.email_id))
        self.assertIsNotNone(self.db.get_cutover_task(task_id))
        self.assertEqual(len(self.db.get_cutover_reports(task_id)), 1)
        self.assertEqual(self.sql('SELECT status FROM mail_deletions')[0][0], 'pending_cleanup')
        self.assertFalse(path.exists())
        self.sql('DROP TRIGGER test_fail_delete')
        self.assertEqual(self.delete().status_code, 200)

    def test_marking_failure_does_not_touch_files_or_rows(self):
        path = self.write(self.message_root / 'source-email-100.eml')
        self.sql("CREATE TRIGGER test_fail_mark BEFORE INSERT ON mail_deletions BEGIN SELECT RAISE(ABORT,'test mark failure'); END")
        self.assertEqual(self.delete().status_code, 500)
        self.assertTrue(path.exists())
        self.assertIsNotNone(self.db.get_email_record_by_id(self.email_id))
        self.assertEqual(self.sql('SELECT count(*) FROM mail_deletions')[0][0], 0)

    def test_shared_legacy_and_canonical_files_and_other_email_are_preserved(self):
        other = self.mail(100, 'other@example.com')
        own_task = self.task(filename='shared.xlsx')
        other_task = self.task(other, filename='shared.xlsx')
        shared_attachment = self.write(self.message_root / 'attachments/shared.pdf')
        attachment = shared_attachment.relative_to(self.root).as_posix()
        self.sql('UPDATE email_records SET attachments=?', (json.dumps([attachment]),))
        shared_screenshot = self.write('rpa/artifacts/shared-report.png')
        self.report(own_task, 'shared-report.png')
        self.report(other_task, 'shared-report.png')
        shared_excel = self.write('shared.xlsx')
        shared_eml = self.write('rpa/backbone-attachments/UID-100.eml')
        shared_legacy_attachment = self.write('email_attachments/100/original.pdf')
        shared_image = self.write(self.image_root / ('email-100-' + 'b' * 32 + '.png'))
        exclusive = self.write(self.message_root / 'source-email-100.eml')
        self.assertEqual(self.delete().status_code, 200)
        for path in (shared_attachment, shared_screenshot, shared_excel, shared_eml, shared_legacy_attachment, shared_image):
            self.assertTrue(path.exists(), str(path))
        self.assertFalse(exclusive.exists())
        self.assertIsNotNone(self.db.get_email_record_by_id(other))
        self.assertIsNotNone(self.db.get_cutover_task(other_task))
        self.assertEqual(len(self.db.get_cutover_reports(other_task)), 1)

    def test_symlink_and_outside_reference_are_rejected_without_deleting_target(self):
        outside = Path(self.tmp.name) / 'outside.txt'
        outside.write_bytes(b'keep outside')
        link = self.message_root / 'attachments/link.pdf'
        link.parent.mkdir(parents=True)
        link.symlink_to(outside)
        self.assertEqual(self.delete().status_code, 500)
        self.assertTrue(outside.exists())
        self.assertIsNotNone(self.db.get_email_record_by_id(self.email_id))
        self.assertEqual(self.sql('SELECT count(*) FROM mail_deletions')[0][0], 0)
        link.unlink()
        self.sql('UPDATE email_records SET attachments=? WHERE id=?', (json.dumps(['../outside.txt']),self.email_id))
        self.assertEqual(self.delete().status_code, 500)
        self.assertEqual(outside.read_bytes(), b'keep outside')

    def test_non_source_sample_removal_keeps_other_draft_contents(self):
        other = self.mail(101, 'inbox@example.com')
        draft_id = self.draft(other, [self.email_id, other])
        before = dict(self.sql('SELECT * FROM supplier_drafts WHERE id=?', (draft_id,))[0])
        self.assertEqual(self.delete().status_code, 200)
        self.assertEqual(dict(self.sql('SELECT * FROM supplier_drafts WHERE id=?', (draft_id,))[0]), before)
        self.assertEqual(self.sql('SELECT count(*) FROM supplier_draft_samples WHERE draft_id=?', (draft_id,))[0][0], 1)

    def test_failed_source_candidate_is_reset_without_a_dangling_source(self):
        draft_id = self.draft(self.email_id, [self.email_id], with_config=False)
        self.assertEqual(self.delete().status_code, 200)
        draft = self.sql('SELECT * FROM supplier_drafts WHERE id=?', (draft_id,))[0]
        self.assertIsNone(draft['source_email_records_id'])
        self.assertEqual(draft['status'], 'collecting')
        self.assertIsNone(draft['draft_json'])

    def test_source_cleanup_keeps_manually_replaced_and_other_category_samples(self):
        draft_id = self.draft(self.email_id, [self.email_id])
        value = json.loads(self.sql('SELECT draft_json FROM supplier_drafts WHERE id=?', (draft_id,))[0][0])
        samples = {'割接通知':{'subject':'New sample','content':'Manually replaced notification'},
            '维护进展':{'subject':'Progress','content':'Manually added sample'}}
        value['config']['email_type_samples'] = samples
        self.sql('UPDATE supplier_drafts SET draft_json=? WHERE id=?', (json.dumps(value),draft_id))
        self.assertEqual(self.delete().status_code, 200)
        saved = json.loads(self.sql('SELECT draft_json FROM supplier_drafts WHERE id=?', (draft_id,))[0][0])
        self.assertEqual(saved['config']['email_type_samples'], samples)
        self.assertIn('请确认运营商默认时区', saved['unresolved_questions'])

    def test_new_nested_directory_during_cleanup_fails_then_retries(self):
        original = self.write(self.message_root / 'source-email-100.eml')
        added = self.message_root / 'unexpected/nested/new-file.txt'
        original_unlink = Path.unlink
        def add_during_unlink(path, *args, **kwargs):
            result = original_unlink(path, *args, **kwargs)
            if path == original:
                self.write(added)
            return result
        with patch.object(Path, 'unlink', add_during_unlink):
            self.assertEqual(self.delete().status_code, 500)
        self.assertTrue(added.exists())
        self.assertIsNotNone(self.db.get_email_record_by_id(self.email_id))
        self.assertEqual(self.delete().status_code, 200)
        self.assertFalse(added.exists())

    def test_historical_body_image_cleanup_is_exact_and_failure_is_retryable(self):
        image = self.write(self.image_root / ('email-100-' + 'c' * 32 + '.png'))
        other = self.write(self.image_root / ('email-1000-' + 'd' * 32 + '.png'))
        invalid = self.write(self.image_root / 'email-100-not-a-uuid.png')
        original_unlink = Path.unlink
        def fail_image(path, *args, **kwargs):
            if path == image:
                raise PermissionError('test image denial')
            return original_unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', fail_image):
            self.assertEqual(self.delete().status_code, 500)
        self.assertIsNotNone(self.db.get_email_record_by_id(self.email_id))
        self.assertTrue(image.exists())
        self.assertEqual(self.delete().status_code, 200)
        self.assertFalse(image.exists())
        self.assertTrue(other.exists())
        self.assertTrue(invalid.exists())

    def test_historical_image_symlink_cannot_remove_external_target(self):
        outside = self.write(Path(self.tmp.name) / 'outside-image.png')
        self.image_root.mkdir()
        link = self.image_root / ('email-100-' + 'e' * 32 + '.png')
        link.symlink_to(outside)
        self.assertEqual(self.delete().status_code, 500)
        self.assertTrue(outside.exists())
        self.assertEqual(self.sql('SELECT count(*) FROM mail_deletions')[0][0], 0)

    def test_unreadable_historical_image_directory_does_not_report_success(self):
        image = self.write(self.image_root / ('email-100-' + 'f' * 32 + '.png'))
        original_iterdir = Path.iterdir
        def deny_images(path):
            if path == self.image_root:
                raise PermissionError('test directory denial')
            return original_iterdir(path)
        with patch.object(Path, 'iterdir', deny_images):
            self.assertEqual(self.delete().status_code, 500)
        self.assertTrue(image.exists())
        self.assertIsNotNone(self.db.get_email_record_by_id(self.email_id))
        self.assertEqual(self.sql('SELECT count(*) FROM mail_deletions')[0][0], 0)

    def test_simultaneous_service_deletes_are_idempotent(self):
        self.write(self.message_root / 'source-email-100.eml')
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _:delete_cutover_email(self.db, self.root, self.email_id), range(2)))
        self.assertEqual(results, [{'email_records_id':self.email_id,'deleted':True}] * 2)
        self.assertEqual(self.sql('SELECT count(*) FROM mail_deletions')[0][0], 1)
        self.assertIsNone(self.db.get_email_record_by_id(self.email_id))

    def test_delete_removes_pending_sample_cleanup(self):
        with self.db.get_connection() as conn:
            conn.execute('INSERT INTO unconfigured_sample_cleanup VALUES (?)', (self.email_id,))
            conn.commit()
        response = self.client.delete(self.url, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        with self.db.get_connection() as conn:
            self.assertIsNone(conn.execute('SELECT 1 FROM unconfigured_sample_cleanup WHERE email_records_id=?', (self.email_id,)).fetchone())


if __name__ == '__main__':
    unittest.main()
