from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ArtifactMigrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FileMigration:
    kind: str
    source: Path
    target: Path
    sha256: str


@dataclass(frozen=True, slots=True)
class DatabaseUpdate:
    table: str
    row_id: int
    column: str
    value: str
    previous_value: str | None


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    project_dir: Path
    data_dir: Path
    database_path: Path
    files: tuple[FileMigration, ...]
    updates: tuple[DatabaseUpdate, ...]


@dataclass(frozen=True, slots=True)
class MigrationResult:
    backup_dir: Path
    manifest_path: Path
    migrated_files: int
    updated_rows: int


@dataclass(frozen=True, slots=True)
class EmailRecord:
    record_id: int
    email_uid: int
    receiver: str
