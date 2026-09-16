import json
import zipfile

import pytest
from test_reviews import prepared

from llm_change_tool.core.exchange import (
    conflicts,
    export_reviews,
    import_reviews,
    read_package,
    resolve_conflict,
)
from llm_change_tool.core.projects import backup_project, restore_project
from llm_change_tool.core.reviews import compare_run, review_queue, save_review


def test_team_new_same_conflict_and_restore(imported, tmp_path):
    project, _ = imported
    run = prepared(project)
    compare_run(project, run)
    other = restore_project(backup_project(project), tmp_path / "other pc")
    sample = review_queue(project, run)[0]
    labels = json.loads(sample["original_labels"])
    save_review(project, run, sample["id"], labels, "확정", "A")
    package = export_reviews(project, run)["path"]
    assert import_reviews(other, run, package)["NEW"] == 1
    assert import_reviews(other, run, package)["already_imported"]
    second = export_reviews(project, run)["path"]
    assert import_reviews(other, run, second)["SAME"] == 1
    revision = review_queue(project, run)[0]["revision"]
    save_review(project, run, sample["id"], labels, "재검수 변경", "A", expected_revision=revision)
    third = export_reviews(project, run)["path"]
    assert import_reviews(other, run, third)["CONFLICT"] == 1
    conflict = conflicts(other, run)[0]
    assert review_queue(other, run)[0]["reviewed_reason"] == "확정"
    resolve_conflict(other, conflict["id"], "incoming", conflict["current"]["revision"])
    assert review_queue(other, run)[0]["reviewed_reason"] == "재검수 변경"
    assert not conflicts(other, run)


def test_zip_extra_member_rejected(imported, tmp_path):
    project, _ = imported
    run = prepared(project)
    compare_run(project, run)
    sample = review_queue(project, run)[0]
    save_review(project, run, sample["id"], json.loads(sample["original_labels"]), "okay", "A")
    package = export_reviews(project, run)["path"]
    with zipfile.ZipFile(package, "a") as z:
        z.writestr("../escape", "bad")
    with pytest.raises(ValueError, match="unsafe"):
        read_package(package)
