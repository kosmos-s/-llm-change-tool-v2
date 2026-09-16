"""One-shot worker protocol: UTF-8 JSON Lines on stdout, no Qt or network imports."""

import argparse
import json
from pathlib import Path

from llm_change_tool.core.projects import diagnose_project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["diagnose"])
    parser.add_argument("--project", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = diagnose_project(args.project)
        print(json.dumps({"type": "completed", "result": result}), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps({"type": "failed", "message": str(exc)}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
