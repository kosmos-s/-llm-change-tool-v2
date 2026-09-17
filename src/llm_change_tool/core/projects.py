"""Local project lifecycle and validated backup/restore."""

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from llm_change_tool import __version__
from llm_change_tool.storage.database import (
    SCHEMA_VERSION,
    DatabaseError,
    backup_database,
    connect,
    migrate,
    validate,
)

DB_NAME = "project.db"


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def local_path(path: Path) -> Path:
    # Windows UNC paths can be identified portably; mapped drives/mounts cannot.
    if str(path).startswith(("\\\\", "//")):
        raise ValueError("프로젝트는 NAS 공유 경로가 아닌 로컬 디스크에 만드세요.")
    return path.expanduser().resolve()


@dataclass(frozen=True)
class Project:
    root: Path
    project_id: str
    name: str
    created_at: str

    @property
    def database(self) -> Path:
        return self.root / DB_NAME


def create_project(path: Path, name: str) -> Project:
    name = name.strip()
    if not name or len(name) > 120:
        raise ValueError("프로젝트 이름은 1~120자로 입력하세요.")
    root = local_path(path)
    # Never adopt, empty or overwrite an existing folder (including source data).
    root.mkdir(parents=False, exist_ok=False)
    try:
        for directory in ("backups", "exports", "logs"):
            (root / directory).mkdir()
        with connect(root / DB_NAME, create=True) as con:
            con.execute("PRAGMA journal_mode = WAL")
            migrate(con, timestamp=now(), new=True)
            with con:
                con.execute(
                    "INSERT INTO project VALUES (1, ?, ?, ?, ?)",
                    (str(uuid4()), name, now(), __version__),
                )
        return open_project(root)
    except Exception:
        shutil.rmtree(root)
        raise


def open_project(path: Path) -> Project:
    root = local_path(path)
    db = root / DB_NAME
    if not db.is_file() or db.is_symlink():
        raise DatabaseError("선택한 폴더에 정상적인 project.db 파일이 없습니다.")
    # Check identity, version and integrity read-only before changing anything.
    with connect(db, readonly=True) as con:
        version = validate(con)
        if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise DatabaseError("DB 무결성 검사에 실패했습니다. 백업을 확인하세요.")
        rows = con.execute("SELECT * FROM project").fetchall()
        if len(rows) != 1:
            raise DatabaseError("프로젝트 정보가 없거나 잘못되었습니다.")
        row = rows[0]
        project = Project(root, row["project_id"], row["name"], row["created_at"])
    if version < SCHEMA_VERSION:
        backup_project(project)
        with connect(db) as con:
            migrate(con, timestamp=now())
    return project


def backup_project(project: Project) -> Path:
    folder = project.root / "backups"
    if folder.is_symlink():
        raise ValueError("백업 폴더에 심볼릭 링크를 사용할 수 없습니다.")
    folder.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = folder / f"project-{stamp}-{uuid4().hex[:8]}.sqlite3"
    backup_database(project.database, destination)
    return destination


def diagnose_project(path: Path) -> dict:
    root = local_path(path)
    db = root / DB_NAME
    if not db.is_file() or db.is_symlink():
        raise DatabaseError("프로젝트 DB를 찾을 수 없습니다.")
    with connect(db, readonly=True) as con:
        version = validate(con)
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise DatabaseError("DB 무결성 검사에 실패했습니다.")
        row = con.execute("SELECT project_id FROM project WHERE singleton = 1").fetchone()
        if row is None:
            raise DatabaseError("프로젝트 정보가 없습니다.")
        return {"project_id": row[0], "schema_version": version, "integrity": integrity}


def restore_project(backup: Path, destination: Path) -> Project:
    """Restore a validated SQLite backup into a new folder only."""
    with connect(backup, readonly=True) as con:
        validate(con)
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise DatabaseError("Backup integrity check failed")
    root = local_path(destination)
    root.mkdir(exist_ok=False)
    try:
        backup_database(backup, root / DB_NAME)
        for name in ("backups", "exports", "logs"):
            (root / name).mkdir()
        return open_project(root)
    except Exception:
        shutil.rmtree(root)
        raise
