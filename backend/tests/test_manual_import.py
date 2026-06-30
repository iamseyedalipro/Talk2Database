"""Failure-path test for the manual-import background task.

A failure anywhere in ``process_manual_import`` (e.g. the post-restore snapshot
rebuild) must move the run to FAILED instead of leaving it stuck on RUNNING, and
the uploaded temp file must always be cleaned up.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import app.importers.manual as manual
from app.models.import_run import ImportStatus


class _FakeSession:
    def __init__(self, run: object) -> None:
        self._run = run
        self.commits = 0

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get(self, _model: object, _pk: object) -> object:
        return self._run

    async def commit(self) -> None:
        self.commits += 1


async def test_failure_marks_run_failed_and_cleans_up(monkeypatch, tmp_path: Path) -> None:
    run = SimpleNamespace(status=ImportStatus.RUNNING, message=None, finished_at=None)
    monkeypatch.setattr(manual, "get_sessionmaker", lambda: (lambda: _FakeSession(run)))

    # Run threadpool work inline so we can drive the stubbed helpers deterministically.
    async def _inline(func, *args):
        return func(*args)

    monkeypatch.setattr(manual, "run_in_threadpool", _inline)
    monkeypatch.setattr(manual, "check_restore_compatibility", lambda *a, **k: None)
    monkeypatch.setattr(manual, "_restore", lambda *a, **k: (True, "restored"))
    monkeypatch.setattr(manual, "ensure_readonly_role", lambda *a, **k: None)

    async def _boom(_session: object) -> None:
        raise RuntimeError("snapshot rebuild failed")

    monkeypatch.setattr(manual, "rebuild_snapshot", _boom)

    dump = tmp_path / "dump.sql"
    dump.write_text("CREATE TABLE t (id int);\n")

    await manual.process_manual_import(1, str(dump), "dump.sql")

    assert run.status == ImportStatus.FAILED
    assert run.finished_at is not None
    assert run.message and "snapshot rebuild failed" in run.message
    assert not dump.exists()  # finally removed the temp file


async def test_success_marks_run_success(monkeypatch, tmp_path: Path) -> None:
    run = SimpleNamespace(status=ImportStatus.RUNNING, message=None, finished_at=None)
    monkeypatch.setattr(manual, "get_sessionmaker", lambda: (lambda: _FakeSession(run)))

    async def _inline(func, *args):
        return func(*args)

    monkeypatch.setattr(manual, "run_in_threadpool", _inline)
    monkeypatch.setattr(manual, "check_restore_compatibility", lambda *a, **k: None)
    monkeypatch.setattr(manual, "_restore", lambda *a, **k: (True, "restored"))
    monkeypatch.setattr(manual, "ensure_readonly_role", lambda *a, **k: None)

    async def _ok(_session: object) -> None:
        return None

    monkeypatch.setattr(manual, "rebuild_snapshot", _ok)

    dump = tmp_path / "dump.sql"
    dump.write_text("CREATE TABLE t (id int);\n")

    await manual.process_manual_import(2, str(dump), "dump.sql")

    assert run.status == ImportStatus.SUCCESS
    assert run.finished_at is not None
    assert not dump.exists()
