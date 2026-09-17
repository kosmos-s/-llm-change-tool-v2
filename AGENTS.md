# Development contract

Build the complete local Windows desktop application in the user's Phase 0–7 order.
UI / Core / DB / Worker / Provider stay separate. Qt is never imported in core.
Use Python 3.11-compatible code, SQLAlchemy, Pydantic, SQLite migrations and PyInstaller.
Original JPG and JSON are read-only. Keep portable relative keys and original bytes/hash.
Use resources/label_schemas/label_schema_v1.json as the label registry.
Latest policy source is the 26.03.24 guideline; road marks alone are not a new positive label.
Do not commit credentials, corporate data, work DBs, exports or backups.
Long-running work belongs in background workers. Preserve all review revisions.
Mock runs are explicitly pilot-only and never count as production AI coverage.
Final Gate must reject stale provenance, unresolved errors, deferred/required reviews.
Run relevant pytest checks and commit each phase; do not wait for routine user decisions.
