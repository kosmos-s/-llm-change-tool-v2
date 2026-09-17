from collections import Counter

import pytest
from conftest import synthetic

from llm_change_tool.core.datasets import import_dataset
from llm_change_tool.core.jobs import RunConfig, create_job
from llm_change_tool.core.plans import create_plan, validate_plan
from llm_change_tool.core.projects import create_project
from llm_change_tool.storage.store import execute, transaction


def test_production_fixes_exactly_3000_ids(tmp_path):
    root = synthetic(tmp_path / "data", 3003)
    # Unique synthetic provenance even where the tiny rendered image repeats.
    for path in root.rglob("*.jpg"):
        with path.open("ab") as stream:
            stream.write(b"synthetic-id:" + path.stem.encode())
    project = create_project(tmp_path / "project", "Production plan test")
    assert import_dataset(project, root)["errors"] == []
    plan_id = create_plan(project, "production")
    with transaction(project) as con:
        _, members = validate_plan(con, plan_id)
    assert len({sample["id"] for sample in members}) == 3000
    assert Counter(sample["split"] for sample in members) == dict(train=1000, val=1000, test=1000)
    assert {sample["source"] for sample in members} == {"errors"}
    assert create_plan(project, "production") == plan_id
    with pytest.raises(ValueError, match="actual OpenAI"):
        create_job(project, plan_id, RunConfig())
    with transaction(project) as con:
        execute(con, "DELETE FROM work_plan_items WHERE sample_id=:id", id=members[0]["id"])
        with pytest.raises(ValueError, match="invalid work plan"):
            validate_plan(con, plan_id)
