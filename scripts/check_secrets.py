"""Scan the Git index (the content that will actually be committed)."""

import json
import re
import subprocess
from pathlib import Path

PATTERNS = [
    re.compile(rb"sk-" + rb"(?:proj-)?[A-Za-z0-9_-]{20,}"),
    re.compile(rb"gh[pousr]_" + rb"[A-Za-z0-9]{20,}"),
    re.compile(rb"-----BEGIN " + rb"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]
FORBIDDEN = {".db", ".sqlite3", ".jpg", ".jpeg", ".tif", ".tiff", ".zip"}


def main():
    paths = subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0")
    errors = []
    for raw in paths:
        if not raw:
            continue
        name = raw.decode()
        path = Path(name)
        if path.suffix.lower() in FORBIDDEN or (
            path.name.startswith(".env") and path.name != ".env.example"
        ):
            errors.append(name + ": forbidden data/credential file")
            continue
        data = subprocess.check_output(["git", "show", ":" + name])
        if len(data) > 5_000_000:
            errors.append(name + ": unexpected large source file")
            continue
        if any(pattern.search(data) for pattern in PATTERNS):
            errors.append(name + ": possible credential (value suppressed)")
        if path.suffix.lower() == ".json":
            try:
                doc = json.loads(data)
                if isinstance(doc, dict) and "Artifact" in doc and "artifact_detail" in doc:
                    errors.append(name + ": possible dataset label JSON")
            except (ValueError, UnicodeDecodeError):
                pass
    if errors:
        raise SystemExit("\n".join(errors))
    print("Secret/data scan passed")


if __name__ == "__main__":
    main()
