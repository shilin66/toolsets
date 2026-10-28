"""Read-only operations analytics, with identical scope for every endpoint."""
import csv
import io

from flask import Response, g, jsonify, request

from operations_query import OperationsRepository, Options
from supplier_config import SupplierConfigRepository


def register_operations_routes(app, get_db):
    def handle(kind):
        try:
            db = get_db()
            SupplierConfigRepository(db)
            repository = OperationsRepository(db, getattr(g, 'principal', None), Options.parse(request.args))
            if kind == 'options':
                return jsonify(success=True, data={'mailboxes': repository.boxes})
            if kind == 'export':
                result = repository.suppliers(export=True)
                output = io.StringIO(newline='')
                writer = csv.writer(output)
                writer.writerow(['运营商', '发件地址', '正式配置', '接收邮件', '割接邮件', '上报邮件',
                                 '上报工单', '上报线路', '回复邮件', '待处理任务', '失败任务'])
                for row in result['items']:
                    values = [row[k] for k in ('name','sender','configured','received','cutover','reported','orders','lines','replies','pending','failed')]
                    # Spreadsheet formula prefixes can follow whitespace/control characters.
                    writer.writerow(["'" + v if isinstance(v, str) and (v.lstrip().startswith(('=','+','-','@')) or v.startswith(('\t','\r','\n'))) else v for v in values])
                return Response('\ufeff' + output.getvalue(), mimetype='text/csv', headers={
                    'Content-Disposition': 'attachment; filename="operations.csv"'})
            return jsonify(success=True, data=getattr(repository, kind)())
        except PermissionError as error:
            return jsonify(success=False, message=str(error)), 403
        except ValueError:
            return jsonify(success=False, message='查询参数无效，请检查日期、邮箱与分页条件'), 400

    for kind in ('options', 'summary', 'suppliers', 'details', 'export'):
        app.add_url_rule('/api/operations/' + kind, 'operations_' + kind,
                         lambda kind=kind: handle(kind), methods=['GET'])
