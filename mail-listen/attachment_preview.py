"""Bounded, offline content previews. Originals are never changed or executed."""

import csv
import io
import re
from datetime import date, datetime, time
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from email_attachments import _decode_text_attachment

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_ZIP_BYTES = 40 * 1024 * 1024
MAX_ROWS = 500
MAX_COLUMNS = 64
MAX_SHEETS = 20
MAX_BLOCKS = 300
MAX_CHARACTERS = 300_000


class PreviewError(ValueError):
    pass


def attachment_display_name(filename):
    return re.sub(r'^[0-9a-f]{32}-', '', Path(filename).name, flags=re.I)


class Budget:
    def __init__(self):
        self.remaining = MAX_CHARACTERS
        self.truncated = False

    def text(self, value):
        value = '' if value is None else str(value)
        length = min(8000, self.remaining)
        if len(value) > length:
            value = value[:length] + '…'
            self.truncated = True
        self.remaining -= min(len(value), length)
        return value


def _check_archive(path):
    """Limit expansion before XML parsers run; Office previews never need DTDs."""
    with ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 2000 or sum(item.file_size for item in entries) > MAX_ZIP_BYTES:
            raise PreviewError('文件展开后过大，请下载查看原文件。')
        for item in entries:
            if item.flag_bits & 1:
                raise PreviewError('加密附件无法预览，请下载后打开。')
            if item.filename.lower().endswith(('.xml', '.rels')):
                # UTF-16/32 XML still has ASCII declaration bytes after NUL removal.
                xml = archive.read(item).replace(b'\x00', b'').upper()
                if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
                    raise PreviewError('附件包含不支持的 XML 声明，无法预览。')


def _text_preview(path, budget):
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise PreviewError('文本附件超过 2 MB，请下载查看原文件。')
    try:
        text, _ = _decode_text_attachment(path.read_bytes(), None)
    except (ValueError, UnicodeError, LookupError) as error:
        raise PreviewError('无法可靠识别附件编码，请下载查看原文件。') from error
    if re.search(r'[\x00-\x08\x0b\x0e-\x1f]', text):
        raise PreviewError('附件不是可预览的文本。')
    if path.suffix.lower() not in ('.csv', '.tsv'):
        return {'kind': 'text', 'text': budget.text(text)}
    try:
        delimiter = '\t' if path.suffix.lower() == '.tsv' else ','
        try:
            delimiter = csv.Sniffer().sniff(text[:65536], delimiters=',\t;').delimiter
        except csv.Error:
            if '\t' in text.split('\n', 1)[0]:
                delimiter = '\t'
        reader = csv.reader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True)
        rows = []
        for index, row in enumerate(reader):
            if index > MAX_ROWS or budget.remaining <= 0:
                budget.truncated = True
                break
            budget.truncated |= len(row) > MAX_COLUMNS
            rows.append([budget.text(cell) for cell in row[:MAX_COLUMNS]])
        columns = rows.pop(0) if rows else []
        width = max([len(columns)] + [len(row) for row in rows])
        columns += [f'列 {index + 1}' for index in range(len(columns), width)]
        return {'kind': 'table', 'sheets': [{'name': 'CSV', 'columns': columns, 'rows': rows}]}
    except csv.Error as error:
        raise PreviewError('表格格式不完整，请下载核对原文件。') from error


def _cell_text(cell):
    value = cell.value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat(sep=' ') if isinstance(value, datetime) else value.isoformat()
    # Preserve common Excel identifier formats such as 000000; text IDs stay exact.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        integer = isinstance(value, int) or value.is_integer()
        number_format = cell.number_format or ''
        if integer and re.fullmatch(r'0{2,64}', number_format):
            return str(int(value)).zfill(len(number_format))
    return value


def _xlsx_preview(path, budget):
    _check_archive(path)
    workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    sheets = []
    try:
        budget.truncated |= len(workbook.worksheets) > MAX_SHEETS
        for worksheet in workbook.worksheets[:MAX_SHEETS]:
            if budget.remaining <= 0:
                budget.truncated = True
                break
            width = min(worksheet.max_column or 1, MAX_COLUMNS)
            budget.truncated |= (worksheet.max_column or 0) > MAX_COLUMNS
            rows = []
            for index, row in enumerate(worksheet.iter_rows(max_row=MAX_ROWS + 1, max_col=width)):
                if index >= MAX_ROWS or budget.remaining <= 0:
                    budget.truncated = True
                    break
                rows.append([budget.text(_cell_text(cell)) for cell in row])
            while rows and not any(rows[-1]):
                rows.pop()
            sheets.append({'name': worksheet.title,
                           'columns': [get_column_letter(index + 1) for index in range(width)], 'rows': rows})
    finally:
        workbook.close()
    return {'kind': 'table', 'sheets': sheets, 'note': 'Excel 按内容预览；公式以原文显示，不执行计算。'}


def _docx_preview(path, budget):
    _check_archive(path)
    with ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read('word/document.xml'))
    namespace = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    body = root.find(namespace + 'body')
    if body is None:
        raise PreviewError('Word 文档缺少正文。')

    def paragraph(node):
        return ''.join((part.text or '') if part.tag == namespace + 't' else
                       '\t' if part.tag == namespace + 'tab' else
                       '\n' if part.tag in (namespace + 'br', namespace + 'cr') else ''
                       for part in node.iter())

    blocks = []
    for child in body:
        if len(blocks) >= MAX_BLOCKS or budget.remaining <= 0:
            budget.truncated = True
            break
        if child.tag == namespace + 'p':
            blocks.append({'kind': 'text', 'text': budget.text(paragraph(child))})
        elif child.tag == namespace + 'tbl':
            rows = []
            for index, row in enumerate(child.findall(namespace + 'tr')):
                if index >= MAX_ROWS or budget.remaining <= 0:
                    budget.truncated = True
                    break
                cells = row.findall(namespace + 'tc')
                budget.truncated |= len(cells) > MAX_COLUMNS
                rows.append([budget.text('\n'.join(paragraph(p) for p in cell.findall(namespace + 'p')))
                             for cell in cells[:MAX_COLUMNS]])
            blocks.append({'kind': 'table', 'rows': rows})
    return {'kind': 'document', 'blocks': blocks, 'note': 'Word 按正文和表格预览；原始排版及图片请下载查看。'}


def build_attachment_preview(path):
    path = Path(path)
    size = path.stat().st_size
    result = {'name': attachment_display_name(path.name), 'size': size, 'truncated': False}
    if size > MAX_FILE_BYTES:
        return {**result, 'kind': 'unsupported', 'note': '附件超过 20 MB，请下载查看原文件。'}
    extension = path.suffix.lower()
    budget = Budget()
    if extension in ('.csv', '.tsv', '.txt', '.log'):
        preview = _text_preview(path, budget)
    elif extension == '.xlsx':
        preview = _xlsx_preview(path, budget)
    elif extension == '.docx':
        preview = _docx_preview(path, budget)
    elif extension == '.pdf':
        with path.open('rb') as source:
            if not source.read(5).startswith(b'%PDF-'):
                raise PreviewError('附件不是有效的 PDF 文件。')
        preview = {'kind': 'pdf'}
    elif extension in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'):
        from PIL import Image
        with Image.open(path) as image:
            if image.format not in ('PNG', 'JPEG', 'GIF', 'WEBP', 'BMP'):
                raise PreviewError('图片格式与文件类型不符。')
            image.verify()
        preview = {'kind': 'image'}
    else:
        preview = {'kind': 'unsupported', 'note': '此格式暂不支持在线预览，请下载后查看。'}
    return {**result, **preview, 'truncated': budget.truncated}
