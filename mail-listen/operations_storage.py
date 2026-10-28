"""Additive evidence for statistics; never infer old events from current task contents."""


def initialize_operations_storage(cursor):
    cursor.execute('''CREATE TABLE IF NOT EXISTS operations_replies (
        id INTEGER PRIMARY KEY AUTOINCREMENT, email_records_id INTEGER NOT NULL,
        sent_at TEXT NOT NULL, legacy INTEGER NOT NULL DEFAULT 0)''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_operations_replies_email ON operations_replies(email_records_id)')
    cursor.execute('''INSERT INTO operations_replies(email_records_id,sent_at,legacy)
        SELECT e.id,e.reply_time,1 FROM email_records e WHERE e.reply_status='sent'
        AND e.reply_time!='' AND NOT EXISTS (
            SELECT 1 FROM operations_replies r WHERE r.email_records_id=e.id)''')
    cursor.execute('''CREATE TRIGGER IF NOT EXISTS operations_reply_success AFTER UPDATE OF reply_status,reply_time ON email_records
        WHEN NEW.reply_status='sent' AND NEW.reply_time!='' AND
            (COALESCE(OLD.reply_status,'')!='sent' OR COALESCE(OLD.reply_time,'')!=NEW.reply_time)
        BEGIN INSERT INTO operations_replies(email_records_id,sent_at) VALUES(NEW.id,NEW.reply_time); END''')
    columns = {r[1] for r in cursor.execute('PRAGMA table_info(cutover_reports)')}
    for name in ('statistics_snapshot', 'completed_at'):
        if name not in columns:
            cursor.execute(f'ALTER TABLE cutover_reports ADD COLUMN {name} TEXT')
    cursor.execute('''UPDATE cutover_reports SET completed_at=COALESCE(json_extract(result,'$.resolved_at'),json_extract(result,'$.updated_at'))
        WHERE completed_at IS NULL AND status='success' AND json_valid(result)
        AND (json_type(result,'$.updated_at')='text' OR json_type(result,'$.resolved_at')='text') ''')
    cursor.execute('''CREATE TRIGGER IF NOT EXISTS operations_report_input AFTER INSERT ON cutover_reports BEGIN
        UPDATE cutover_reports SET statistics_snapshot=(SELECT json_object(
            'carrier_ticket_no',carrier_ticket_no,'line_type',line_type,'fill_result',fill_result)
            FROM cutover_tasks WHERE id=NEW.task_id),
            completed_at=CASE WHEN NEW.status='success' THEN COALESCE(
                CASE WHEN json_valid(NEW.result) THEN COALESCE(json_extract(NEW.result,'$.resolved_at'),json_extract(NEW.result,'$.updated_at')) END,
                strftime('%Y-%m-%dT%H:%M:%fZ','now')) END WHERE id=NEW.id;
        END''')
    cursor.execute('''CREATE TRIGGER IF NOT EXISTS operations_report_success AFTER UPDATE OF status ON cutover_reports
        WHEN NEW.status='success' AND OLD.status!='success' BEGIN
        UPDATE cutover_reports SET completed_at=COALESCE(completed_at,
            CASE WHEN json_valid(NEW.result) THEN COALESCE(json_extract(NEW.result,'$.resolved_at'),json_extract(NEW.result,'$.updated_at')) END,
            strftime('%Y-%m-%dT%H:%M:%fZ','now')) WHERE id=NEW.id; END''')


def initialize_supplier_evidence(cursor):
    cursor.execute('''CREATE TABLE IF NOT EXISTS operations_activations (
        sender TEXT PRIMARY KEY, first_enabled_at TEXT, legacy INTEGER NOT NULL DEFAULT 0)''')
    # Formal configurations already have a creation date; edits are not new enablements.
    cursor.execute('''INSERT OR IGNORE INTO operations_activations(sender,first_enabled_at,legacy)
        SELECT lower(trim(email)),create_time,1 FROM supplier_configs''')
    cursor.execute('''UPDATE operations_activations SET first_enabled_at=(
            SELECT MIN(create_time) FROM supplier_configs c WHERE lower(trim(c.email))=operations_activations.sender)
        WHERE first_enabled_at IS NULL AND legacy=1''')
    cursor.execute('''CREATE TRIGGER IF NOT EXISTS operations_supplier_created AFTER INSERT ON supplier_configs BEGIN
        INSERT OR IGNORE INTO operations_activations(sender,first_enabled_at)
        VALUES(lower(trim(NEW.email)),strftime('%Y-%m-%dT%H:%M:%fZ','now')); END''')
    cursor.execute('''CREATE TRIGGER IF NOT EXISTS operations_supplier_renamed AFTER UPDATE OF email ON supplier_configs BEGIN
        INSERT OR IGNORE INTO operations_activations(sender,first_enabled_at,legacy)
        SELECT lower(trim(NEW.email)),first_enabled_at,legacy FROM operations_activations
        WHERE sender=lower(trim(OLD.email)); END''')
