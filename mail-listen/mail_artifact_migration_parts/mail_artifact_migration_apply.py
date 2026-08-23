from __future__ import annotations

# pyright: reportImplicitRelativeImport=false

import json
import re
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .mail_artifact_migration_models import (
    ArtifactMigrationError,
    DatabaseUpdate,
    MigrationPlan,
    MigrationResult,
)
from .mail_artifact_migration_support import sha256_file
from mail_artifacts import write_private_bytes


_BACKUP_LABEL_PATTERN = re.compile(r"[A-Za-z0-9._-]+")


def _apply_database_updates(
    connection: sqlite3.Connection,
    updates: tuple[DatabaseUpdate, ...],
) -> None:
    allowed_columns = {
        ("email_records", "attachments"),
        ("cutover_reports", "result"),
    }
    for update in updates:
        if (update.table, update.column) not in allowed_columns:
            raise ArtifactMigrationError(
                f"不允许更新数据库字段：{update.table}.{update.column}"
            )
        current_row = connection.execute(
            f"SELECT {update.column} FROM {update.table} WHERE id = ?",
            (update.row_id,),
        ).fetchone()
        if current_row is None or current_row[0] != update.previous_value:
            raise ArtifactMigrationError(
                f"数据库记录已在预演后发生变化：{update.table}#{update.row_id}"
            )
        connection.execute(
            f"UPDATE {update.table} SET {update.column} = ? WHERE id = ?",
            (update.value, update.row_id),
        )


def _backup_database(plan: MigrationPlan, backup_dir: Path) -> None:
    with closing(sqlite3.connect(plan.database_path)) as source:
        with closing(sqlite3.connect(backup_dir / "mail_listener.db")) as target:
            source.backup(target)
    (backup_dir / "mail_listener.db").chmod(0o600)


def _copy_and_verify_files(plan: MigrationPlan) -> set[Path]:
    migrated_targets: set[Path] = set()
    for item in plan.files:
        if not item.source.is_file():
            raise ArtifactMigrationError(f"待迁移文件已不存在：{item.source}")
        if sha256_file(item.source) != item.sha256:
            raise ArtifactMigrationError(f"待迁移文件已发生变化：{item.source}")
        if item.target.exists():
            if not item.target.is_file() or sha256_file(item.target) != item.sha256:
                raise ArtifactMigrationError(f"目标文件已存在且内容不同：{item.target}")
        else:
            write_private_bytes(plan.data_dir, item.target, item.source.read_bytes())
        if sha256_file(item.target) != item.sha256:
            raise ArtifactMigrationError(f"迁移后文件校验失败：{item.target}")
        migrated_targets.add(item.target)
    return migrated_targets


def _archive_sources(plan: MigrationPlan, backup_dir: Path) -> None:
    archived_sources: set[Path] = set()
    for item in plan.files:
        if item.source in archived_sources:
            continue
        archive_path = backup_dir / "legacy" / item.source.relative_to(plan.data_dir)
        archive_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        archive_path.parent.chmod(0o700)
        source_parent = item.source.parent
        shutil.move(str(item.source), str(archive_path))
        archive_path.chmod(0o600)
        archived_sources.add(item.source)
        while source_parent != plan.data_dir:
            try:
                source_parent.rmdir()
            except OSError:
                break
            source_parent = source_parent.parent


def _write_manifest(plan: MigrationPlan, backup_dir: Path) -> Path:
    manifest = {
        "format_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database_backup": "mail_listener.db",
        "files": [
            {
                "kind": item.kind,
                "source": item.source.relative_to(plan.data_dir).as_posix(),
                "target": item.target.relative_to(plan.data_dir).as_posix(),
                "sha256": item.sha256,
            }
            for item in plan.files
        ],
        "database_updates": [
            {
                "table": update.table,
                "row_id": update.row_id,
                "column": update.column,
            }
            for update in plan.updates
        ],
    }
    manifest_path = backup_dir / "manifest.json"
    write_private_bytes(
        plan.data_dir,
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    return manifest_path


def apply_migration(
    plan: MigrationPlan,
    *,
    backup_label: str | None = None,
) -> MigrationResult:
    normalized_label = backup_label or datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    if _BACKUP_LABEL_PATTERN.fullmatch(normalized_label) is None:
        raise ArtifactMigrationError(
            "备份标签只能包含字母、数字、点、下划线和短横线"
        )
    backup_dir = plan.data_dir / "migration-backups" / normalized_label
    if backup_dir.exists():
        raise ArtifactMigrationError(f"备份目录已存在：{backup_dir}")
    backup_dir.mkdir(parents=True, mode=0o700)
    backup_dir.chmod(0o700)
    _backup_database(plan, backup_dir)
    migrated_targets = _copy_and_verify_files(plan)
    with sqlite3.connect(plan.database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _apply_database_updates(connection, plan.updates)
    _archive_sources(plan, backup_dir)
    manifest_path = _write_manifest(plan, backup_dir)
    return MigrationResult(
        backup_dir,
        manifest_path,
        len(migrated_targets),
        len(plan.updates),
    )
