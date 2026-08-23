"""
割接上报任务业务逻辑。

一封邮件按线路类型拆分割接任务（每个任务只负责一种线路的上报）：
- 客户线路：生成 Excel 表格，后续上传综调系统
- 骨干线路：生成填报表单字段，后续在综调系统填报

任务支持在管理台查看与编辑，人工确认后触发上报（见 cutover_report.py）。
"""
from datetime import datetime

from loguru import logger

from database import email_db

# 任务状态机：draft -> confirmed -> reporting -> reported / report_failed
# 编辑任务数据后回退为 draft，需要重新人工确认。
CUTOVER_TASK_STATUS_DRAFT = 'draft'
CUTOVER_TASK_STATUS_CONFIRMED = 'confirmed'
CUTOVER_TASK_STATUS_REPORTING = 'reporting'
CUTOVER_TASK_STATUS_REPORTED = 'reported'
CUTOVER_TASK_STATUS_REPORT_FAILED = 'report_failed'

CUTOVER_TASK_STATUS_LABELS = {
    CUTOVER_TASK_STATUS_DRAFT: '待确认',
    CUTOVER_TASK_STATUS_CONFIRMED: '已确认',
    CUTOVER_TASK_STATUS_REPORTING: '上报中',
    CUTOVER_TASK_STATUS_REPORTED: '已上报',
    CUTOVER_TASK_STATUS_REPORT_FAILED: '上报失败',
}

# 任务线路类型：每个任务只做一种线路的上报
CUTOVER_LINE_TYPE_CUSTOMER = 'customer'
CUTOVER_LINE_TYPE_BACKBONE = 'backbone'

CUTOVER_LINE_TYPE_LABELS = {
    CUTOVER_LINE_TYPE_CUSTOMER: '客户线路',
    CUTOVER_LINE_TYPE_BACKBONE: '骨干线路',
}

# 割接场景：FastGPT 判定后回写邮件记录。
# emergency/major_event/in_window 为已回复拒绝割接（回复经人工确认发送后写入），
# 其中紧急割接仍会调用 /api/cutover/tasks/generate 生成上报任务；
# rule_skipped 为命中供应商特殊规则（由 /api/cutover/scene 写入），不生成任务。
CUTOVER_SCENE_NORMAL = 'normal'
CUTOVER_SCENE_EMERGENCY = 'emergency'
CUTOVER_SCENE_MAJOR_EVENT = 'major_event'
CUTOVER_SCENE_IN_WINDOW = 'in_window'
CUTOVER_SCENE_RULE_SKIPPED = 'rule_skipped'

CUTOVER_SCENE_LABELS = {
    CUTOVER_SCENE_NORMAL: '正常割接',
    CUTOVER_SCENE_EMERGENCY: '紧急割接',
    CUTOVER_SCENE_MAJOR_EVENT: '重保期割接',
    CUTOVER_SCENE_IN_WINDOW: '已在割接窗口内',
    CUTOVER_SCENE_RULE_SKIPPED: '命中特殊规则',
}

# /api/cutover/reply 可携带的场景（不含 rule_skipped，该场景由 /api/cutover/scene 写入）
VALID_CUTOVER_SCENES = {
    CUTOVER_SCENE_NORMAL,
    CUTOVER_SCENE_EMERGENCY,
    CUTOVER_SCENE_MAJOR_EVENT,
    CUTOVER_SCENE_IN_WINDOW,
}

# /api/cutover/scene 可写入的全部场景
WRITABLE_CUTOVER_SCENES = set(CUTOVER_SCENE_LABELS)

# 回复生命周期：/api/cutover/reply 只登记草稿（待人工确认），
# /api/cutover/reply/confirm 人工确认后发送，/api/cutover/reply/cancel 放弃草稿。
REPLY_STATUS_PENDING = 'pending'
REPLY_STATUS_SENT = 'sent'
REPLY_STATUS_CANCELLED = 'cancelled'

# 邮件标签：场景标签 + 重复邮件，用于列表展示与按标签过滤；normal 场景不算标签。
CUTOVER_TAG_DUPLICATE = 'duplicate'

CUTOVER_TAG_LABELS = {
    CUTOVER_SCENE_EMERGENCY: '紧急割接',
    CUTOVER_SCENE_MAJOR_EVENT: '重保期割接',
    CUTOVER_SCENE_IN_WINDOW: '已在割接窗口内',
    CUTOVER_SCENE_RULE_SKIPPED: '命中特殊规则',
    CUTOVER_TAG_DUPLICATE: '重复邮件',
}

VALID_CUTOVER_TAGS = set(CUTOVER_TAG_LABELS)

# 各类型任务在管理台可编辑的 fill_result 字段
EDITABLE_RESULT_FIELDS_BY_TYPE = {
    CUTOVER_LINE_TYPE_CUSTOMER: ('circuits', 'reasons'),
    CUTOVER_LINE_TYPE_BACKBONE: ('backbone_circuits',),
}


def cutover_task_status_label(status):
    return CUTOVER_TASK_STATUS_LABELS.get(status, status or '未设置')


def cutover_line_type_label(line_type):
    return CUTOVER_LINE_TYPE_LABELS.get(line_type, line_type or '未设置')


def cutover_scene_label(scene):
    return CUTOVER_SCENE_LABELS.get(scene, scene or '未设置')


def save_cutover_fill_tasks(email_records_id, payload, result, customer_excel_filename=None):
    """根据 /api/cutover/tasks/generate 的入参与生成结果，按线路类型创建或覆盖割接任务。

    fill 结果即该邮件任务的唯一来源：存在的类型覆盖更新（状态重置为 draft），
    本次结果中不再包含的类型对应的旧任务会被删除。
    返回保存后的任务列表。
    """
    result = result or {}
    title = result.get('title')
    shared_fields = {
        'validation_messages': result.get('validation_messages') or [],
        'cutStartTime': result.get('cutStartTime'),
        'cutEndTime': result.get('cutEndTime'),
    }

    task_specs = []
    if result.get('circuits'):
        task_specs.append({
            'line_type': CUTOVER_LINE_TYPE_CUSTOMER,
            'fill_result': {
                'title': title,
                'filename': result.get('filename'),
                'circuits': result.get('circuits') or [],
                'reasons': result.get('reasons') or [],
                'matched_circuits': result.get('matched_circuits') or [],
                **shared_fields,
            },
            'customer_excel_filename': customer_excel_filename,
        })
    if result.get('backbone_circuits'):
        task_specs.append({
            'line_type': CUTOVER_LINE_TYPE_BACKBONE,
            'fill_result': {
                'title': title,
                'backbone_circuits': result.get('backbone_circuits') or [],
                **shared_fields,
            },
            'customer_excel_filename': None,
        })

    if not task_specs:
        raise ValueError('割接填报结果不包含客户或骨干线路，无法生成割接任务')

    # 删除本次 fill 结果中不再包含的类型对应的旧任务
    existing_tasks = email_db.list_cutover_tasks_by_email(email_records_id)
    keep_types = {spec['line_type'] for spec in task_specs}
    for existing in existing_tasks:
        if existing.get('line_type') not in keep_types:
            email_db.delete_cutover_task(existing.get('id'))
            logger.info(
                f"割接任务已删除（本次填报不再包含该线路类型）: id={existing.get('id')}, "
                f"email_records_id={email_records_id}, line_type={existing.get('line_type')}"
            )

    tasks = []
    for spec in task_specs:
        task_id = email_db.upsert_cutover_task(
            email_records_id=email_records_id,
            line_type=spec['line_type'],
            supplier=(payload or {}).get('supplier'),
            carrier_ticket_no=(payload or {}).get('carrier_ticket_no'),
            title=title,
            fill_payload=payload,
            fill_result=spec['fill_result'],
            customer_excel_filename=spec['customer_excel_filename'],
        )
        if not task_id:
            raise ValueError(
                f'保存割接任务失败：email_records_id={email_records_id}, line_type={spec["line_type"]}'
            )
        tasks.append(email_db.get_cutover_task(task_id))

    logger.info(
        f"割接任务已保存: email_records_id={email_records_id}, "
        f"ids={[task.get('id') for task in tasks]}"
    )
    return tasks


def get_cutover_task_detail(task_id):
    """获取任务详情，附带关联邮件摘要与历史上报记录。"""
    task = email_db.get_cutover_task(task_id)
    if not task:
        return None

    email_record = email_db.get_email_record_by_id(task.get('email_records_id'))
    task['email'] = None
    if email_record:
        task['email'] = {
            'id': email_record.get('id'),
            'email_id': email_record.get('email_id'),
            'sender': email_record.get('sender'),
            'subject': email_record.get('subject'),
            'create_time': str(email_record.get('create_time') or ''),
        }
    task['reports'] = email_db.get_cutover_reports(task_id)
    task['status_label'] = cutover_task_status_label(task.get('status'))
    task['line_type_label'] = cutover_line_type_label(task.get('line_type'))
    scene = (email_record or {}).get('cutover_scene') or CUTOVER_SCENE_NORMAL
    task['cutover_scene'] = scene
    task['cutover_scene_label'] = cutover_scene_label(scene)
    return task


def apply_task_edit(task_id, edits):
    """编辑任务中可修改的填报数据。

    每个任务只做一种线路的上报：客户线路任务仅允许修改 circuits / reasons，
    骨干线路任务仅允许修改 backbone_circuits。客户侧数据变更后自动重新生成
    Excel（覆盖同名文件）。编辑后状态回退为 draft。
    """
    task = email_db.get_cutover_task(task_id)
    if not task:
        raise LookupError(f'割接任务不存在：id={task_id}')
    if task.get('status') == CUTOVER_TASK_STATUS_REPORTING:
        raise ValueError('任务正在上报中，暂时无法编辑')

    allowed_fields = EDITABLE_RESULT_FIELDS_BY_TYPE.get(task.get('line_type'), ())
    for field in edits:
        if field not in allowed_fields:
            raise ValueError(
                f"{cutover_line_type_label(task.get('line_type'))}任务不支持编辑字段：{field}"
            )

    fill_result = dict(task.get('fill_result') or {})
    changed = False

    for field in allowed_fields:
        if field not in edits:
            continue
        value = edits[field]
        if not isinstance(value, list):
            raise ValueError(f'{field} 必须是数组')
        if fill_result.get(field) != value:
            fill_result[field] = value
            changed = True

    if not changed:
        return task

    excel_filename = task.get('customer_excel_filename')
    customer_changed = task.get('line_type') == CUTOVER_LINE_TYPE_CUSTOMER
    if customer_changed and fill_result.get('circuits'):
        # 延迟导入，避免与 api_server 形成循环依赖
        from api_server import build_template_workbook, save_workbook_output

        filename = excel_filename or fill_result.get('filename')
        output = build_template_workbook({
            'circuits': fill_result.get('circuits') or [],
            'reasons': fill_result.get('reasons') or [],
        })
        output_path = save_workbook_output(output, filename)
        excel_filename = output_path.name
        logger.info(f"割接任务 Excel 已重新生成: task_id={task_id}, filename={excel_filename}")

    email_db.update_cutover_task(
        task_id,
        fill_result=fill_result,
        customer_excel_filename=excel_filename,
        status=CUTOVER_TASK_STATUS_DRAFT,
        confirmed_at=None,
    )
    return email_db.get_cutover_task(task_id)


def _convert_fill_result_to_backbone(task):
    """将客户线路填报数据转换为骨干线路填报结构，尽量携带已有数据。"""
    # 延迟导入，避免与 api_server 形成循环依赖
    from api_server import backbone_fixed_sections

    fill_result = task.get('fill_result') or {}
    payload = task.get('fill_payload') or {}
    title = fill_result.get('title') or task.get('title')
    cutover_reason = payload.get('cutover_reason') or ''
    location = payload.get('location') or ''
    cut_start = fill_result.get('cutStartTime')
    cut_end = fill_result.get('cutEndTime')

    backbone_circuits = []
    for row in (fill_result.get('circuits') or [{}]):
        backbone_circuits.append({
            '基本信息': {
                '标题': title,
                '割接分类': '线路割接',
                '割接原因分类': '其它运营商割接',
                '涉及系统（网络）': '',
                '操作厂家': '',
                '设备名称': '',
                '割接省份': '国际',
                '变更操作内容': '其他单段光缆割接',
                '变更操作等级': '四级',
                '调度方式': '',
                '中断类型': None,
                '需要配合的省': '',
                '中断原因': f'Location:{location}. Reason: {cutover_reason}',
                '是否涉及集团维护设备或业务影响超出本省范围': '否',
                '是否有回退应急预案和舆情应对方案': '不涉及',
                '割接地点': location,
                '是否跨专业': '否'
            },
            '割接对象': {
                '割接类型': '正常割接',
                '割接对象所属机构': '国际',
                '割接对象类型': '高阶通道',
                '系统名称': (row or {}).get('电路代号'),
                '割接开始时间': cut_start,
                '割接结束时间': cut_end,
                '割接名称': ''
            },
            **backbone_fixed_sections(title, cutover_reason, location),
        })

    return {
        'title': title,
        'backbone_circuits': backbone_circuits,
        'validation_messages': fill_result.get('validation_messages') or [],
        'cutStartTime': cut_start,
        'cutEndTime': cut_end,
    }


def _convert_fill_result_to_customer(task):
    """将骨干线路填报数据转换为客户线路电路表/割接原因表，尽量携带已有数据。"""
    # 延迟导入，避免与 api_server 形成循环依赖
    from api_server import build_customer_circuit, build_customer_reason

    fill_result = task.get('fill_result') or {}
    payload = task.get('fill_payload') or {}
    title = fill_result.get('title') or task.get('title')
    cutover_time = payload.get('cutover_time') or ''
    cutover_timezone = payload.get('cutover_timezone') or 'UTC'
    cutover_reason = payload.get('cutover_reason') or ''
    location = payload.get('location') or ''
    payload_lines = (payload.get('line_array_info') or {}).get('data') or []
    first_line = payload_lines[0] if payload_lines else {}

    circuits = []
    for circuit in (fill_result.get('backbone_circuits') or [{}]):
        circuit = circuit or {}
        base_info = circuit.get('基本信息') or {}
        cutover_object = circuit.get('割接对象') or {}
        circuits.append(build_customer_circuit(
            first_line,
            {'circuit_id': cutover_object.get('系统名称')},
            base_info.get('标题') or title,
            cutover_time,
            cutover_timezone,
        ))

    reasons = []
    if circuits:
        reasons.append(build_customer_reason(title, cutover_time, cutover_timezone, cutover_reason, location))

    return {
        'title': title,
        'circuits': circuits,
        'reasons': reasons,
        'matched_circuits': [],
        'validation_messages': fill_result.get('validation_messages') or [],
        'cutStartTime': fill_result.get('cutStartTime'),
        'cutEndTime': fill_result.get('cutEndTime'),
    }


def switch_task_line_type(task_id, target_type):
    """切换任务的线路类型，已有填报数据会转换带入新类型的填报。

    切换后状态回退为 draft；同一封邮件已存在目标类型的任务时拒绝切换。
    切换为客户线路时自动重新生成 Excel。
    """
    if target_type not in CUTOVER_LINE_TYPE_LABELS:
        raise ValueError(f'不支持的线路类型：{target_type}')

    task = email_db.get_cutover_task(task_id)
    if not task:
        raise LookupError(f'割接任务不存在：id={task_id}')
    if task.get('status') == CUTOVER_TASK_STATUS_REPORTING:
        raise ValueError('任务正在上报中，暂时无法切换类型')
    if task.get('line_type') == target_type:
        return task

    for existing in email_db.list_cutover_tasks_by_email(task.get('email_records_id')):
        if existing.get('id') != task_id and existing.get('line_type') == target_type:
            raise ValueError(
                f'该邮件已存在{cutover_line_type_label(target_type)}任务（id={existing.get("id")}），无法切换'
            )

    if target_type == CUTOVER_LINE_TYPE_BACKBONE:
        new_result = _convert_fill_result_to_backbone(task)
        excel_filename = None
    else:
        from api_server import build_cutover_filename, build_template_workbook, save_workbook_output

        new_result = _convert_fill_result_to_customer(task)
        excel_filename = None
        if new_result.get('circuits'):
            filename = (
                task.get('customer_excel_filename')
                or build_cutover_filename(task.get('supplier'), task.get('carrier_ticket_no'))
            )
            output = build_template_workbook({
                'circuits': new_result.get('circuits') or [],
                'reasons': new_result.get('reasons') or [],
            })
            output_path = save_workbook_output(output, filename)
            excel_filename = output_path.name
            new_result['filename'] = excel_filename
            logger.info(f"割接任务切换为客户线路，Excel 已生成: task_id={task_id}, filename={excel_filename}")

    email_db.update_cutover_task(
        task_id,
        line_type=target_type,
        fill_result=new_result,
        customer_excel_filename=excel_filename,
        status=CUTOVER_TASK_STATUS_DRAFT,
        confirmed_at=None,
    )
    logger.info(
        f"割接任务类型已切换: id={task_id}, {task.get('line_type')} -> {target_type}"
    )
    return email_db.get_cutover_task(task_id)


def confirm_task(task_id):
    """人工确认任务：draft -> confirmed。"""
    task = email_db.get_cutover_task(task_id)
    if not task:
        raise LookupError(f'割接任务不存在：id={task_id}')
    if task.get('status') != CUTOVER_TASK_STATUS_DRAFT:
        raise ValueError(
            f"仅待确认状态的任务可以确认，当前状态：{cutover_task_status_label(task.get('status'))}"
        )

    email_db.update_cutover_task(
        task_id,
        status=CUTOVER_TASK_STATUS_CONFIRMED,
        confirmed_at=datetime.now(),
    )
    return email_db.get_cutover_task(task_id)
