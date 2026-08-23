from collections.abc import Mapping


BACKBONE_NOC_PHONE_KEY = "backbone_noc_phone"
BACKBONE_PROVINCE_REVIEWER_NAME_KEY = "backbone_province_reviewer_name"
BACKBONE_PROVINCE_REVIEWER_PHONE_KEY = "backbone_province_reviewer_phone"

BACKBONE_PERSONNEL_DEFAULTS = {
    BACKBONE_NOC_PHONE_KEY: "+85231000000",
    BACKBONE_PROVINCE_REVIEWER_NAME_KEY: "Andrew",
    BACKBONE_PROVINCE_REVIEWER_PHONE_KEY: "+85291089855",
}
BACKBONE_PERSONNEL_SETTING_KEYS = tuple(BACKBONE_PERSONNEL_DEFAULTS)


def resolve_backbone_personnel_settings(
    stored: Mapping[str, str | None],
) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for key, default in BACKBONE_PERSONNEL_DEFAULTS.items():
        value = stored.get(key)
        normalized = value.strip() if isinstance(value, str) else ""
        resolved[key] = normalized or default
    return resolved


def build_backbone_personnel_fields(
    supplier_name: str | None,
    sender_email: str | None,
    settings: Mapping[str, str],
) -> dict[str, str]:
    supplier = (supplier_name or "").strip()
    sender = (sender_email or "").strip()
    noc_phone = settings[BACKBONE_NOC_PHONE_KEY]
    reviewer_name = settings[BACKBONE_PROVINCE_REVIEWER_NAME_KEY]
    reviewer_phone = settings[BACKBONE_PROVINCE_REVIEWER_PHONE_KEY]
    operation_reviewer = f"{supplier} NOC".strip()

    return {
        "现场指挥人员名称": supplier,
        "现场指挥人电话": sender,
        "现场指挥人单位": "国际公司",
        "支撑人员": "NOC",
        "支撑人电话": noc_phone,
        "支撑人单位": "国际公司",
        "省公司审核人姓名": reviewer_name,
        "省公司审核人电话": reviewer_phone,
        "省公司审核人单位": "国际公司",
        "业务测试人员": "NOC",
        "业务测试人员电话": noc_phone,
        "业务测试人单位": "国际公司",
        "操作审核人姓名": operation_reviewer,
        "操作审核人电话": sender,
        "操作审核人单位": "国际公司",
        "业务复核人姓名": "NOC",
        "业务复核人电话": noc_phone,
        "业务复核人单位": "国际公司",
    }
