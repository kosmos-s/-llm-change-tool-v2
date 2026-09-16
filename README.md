# LLM Change Tool v2

Local-first desktop application for the Woosong University × Elcomtech aerial-image change-detection data curation project.

> **Status:** Phase 0 architecture/scaffold. The production LLM pipeline is not implemented yet.

## Direction

- Windows-first desktop app (PySide6), no always-on server required.
- Existing JPG/JSON data remains the external source/target format.
- SQLite is the internal source of truth for project state, runs, review history, jobs, and manifests.
- Original files are read-only; reviewed/final labels are stored separately and exported back to the existing JSON schema.
- Long-running work is modeled as resumable jobs; UI, domain logic, database, providers, workers, and export code stay separated.
- NAS access is optional input storage, never a runtime dependency.

## Phase 0 deliverables

- Architecture and database design documents
- Data/label format decisions
- Python package scaffold
- SQLite/SQLAlchemy and Alembic scaffold
- Minimal PySide6 main window
- Versioned label schema and prompt resource
- CI: secret scan → compile → pytest

## Development quick start

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"
python -m llm_change_tool
```

Tests:

```powershell
pytest
python -m compileall src tests scripts
python scripts/secret_scan.py
```

## Documents

- [Architecture](docs/ARCHITECTURE.md)
- [Database schema](docs/DB_SCHEMA.md)
- [Data format](docs/DATA_FORMAT.md)
- [Label schema](docs/LABEL_SCHEMA.md)
- [Workflow](docs/WORKFLOW.md)
- [Development](docs/DEVELOPMENT.md)
- [Source decisions](docs/SOURCE_DECISIONS.md)
- [Security](SECURITY.md)

## v1 relationship

`kosmos-s/llm-change-auto` remains the validated Streamlit prototype and production-run fallback. v2 reuses validated **rules**, not the Streamlit/CSV/checkpoint architecture.

## Security

Do not commit company data, datasets, project databases, review packages, API keys, NAS credentials, or exports. This repository should remain private unless project stakeholders explicitly approve public release.
