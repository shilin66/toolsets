"""Incremental circuit imports use real workbooks and isolated SQLite databases."""
import base64
import io
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from openpyxl import load_workbook

from tests.api import test_supplier_circuits_api as fixture


class CircuitIncrementalApiTest(unittest.TestCase):
    setUp = fixture.SupplierCircuitsApiTest.setUp
    tearDown = fixture.SupplierCircuitsApiTest.tearDown
    create_circuit = fixture.SupplierCircuitsApiTest.create_circuit

    def row(self, number='000123', **extra):
        return dict(supplier='RT', supplier_circuit_id=number, circuit_id='Internal-01',
                    line_type='骨干', line_status='', remark='', **extra)

    def upload(self, rows, token=None, client=None):
        if not hasattr(self, 'files'):
            self.files = {}
        key = json.dumps(rows, sort_keys=True)
        if key not in self.files:
            self.files[key] = fixture.build_import_workbook_bytes(rows)
        data = {'mode': 'append', 'file': (io.BytesIO(self.files[key]), '线路表.xlsx')}
        if token is not None:
            data.update(confirm='true', preview_token=token)
        return (client or self.client).post('/api/circuits/import', headers=self.headers, data=data)

    def test_preview_commit_and_retry_preserve_existing(self):
        old = self.create_circuit(supplier_circuit_id='OLD', line_status='已拆机')
        rows = [self.row(), {**self.row('OLD'), 'line_status': '正常'}, self.row()]
        preview = self.upload(rows).get_json()['data']
        self.assertEqual(preview['counts'], {'new': 1, 'skipped': 2, 'errors': 0, 'review': 1})
        self.assertEqual(self.db.count_supplier_circuits(), 1)
        response = self.upload(rows, preview['preview_token'])
        self.assertEqual(response.status_code, 200, response.get_json())
        result = response.get_json()['data']
        self.assertEqual(result['inserted'], 1)
        self.assertEqual(self.db.get_supplier_circuit(old['id']), old)
        self.assertEqual(self.db.count_supplier_circuits(), 2)
        self.assertEqual(self.upload(rows, preview['preview_token']).status_code, 409)
        self.assertEqual(self.db.count_supplier_circuits(), 2)
        wb = load_workbook(io.BytesIO(base64.b64decode(result['report_base64'])))
        self.assertEqual(wb.active.max_row, 4)
        self.assertEqual(wb.active.cell(2, 4).value, '000123')
        self.assertIn('新增', wb.active.cell(2, 8).value)
        wb.close()

    def test_multiline_overlap_file_conflicts_and_exact_matching(self):
        self.create_circuit(supplier_circuit_id='A\nB')
        rows = [self.row('B\nC'), self.row('X'), {**self.row('X'), 'remark': 'conflict'},
                self.row('Q\nR'), self.row('R\nS'), self.row('A1'), self.row('a'),
                {**self.row('A'), 'supplier': 'CT'}, self.row('P'), self.row('P')]
        data = self.upload(rows).get_json()['data']
        self.assertEqual(data['counts'], {'new': 4, 'skipped': 6, 'errors': 0, 'review': 5})
        self.assertEqual([row['status'] for row in data['rows'][:5]], ['skipped'] * 5)
        self.assertTrue(all(row['needs_review'] for row in data['rows'][:5]))
        self.assertEqual(self.upload(rows, data['preview_token']).status_code, 200)
        self.assertEqual(self.db.count_supplier_circuits(), 5)

    def test_errors_block_entire_batch_and_preserve_physical_row_numbers(self):
        rows = [self.row(), {}, {**self.row('bad'), 'supplier': ''}]
        data = self.upload(rows).get_json()['data']
        self.assertEqual(data['counts']['errors'], 1)
        self.assertEqual([row['row_number'] for row in data['rows']], [2, 4])
        self.assertEqual(self.upload(rows, data['preview_token']).status_code, 400)
        self.assertEqual(self.db.count_supplier_circuits(), 0)

    def test_changed_file_and_database_require_new_preview(self):
        rows = [self.row()]
        data = self.upload(rows).get_json()['data']
        changed = [{**rows[0], 'remark': 'changed'}]
        self.assertEqual(self.upload(changed, data['preview_token']).status_code, 409)
        self.create_circuit(supplier_circuit_id='000123')
        response = self.upload(rows, data['preview_token'])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()['data']['counts']['new'], 0)
        self.assertEqual(self.db.count_supplier_circuits(), 1)

    def test_missing_tampered_or_expired_preview_never_writes(self):
        for token in ('', 'not-signed'):
            self.assertEqual(self.upload([self.row()], token).status_code, 409)
        with patch('itsdangerous.timed.TimestampSigner.get_timestamp', return_value=1):
            token = self.upload([self.row()]).get_json()['data']['preview_token']
        self.assertEqual(self.upload([self.row()], token).status_code, 409)
        self.assertEqual(self.db.count_supplier_circuits(), 0)

    def test_concurrent_confirmations_only_insert_once(self):
        rows = [self.row()]
        token = self.upload(rows).get_json()['data']['preview_token']
        barrier = threading.Barrier(2)
        def commit():
            client = fixture.api_server.app.test_client()
            barrier.wait()
            return self.upload(rows, token, client).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = sorted(pool.map(lambda _: commit(), range(2)))
        self.assertEqual(statuses, [200, 409])
        self.assertEqual(self.db.count_supplier_circuits(), 1)

    def test_failed_insert_rolls_back_entire_batch(self):
        with self.db.get_connection() as conn:
            conn.execute("CREATE TRIGGER reject_test BEFORE INSERT ON supplier_circuits WHEN NEW.supplier_circuit_id = 'FAIL' BEGIN SELECT RAISE(ABORT, 'test failure'); END")
            conn.commit()
        rows = [self.row(), self.row('FAIL')]
        token = self.upload(rows).get_json()['data']['preview_token']
        self.assertEqual(self.upload(rows, token).status_code, 500)
        self.assertEqual(self.db.count_supplier_circuits(), 0)

    def test_template_is_blank_text_formatted_and_round_trips(self):
        response = self.client.get('/api/circuits/template', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        wb = load_workbook(io.BytesIO(response.data))
        self.assertEqual(wb.active.title, '线路表')
        self.assertEqual(wb.sheetnames, ['线路表', '填写说明与示例'])
        self.assertEqual(tuple(cell.value for cell in wb.active[1]), fixture.supplier_circuits.CIRCUIT_EXPORT_HEADERS)
        self.assertTrue(all(cell.value is None for row in wb.active.iter_rows(min_row=2) for cell in row))
        self.assertEqual(wb.active['B2'].number_format, '@')
        for index, value in enumerate(['RT', '0000123\n0000456', 'Internal\nSecond', '', '', ''], 1):
            wb.active.cell(2, index, value)
        wb.active = 1  # Opening the instructions must not change which sheet is imported.
        buf = io.BytesIO()
        wb.save(buf)
        wb.close()
        response = self.client.post('/api/circuits/import', headers=self.headers, data={
            'mode': 'append', 'file': (io.BytesIO(buf.getvalue()), 'filled.xlsx')})
        data = response.get_json()['data']
        self.assertEqual(data['counts']['new'], 1)
        self.assertEqual(data['rows'][0]['supplier_circuit_id'], '0000123\n0000456')
        self.assertEqual(data['rows'][0]['line_status'], '')
        legacy = self.client.post('/api/circuits/import', headers=self.headers, data={
            'mode': 'replace', 'file': (io.BytesIO(buf.getvalue()), 'filled.xlsx')})
        self.assertEqual(legacy.status_code, 200)
        self.assertEqual(legacy.get_json()['data']['total'], 1)
        self.assertEqual(self.client.get('/api/circuits/template').status_code, 401)

    def test_invalid_mode_and_file_are_rejected(self):
        for filename, content, mode in [('bad.txt', b'bad', 'append'), ('bad.xlsx', b'bad', 'append'),
                                       ('file.xlsx', fixture.build_import_workbook_bytes([self.row()]), 'unknown')]:
            response = self.client.post('/api/circuits/import', headers=self.headers,
                data={'mode': mode, 'file': (io.BytesIO(content), filename)})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.count_supplier_circuits(), 0)

    def test_formulas_are_validation_errors(self):
        data = self.upload([{**self.row(), 'remark': '=1+1'}]).get_json()['data']
        self.assertEqual(data['counts']['errors'], 1)
        self.assertIn('公式', data['rows'][0]['reason'])

    def test_scientific_notation_and_long_numeric_identifiers_need_text(self):
        for value in (1.23456789e20, 1234567890123456):
            with self.subTest(value=value):
                data = self.upload([self.row(value)]).get_json()['data']
                self.assertEqual(data['counts']['errors'], 1)
                self.assertIn('文本格式', data['rows'][0]['reason'])
                self.assertEqual(self.upload([self.row(value)], data['preview_token']).status_code, 400)
        self.assertEqual(self.db.count_supplier_circuits(), 0)

    def test_size_and_row_limits_and_blank_template(self):
        response = self.client.post('/api/circuits/import', headers=self.headers,
            data={'mode': 'append', 'file': (io.BytesIO(b'x' * (10 * 1024 * 1024 + 1)), 'large.xlsx')})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.upload([self.row(str(i)) for i in range(10001)]).status_code, 400)
        template = self.client.get('/api/circuits/template', headers=self.headers).data
        response = self.client.post('/api/circuits/import', headers=self.headers,
            data={'mode': 'append', 'file': (io.BytesIO(template), 'blank.xlsx')})
        self.assertEqual(response.status_code, 400)
        self.assertIn('没有数据', response.get_json()['message'])
        self.assertEqual(self.db.count_supplier_circuits(), 0)

    def test_regular_user_template_and_import_require_session_and_csrf(self):
        from user_access import UserAccessRepository
        repo = UserAccessRepository(self.db)
        repo.create_user('importer', 'a-secure-password', 'Importer')
        client = fixture.api_server.app.test_client()
        response = client.post('/api/auth/login', json={'username': 'importer', 'password': 'a-secure-password'})
        csrf = response.get_json()['data']['csrf_token']
        self.assertEqual(client.get('/api/circuits/template').status_code, 200)
        content = fixture.build_import_workbook_bytes([self.row()])
        def upload(headers, token=None):
            data = {'mode': 'append', 'file': (io.BytesIO(content), 'new.xlsx')}
            if token is not None:
                data.update(confirm='true', preview_token=token)
            return client.post('/api/circuits/import', data=data, headers=headers)
        self.assertEqual(upload({}).status_code, 403)
        data = upload({'X-CSRF-Token': csrf}).get_json()['data']
        self.assertEqual(self.upload([self.row()], data['preview_token']).status_code, 409)
        self.assertEqual(upload({'X-CSRF-Token': csrf}, data['preview_token']).status_code, 200)

    def test_text_that_looks_like_formula_remains_text_in_report(self):
        from circuit_import import build_import_report
        content = build_import_report([{**self.row('=123'), 'row_number': 2, 'needs_review': False,
                                       'status': 'inserted', 'reason': '', 'remark': '=HYPERLINK("https://example.com")'}])
        wb = load_workbook(io.BytesIO(content), data_only=False)
        self.assertEqual(wb.active['D2'].data_type, 's')
        self.assertEqual(wb.active['J2'].data_type, 's')
        wb.close()
