"""Permission-scoped SQL aggregates. Only bounded aggregates/pages leave SQLite."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from rpa.session_config import PortalSessionSettings
from user_access import UserAccessRepository

TZ = ZoneInfo('Asia/Shanghai')


def local_day(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return timestamp.replace(tzinfo=TZ).date().isoformat() if timestamp.tzinfo is None else timestamp.astimezone(TZ).date().isoformat()
    except ValueError:
        return None


def local_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=TZ)
        return timestamp.astimezone(TZ).strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None


def report_day(completed_at, result, created_at):
    """Success timestamps are local/offset-aware; SQLite report creation is UTC."""
    result = json_object(result)
    for value in (completed_at, result.get('resolved_at'), result.get('updated_at')):
        day = local_day(value)
        if day:
            return day
    try:
        timestamp = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(TZ).date().isoformat()
    except (AttributeError, ValueError, TypeError):
        return None


def json_object(value):
    try:
        value = json.loads(value) if isinstance(value, str) else value
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def url_origin(value):
    try:
        url = urlsplit(str(value or ''))
        if url.scheme not in ('http', 'https') or not url.hostname:
            return None
        return url.scheme, url.hostname, url.port or (443 if url.scheme == 'https' else 80)
    except ValueError:
        return None


@dataclass
class Options:
    start: str
    end: str
    mailboxes: list[int] | None
    environment: str = 'all'
    supplier: str | None = None
    search: str = ''
    status: str = 'active'
    sort: str = 'received'
    page: int = 1
    page_size: int = 20
    kind: str = 'orders'
    ticket: str = ''

    @classmethod
    def parse(cls, args):
        if any(len(args.getlist(key)) > 1 for key in args):
            raise ValueError('查询参数不可重复')
        today = datetime.now(TZ).date()
        defaults = {'start': (today-timedelta(days=today.weekday())).isoformat(), 'end': today.isoformat()}
        values = {}
        for key in ('start', 'end'):
            raw = args.getlist(key)
            if len(raw) > 1:
                raise ValueError('日期参数不可重复')
            value = args.get(key, defaults[key])
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError('日期格式须为 YYYY-MM-DD')
            values[key] = value
        if not 0 <= (date.fromisoformat(values['end'])-date.fromisoformat(values['start'])).days <= 366:
            raise ValueError('统计周期须为 1–367 天')
        values['mailboxes'] = None
        if 'mailboxes' in args:
            raw = args.getlist('mailboxes')
            if len(raw) != 1:
                raise ValueError('邮箱参数不可重复')
            values['mailboxes'] = sorted({int(v) for v in raw[0].split(',') if v})
            if len(values['mailboxes']) > 1000 or any(v <= 0 for v in values['mailboxes']):
                raise ValueError('邮箱参数无效')
        allowed = {'environment': ('production','test','all'), 'status': ('active','all','unconfigured','pending','configured'),
                   'sort': ('received','reported','pending','name'), 'kind': ('orders','lines','emails','replies')}
        for key, choices in allowed.items():
            values[key] = args.get(key, getattr(cls, key))
            if values[key] not in choices:
                raise ValueError('筛选选项无效')
        for key, limit in [('supplier', 254), ('search', 100), ('ticket', 256)]:
            if key == 'supplier' and key not in args:
                values[key] = None
                continue
            values[key] = args.get(key, '').strip()
            if len(values[key]) > limit:
                raise ValueError('查询内容过长')
        for key in ('page','page_size'):
            values[key] = int(args.get(key, getattr(cls, key)))
        if values['page'] < 1 or values['page'] > 100000 or values['page_size'] not in (20,50):
            raise ValueError('分页参数无效')
        return cls(**values)


class OperationsRepository:
    def __init__(self, db, principal, options):
        if principal is None:
            raise PermissionError('请先登录')
        self.db, self.principal, self.options = db, principal, options
        self.boxes = [b for b in UserAccessRepository(db).mailbox_options(principal) if b['can_operate']]
        available = {b['account_id'] for b in self.boxes}
        selected = available if options.mailboxes is None else set(options.mailboxes)
        if not selected <= available:
            raise PermissionError('选择的邮箱不存在或没有操作权限')
        self.selected = selected
        settings = PortalSessionSettings()
        self.environment_origins = {
            env: {origin for field in ('login_url', 'mobile_login_url', 'session_check_url')
                  if (origin := url_origin(getattr(settings, env + '_' + field)))}
            for env in ('test', 'production')
        }

    def report_environment(self, result, job_environment):
        result = json_object(result)
        identity = result.get('execution_identity')
        identity = identity if isinstance(identity, dict) else {}
        for value in (job_environment, identity.get('environment'), result.get('environment')):
            if value in ('test', 'production'):
                return value
        origin = url_origin(result.get('final_url'))
        matches = [env for env, origins in self.environment_origins.items() if origin in origins]
        return matches[0] if len(matches) == 1 else None

    def _base(self, conn, filter_supplier=True):
        conn.create_function('ops_day', 1, local_day, deterministic=True)
        conn.create_function('ops_time', 1, local_timestamp, deterministic=True)
        conn.create_function('ops_report_day', 3, report_day, deterministic=True)
        conn.create_function('ops_environment', 2, self.report_environment, deterministic=True)
        o = self.options
        scope, params = UserAccessRepository.email_scope(self.principal, 'e', operate=True)
        # Admin without explicit mailbox filter includes historical/unconfigured receivers.
        if o.mailboxes is not None or not self.principal.is_admin:
            addresses = [b['email_address'].strip().lower() for b in self.boxes if b['account_id'] in self.selected]
            scope += ' AND lower(trim(e.receiver)) IN (' + ','.join('?' for _ in addresses) + ')' if addresses else ' AND 0'
            params.extend(addresses)
        if filter_supplier and o.supplier is not None:
            scope += " AND lower(trim(COALESCE(e.sender,'')))=?"
            params.append(o.supplier.lower())
        params += [o.environment, o.environment]
        sql = f'''WITH
        m AS MATERIALIZED (
            SELECT e.id,lower(trim(COALESCE(e.sender,''))) sender,e.receiver,e.subject,
                ops_day(e.create_time) received,e.mail_type FROM email_records e
            WHERE {scope} AND NOT EXISTS (SELECT 1 FROM mail_deletions d WHERE d.email_records_id=e.id)),
        tasks AS MATERIALIZED (
            SELECT t.id,t.email_records_id,t.carrier_ticket_no ticket,t.status,t.create_time,t.update_time,
                t.line_type,t.fill_result,m.sender
            FROM cutover_tasks t JOIN m ON m.id=t.email_records_id),
        reports_raw AS (
            SELECT r.id,r.task_id,r.status,ops_report_day(r.completed_at,r.result,r.create_time) completed,
                COALESCE(CASE WHEN json_valid(j.task_snapshot) THEN j.task_snapshot END,
                    CASE WHEN json_valid(r.statistics_snapshot) THEN r.statistics_snapshot END,
                    json_object('carrier_ticket_no',t.ticket,'line_type',COALESCE(r.report_type,t.line_type),
                        'fill_result',CASE WHEN COALESCE(r.report_type,t.line_type)=t.line_type THEN t.fill_result END)) snapshot,
                (COALESCE(json_valid(j.task_snapshot),0) OR COALESCE(json_valid(r.statistics_snapshot),0)) has_snapshot,
                ops_environment(r.result,j.environment) environment
            FROM cutover_reports r JOIN tasks t ON t.id=r.task_id LEFT JOIN rpa_report_jobs j ON j.report_id=r.id
            UNION ALL
            SELECT -t.id,t.id,'success',COALESCE(ops_day(t.update_time),ops_day(t.create_time)),
                json_object('carrier_ticket_no',t.ticket,'line_type',t.line_type,'fill_result',t.fill_result),0,NULL
            FROM tasks t WHERE t.status='reported'
                AND NOT EXISTS(SELECT 1 FROM cutover_reports r WHERE r.task_id=t.id)),
        reports AS MATERIALIZED (
            SELECT * FROM reports_raw WHERE status='success' AND completed IS NOT NULL
            AND (?='all' OR environment=?) AND json_valid(snapshot)),
        success_tasks AS (
            SELECT task_id,MIN(completed) completed FROM reports GROUP BY task_id),
        task_state AS (
            SELECT t.id,t.email_records_id,t.ticket,t.status,t.sender,
                CASE WHEN s.completed<=:end THEN s.completed END completed
            FROM tasks t LEFT JOIN success_tasks s ON s.task_id=t.id),
        email_state AS (
            SELECT email_records_id id,sender,COUNT(*) tasks,COUNT(completed) done,MAX(completed) completed
            FROM task_state GROUP BY email_records_id),
        snapshots AS (
            SELECT r.id report_id,r.task_id,r.completed,t.email_records_id email_id,t.sender,
                trim(COALESCE(json_extract(r.snapshot,'$.carrier_ticket_no'),'')) ticket,
                json_extract(r.snapshot,'$.line_type') line_type,
                CASE WHEN json_valid(json_extract(r.snapshot,'$.fill_result'))
                    THEN json_extract(r.snapshot,'$.fill_result') ELSE '{{}}' END payload
            FROM reports r JOIN tasks t ON t.id=r.task_id),
        order_members AS (
            SELECT task_id,email_id,sender,ticket,MIN(completed) completed FROM snapshots
            WHERE completed<=:end GROUP BY task_id,ticket
            UNION ALL
            SELECT t.id,t.email_records_id,t.sender,trim(t.ticket),NULL FROM tasks t
            WHERE NOT EXISTS (SELECT 1 FROM snapshots s WHERE s.task_id=t.id AND s.ticket=trim(t.ticket)
                AND s.completed<=:end)),
        order_state AS (
            SELECT grouped.*,m.sender FROM (SELECT ticket,COUNT(DISTINCT sender) suppliers,
                COUNT(*) tasks,COUNT(completed) done,MAX(completed) completed,MIN(email_id) email_id
                FROM order_members WHERE COALESCE(ticket,'')!='' GROUP BY ticket) grouped
            JOIN m ON m.id=grouped.email_id),
        line_items AS (
            SELECT s.*,trim(CAST(json_extract(CASE WHEN c.type='object' THEN c.value ELSE '{{}}' END,'$.电路代号') AS TEXT)) line_id FROM snapshots s,
                json_each(s.payload,'$.circuits') c WHERE s.line_type='customer'
            UNION ALL
            SELECT s.*,CASE WHEN n.type IN ('text','integer') THEN trim(CAST(n.value AS TEXT)) END line_id FROM snapshots s,
                json_each(s.payload,'$.backbone_circuits') c,
                json_each(CASE WHEN c.type='object' THEN
                    CASE WHEN json_type(c.value,'$.割接对象.系统名称')='array' AND json_array_length(c.value,'$.割接对象.系统名称')>0
                        THEN json_extract(c.value,'$.割接对象.系统名称') ELSE json_array(json_extract(c.value,'$.割接对象.系统名称')) END
                    ELSE '[null]' END) n WHERE s.line_type='backbone'),
        lines AS (
            SELECT grouped.*,m.sender FROM (SELECT ticket,line_id,MIN(completed) completed,MIN(email_id) email_id,
                COUNT(DISTINCT sender) suppliers FROM line_items
                WHERE ticket!='' AND COALESCE(line_id,'')!='' GROUP BY ticket,line_id) grouped
            JOIN m ON m.id=grouped.email_id),
        replies AS (SELECT r.*,m.sender FROM operations_replies r JOIN m ON m.id=r.email_records_id),
        suppliers AS (
            SELECT lower(trim(c.email)) sender,c.name,1 configured,a.first_enabled_at,a.legacy
            FROM (SELECT MIN(name) name,lower(trim(email)) email FROM supplier_configs GROUP BY lower(trim(email))) c
            LEFT JOIN operations_activations a ON a.sender=lower(trim(c.email))
            WHERE {"1=1" if self.principal.is_admin and o.mailboxes is None and o.supplier is None else 'EXISTS(SELECT 1 FROM m WHERE m.sender=lower(trim(c.email)))'}
            UNION ALL SELECT DISTINCT m.sender,CASE WHEN m.sender='' THEN '无法识别发件方' ELSE m.sender END,0,NULL,0
            FROM m WHERE NOT EXISTS(SELECT 1 FROM supplier_configs c WHERE lower(trim(c.email))=m.sender)),
        received_agg AS (SELECT sender,COUNT(*) received,SUM(CASE WHEN mail_type='割接通知' THEN 1 ELSE 0 END) cutover
            FROM m WHERE received BETWEEN :start AND :end GROUP BY sender),
        reported_agg AS (SELECT sender,COUNT(*) reported FROM email_state WHERE done=tasks AND completed BETWEEN :start AND :end GROUP BY sender),
        orders_agg AS (SELECT sender,COUNT(*) orders FROM order_state WHERE done=tasks AND completed BETWEEN :start AND :end GROUP BY sender),
        lines_agg AS (SELECT sender,COUNT(*) lines FROM lines WHERE completed BETWEEN :start AND :end GROUP BY sender),
        replies_agg AS (SELECT sender,COUNT(*) replies FROM replies WHERE ops_day(sent_at) BETWEEN :start AND :end GROUP BY sender),
        pending_agg AS (SELECT t.sender,COUNT(*) pending,SUM(CASE WHEN t.status='report_failed' THEN 1 ELSE 0 END) failed
            FROM tasks t WHERE NOT EXISTS (SELECT 1 FROM reports_raw r WHERE r.task_id=t.id AND r.status='success'
                AND ({"1=1" if o.environment=='all' else "r.environment IS NULL OR r.environment='"+o.environment+"'"})) GROUP BY t.sender),
        evidence_agg AS (SELECT t.sender,COUNT(*) evidence FROM reports_raw r JOIN tasks t ON t.id=r.task_id
            WHERE r.status='success' AND (r.completed IS NULL OR r.completed BETWEEN :start AND :end)
            AND (r.completed IS NULL OR NOT r.has_snapshot OR r.environment IS NULL)
            AND ({"1=1" if o.environment=='all' else "r.environment IS NULL OR r.environment='"+o.environment+"'"}) GROUP BY t.sender),
        rows AS (SELECT s.*,COALESCE(r.received,0) received,COALESCE(r.cutover,0) cutover,
            COALESCE(p.reported,0) reported,COALESCE(o.orders,0) orders,COALESCE(l.lines,0) lines,
            COALESCE(a.replies,0) replies,COALESCE(q.pending,0) pending,COALESCE(q.failed,0) failed,
            COALESCE(e.evidence,0) missing_evidence
            FROM suppliers s LEFT JOIN received_agg r USING(sender) LEFT JOIN reported_agg p USING(sender)
            LEFT JOIN orders_agg o USING(sender) LEFT JOIN lines_agg l USING(sender)
            LEFT JOIN replies_agg a USING(sender) LEFT JOIN pending_agg q USING(sender)
            LEFT JOIN evidence_agg e USING(sender))
        '''
        # SQLite supports positional parameters and named placeholders; use one positional sequence in lexical order.
        sql = sql.replace(':start', "'"+o.start+"'").replace(':end', "'"+o.end+"'")
        return sql, params

    def query(self, tail, params=(), *, filter_supplier=True):
        with self.db.get_connection() as conn:
            sql, bound = self._base(conn, filter_supplier=filter_supplier)
            return [dict(r) for r in conn.execute(sql + tail, [*bound, *params])]

    def summary(self):
        o = self.options
        rows = self.query('SELECT * FROM rows')
        totals = {key: sum(r[key] for r in rows) for key in ('received','cutover','reported','orders','lines','replies','pending','failed')}
        known = [r for r in rows if r['configured'] and r['cutover']]
        unmapped = [r for r in rows if not r['configured'] and r['cutover']]
        end = date.fromisoformat(o.end)
        past = end < datetime.now(TZ).date()
        covered = [r for r in known if r['first_enabled_at'] and local_day(r['first_enabled_at'])<=o.end or not past and r['legacy']]
        coverage = None if unmapped or len(covered)!=len(known) or not known else round(100*len(covered)/(len(known)+len(unmapped)),1)
        partial = self.query('''SELECT
            (SELECT COUNT(*) FROM email_state WHERE done>0 AND done<tasks AND completed BETWEEN ? AND ?) partial_emails,
            (SELECT COUNT(*) FROM order_state WHERE done>0 AND done<tasks AND completed BETWEEN ? AND ?) partial_orders,
            (SELECT COUNT(*) FROM order_state WHERE suppliers>1) conflicting_tickets,
            (SELECT COUNT(*) FROM reports_raw WHERE status='success' AND (completed IS NULL OR completed BETWEEN ? AND ?)
                AND (?='all' OR environment=? OR environment IS NULL)
                AND (completed IS NULL OR NOT has_snapshot OR environment IS NULL)) missing_report_evidence,
            (SELECT COUNT(*) FROM snapshots WHERE completed BETWEEN ? AND ? AND
                (ticket='' OR line_type NOT IN ('customer','backbone') OR line_type IS NULL OR
                NOT EXISTS(SELECT 1 FROM line_items li WHERE li.report_id=snapshots.report_id))) missing_line_payloads,
            (SELECT COUNT(*) FROM line_items WHERE completed BETWEEN ? AND ? AND (ticket='' OR COALESCE(line_id,'')='')) missing_line_ids,
            (SELECT COUNT(*) FROM snapshots WHERE completed BETWEEN ? AND ? AND ticket='') missing_ticket_ids,
            (SELECT COUNT(*) FROM replies WHERE legacy=1) legacy_replies''',
            [o.start,o.end,o.start,o.end,o.start,o.end,o.environment,o.environment,o.start,o.end,o.start,o.end,o.start,o.end])[0]
        metrics = {'received_emails':totals['received'],'cutover_emails':totals['cutover'],
                   'reported_emails':totals['reported'],
                   'reported_orders':totals['orders'],
                   'fully_reported_emails':totals['reported'],'fully_reported_orders':totals['orders'],
                   'reported_lines':totals['lines'],
                   'confirmed_lines':totals['lines'],'reply_emails':totals['replies'],
                   'connected_suppliers':sum(r['configured'] for r in rows),
                   'new_suppliers':sum(bool(r['first_enabled_at'] and o.start<=local_day(r['first_enabled_at'])<=o.end) for r in rows),
                   'unknown_activation_dates':sum(bool(r['configured'] and not r['first_enabled_at']) for r in rows),
                   'incoming_suppliers':len(known),'unmapped_senders':len(unmapped),'coverage_percent':coverage,
                   'pending_tasks':totals['pending'],'failed_tasks':totals['failed'],**partial}
        trend_start=end-timedelta(days=end.weekday()+49)
        trend = self.query('''SELECT completed day,COUNT(*) count FROM email_state
            WHERE tasks=done AND completed BETWEEN ? AND ? GROUP BY completed''',[trend_start.isoformat(),o.end])
        trend_mail = self.query('SELECT received day,COUNT(*) count FROM m WHERE received BETWEEN ? AND ? GROUP BY received',[trend_start.isoformat(),o.end])
        weeks=[]
        for i in range(8):
            start=trend_start+timedelta(weeks=i); finish=start+timedelta(days=6)
            weeks.append({'start':start.isoformat(),'reported':sum(r['count'] for r in trend if start.isoformat()<=r['day']<=finish.isoformat()),
                          'received':sum(r['count'] for r in trend_mail if start.isoformat()<=r['day']<=finish.isoformat())})
        return {'metrics':metrics,'trend':weeks,'focus':{
            'volume':sorted([r for r in rows if r['received']],key=lambda r:(-r['received'],r['sender']))[:10],
            'onboarding':sorted(unmapped,key=lambda r:(-r['cutover'],r['sender']))[:10],
            'pending':sorted([r for r in rows if r['pending']],key=lambda r:(-r['failed'],-r['pending'],r['sender']))[:10]},
            'scope':{'start':o.start,'end':o.end,'environment':o.environment,'mailbox_count':len(self.selected)}}

    def suppliers(self, export=False):
        o=self.options; conditions=[]; params=[]
        if o.search:
            conditions.append('(name LIKE ? ESCAPE \'\\\' OR sender LIKE ? ESCAPE \'\\\')')
            term='%'+o.search.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'; params += [term,term]
        filters={'active':'(received>0 OR reported>0 OR orders>0 OR lines>0 OR replies>0 OR missing_evidence>0)', 'unconfigured':'configured=0', 'configured':'configured=1','pending':'pending>0','all':'1=1'}
        conditions.append(filters[o.status]); where=' WHERE '+' AND '.join(conditions)
        order={'received':'received DESC','reported':'reported DESC','pending':'pending DESC','name':'name COLLATE NOCASE'}[o.sort]+',sender'
        total=self.query('SELECT COUNT(*) total FROM rows'+where,params)[0]['total']
        tail='SELECT * FROM rows'+where+' ORDER BY '+order
        if not export: tail+=' LIMIT ? OFFSET ?'; params += [o.page_size,(o.page-1)*o.page_size]
        return {'items':self.query(tail,params),'total':total,'page':o.page,'page_size':o.page_size}

    def details(self):
        o=self.options; params=[o.start,o.end]
        selects={
            'orders':"SELECT ticket,sender,email_id,tasks,done,completed FROM order_state WHERE done=tasks AND completed BETWEEN ? AND ?",
            'lines':"SELECT ticket,line_id,sender,email_id,completed FROM lines WHERE completed BETWEEN ? AND ?",
            'emails':"SELECT m.id email_id,m.subject,m.sender,m.receiver,e.completed FROM email_state e JOIN m ON m.id=e.id WHERE done=tasks AND completed BETWEEN ? AND ?",
            'replies':"SELECT email_records_id email_id,sender,ops_time(sent_at) completed FROM replies WHERE ops_day(sent_at) BETWEEN ? AND ?"}
        sql=selects[o.kind]
        if o.ticket and o.kind in ('orders','lines'):
            sql+=' AND ticket=?';params.append(o.ticket)
        if o.supplier is not None:
            sql='SELECT * FROM ('+sql+') WHERE sender=?'
            params.append(o.supplier.lower())
        total=self.query('SELECT COUNT(*) total FROM ('+sql+')',params,filter_supplier=False)[0]['total']
        items=self.query(sql+' ORDER BY completed DESC,email_id LIMIT ? OFFSET ?',[*params,o.page_size,(o.page-1)*o.page_size],filter_supplier=False)
        return {'items':items,'total':total,'page':o.page,'page_size':o.page_size}
