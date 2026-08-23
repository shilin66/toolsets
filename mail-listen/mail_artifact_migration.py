from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false

import sqlite3
from contextlib import closing
from pathlib import Path

from mail_artifact_migration_parts import (
    ArtifactMigrationError,
    DatabaseUpdate,
    FileMigration,
    MigrationPlan,
    MigrationResult,
    apply_migration as _apply_migration,
)
from mail_artifact_migration_parts.mail_artifact_migration_email import (
    plan_attachments,
    plan_customer_excels,
    plan_source_emails,
)
from mail_artifact_migration_parts.mail_artifact_migration_reports import (
    plan_reports,
)
from mail_artifact_migration_parts.mail_artifact_migration_support import (
    MigrationPlanningState,
)


def build_migration_plan(project_dir: Path) -> MigrationPlan:
    resolved_project = project_dir.resolve()
    data_dir = resolved_project / "data"
    database_path = data_dir / "mail_listener.db"
    if not database_path.is_file():
        raise ArtifactMigrationError(f"数据库不存在：{database_path}")
    with closing(
        sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    ) as connection:
        connection.row_factory = sqlite3.Row
        state = MigrationPlanningState(
            resolved_project,
            data_dir,
            connection,
        )
        plan_attachments(state)
        plan_customer_excels(state)
        plan_reports(state)
        plan_source_emails(state)
    return MigrationPlan(
        resolved_project,
        data_dir,
        database_path,
        tuple(sorted(
            state.files,
            key=lambda item: (str(item.target), str(item.source)),
        )),
        tuple(sorted(
            state.updates,
            key=lambda item: (item.table, item.row_id, item.column),
        )),
    )


def apply_migration(
    plan: MigrationPlan,
    *,
    backup_label: str | None = None,
) -> MigrationResult:
    return _apply_migration(plan, backup_label=backup_label)


__all__ = [
    "ArtifactMigrationError",
    "DatabaseUpdate",
    "FileMigration",
    "MigrationPlan",
    "MigrationResult",
    "apply_migration",
    "build_migration_plan",
]
