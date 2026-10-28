import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('API_KEY', 'test-key')
import api_server
from database import EmailDatabase
from supplier_config import SupplierConfigRepository, SupplierConfigCreate, SupplierConfigUpdate
from user_access import UserAccessRepository


class OperationsApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = EmailDatabase(str(Path(self.tmp.name) / 'stats.db'))
        for key, value in [('email_db', self.db), ('API_KEY', 'test-key')]:
            p = patch.object(api_server, key, value); p.start(); self.addCleanup(p.stop)
        self.suppliers = SupplierConfigRepository(self.db)
        self.supplier = self.suppliers.create(SupplierConfigCreate(name='运营商甲', email='carrier@example.com', prompt_mode='auto'))
        self.repo = UserAccessRepository(self.db)
        self.user = self.repo.create_user('stats', 'stats-password-123')
        self.accounts = [self.db.add_mail_account({'email_address': a, 'imap_server': 'example.com'}) for a in ['one@example.com', 'two@example.com']]
        self.repo.set_grants(self.user['id'], [{'account_id': self.accounts[0], 'can_operate': True}, {'account_id': self.accounts[1], 'can_operate': False}])
        self.client = api_server.app.test_client()
        self.admin = {'Authorization': 'Bearer test-key'}
        self.query = '?start=2026-10-26&end=2026-11-01&environment=production'
        self.e1, self.t1 = self.add_mail(1, 'one@example.com', 'CT-1', ['A', 'B', 'C'])
        self.e2, self.t2 = self.add_mail(2, 'two@example.com', 'CT-1', ['D', 'E'])
        self.report(self.t1, '2026-10-27T10:00:00+08:00')
        self.report(self.t2, '2026-10-27T10:00:00+08:00')

    def add_mail(self, uid, receiver, ticket, lines, sender='carrier@example.com'):
        self.db.add_email_record(uid, sender=sender, receiver=receiver, subject='割接通知', content='')
        email_id = self.db.get_email_record(uid, receiver=receiver)['id']
        with self.db.get_connection() as c:
            c.execute("UPDATE email_records SET mail_type='割接通知',create_time='2026-10-27 09:00:00' WHERE id=?", (email_id,)); c.commit()
        task = self.db.upsert_cutover_task(email_records_id=email_id, supplier='运营商甲', carrier_ticket_no=ticket, fill_result={'circuits': [{'电路代号': x} for x in lines]})
        return email_id, task

    def report(self, task, at, environment='production'):
        return self.db.add_cutover_report(task, 'customer', 'success', {'updated_at': at, 'execution_identity': {'environment': environment}})

    def login(self):
        self.assertEqual(self.client.post('/api/auth/login', json={'username': 'stats', 'password': 'stats-password-123'}).status_code, 200)

    def get(self, route='summary', extra='', admin=True):
        response = self.client.get('/api/operations/' + route + self.query + extra, headers=self.admin if admin else {})
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()['data']

    def test_permission_and_mailbox_filter(self):
        self.login()
        opts = self.client.get('/api/operations/options').get_json()['data']
        self.assertEqual([x['account_id'] for x in opts['mailboxes']], [self.accounts[0]])
        data = self.get(admin=False)
        self.assertEqual(data['metrics']['received_emails'], 1)
        self.assertEqual(data['metrics']['reported_lines'], 3)
        for route in ['summary', 'suppliers', 'details', 'export']:
            r = self.client.get('/api/operations/' + route + self.query + '&mailboxes=' + str(self.accounts[1]))
            self.assertEqual(r.status_code, 403)
        self.repo.set_grants(self.user['id'], [])
        self.assertEqual(self.get(admin=False)['metrics']['received_emails'], 0)

    def test_cross_mailbox_workorder_and_line_deduplication(self):
        self.report(self.t1, '2026-10-28T10:00:00+08:00')
        metrics = self.get()['metrics']
        self.assertEqual(metrics['reported_orders'], 1)
        self.assertEqual(metrics['reported_emails'], 2)
        self.assertEqual(metrics['reported_lines'], 5)
        self.assertEqual(self.get(extra='&mailboxes=')['metrics']['received_emails'], 0)

    def test_snapshot_not_current_task(self):
        self.db.update_cutover_task(self.t1, fill_result={'circuits': [{'电路代号': 'MUTATED'}]})
        self.assertEqual(self.get()['metrics']['reported_lines'], 5)
        details = self.get('details', '&kind=lines')
        self.assertEqual({x['line_id'] for x in details['items']}, {'A','B','C','D','E'})

    def test_distinct_ticket_in_later_success_is_not_lost(self):
        self.db.update_cutover_task(self.t1, carrier_ticket_no='CT-NEW')
        self.report(self.t1, '2026-10-28T10:00:00+08:00')
        self.assertEqual(self.get()['metrics']['reported_orders'], 2)
        self.assertEqual({r['ticket'] for r in self.get('details')['items']}, {'CT-1', 'CT-NEW'})
        self.assertEqual(self.get()['metrics']['reported_lines'], 8)

    def test_empty_sender_drilldown_is_distinct_from_all_senders(self):
        _, task = self.add_mail(3, 'one@example.com', 'CT-EMPTY', ['UNKNOWN'], sender='')
        self.report(task, '2026-10-28T10:00:00+08:00')
        detail = self.get('details', '&kind=lines&supplier=')
        self.assertEqual(detail['total'], 1)
        self.assertEqual(detail['items'][0]['line_id'], 'UNKNOWN')

    def test_shared_ticket_is_counted_once_without_hiding_other_totals(self):
        _, task = self.add_mail(3, 'one@example.com', 'CT-1', ['A'], sender='another@example.com')
        self.report(task, '2026-10-28T10:00:00+08:00')
        metrics = self.get()['metrics']
        self.assertEqual(metrics['conflicting_tickets'], 1)
        self.assertEqual(metrics['reported_lines'], 5)
        self.assertEqual(metrics['reported_orders'], 1)

    def test_backbone_names_are_individual_lines_and_duplicate_ids_dedup(self):
        task = self.db.upsert_cutover_task(email_records_id=self.e1, line_type='backbone', carrier_ticket_no='CT-1',
            fill_result={'backbone_circuits': [{'割接对象': {'系统名称': ['BB-A','BB-B','BB-A']}}, {'割接对象': {'系统名称': 'BB-C'}}]})
        self.report(task, '2026-10-28T10:00:00+08:00')
        self.assertEqual(self.get()['metrics']['reported_lines'], 8)

    def test_old_successes_use_existing_task_fields_without_a_snapshot(self):
        with self.db.get_connection() as c:
            c.execute('UPDATE cutover_reports SET statistics_snapshot=NULL'); c.commit()
        metrics = self.get()['metrics']
        self.assertEqual(metrics['missing_report_evidence'], 2)
        self.assertEqual(metrics['reported_emails'], 2)
        self.assertEqual(metrics['reported_orders'], 1)
        self.assertEqual(metrics['reported_lines'], 5)
        self.assertEqual(metrics['pending_tasks'], 0)

    def test_legacy_date_and_environment_recovery(self):
        # Old reports store the destination URL and SQLite UTC creation time.
        with self.db.get_connection() as c:
            c.execute("UPDATE cutover_reports SET statistics_snapshot=NULL,completed_at=NULL,create_time='2026-10-25 16:30:00',result=?",
                (json.dumps({'final_url': 'https://legacy-test.example.com/app/success'}),))
            c.commit()
        from rpa.session_config import PortalSessionSettings
        config = PortalSessionSettings.model_construct(test_login_url='https://legacy-test.example.com/login')
        with patch('operations_query.PortalSessionSettings', return_value=config):
            response = self.client.get('/api/operations/summary?start=2026-10-26&end=2026-10-26&environment=test', headers=self.admin)
            metrics = response.get_json()['data']['metrics']
            self.assertEqual((metrics['reported_emails'],metrics['reported_orders'],metrics['reported_lines']), (2,1,5))
            self.assertEqual(self.get()['metrics']['reported_emails'], 0)

    def test_unknown_environment_is_in_all_but_not_production_or_test(self):
        with self.db.get_connection() as c:
            c.execute("UPDATE cutover_reports SET statistics_snapshot=NULL,completed_at=NULL,result='{}',create_time='2026-10-27 10:00:00'")
            c.commit()
        self.assertEqual(self.get()['metrics']['reported_emails'], 0)
        response = self.client.get('/api/operations/summary?start=2026-10-26&end=2026-11-01&environment=all', headers=self.admin)
        self.assertEqual(response.get_json()['data']['metrics']['reported_emails'], 2)

    def test_unrelated_old_reports_do_not_blank_current_week_and_reports_use_success_time(self):
        _, task = self.add_mail(3, 'one@example.com', 'OLD', ['OLD-LINE'])
        report = self.report(task, '2026-09-01T10:00:00+08:00')
        with self.db.get_connection() as c:
            c.execute("UPDATE cutover_reports SET statistics_snapshot=NULL,completed_at=NULL,result='{}',create_time='2026-09-01 01:00:00' WHERE id=?", (report,))
            c.commit()
        metrics = self.get()['metrics']
        self.assertEqual((metrics['reported_emails'],metrics['reported_orders'],metrics['reported_lines']), (2,1,5))

    def test_legacy_fallback_does_not_read_changed_line_type_as_old_report(self):
        with self.db.get_connection() as c:
            c.execute('UPDATE cutover_reports SET statistics_snapshot=NULL WHERE task_id=?', (self.t1,))
            c.execute("UPDATE cutover_tasks SET line_type='backbone',fill_result=? WHERE id=?", (json.dumps({'backbone_circuits':[{'割接对象':{'系统名称':['NEW-BACKBONE']}}]}),self.t1))
            c.commit()
        metrics = self.get()['metrics']
        self.assertEqual(metrics['reported_emails'], 2)
        self.assertEqual(metrics['reported_lines'], 2)

    def test_legacy_reported_task_without_report_log_is_counted_in_all_environments(self):
        _, task = self.add_mail(3, 'one@example.com', 'LEGACY', ['L1'])
        with self.db.get_connection() as c:
            c.execute("UPDATE cutover_tasks SET status='reported',update_time='2026-10-27 12:00:00' WHERE id=?",(task,))
            c.commit()
        result = self.client.get('/api/operations/summary?start=2026-10-26&end=2026-11-01&environment=all', headers=self.admin)
        self.assertEqual(result.get_json()['data']['metrics']['reported_emails'],3)

    def test_missing_payload_does_not_hide_known_email_and_order_counts(self):
        with self.db.get_connection() as c:
            c.execute("UPDATE cutover_reports SET statistics_snapshot=json_set(statistics_snapshot,'$.fill_result','{}')"); c.commit()
        metrics = self.get()['metrics']
        self.assertEqual(metrics['reported_emails'], 2)
        self.assertEqual(metrics['reported_orders'], 1)
        self.assertEqual(metrics['reported_lines'], 0)
        self.assertEqual(metrics['missing_line_payloads'], 2)

    def test_success_without_ticket_identifier_still_counts_emails(self):
        with self.db.get_connection() as c:
            c.execute("UPDATE cutover_reports SET statistics_snapshot=json_set(statistics_snapshot,'$.carrier_ticket_no','')"); c.commit()
        metrics = self.get()['metrics']
        self.assertEqual(metrics['reported_orders'], 0)
        self.assertEqual(metrics['reported_emails'], 2)
        self.assertEqual(metrics['missing_ticket_ids'], 2)

    def test_beijing_boundary_and_environment(self):
        _, task = self.add_mail(3, 'one@example.com', 'CT-3', ['Z'])
        self.report(task, '2026-10-25T16:30:00Z', 'test')
        self.assertEqual(self.get()['metrics']['reported_orders'], 1)
        response = self.client.get('/api/operations/summary?start=2026-10-26&end=2026-10-26&environment=test', headers=self.admin)
        self.assertEqual(response.get_json()['data']['metrics']['reported_orders'], 1)
        self.db.mark_reply_sent(self.e1, '2026-10-25T16:30:00Z')
        self.assertEqual(self.get('details', '&kind=replies')['items'][0]['completed'], '2026-10-26 00:30:00')

    def test_first_activation_survives_edit_delete_and_recreate(self):
        with self.db.get_connection() as c:
            c.execute("UPDATE operations_activations SET first_enabled_at='2026-10-20T08:00:00Z'"); c.commit()
        self.suppliers.update(self.supplier['id'], SupplierConfigUpdate(name='改名运营商'))
        self.assertEqual(self.get()['metrics']['new_suppliers'], 0)
        self.suppliers.delete(self.supplier['id'])
        self.suppliers.create(SupplierConfigCreate(name='重建运营商', email='carrier@example.com', prompt_mode='auto'))
        self.assertEqual(self.get()['metrics']['new_suppliers'], 0)
        self.suppliers.create(SupplierConfigCreate(name='新增运营商', email='new@example.com', prompt_mode='auto'))
        with self.db.get_connection() as c:
            c.execute("UPDATE operations_activations SET first_enabled_at='2026-10-28T08:00:00Z' WHERE sender='new@example.com'"); c.commit()
        self.assertEqual(self.get()['metrics']['new_suppliers'], 1)
        self.login()
        self.assertEqual(self.get(admin=False)['metrics']['connected_suppliers'], 1)

    def test_legacy_activation_uses_config_creation_not_last_edit(self):
        with self.db.get_connection() as c:
            c.execute("UPDATE operations_activations SET first_enabled_at=NULL,legacy=1")
            c.execute("UPDATE supplier_configs SET create_time='2026-10-20 10:00:00',update_time='2026-10-28 10:00:00'")
            c.commit()
        self.assertEqual(self.get()['metrics']['new_suppliers'], 0)
        result = self.client.get('/api/operations/summary?start=2026-10-19&end=2026-10-25', headers=self.admin)
        self.assertEqual(result.get_json()['data']['metrics']['new_suppliers'], 1)
        self.suppliers.delete(self.supplier['id'])
        self.suppliers.create(SupplierConfigCreate(name='重建', email='carrier@example.com', prompt_mode='auto'))
        self.assertEqual(self.get()['metrics']['new_suppliers'], 0)

    def test_legacy_totals_match_trend_supplier_details_and_export(self):
        with self.db.get_connection() as c:
            c.execute('UPDATE cutover_reports SET statistics_snapshot=NULL,completed_at=NULL')
            c.commit()
        summary = self.get()
        row = self.get('suppliers')['items'][0]
        for kind, key, value in [('orders','orders',1), ('emails','reported',2), ('lines','lines',5)]:
            self.assertEqual(row[key], value)
            self.assertEqual(self.get('details', '&kind='+kind+'&supplier=carrier%40example.com')['total'], value)
        self.assertEqual(summary['trend'][-1]['reported'], 2)
        self.assertIn(',1,2,2,2,1,5,0,0,0', self.client.get('/api/operations/export'+self.query, headers=self.admin).data.decode('utf-8-sig'))

    def test_migration_is_idempotent_and_legacy_replies_are_marked(self):
        with self.db.get_connection() as c:
            c.execute('DROP TRIGGER operations_reply_success')
            c.execute("UPDATE email_records SET reply_status='sent',reply_time='2026-10-27 11:00:00' WHERE id=?", (self.e1,)); c.commit()
        EmailDatabase(self.db.db_path); EmailDatabase(self.db.db_path)
        metrics = self.get()['metrics']
        self.assertEqual(metrics['reply_emails'], 1)
        self.assertEqual(metrics['legacy_replies'], 1)

    def test_csv_protects_formula_names_and_has_same_scope(self):
        self.suppliers.update(self.supplier['id'], SupplierConfigUpdate(name='=1+1'))
        self.login()
        result = self.client.get('/api/operations/export' + self.query)
        self.assertIn("'=1+1", result.data.decode('utf-8-sig'))
        self.assertIn(',1,1,1,1,1,3,0,0,0', result.data.decode('utf-8-sig'))
        self.assertIn('no-store', result.headers['Cache-Control'])

    def test_large_dataset_pagination_search_and_aggregate(self):
        with self.db.get_connection() as c:
            c.executemany('INSERT INTO supplier_configs(name,email,prompt_mode,create_time,update_time) VALUES (?,?,\'auto\',?,?)',
                [(f'运营商{i:03}', f's{i}@example.com','2026-10-27','2026-10-27') for i in range(320)])
            c.executemany("INSERT INTO email_records(email_id,sender,receiver,subject,create_time,mail_type) VALUES (?,?,'one@example.com','维护','2026-10-27 12:00:00','割接通知')",
                [(i+100, f's{i%320}@example.com') for i in range(10000)])
            c.execute("INSERT INTO cutover_tasks(email_records_id,line_type,carrier_ticket_no,fill_result) SELECT id,'customer','LOAD-'||id,? FROM email_records WHERE email_id>=100 LIMIT 3000",
                (json.dumps({'circuits': [{'电路代号': 'L1'}, {'电路代号': 'L2'}]}),))
            c.execute("INSERT INTO cutover_reports(task_id,report_type,status,result) SELECT id,'customer','success',? FROM cutover_tasks WHERE carrier_ticket_no LIKE 'LOAD-%'",
                (json.dumps({'updated_at':'2026-10-27T12:00:00+08:00','execution_identity':{'environment':'production'}}),))
            c.commit()
        before = time.perf_counter()
        metrics = self.get()['metrics']
        elapsed = time.perf_counter()-before
        self.assertEqual(metrics['received_emails'], 10002)
        self.assertEqual(metrics['reported_orders'], 3001)
        self.assertEqual(metrics['reported_lines'], 6005)
        first = self.get('suppliers'); second = self.get('suppliers', '&page=2')
        self.assertEqual(first['total'], 321)
        self.assertEqual(len(first['items']), 20)
        self.assertFalse({r['sender'] for r in first['items']} & {r['sender'] for r in second['items']})
        self.assertEqual(self.get('suppliers','&search=%25')['total'], 0)
        self.assertEqual(self.get('suppliers','&search=s319%40example.com')['total'], 1)
        print(f'Operations scale: 321 suppliers / 10002 emails / 3001 orders; summary {elapsed:.3f}s')

    def test_replies_count_success_events_not_current_state(self):
        self.db.mark_reply_sent(self.e1, '2026-10-27 11:00:00')
        self.db.mark_reply_sent(self.e1, '2026-10-27 11:00:00')
        with self.db.get_connection() as c:
            c.execute("UPDATE email_records SET reply_status='pending' WHERE id=?", (self.e1,)); c.commit()
        self.db.mark_reply_sent(self.e1, '2026-10-28 11:00:00')
        self.assertEqual(self.get()['metrics']['reply_emails'], 2)

    def test_partial_success_does_not_blank_other_completed_orders(self):
        self.add_mail(3, 'one@example.com', 'CT-1', ['F'])
        _, complete = self.add_mail(4, 'one@example.com', 'CT-COMPLETE', ['X'])
        self.report(complete, '2026-10-28T10:00:00+08:00')
        data = self.get()['metrics']
        self.assertEqual(data['reported_orders'], 1)
        self.assertEqual(data['reported_emails'], 3)
        self.assertEqual(data['reported_lines'], 6)
        self.assertEqual(data['partial_orders'], 1)

    def test_input_validation(self):
        for extra in ['&page=0', '&page_size=10000', '&sort=drop', '&start=bad', '&environment=secret']:
            response = self.client.get('/api/operations/suppliers' + self.query + extra, headers=self.admin)
            self.assertEqual(response.status_code, 400, extra)
        self.assertEqual(self.client.get('/api/operations/summary').status_code, 401)

    def test_unmapped_senders_do_not_pretend_to_be_known_operators(self):
        self.add_mail(3, 'one@example.com', 'CT-2', [], 'unknown@example.com')
        data = self.get()
        self.assertIsNone(data['metrics']['coverage_percent'])
        self.assertEqual(data['metrics']['unmapped_senders'], 1)
        self.assertEqual(data['focus']['onboarding'][0]['sender'], 'unknown@example.com')


if __name__ == '__main__':
    unittest.main()
