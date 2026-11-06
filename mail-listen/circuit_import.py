"""Validated, append-only circuit imports. Uploads and reports are kept in memory."""
import base64
import hashlib
import json
import secrets
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from xml.etree.ElementTree import ParseError

from itsdangerous import BadSignature, URLSafeTimedSerializer
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils.exceptions import InvalidFileException

from supplier_circuits import (
    CIRCUIT_EXPORT_HEADERS, CIRCUIT_EXPORT_SHEET_NAME, CIRCUIT_REQUIRED_HEADERS,
    _map_header_row, normalize_circuit_cell,
)

MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_IMPORT_ROWS = 10000
FIELDS = ('supplier', 'supplier_circuit_id', 'circuit_id', 'line_type', 'line_status', 'remark')
LABELS = dict(zip(FIELDS, CIRCUIT_EXPORT_HEADERS))
_FALLBACK_SIGNING_KEY = secrets.token_hex(32)


def parse_import(content):
    if len(content) > MAX_IMPORT_BYTES:
        raise ValueError('文件不能超过 10 MB')
    try:
        with ZipFile(BytesIO(content)) as archive:
            if len(archive.infolist()) > 1000 or sum(f.file_size for f in archive.infolist()) > 50 * 1024 * 1024:
                raise ValueError('Excel 解压后过大，请拆分文件')
        wb = load_workbook(BytesIO(content), read_only=True, data_only=False, keep_links=False)
    except (BadZipFile, KeyError, OSError, InvalidFileException, ParseError) as exc:
        raise ValueError('无法读取 Excel，请上传有效的 .xlsx 文件') from exc
    try:
        ws = wb[CIRCUIT_EXPORT_SHEET_NAME] if CIRCUIT_EXPORT_SHEET_NAME in wb.sheetnames else wb.active
        if (ws.max_column or 0) > 100 or (ws.max_row or 0) > MAX_IMPORT_ROWS + 1:
            raise ValueError('线路表最多支持 10,000 行数据、100 列，请拆分文件')
        iterator = ws.iter_rows()
        header = next(iterator, ())
        mapping = _map_header_row([c.value for c in header])
        missing = [LABELS[f] for f in CIRCUIT_REQUIRED_HEADERS if f not in mapping.values()]
        if missing:
            raise ValueError('线路表缺少必需表头：' + '、'.join(missing))
        # Duplicate recognized columns are ambiguous, never silently pick one.
        recognized = [next(iter(_map_header_row([c.value]).values()), None) for c in header]
        if any(recognized.count(f) > 1 for f in mapping.values()):
            raise ValueError('线路表存在重复表头，请保留每个字段的一列')
        rows = []
        for number, cells in enumerate(iterator, 2):
            if number > MAX_IMPORT_ROWS + 1 or len(cells) > 100:
                raise ValueError('线路表超过行数或列数限制')
            row = {f: '' for f in FIELDS}
            problems = []
            for index, field in mapping.items():
                if index >= len(cells):
                    continue
                cell = cells[index]
                row[field] = normalize_circuit_cell(cell.value)
                if len(row[field]) > 32767:
                    problems.append(f'{LABELS[field]} 超过 Excel 单元格长度限制')
                if cell.data_type in ('f', 'e'):
                    problems.append(f'{LABELS[field]} 不能包含公式或 Excel 错误值，请粘贴为文本')
                if field in ('supplier_circuit_id', 'circuit_id') and cell.data_type == 'n' and cell.value is not None:
                    if abs(cell.value) >= 10 ** 15 or len(row[field].replace('.', '').replace('-', '')) > 15:
                        problems.append(f'{LABELS[field]} 的长编号须使用文本格式，避免精度丢失')
            if not any(row.values()):
                continue
            for field in ('supplier', 'supplier_circuit_id'):
                if not row[field]:
                    problems.append(f'{LABELS[field]} 必填')
            row.update(row_number=number, validation_errors=problems)
            rows.append(row)
        if not rows:
            raise ValueError('线路表中没有数据，请填写模板后再导入')
        return rows
    except (BadZipFile, KeyError, OSError, ParseError) as exc:
        raise ValueError('无法读取 Excel，请检查线路表内容') from exc
    finally:
        wb.close()


def identifiers(row):
    return frozenset(value.strip() for value in row['supplier_circuit_id'].splitlines() if value.strip())


def fingerprint(row):
    return (row['supplier'], tuple(sorted(identifiers(row))), *(row[f] for f in FIELDS[2:]))


def classify_import(rows, existing):
    stored = [{f: normalize_circuit_cell(row.get(f)) for f in FIELDS} for row in existing]
    existing_index, file_index = defaultdict(set), defaultdict(list)
    for index, row in enumerate(stored):
        for number in identifiers(row):
            existing_index[(row['supplier'], number)].add(index)
    signatures = [fingerprint(row) for row in rows]
    for index, row in enumerate(rows):
        for number in identifiers(row):
            file_index[(row['supplier'], number)].append(index)
    conflicts = set()
    for members in file_index.values():
        if len({signatures[i] for i in members}) > 1:
            conflicts.update(members)
    first_seen, results = {}, []
    for index, row in enumerate(rows):
        result = {f: row[f] for f in FIELDS}
        result.update(row_number=row['row_number'], status='new', reason='', needs_review=False)
        signature = signatures[index]
        if row['validation_errors']:
            result.update(status='error', reason='；'.join(row['validation_errors']))
        elif index in conflicts:
            result.update(status='skipped', needs_review=True, reason='文件内编号重合且内容不同，相关行全部跳过，请核对后重新导入')
        else:
            matches = set()
            for number in identifiers(row):
                matches.update(existing_index.get((row['supplier'], number), ()))
            if matches:
                exact = len(matches) == 1 and signature == fingerprint(stored[next(iter(matches))])
                reason = '系统中已存在，内容一致'
                if not exact:
                    if len(matches) == 1 and identifiers(row) == identifiers(stored[next(iter(matches))]):
                        old = stored[next(iter(matches))]
                        changes = [f'{LABELS[f]}：现有「{old[f] or "空"}」，文件「{row[f] or "空"}」'
                                   for f in FIELDS[2:] if old[f] != row[f]]
                        reason = '已有线路，保留现有值；' + '；'.join(changes)
                    else:
                        reason = '编号与已有线路部分重合或匹配多条记录，整行跳过，请核对'
                result.update(status='skipped', needs_review=not exact, reason=reason)
            elif signature in first_seen:
                result.update(status='skipped', reason=f'与文件第 {first_seen[signature]} 行完全重复')
            else:
                first_seen[signature] = row['row_number']
        results.append(result)
    return {'total': len(results), 'rows': results, 'warnings': [], 'counts': {
        'new': sum(r['status'] == 'new' for r in results),
        'skipped': sum(r['status'] == 'skipped' for r in results),
        'errors': sum(r['status'] == 'error' for r in results),
        'review': sum(r['needs_review'] for r in results),
    }}


def _digest(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def import_incremental(db, content, secret, principal, *, confirm=False, token=''):
    rows = parse_import(content)
    signer = URLSafeTimedSerializer(secret or _FALLBACK_SIGNING_KEY, salt='circuit-import-preview-v1')
    # The write lock covers both classification and insert. Other writers cannot
    # change the reviewed records between these two operations.
    with db.get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE' if confirm else 'BEGIN')
        existing = [dict(row) for row in conn.execute('SELECT * FROM supplier_circuits ORDER BY id')]
        plan = classify_import(rows, existing)
        receipt = {'digest': _digest(plan), 'file': hashlib.sha256(content).hexdigest(), 'principal': principal}
        plan['preview_token'] = signer.dumps(receipt)
        if not confirm:
            return plan, 200
        try:
            approved = signer.loads(token, max_age=900)
        except BadSignature:
            approved = None
        if approved != receipt:
            plan['message'] = '文件、数据或预览有效期已变化，请重新核对预览后确认'
            return plan, 409
        if plan['counts']['errors']:
            plan['message'] = '存在校验错误，请修正文件后重新预览，本次未写入任何线路'
            return plan, 400
        if not plan['counts']['new']:
            plan['message'] = '没有需要新增的线路'
            return plan, 400
        now = datetime.now()
        for row in plan['rows']:
            if row['status'] != 'new':
                continue
            conn.execute('''INSERT INTO supplier_circuits
                (supplier, supplier_circuit_id, circuit_id, line_type, line_status, remark, create_time, update_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', tuple(row[f] for f in FIELDS) + (now, now))
            row['status'] = 'inserted'
        plan['inserted'] = plan['counts']['new']
        # Build the report before commit so a report-generation failure cannot
        # leave the UI reporting failure after the data was already committed.
        plan['report_base64'] = base64.b64encode(build_import_report(plan['rows'])).decode('ascii')
        conn.commit()
        return plan, 200


def _text_cell(ws, row, col, value):
    cell = ws.cell(row, col, str(value))
    cell.data_type = 's'  # Never let untrusted identifiers/remarks become Excel formulas.
    cell.number_format = '@'
    cell.alignment = Alignment(vertical='top', wrap_text=True)


def _style_sheet(ws, widths):
    ws.freeze_panes = 'A2'
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='3370FF')
        cell.alignment = Alignment(wrap_text=True, vertical='center')
    ws.row_dimensions[1].height = 30
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    ws.auto_filter.ref = ws.dimensions


def build_import_report(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = '导入结果'
    ws.append(['原始行号', '需核对', *CIRCUIT_EXPORT_HEADERS[:2], *CIRCUIT_EXPORT_HEADERS[2:5], '处理结果', '原因', '备注'])
    labels = {'inserted': '已新增', 'new': '待新增', 'skipped': '已跳过', 'error': '校验错误'}
    for number, row in enumerate(rows, 2):
        values = [row['row_number'], '是' if row['needs_review'] else '否', row['supplier'],
                  row['supplier_circuit_id'], row['circuit_id'], row['line_type'], row['line_status'],
                  labels[row['status']], row['reason'], row['remark']]
        for col, value in enumerate(values, 1):
            _text_cell(ws, number, col, value)
    _style_sheet(ws, {'A': 12, 'B': 10, 'C': 18, 'D': 28, 'E': 32, 'F': 12, 'G': 14, 'H': 14, 'I': 70, 'J': 40})
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def build_import_template():
    wb = Workbook()
    ws = wb.active
    ws.title = CIRCUIT_EXPORT_SHEET_NAME
    ws.append(CIRCUIT_EXPORT_HEADERS)
    _style_sheet(ws, {'A': 18, 'B': 36, 'C': 48, 'D': 18, 'E': 18, 'F': 48})
    for row in range(2, MAX_IMPORT_ROWS + 2):
        for col in (2, 3):
            cell = ws.cell(row, col)
            cell.number_format = '@'
            cell.alignment = Alignment(wrap_text=True, vertical='top')
    for col, values in [('D', '客户,骨干,语音电路,NNI'), ('E', '正常,待确认,无需上报,已拆机')]:
        validation = DataValidation(type='list', formula1='"' + values + '"', allow_blank=True)
        validation.showErrorMessage = False  # Suggestions, not a new business enum.
        ws.add_data_validation(validation)
        validation.add(f'{col}2:{col}{MAX_IMPORT_ROWS + 1}')
    guide = wb.create_sheet('填写说明与示例')
    guide.append(['字段 / 规则', '填写说明', '示例（不参与导入）'])
    instructions = [
        ('Supplier', '必填；沿用台账中的供应商名称，去除首尾空白后精确匹配', 'RT'),
        ('Supplier Circuit ID', '必填；文本格式，保留前导零；多个完整编号在同一单元格内换行', '0000123\n0000456'),
        ('Circuit ID', '选填；内部编号，支持单元格内换行；表头不能删除', 'NOC-BJ-001\nNOC-BJ-002'),
        ('类型', '选填；下拉选项仅为建议，也可填写现有业务类型', '客户 / 骨干 / 语音电路 / NNI'),
        ('线路状态', '选填；填写真实状态，留空不会自动变为正常', '正常 / 待确认 / 无需上报 / 已拆机'),
        ('备注', '选填；按原文填写，不支持公式', '线路用途或特殊处理说明'),
        ('导入范围', '仅导入“线路表”页；保留首行六列表头，示例只在本页', '版本 v1'),
        ('增量规则', '已有线路、部分编号重合整行跳过；文件内完全重复只导入一次，冲突相关行全部跳过', ''),
        ('校验错误', '缺必填值、公式、错误值须修正后重新预览；错误未修正时整批不写入', ''),
        ('文件限制', '仅支持 .xlsx，10 MB / 10,000 个数据行；编号请使用文本，避免 Excel 精度丢失', ''),
    ]
    for row in instructions:
        guide.append(row)
    _style_sheet(guide, {'A': 24, 'B': 90, 'C': 45})
    for row in guide.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
    wb.active = 0
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
