"""Durable, retryable cleanup for mail belonging to excluded supplier drafts."""
import time
from loguru import logger


def cleanup_excluded_sender_mail(db, *, data_dir=None):
    from email_attachments import DATA_DIR
    from cutover_deletion import delete_cutover_email

    root = data_dir if data_dir is not None else DATA_DIR
    with db.get_connection() as conn:
        targets = conn.execute('SELECT email_records_id FROM excluded_sender_mail_cleanup WHERE next_run_at<=? LIMIT 20',
                               (time.time(),)).fetchall()
    for target in targets:
        email_id = target['email_records_id']
        try:
            delete_cutover_email(db, root, email_id)
            with db.get_connection() as conn:
                conn.execute('DELETE FROM excluded_sender_mail_cleanup WHERE email_records_id=?', (email_id,))
                conn.commit()
        except Exception as error:
            logger.warning('排除发件人邮件清理待重试 email_records_id={} error={}', email_id, type(error).__name__)
            with db.get_connection() as conn:
                conn.execute('UPDATE excluded_sender_mail_cleanup SET next_run_at=? WHERE email_records_id=?',
                             (time.time() + 30, email_id))
                conn.commit()
