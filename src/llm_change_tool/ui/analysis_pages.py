"""Team exchange, conflicts and model evaluation views."""

import json
from pathlib import Path
from uuid import uuid4

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from llm_change_tool.core.exchange import (
    conflicts,
    export_reviews,
    import_reviews,
    resolve_conflict,
)
from llm_change_tool.core.metrics import (
    create_golden,
    dashboard,
    evaluate_golden,
    export_golden_template,
    import_model_predictions,
    model_comparison,
)
from llm_change_tool.core.projects import restore_project
from llm_change_tool.storage.store import rows, transaction


def add_pages(window):
    team = QWidget()
    layout = QVBoxLayout(team)
    bar = QHBoxLayout()
    window.button(
        "검수 ZIP 내보내기",
        lambda: window.background(lambda p: export_reviews(window.project, window.run_id)),
        bar,
    )
    window.button("검수 ZIP 가져오기", lambda: choose_zip(window), bar)
    window.button("충돌 해결", lambda: resolve_next(window), bar)
    window.button("백업에서 새 프로젝트 복원", lambda: restore(window), bar)
    layout.addLayout(bar)
    description = QTextEdit()
    description.setReadOnly(True)
    description.setPlainText(
        "동일 프로젝트 데이터와 작업 계획, Run 설정을 사용하는 팀원끼리 교환합니다.\n팀원에게 프로젝트 DB 백업을 전달하고, 팀원 PC에서 데이터 루트를 다시 Import하면 상대경로로 연결됩니다.\nZIP은 NEW / SAME / CONFLICT로 구분하며 CONFLICT는 자동 덮어쓰지 않습니다.\n원본 이미지와 API Key는 ZIP에 포함되지 않습니다.\n처리 결과는 데이터 · AI 작업 탭과 품질 · Export 탭에서 확인합니다."
    )
    layout.addWidget(description)
    window.tabs.addTab(team, "팀 작업 · 복원")
    stats = QWidget()
    layout = QVBoxLayout(stats)
    bar = QHBoxLayout()
    window.button(
        "통계 새로고침",
        lambda: window.background(
            lambda p: dashboard(window.project, window.run_id), lambda v: display(window, v)
        ),
        bar,
    )
    window.button("Golden Set 고정", lambda: new_golden(window), bar)
    window.button("Golden: 모든 Run 비교", lambda: golden_action(window, "evaluate"), bar)
    layout.addLayout(bar)
    bar = QHBoxLayout()
    window.button("모델 예측 JSON 템플릿", lambda: golden_action(window, "template"), bar)
    window.button("Baseline / Retrained 예측 가져오기", lambda: model_import(window), bar)
    window.button(
        "모델 평가 비교",
        lambda: window.background(
            lambda p: model_comparison(window.project), lambda v: display(window, v)
        ),
        bar,
    )
    layout.addLayout(bar)
    window.analysis = QTextEdit()
    window.analysis.setReadOnly(True)
    layout.addWidget(window.analysis)
    window.tabs.addTab(stats, "통계 · 평가")


def display(window, value):
    window.analysis.setPlainText(json.dumps(value, ensure_ascii=False, indent=2))


def choose_zip(window):
    path, _ = QFileDialog.getOpenFileName(window, "검수 패키지", "", "ZIP (*.zip)")
    if path:
        window.background(lambda p: import_reviews(window.project, window.run_id, Path(path)))


def resolve_next(window):
    if not window.project or not window.run_id:
        return
    values = conflicts(window.project, window.run_id)
    if not values:
        return QMessageBox.information(window, "충돌", "미해결 충돌이 없습니다.")
    conflict = values[0]
    incoming = json.loads(conflict["payload"])
    current = conflict["current"]
    dialog = QMessageBox(window)
    dialog.setWindowTitle(f"충돌 해결 · 남은 {len(values)}건")
    dialog.setText(
        f"샘플 {conflict['sample_id']}\n\n내 결과 ({current['reviewer']})\n{current['labels']}\n{current['reason']}\n\n가져온 결과 ({incoming['reviewer']})\n{json.dumps(incoming['labels'])}\n{incoming['reason']}"
    )
    local = dialog.addButton("내 결과 유지", QMessageBox.ButtonRole.AcceptRole)
    remote = dialog.addButton("가져온 결과 사용", QMessageBox.ButtonRole.DestructiveRole)
    dialog.addButton("나중에", QMessageBox.ButtonRole.RejectRole)
    dialog.exec()
    if dialog.clickedButton() in (local, remote):
        choice = "local" if dialog.clickedButton() == local else "incoming"
        window.background(
            lambda p: resolve_conflict(window.project, conflict["id"], choice, current["revision"])
        )


def restore(window):
    path, _ = QFileDialog.getOpenFileName(window, "DB 백업 선택", "", "SQLite (*.db *.sqlite3)")
    if not path:
        return
    parent = QFileDialog.getExistingDirectory(window, "복원할 새 프로젝트의 부모 폴더")
    if parent:
        window.perform_project_operation(
            lambda: restore_project(Path(path), Path(parent) / f"restored-{uuid4().hex[:10]}"),
            window.set_project,
        )


def new_golden(window):
    name, ok = QInputDialog.getText(window, "Golden Dataset", "Reference set 이름")
    if ok:
        window.background(
            lambda p: create_golden(window.project, window.run_id, name),
            lambda v: display(window, v),
        )


def golden_action(window, action):
    if not window.project:
        return
    with transaction(window.project) as con:
        sets = rows(con, "SELECT * FROM golden_sets ORDER BY created_at")
    if not sets:
        return window._error(ValueError("먼저 Golden Set을 고정하세요."))
    names = [f"{s['name']} · {s['id']}" for s in sets]
    selected, ok = QInputDialog.getItem(window, "Golden Set", "선택", names, 0, False)
    if ok:
        gid = sets[names.index(selected)]["id"]
        fn = evaluate_golden if action == "evaluate" else export_golden_template
        window.background(lambda p: fn(window.project, gid), lambda v: display(window, v))


def model_import(window):
    path, _ = QFileDialog.getOpenFileName(window, "실제 모델 예측 JSON", "", "JSON (*.json)")
    if not path:
        return
    name, ok = QInputDialog.getText(window, "모델 구분", "Baseline 또는 Retrained 모델 이름")
    if ok:
        window.background(
            lambda p: import_model_predictions(window.project, Path(path), name),
            lambda v: display(window, v),
        )
