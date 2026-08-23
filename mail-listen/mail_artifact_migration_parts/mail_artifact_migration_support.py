from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .mail_artifact_migration_models import (
    ArtifactMigrationError,
    DatabaseUpdate,
    EmailRecord,
    FileMigration,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_mail_store_reference(value: str) -> bool:
    return PurePosixPath(value).parts[:2] == ("mail_store", "mailboxes")


@dataclass(slots=True)
class MigrationPlanningState:
    project_dir: Path
    data_dir: Path
    connection: sqlite3.Connection
    files: list[FileMigration] = field(default_factory=list)
    updates: list[DatabaseUpdate] = field(default_factory=list)
    records: dict[int, EmailRecord] = field(default_factory=dict)

    def relative_path(self, path: Path) -> str:
        resolved_data = self.data_dir.resolve()
        resolved_path = path.resolve()
        if not resolved_path.is_relative_to(resolved_data):
            raise ArtifactMigrationError(f"文件不在 data 目录内：{path}")
        return resolved_path.relative_to(resolved_data).as_posix()

    def add_file(self, kind: str, source: Path, target: Path) -> None:
        self.relative_path(source)
        self.relative_path(target)
        resolved_source = source.resolve()
        resolved_target = target.resolve()
        if resolved_source == resolved_target:
            if not target.is_file():
                raise ArtifactMigrationError(f"标准路径中的文件不存在：{target}")
            return
        if not source.is_file():
            if target.is_file():
                return
            raise ArtifactMigrationError(f"待迁移文件不存在：{source}")
        source_hash = sha256_file(source)
        if target.exists() and (
            not target.is_file() or sha256_file(target) != source_hash
        ):
            raise ArtifactMigrationError(f"目标文件已存在且内容不同：{target}")
        for item in self.files:
            if item.source == resolved_source and item.target == resolved_target:
                return
            if item.target == resolved_target and item.sha256 != source_hash:
                raise ArtifactMigrationError(f"多个源文件会覆盖同一目标：{target}")
        self.files.append(
            FileMigration(kind, resolved_source, resolved_target, source_hash)
        )
