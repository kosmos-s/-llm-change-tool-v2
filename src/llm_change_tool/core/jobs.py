"""Persistent sequential job queue with crash-safe reservations and frozen provenance."""

import hashlib
import time
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from llm_change_tool.core.datasets import sample_images, verify_sources
from llm_change_tool.core.labels import SCHEMA_HASH, Prediction, canonical, digest, prompt_text
from llm_change_tool.core.locking import worker_lock
from llm_change_tool.core.plans import validate_plan
from llm_change_tool.core.projects import now
from llm_change_tool.providers.base import ProviderFailure
from llm_change_tool.providers.mock import MockProvider
from llm_change_tool.providers.openai import OpenAIProvider
from llm_change_tool.storage.store import execute, one, rows, transaction


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_default=True)
    provider: Literal["mock", "openai"] = "mock"
    model: str = Field(default="gpt-4o-mini", min_length=1, max_length=100)
    timeout: float = Field(default=60, ge=5, le=180)
    retries: int = Field(default=2, ge=0, le=5)
    max_output_tokens: int = Field(default=1200, ge=100, le=8192)
    input_token_reserve: int = Field(default=20000, ge=1000, le=200000)
    input_price: float = Field(default=0, ge=0, le=1000)
    output_price: float = Field(default=0, ge=0, le=1000)
    cost_limit: float = Field(default=5, gt=0, le=1000)
    confidence_threshold: float = Field(default=0.7, ge=0, le=1)
    review_policy: Literal["core", "detailed"] = "core"

    @model_validator(mode="after")
    def prices(self):
        if self.provider == "openai" and (self.input_price <= 0 or self.output_price <= 0):
            raise ValueError("Enter current USD prices per 1M tokens for the selected model")
        return self

    def reserve(self):
        return (
            0.0
            if self.provider == "mock"
            else (
                self.input_token_reserve * self.input_price
                + self.max_output_tokens * self.output_price
            )
            / 1_000_000
        )


def create_job(project, plan_id, config: RunConfig, prompt=None):
    prompt = prompt if prompt is not None else prompt_text()
    if not prompt.strip():
        raise ValueError("Prompt is empty")
    config_hash = digest({"config": config.model_dump(), "prompt": prompt, "schema": SCHEMA_HASH})
    with transaction(project) as con:
        plan, members = validate_plan(con, plan_id)
        if plan["mode"] == "production" and config.provider != "openai":
            raise ValueError("Production requires actual OpenAI results; use pilot for Mock")
        old = rows(
            con,
            """SELECT j.id FROM jobs j JOIN llm_runs r ON r.id=j.run_id
            WHERE r.plan_id=:p AND r.config_hash=:h""",
            p=plan_id,
            h=config_hash,
        )
        if old:
            return old[0]["id"]
        run_id, job_id = str(uuid4()), str(uuid4())
        execute(
            con,
            "INSERT INTO llm_runs VALUES (:id,:plan,:config,:hash,:prompt,:ph,:sh,:time)",
            id=run_id,
            plan=plan_id,
            config=canonical(config.model_dump()),
            hash=config_hash,
            prompt=prompt,
            ph=hashlib.sha256(prompt.encode()).hexdigest(),
            sh=SCHEMA_HASH,
            time=now(),
        )
        execute(
            con,
            "INSERT INTO jobs(id,run_id,state) VALUES (:id,:run,'PENDING')",
            id=job_id,
            run=run_id,
        )
        for sample in members:
            execute(
                con,
                "INSERT INTO job_items(job_id,sample_id) VALUES (:job,:sid)",
                job=job_id,
                sid=sample["id"],
            )
        return job_id


def validate_run(con, run):
    config = RunConfig.model_validate_json(run["config"])
    if (
        digest({"config": config.model_dump(), "prompt": run["prompt"], "schema": SCHEMA_HASH})
        != run["config_hash"]
        or run["schema_hash"] != SCHEMA_HASH
    ):
        raise ValueError("Run configuration/schema was modified")
    if hashlib.sha256(run["prompt"].encode()).hexdigest() != run["prompt_hash"]:
        raise ValueError("Run prompt hash mismatch")
    validate_plan(con, run["plan_id"])
    return config


def job_info(project, job_id):
    with transaction(project) as con:
        job = one(con, "SELECT * FROM jobs WHERE id=:id", id=job_id)
        job["counts"] = {
            r["state"]: r["n"]
            for r in rows(
                con,
                "SELECT state,count(*) n FROM job_items WHERE job_id=:id GROUP BY state",
                id=job_id,
            )
        }
        job["usage"] = one(
            con,
            """SELECT coalesce(sum(input_tokens),0) input_tokens,
            coalesce(sum(output_tokens),0) output_tokens,coalesce(sum(charged_cost),0) cost,
            coalesce(sum(CASE WHEN state IN ('RUNNING','UNKNOWN') THEN reserved_cost ELSE 0 END),0) reserved
            FROM attempts WHERE job_id=:id""",
            id=job_id,
        )
        return job


def control_job(project, job_id, action):
    if action not in ("pause", "cancel", "retry"):
        raise ValueError("Invalid action")
    if action == "retry":
        with worker_lock(project), transaction(project) as con:
            job = one(con, "SELECT * FROM jobs WHERE id=:id", id=job_id)
            if job["state"] == "CANCELLED":
                raise ValueError("Cancelled jobs cannot resume")
            execute(
                con,
                "UPDATE job_items SET state='PENDING',error='' WHERE job_id=:id AND state='FAILED'",
                id=job_id,
            )
            execute(
                con,
                "UPDATE jobs SET state='PAUSED',message='Retry requested' WHERE id=:id",
                id=job_id,
            )
    else:
        with transaction(project) as con:
            state = "PAUSED" if action == "pause" else "CANCELLED"
            execute(
                con,
                "UPDATE jobs SET state=:state WHERE id=:id AND state NOT IN ('COMPLETED','CANCELLED')",
                state=state,
                id=job_id,
            )


def _recover(con):
    # Only call while holding project OS lock: a live worker can never be recovered.
    execute(con, "UPDATE attempts SET state='UNKNOWN' WHERE state='RUNNING'")
    execute(
        con,
        "UPDATE job_items SET state='FAILED',error='interrupted_unknown_outcome' WHERE state='RUNNING'",
    )
    execute(
        con,
        "UPDATE jobs SET state='PAUSED',owner=NULL,message='Recovered after interruption; retry failed items explicitly' WHERE state='RUNNING'",
    )


def recover_jobs(project):
    with worker_lock(project), transaction(project) as con:
        _recover(con)


def run_job(project, job_id, api_key="", provider=None, progress=lambda value: None):
    with worker_lock(project):
        with transaction(project) as con:
            _recover(con)
            job = one(con, "SELECT * FROM jobs WHERE id=:id", id=job_id)
            run = one(con, "SELECT * FROM llm_runs WHERE id=:id", id=job["run_id"])
            config = validate_run(con, run)
            if job["state"] in ("COMPLETED", "CANCELLED"):
                return {"state": job["state"]}
        errors = verify_sources(project)
        if errors:
            raise ValueError(f"Source integrity/quality errors: {len(errors)}")
        provider = provider or (
            MockProvider() if config.provider == "mock" else OpenAIProvider(api_key)
        )
        owner = str(uuid4())
        with transaction(project) as con:
            execute(
                con,
                "UPDATE jobs SET state='RUNNING',owner=:owner,heartbeat=:t,message='' WHERE id=:id",
                owner=owner,
                t=now(),
                id=job_id,
            )
        try:
            while True:
                with transaction(project) as con:
                    job = one(con, "SELECT * FROM jobs WHERE id=:id", id=job_id)
                    if job["state"] != "RUNNING":
                        break
                    pending = rows(
                        con,
                        "SELECT s.*,i.attempts FROM job_items i JOIN samples s ON s.id=i.sample_id WHERE i.job_id=:id AND i.state='PENDING' ORDER BY s.logical_key LIMIT 1",
                        id=job_id,
                    )
                    if not pending:
                        failed = execute(
                            con,
                            "SELECT count(*) FROM job_items WHERE job_id=:id AND state='FAILED'",
                            id=job_id,
                        ).scalar()
                        execute(
                            con,
                            "UPDATE jobs SET state=:state,owner=NULL WHERE id=:id",
                            state="FAILED" if failed else "COMPLETED",
                            id=job_id,
                        )
                        break
                    sample = pending[0]
                    spent = execute(
                        con,
                        "SELECT coalesce(sum(charged_cost + CASE WHEN state IN ('RUNNING','UNKNOWN') THEN reserved_cost ELSE 0 END),0) FROM attempts WHERE job_id=:id",
                        id=job_id,
                    ).scalar()
                    if spent + config.reserve() > config.cost_limit + 1e-9:
                        execute(
                            con,
                            "UPDATE jobs SET state='PAUSED',message='Estimated cost limit reached',owner=NULL WHERE id=:id",
                            id=job_id,
                        )
                        break
                    aid = str(uuid4())
                    execute(
                        con,
                        "INSERT INTO attempts(id,job_id,sample_id,state,reserved_cost,created_at) VALUES (:id,:job,:sid,'RUNNING',:cost,:t)",
                        id=aid,
                        job=job_id,
                        sid=sample["id"],
                        cost=config.reserve(),
                        t=now(),
                    )
                    execute(
                        con,
                        "UPDATE job_items SET state='RUNNING',attempts=attempts+1 WHERE job_id=:job AND sample_id=:sid",
                        job=job_id,
                        sid=sample["id"],
                    )
                response = None
                try:
                    response = provider.predict(
                        sample_images(project, sample), run["prompt"], config
                    )
                    prediction = Prediction.model_validate_json(response.raw)
                    cost = (
                        0
                        if config.provider == "mock"
                        else (
                            response.input_tokens * config.input_price
                            + response.output_tokens * config.output_price
                        )
                        / 1_000_000
                    )
                    with transaction(project) as con:
                        execute(
                            con,
                            "UPDATE attempts SET state='COMPLETED',charged_cost=:cost,input_tokens=:it,output_tokens=:ot WHERE id=:id",
                            cost=cost,
                            it=response.input_tokens,
                            ot=response.output_tokens,
                            id=aid,
                        )
                        execute(
                            con,
                            "INSERT INTO llm_results VALUES (:run,:sid,:prediction,:raw,:t)",
                            run=run["id"],
                            sid=sample["id"],
                            prediction=canonical(prediction.model_dump()),
                            raw=response.raw,
                            t=now(),
                        )
                        execute(
                            con,
                            "UPDATE job_items SET state='COMPLETED',error='' WHERE job_id=:job AND sample_id=:sid",
                            job=job_id,
                            sid=sample["id"],
                        )
                        if cost > config.reserve() and config.provider == "openai":
                            execute(
                                con,
                                "UPDATE jobs SET state='PAUSED',message='Actual usage exceeded reserve; inspect pricing/reserve' WHERE id=:id",
                                id=job_id,
                            )
                except Exception as exc:
                    retry = (
                        isinstance(exc, ProviderFailure)
                        and exc.retryable
                        and sample["attempts"] < config.retries
                    )
                    code = (
                        str(exc)
                        if isinstance(exc, ProviderFailure)
                        else ("malformed_output" if response else type(exc).__name__)
                    )
                    with transaction(project) as con:
                        # Unknown remote outcomes reserve full estimated cost; never erase on retry.
                        if response:
                            cost = (
                                0
                                if config.provider == "mock"
                                else (
                                    response.input_tokens * config.input_price
                                    + response.output_tokens * config.output_price
                                )
                                / 1_000_000
                            )
                            execute(
                                con,
                                "UPDATE attempts SET state='FAILED',charged_cost=:cost,input_tokens=:it,output_tokens=:ot WHERE id=:id",
                                cost=cost,
                                it=response.input_tokens,
                                ot=response.output_tokens,
                                id=aid,
                            )
                        else:
                            execute(con, "UPDATE attempts SET state='UNKNOWN' WHERE id=:id", id=aid)
                        execute(
                            con,
                            "UPDATE job_items SET state=:state,error=:error WHERE job_id=:job AND sample_id=:sid",
                            state="PENDING" if retry else "FAILED",
                            error=code,
                            job=job_id,
                            sid=sample["id"],
                        )
                    if retry:
                        time.sleep(min(2 ** sample["attempts"], 16))
                with transaction(project) as con:
                    execute(con, "UPDATE jobs SET heartbeat=:t WHERE id=:id", t=now(), id=job_id)
                progress(job_info(project, job_id))
        except BaseException:
            with transaction(project) as con:
                execute(
                    con,
                    "UPDATE jobs SET state='PAUSED',owner=NULL,message='Interrupted; recover before retry' WHERE id=:id AND state='RUNNING'",
                    id=job_id,
                )
            raise
    return job_info(project, job_id)
