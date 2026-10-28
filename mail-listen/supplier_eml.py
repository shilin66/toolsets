"""Parse an uploaded supplier sample without storing mail or contacting services."""
import base64
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr

from email_attachments import is_calendar_attachment, normalize_text_attachment, sanitize_attachment_filename

MAX_EML_BYTES = 20 * 1024 * 1024


def parse_supplier_eml(raw: bytes) -> dict:
    if not raw or len(raw) > MAX_EML_BYTES:
        raise ValueError('邮件文件不能为空，且不能超过 20 MB')
    message = BytesParser(policy=policy.default).parsebytes(raw)
    if not message.get('From') and not message.get('Subject'):
        raise ValueError('无法识别邮件，请选择完整的 .eml 文件')
    body = message.get_body(preferencelist=('html', 'plain'))
    content = ''
    if body is not None:
        try:
            content = body.get_content()
        except LookupError:
            content = (body.get_payload(decode=True) or b'').decode('utf-8', errors='replace')
    if len(content.encode('utf-8')) > 2 * 1024 * 1024:
        raise ValueError('邮件正文超过 2 MB，请使用更小的邮件样本')
    attachments, skipped = [], []

    def collect(part):
        name = part.get_filename()
        if is_calendar_attachment(name or '', part.get_content_type()):
            skipped.append(name or 'calendar.ics')
            return
        if part.get_content_disposition() == 'attachment' or name:
            if len(attachments) >= 30:
                raise ValueError('邮件附件超过 30 个，请使用更小的邮件样本')
            # Forwarded messages remain one attachment, never another sample body.
            if part.get_content_type() == 'message/rfc822':
                payload = part.get_payload()[0].as_bytes()
                name = name or 'forwarded.eml'
            else:
                payload = part.get_payload(decode=True) or b''
            name = sanitize_attachment_filename(name or 'attachment')
            payload = normalize_text_attachment(name, payload, charset=part.get_content_charset())
            attachments.append({'name': name, 'type': part.get_content_type(),
                                'base64': base64.b64encode(payload).decode('ascii')})
        elif part.is_multipart():
            for child in part.iter_parts():
                collect(child)

    collect(message)
    return {'subject': str(message.get('Subject', '')), 'sender': parseaddr(str(message.get('From', '')))[1],
            'content': content, 'attachments': attachments, 'skipped_attachments': skipped}
