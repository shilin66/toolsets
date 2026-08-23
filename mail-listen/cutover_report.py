"""
割接任务上报模块（Playwright 对接综调系统）。

当前为占位实现。后续对接综调系统时，只需在本模块实现 report_cutover_task：
- 客户线路：将任务生成的 customer_excel_filename Excel 上传到综调系统
- 骨干线路：根据 fill_result.backbone_circuits 的字段在综调系统填报表单中填写

API 层与前端不需要改动。
"""
from loguru import logger


class CutoverReportNotReady(Exception):
    """上报通道尚未对接时抛出。"""


def report_cutover_task(task: dict) -> dict:
    """触发单个割接任务上报到综调系统。

    Args:
        task: 割接任务字典，包含 fill_result、customer_excel_filename 等。

    Returns:
        结果字典，例如 {'status': 'success', 'zongdiao_ticket_no': '...'}。

    Raises:
        CutoverReportNotReady: Playwright 对接综调系统完成前抛出。
    """
    logger.info(f"割接任务触发上报: id={task.get('id')}（综调系统尚未对接）")
    raise CutoverReportNotReady('Playwright 上报综调系统尚未对接，任务已进入待上报队列')
