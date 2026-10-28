"""Release excess sample source data after all independent AI branches finish."""
from pathlib import Path

from loguru import logger


def cleanup_excess_samples(db):
    from email_attachments import DATA_DIR, attachment_path_from_relative
    from mail_artifacts import source_email_archive_path

    root = Path(DATA_DIR).resolve()
    try:
        with db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('DELETE FROM unconfigured_sample_cleanup WHERE email_records_id NOT IN (SELECT id FROM email_records)')
            records = conn.execute('''SELECT e.* FROM unconfigured_sample_cleanup c
                JOIN email_records e ON e.id=c.email_records_id
                WHERE e.processing_origin='unconfigured'
                AND NOT EXISTS (SELECT 1 FROM supplier_draft_samples s WHERE s.email_records_id=e.id)
                AND NOT EXISTS (SELECT 1 FROM mail_ai_jobs j WHERE j.email_records_id=e.id
                    AND j.status NOT IN ('succeeded','cancelled'))
                AND NOT EXISTS (SELECT 1 FROM mail_deletions d WHERE d.email_records_id=e.id)
                LIMIT 20''').fetchall()
            if not records:
                conn.commit()
                return
            # Resolve aliases before comparing: shared files must survive cleanup.
            references = {}
            for other in conn.execute('SELECT id,attachments FROM email_records'):
                for value in db.deserialize_attachments(other['attachments']):
                    path = attachment_path_from_relative(value, data_dir=root)
                    if path:
                        references.setdefault(path.resolve(), set()).add(other['id'])
            for record in records:
                paths = set()
                for value in db.deserialize_attachments(record['attachments']):
                    path = attachment_path_from_relative(value, data_dir=root)
                    if path and references.get(path.resolve(), set()) <= {record['id']}:
                        paths.add(path)
                archive = source_email_archive_path(root, mailbox_address=record['receiver'], email_uid=int(record['email_id']))
                shared_archive = conn.execute('''SELECT 1 FROM email_records WHERE id!=? AND email_id=?
                    AND lower(receiver)=lower(?)''', (record['id'], record['email_id'], record['receiver'])).fetchone()
                if not shared_archive:
                    paths.add(archive)
                try:
                    for path in paths:
                        # Never follow a link outside the managed directory or remove directories.
                        if path.resolve().is_relative_to(root) and not path.is_dir():
                            path.unlink(missing_ok=True)
                except OSError as error:
                    logger.warning('超额样本文件清理待重试 email_records_id={} error={}', record['id'], type(error).__name__)
                    continue
                conn.execute("UPDATE email_records SET content='', html_content='', attachments='[]' WHERE id=?", (record['id'],))
                for owners in references.values():
                    owners.discard(record['id'])
                conn.execute('DELETE FROM unconfigured_sample_cleanup WHERE email_records_id=?', (record['id'],))
                logger.info('超额样本原文已清理 email_records_id={} reason_code=sample_source_released', record['id'])
            conn.commit()
    except Exception as error:
        # Cleanup must not turn a successfully persisted analysis into a failed job.
        logger.warning('超额样本清理待重试 error={}', type(error).__name__)
