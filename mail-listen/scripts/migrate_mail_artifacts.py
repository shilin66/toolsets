from __future__ import annotations

# pyright: reportImplicitRelativeImport=false

import argparse
import sys
from collections import Counter
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from mail_artifact_migration import apply_migration, build_migration_plan


def main() -> int:
    parser = argparse.ArgumentParser(description="迁移邮件与割接业务文件到标准目录")
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=PROJECT_DIR,
        help="mail-listen 项目目录",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="执行迁移；未指定时仅预演",
    )
    parser.add_argument(
        "--backup-label",
        help="data/migration-backups 下的备份目录名",
    )
    arguments = parser.parse_args()
    plan = build_migration_plan(arguments.project_dir)
    counts = Counter(item.kind for item in plan.files)
    print(f"待迁移源文件：{len(plan.files)}")
    print(f"待更新数据库记录：{len(plan.updates)}")
    for kind, count in sorted(counts.items()):
        print(f"  {kind}: {count}")
    if not arguments.apply:
        for item in plan.files:
            source = item.source.relative_to(plan.data_dir)
            target = item.target.relative_to(plan.data_dir)
            print(f"  {source} -> {target}")
        print("预演完成，未修改文件和数据库。")
        return 0
    if not plan.files and not plan.updates:
        print("当前数据已经符合标准目录，无需迁移。")
        return 0
    result = apply_migration(plan, backup_label=arguments.backup_label)
    print(f"迁移完成：{result.migrated_files} 个目标文件")
    print(f"数据库更新：{result.updated_rows} 条记录")
    print(f"备份目录：{result.backup_dir}")
    print(f"迁移清单：{result.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
