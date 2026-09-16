"""Generated synthetic dataset and full offline self-test. No corporate fixtures."""

import json
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from llm_change_tool.core.datasets import import_dataset
from llm_change_tool.core.exporting import export_run
from llm_change_tool.core.jobs import RunConfig, create_job, run_job
from llm_change_tool.core.labels import FIELDS
from llm_change_tool.core.plans import create_plan
from llm_change_tool.core.projects import create_project
from llm_change_tool.core.reviews import compare_run, review_queue, save_review


def generate_dataset(root: Path, count=6):
    root.mkdir(exist_ok=False)
    for i in range(count):
        folder = root / "errors" / ("train", "val", "test")[i % 3] / "synthetic_fn"
        folder.mkdir(parents=True, exist_ok=True)
        doc = {
            "artifact_detail": {},
            "reason": "SYNTHETIC",
            "reason_ko": "합성 데이터",
            "metadata": {"synthetic": True, "index": i},
        }
        for f in FIELDS:
            target = doc
            for key in f["path"][:-1]:
                target = target.setdefault(key, {})
            target[f["path"][-1]] = "x"
        (folder / f"{i:04d}_combined.json").write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8"
        )
        im = Image.new("RGB", (512, 256), (i * 30 % 255, 75, 95))
        draw = ImageDraw.Draw(im)
        draw.rectangle((30 + i * 3, 30, 100 + i * 3, 100), fill=(180, 180, 180))
        draw.rectangle((286 + i * 3, 30, 356 + i * 3, 100), fill=(180, 180, 180))
        im.save(folder / f"{i:04d}_combined.jpg")
    return root


def self_test():
    with tempfile.TemporaryDirectory(prefix="llm-change-selftest-") as temporary:
        root = Path(temporary)
        project = create_project(root / "project", "Synthetic self test")
        report = import_dataset(project, generate_dataset(root / "data"))
        if report["errors"]:
            raise ValueError(report["errors"])
        job = create_job(project, create_plan(project), RunConfig())
        result = run_job(project, job)
        if result["state"] != "COMPLETED":
            raise ValueError(result)
        run_id = result["run_id"]
        compare_run(project, run_id)
        for sample in review_queue(project, run_id):
            save_review(
                project,
                run_id,
                sample["id"],
                json.loads(sample["original_labels"]),
                "Synthetic self test",
                "self-test",
            )
        exported = export_run(project, run_id)
        if exported["samples"] != 6:
            raise ValueError("Incomplete self test export")
        return {"passed": True, "samples": 6, "mode": "pilot", "network_calls": 0}
