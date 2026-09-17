import subprocess
import sys
from pathlib import Path


def test_index_secret_not_hidden_by_working_copy(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    path = tmp_path / "settings.txt"
    path.write_text("sk-" + "a" * 40)
    subprocess.run(["git", "add", "settings.txt"], cwd=tmp_path, check=True)
    path.write_text("harmless unstaged copy")
    script = Path(__file__).resolve().parents[1] / "scripts/check_secrets.py"
    result = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "possible credential" in result.stderr
    assert "a" * 40 not in result.stderr
