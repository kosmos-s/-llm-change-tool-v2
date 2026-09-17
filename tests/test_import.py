import json
import shutil

import pytest

from llm_change_tool.core.datasets import import_dataset, verify_sources
from llm_change_tool.core.labels import effective_doc, original_labels, strict_json
from llm_change_tool.storage.store import rows, transaction


def test_idempotent_and_portable(imported, tmp_path):
    project, root = imported
    original = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    report = import_dataset(project, root)
    assert report["reimport"]
    moved = tmp_path / "new pc 한글"
    shutil.copytree(root, moved)
    assert import_dataset(project, moved)["fingerprint"] == report["fingerprint"]
    assert verify_sources(project) == []
    with transaction(project) as con:
        assert len(rows(con, "SELECT * FROM samples")) == 6
    assert original == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_stale_source_blocks_import(imported):
    project, root = imported
    path = next(root.rglob("*.json"))
    path.write_bytes(path.read_bytes() + b" ")
    assert verify_sources(project)
    with pytest.raises(ValueError, match="changed"):
        import_dataset(project, root)


def test_export_adapter_preserves_unknown(imported):
    project, _ = imported
    with transaction(project) as con:
        sample = rows(con, "SELECT * FROM samples")[0]
    labels = json.loads(sample["original_labels"])
    original, _ = strict_json(sample["original_raw"])
    result = effective_doc(sample["original_raw"], labels, "검수 완료")
    assert result["unknown_metadata"] == original["unknown_metadata"]
    assert original_labels(result) == labels


def test_duplicate_leakage_and_invalid_json(tmp_path):
    from conftest import synthetic

    from llm_change_tool.core.datasets import scan_dataset

    root = synthetic(tmp_path / "data", 3)
    images = sorted(root.rglob("*.jpg"))
    images[1].write_bytes(images[0].read_bytes())
    (root / "bad.json").write_text('{"Artifact":"x", "Artifact":"o"}')
    _, errors, _ = scan_dataset(root)
    assert any(e["error"] == "split_leakage" for e in errors)
    assert any("duplicate JSON key" in e["error"] for e in errors)
