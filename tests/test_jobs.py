import pytest

from llm_change_tool.core.jobs import (
    RunConfig,
    control_job,
    create_job,
    job_info,
    recover_jobs,
    run_job,
)
from llm_change_tool.core.plans import create_plan
from llm_change_tool.providers.base import ProviderResponse
from llm_change_tool.providers.mock import MockProvider
from llm_change_tool.storage.store import execute, rows, transaction


def test_mock_job_resume_idempotent(imported):
    project, _ = imported
    plan = create_plan(project)
    job = create_job(project, plan, RunConfig())
    assert create_job(project, plan, RunConfig()) == job

    def pause(info):
        control_job(project, job, "pause")

    assert run_job(project, job, progress=pause)["state"] == "PAUSED"
    assert job_info(project, job)["counts"]["COMPLETED"] == 1
    assert run_job(project, job)["state"] == "COMPLETED"
    assert run_job(project, job)["state"] == "COMPLETED"
    with transaction(project) as con:
        assert len(rows(con, "SELECT * FROM llm_results")) == 6
        assert len(rows(con, "SELECT * FROM attempts")) == 6


def test_malformed_retry_and_configuration_provenance(imported):
    project, _ = imported
    job = create_job(project, create_plan(project), RunConfig())

    class Bad:
        def predict(self, *args):
            return ProviderResponse("{}")

    assert run_job(project, job, provider=Bad())["state"] == "FAILED"
    control_job(project, job, "retry")
    assert run_job(project, job, provider=MockProvider())["state"] == "COMPLETED"
    with transaction(project) as con:
        execute(con, "UPDATE llm_runs SET prompt='changed'")
    with pytest.raises(ValueError, match="modified"):
        run_job(project, job)


def test_budget_and_crash_recovery(imported):
    project, _ = imported
    config = RunConfig(provider="openai", input_price=100, output_price=100, cost_limit=0.001)
    job = create_job(project, create_plan(project), config)
    assert run_job(project, job, provider=MockProvider())["state"] == "PAUSED"
    with transaction(project) as con:
        assert not rows(con, "SELECT * FROM attempts")
        execute(con, "UPDATE jobs SET state='RUNNING' WHERE id=:id", id=job)
        execute(con, "UPDATE job_items SET state='RUNNING' WHERE job_id=:id", id=job)
    recover_jobs(project)
    assert job_info(project, job)["counts"]["FAILED"] == 6
    assert job_info(project, job)["state"] == "PAUSED"


def test_cancel_and_production_count(imported):
    project, _ = imported
    with pytest.raises(ValueError, match="1000"):
        create_plan(project, "production")
    job = create_job(project, create_plan(project), RunConfig())
    control_job(project, job, "cancel")
    assert run_job(project, job)["state"] == "CANCELLED"
    with pytest.raises(ValueError, match="Cancelled"):
        control_job(project, job, "retry")
