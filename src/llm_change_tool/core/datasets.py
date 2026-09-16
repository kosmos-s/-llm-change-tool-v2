"""Read-only source scanner and atomic, idempotent import."""

import hashlib
import json
from pathlib import Path, PurePosixPath

from PIL import Image

from llm_change_tool.core.labels import canonical, digest, original_labels, strict_json
from llm_change_tool.core.projects import now
from llm_change_tool.storage.store import execute, one, rows, transaction


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_path(root: Path, relative: str):
    p = PurePosixPath(relative)
    if not relative or p.is_absolute() or ".." in p.parts or "\\" in relative or ":" in relative:
        raise ValueError("Unsafe relative path")
    result = (root / Path(*p.parts)).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError("Source path escapes dataset root")
    return result


def scan_dataset(root: Path, progress=lambda value: None):
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Dataset folder not found")
    samples, errors = [], []
    candidates = sorted(root.rglob("*.json"))
    image_keys, logical_keys, used_images = {}, set(), set()
    for index, path in enumerate(candidates):
        rel = path.relative_to(root).as_posix()
        try:
            safe_path(root, rel)
            if path.stat().st_size > 2_000_000:
                raise ValueError("JSON exceeds 2 MB")
            raw = path.read_bytes()
            doc, encoding = strict_json(raw)
            labels = original_labels(doc)
            parts = list(path.relative_to(root).parts)
            split_positions = [
                i for i, p in enumerate(parts[:-1]) if p.lower() in ("train", "val", "test")
            ]
            if len(split_positions) != 1:
                raise ValueError("Select common dataset root containing train/val/test")
            split_at = split_positions[0]
            split = parts[split_at].lower()
            source = (
                "errors"
                if "errors" in [p.lower() for p in parts[:split_at]]
                or root.name.lower() == "errors"
                else "dataset"
            )
            tail = "/".join(parts[split_at + 1 :])
            key = f"{source}/{split}/{tail}"
            if key.casefold() in logical_keys:
                raise ValueError("Duplicate logical key (case-insensitive Windows path)")
            logical_keys.add(key.casefold())
            stem = path.stem.removesuffix("_combined")
            siblings = {p.name.lower(): p for p in path.parent.iterdir() if p.is_file()}

            def find(name, siblings=siblings):
                return next(
                    (
                        siblings.get((name + ext).lower())
                        for ext in (".jpg", ".jpeg")
                        if (name + ext).lower() in siblings
                    ),
                    None,
                )

            combined = find(stem + "_combined")
            t1, t2 = find(stem + "_left"), find(stem + "_right")
            if bool(t1) != bool(t2):
                raise ValueError("Missing T1/T2 counterpart")
            if not combined and not (t1 and t2):
                raise ValueError("Missing combined image or T1/T2 pair")
            paths = {"json": rel}
            sizes = {}
            for role, image in [("combined", combined), ("t1", t1), ("t2", t2)]:
                if image:
                    image_rel = image.relative_to(root).as_posix()
                    safe_path(root, image_rel)
                    with Image.open(image) as im:
                        sizes[role] = im.size
                        im.verify()
                    paths[role] = image_rel
                    used_images.add(image_rel)
            if t1 and sizes["t1"] != sizes["t2"]:
                raise ValueError("T1/T2 dimensions differ")
            if combined and sizes["combined"][0] % 2:
                raise ValueError("Combined image width must be even")
            hashes = {role: sha(safe_path(root, p)) for role, p in paths.items()}
            image_hash = digest([hashes.get("t1"), hashes.get("t2")]) if t1 else hashes["combined"]
            if image_hash in image_keys:
                previous = image_keys[image_hash]
                errors.append(
                    {
                        "path": rel,
                        "error": "split_leakage" if previous[0] != split else "duplicate_image",
                        "other": previous[1],
                    }
                )
            else:
                image_keys[image_hash] = (split, rel)
            samples.append(
                dict(
                    id=digest(key),
                    logical_key=key,
                    source=source,
                    split=split,
                    error_type=parts[split_at + 1]
                    if source == "errors" and len(parts) > split_at + 2
                    else "",
                    paths=canonical(paths),
                    hashes=canonical(hashes),
                    original_raw=raw,
                    original_labels=canonical(labels),
                    encoding=encoding,
                )
            )
        except Exception as exc:
            errors.append({"path": rel, "error": str(exc)})
        progress({"current": index + 1, "total": len(candidates)})
    for image in root.rglob("*"):
        if image.is_file() and image.suffix.lower() in (".jpg", ".jpeg"):
            if image.relative_to(root).as_posix() not in used_images:
                errors.append({"path": image.relative_to(root).as_posix(), "error": "orphan_image"})
    if not samples:
        errors.append({"path": ".", "error": "No valid samples"})
    fingerprint = digest(sorted((s["logical_key"], json.loads(s["hashes"])) for s in samples))
    return samples, errors, fingerprint


def import_dataset(project, root: Path, progress=lambda value: None):
    root = root.expanduser().resolve()
    if project.root.is_relative_to(root) or root.is_relative_to(project.root):
        raise ValueError("Keep dataset and project folders separate")
    samples, errors, fingerprint = scan_dataset(root, progress)
    with transaction(project) as con:
        old = rows(con, "SELECT * FROM datasets")
        if old and old[0]["fingerprint"] != fingerprint:
            raise ValueError(
                "Dataset content changed. Existing runs remain preserved; use a new project."
            )
        if not old:
            for sample in samples:
                execute(
                    con,
                    """INSERT INTO samples VALUES (:id,:logical_key,:source,:split,:error_type,
                    :paths,:hashes,:original_raw,:original_labels,:encoding)""",
                    **sample,
                )
        execute(
            con,
            """INSERT INTO datasets VALUES (1,:root,:fp,:quality,:time)
            ON CONFLICT(id) DO UPDATE SET root=:root, quality=:quality, imported_at=:time""",
            root=str(root),
            fp=fingerprint,
            quality=canonical(errors),
            time=now(),
        )
    return {
        "samples": len(samples),
        "errors": errors,
        "fingerprint": fingerprint,
        "reimport": bool(old),
    }


def verify_sources(project):
    with transaction(project) as con:
        dataset = one(con, "SELECT * FROM datasets")
        samples = rows(con, "SELECT * FROM samples ORDER BY logical_key")
    errors = json.loads(dataset["quality"])
    root = Path(dataset["root"])
    for sample in samples:
        try:
            for role, rel in json.loads(sample["paths"]).items():
                if sha(safe_path(root, rel)) != json.loads(sample["hashes"])[role]:
                    raise ValueError(f"Source SHA256 changed: {rel}")
            if (
                hashlib.sha256(sample["original_raw"]).hexdigest()
                != json.loads(sample["hashes"])["json"]
            ):
                raise ValueError("Stored original hash mismatch")
        except Exception as exc:
            errors.append({"path": sample["logical_key"], "error": str(exc)})
    current = digest(sorted((s["logical_key"], json.loads(s["hashes"])) for s in samples))
    if current != dataset["fingerprint"]:
        errors.append({"error": "Dataset fingerprint mismatch"})
    return errors


def sample_images(project, sample):
    with transaction(project) as con:
        root = Path(one(con, "SELECT root FROM datasets")["root"])
    paths = json.loads(sample["paths"])
    if "t1" in paths:
        with Image.open(safe_path(root, paths["t1"])) as im:
            left = im.convert("RGB")
        with Image.open(safe_path(root, paths["t2"])) as im:
            right = im.convert("RGB")
        return left, right
    with Image.open(safe_path(root, paths["combined"])) as im:
        im = im.convert("RGB")
        w, h = im.size
        return im.crop((0, 0, w // 2, h)), im.crop((w // 2, 0, w, h))
