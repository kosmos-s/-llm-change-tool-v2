import json

import pytest

from llm_change_tool.core.jobs import RunConfig, create_job, run_job
from llm_change_tool.core.plans import create_plan
from llm_change_tool.core.reviews import (
    compare_run,
    review_history,
    review_queue,
    save_review,
    undo_review,
)
from llm_change_tool.storage.store import one, transaction


def prepared(project):
    job = create_job(project, create_plan(project), RunConfig())
    run_job(project, job)
    with transaction(project) as con:
        run = one(con, "SELECT run_id FROM jobs WHERE id=:id", id=job)["run_id"]
    return run


def test_compare_review_revisions_and_optimistic_lock(imported):
    project, _ = imported
    run = prepared(project)
    assert compare_run(project, run) == {"compared": 6, "required": 6}
    sample = review_queue(project, run)[0]
    labels = json.loads(sample["original_labels"])
    rev = save_review(project, run, sample["id"], labels, "확인", "tester")
    with pytest.raises(ValueError, match="changed"):
        save_review(project, run, sample["id"], labels, "stale", "other")
    rev2 = save_review(project, run, sample["id"], labels, "보류", "tester", "DEFERRED", rev)
    assert len(review_queue(project, run, "deferred")) == 1
    undo_review(project, run, sample["id"], "tester")
    assert review_queue(project, run)[0]["review_state"] == "DONE"
    assert len(review_history(project, run, sample["id"])) == 3
    compare_run(project, run)
    assert review_queue(project, run)[0]["revision"] > rev2
