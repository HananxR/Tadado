"""生成双 exe 打包 spec（Tadado.exe GUI + tadado-cli.exe CLI）.

Tadado.spec 是 gitignore 文件，容易被 pyinstaller 命令行构建覆盖回单 exe。
build.bat 在每次构建前调用本脚本重写 spec，保证双 exe 配置永不丢失。
"""

from __future__ import annotations

from pathlib import Path

_SPEC = '''# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('resources', 'resources')],
    hiddenimports=['PySide6.QtSvg', 'src.version',
                   'src.cli.headless', 'src.cli.commands', 'src.cli.parser',
                   'src.cli.output', 'src.cli.forward', 'src.cli.protocol'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe_gui = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Tadado',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['resources\\\\icons\\\\app.ico'],
)
exe_cli = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='tadado-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['resources\\\\icons\\\\app.ico'],
)
coll = COLLECT(
    exe_gui,
    exe_cli,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Tadado',
)
'''


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    spec = root / "Tadado.spec"
    spec.write_text(_SPEC, encoding="utf-8")
    print(f"[OK] Dual-exe spec written: {spec}")


if __name__ == "__main__":
    main()
