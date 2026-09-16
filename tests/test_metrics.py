import json

import pytest
from test_gate import approve
from test_reviews import prepared

from llm_change_tool.core.metrics import (
    binary_metrics,
    create_golden,
    dashboard,
    evaluate_golden,
    model_evaluation,
)
from llm_change_tool.core.reviews import review_queue


def test_metrics_known_confusion():
    result = binary_metrics([1, 1, 0, 0], [1, 0, 1, 0])
    assert result["f2"] == pytest.approx(0.5)
    assert result["precision"] == 0.5
    assert binary_metrics([0], [0])["f1"] == 0


def test_golden_and_model_evaluation(imported):
    project, _ = imported
    run = prepared(project)
    approve(project, run)
    stats = dashboard(project, run)
    assert stats["review_completed"] == 6 and stats["AI_success"] == 6
    assert stats["GPT_human_agreement"] == 1
    golden = create_golden(project, run, "reference")
    report = evaluate_golden(project, golden["id"])
    assert report["runs"][0]["coverage"] == 1
    predictions = {s["id"]: json.loads(s["reviewed_labels"]) for s in review_queue(project, run)}
    result = model_evaluation(project, golden["id"], "baseline", predictions)
    assert result["kind"] == "change_detection_model"
    assert result["matched"] == 6
    with pytest.raises(ValueError, match="exactly"):
        model_evaluation(project, golden["id"], "incomplete", {})
