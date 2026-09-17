"""One-shot worker protocol: UTF-8 JSON Lines on stdout, no Qt or network imports."""

import argparse
import json
import sys
from pathlib import Path

from llm_change_tool.core.projects import diagnose_project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["diagnose"])
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    def emit(message):
        encoded = json.dumps(message)
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(encoded)
        elif sys.stdout is not None:
            print(encoded, flush=True)

    try:
        result = diagnose_project(args.project)
        emit({"type": "completed", "result": result})
        return 0
    except Exception as exc:
        emit({"type": "failed", "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
