# Build on the target OS. Windows executable uses the same installed package entry.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

a = Analysis(['scripts/entry.py'], pathex=['src'],
    binaries=[], datas=collect_data_files('llm_change_tool'),
    hiddenimports=collect_submodules('llm_change_tool') + ['sqlalchemy.dialects.sqlite.pysqlite'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['tkinter','matplotlib','pandas','pytest'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='LLMChangeTool',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='LLMChangeTool')
