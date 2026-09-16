"""Scan tracked source only; never print secret values in diagnostics."""

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
        path = Path(raw.decode())
        if not path.is_file():
            continue
        if path.suffix.lower() in FORBIDDEN or (
            path.name.startswith(".env") and path.name != ".env.example"
        ):
            errors.append(str(path) + ": forbidden data/credential file")
            continue
        if path.stat().st_size > 5_000_000:
            errors.append(str(path) + ": unexpected large source file")
            continue
        if any(pattern.search(path.read_bytes()) for pattern in PATTERNS):
            errors.append(str(path) + ": possible credential (value suppressed)")
    if errors:
        raise SystemExit("\n".join(errors))
    print("Secret/data scan passed")


if __name__ == "__main__":
    main()
