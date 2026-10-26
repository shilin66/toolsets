import unittest

from mail_operation_guard import MailOperationConflict, guard_mail_operation
from tests.api import test_cutover_task_api as fixture


class MailOperationGuardTest(unittest.TestCase):
    def setUp(self):
        self.api = fixture.CutoverTaskApiTest()
        self.api.setUp()
        self.addCleanup(self.api.tearDown)
        self.db = self.api.db
        self.record_id = self.api.email_records_id

    def mark_deleting(self):
        record = self.db.get_email_record_by_id(self.record_id)
        with self.db.get_connection() as conn:
            conn.execute('''INSERT INTO mail_deletions
                (email_records_id,mailbox_address,email_uid) VALUES (?,?,?)''',
                (self.record_id, record['receiver'].strip().casefold(), record['email_id']))
            conn.commit()

    def test_pending_delete_blocks_mutations_but_keeps_detail_available_for_retry(self):
        self.mark_deleting()
        requests = [
            ('put', f'/api/cutover/emails/{self.record_id}/extraction', {}),
            ('post', '/api/cutover/tasks/generate', {'email_records_id': self.record_id}),
            ('post', '/api/cutover/reply', {'email_records_id': self.record_id}),
            ('post', '/api/cutover/reply/confirm', {'email_records_id': self.record_id}),
            ('post', f'/api/cutover/emails/{self.record_id}/forward-attempts', {}),
        ]
        for method, url, body in requests:
            with self.subTest(url=url):
                response = getattr(self.api.client, method)(url, headers=self.api.headers, json=body)
                self.assertEqual(response.status_code, 409)
                self.assertIn('删除', response.get_json()['message'])
        self.assertEqual(self.api.client.get(f'/api/cutover/emails/{self.record_id}',
            headers=self.api.headers).status_code, 200)

    def test_authentication_precedes_deletion_state_check(self):
        self.mark_deleting()
        response = self.api.client.post('/api/cutover/tasks/generate',
            json={'email_records_id': self.record_id})
        self.assertEqual(response.status_code, 401)

    def test_active_api_mutation_prevents_delete_without_touching_records(self):
        with guard_mail_operation(self.db, self.record_id):
            response = self.api.client.delete(f'/api/cutover/emails/{self.record_id}',
                headers=self.api.headers)
            self.assertEqual(response.status_code, 409)
            self.assertIsNone(self.db.get_mail_deletion(self.record_id))
        self.assertIsNotNone(self.db.get_email_record_by_id(self.record_id))

    def test_forwarding_does_not_hold_lock_needed_by_synchronous_workflow_callback(self):
        with guard_mail_operation(self.db, self.record_id, forwarding=True):
            with guard_mail_operation(self.db, self.record_id):
                pass
        with guard_mail_operation(self.db, self.record_id):
            with self.assertRaises(MailOperationConflict):
                with guard_mail_operation(self.db, self.record_id, deleting=True):
                    self.fail('Concurrent delete must not enter')

    def test_other_mail_remains_independent_and_lock_releases_on_error(self):
        other_id = self.api.insert_email_record()
        with guard_mail_operation(self.db, self.record_id):
            with guard_mail_operation(self.db, other_id):
                pass
        with self.assertRaisesRegex(RuntimeError, 'failed edit'):
            with guard_mail_operation(self.db, self.record_id):
                raise RuntimeError('failed edit')
        with guard_mail_operation(self.db, self.record_id):
            pass
