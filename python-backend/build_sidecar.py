from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = PROJECT_ROOT / "python-backend"
TAURI_BIN_DIR = PROJECT_ROOT / "src-tauri" / "binaries"
DIST_EXE = BACKEND_ROOT / "dist" / "qingjuan-backend.exe"
TARGET_EXE = TAURI_BIN_DIR / "qingjuan-backend-x86_64-pc-windows-msvc.exe"
IGNORED_PYINSTALLER_WARNING_PATTERNS = (
    'Hidden import "pycparser.lextab" not found!',
    'Hidden import "pycparser.yacctab" not found!',
    'Hidden import "tzdata" not found!',
)


def _is_known_benign_pyinstaller_warning(line: str) -> bool:
    normalized = line.strip()
    return any(pattern in normalized for pattern in IGNORED_PYINSTALLER_WARNING_PATTERNS)


def _run_pyinstaller(command: list[str]) -> None:
    suppressed_count = 0
    process = subprocess.Popen(
        command,
        cwd=BACKEND_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert process.stdout is not None
    for line in process.stdout:
        if _is_known_benign_pyinstaller_warning(line):
            suppressed_count += 1
            continue
        sys.stdout.write(line)

    return_code = process.wait()
    if suppressed_count:
        print(f"已忽略 {suppressed_count} 条已知可选依赖告警（pycparser/tzdata）。")
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, command)


def main() -> None:
    _run_pyinstaller(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--name",
            "qingjuan-backend",
            "--paths",
            str(BACKEND_ROOT),
            "--collect-all",
            "curl_cffi",
            "--collect-all",
            "websockets",
            "--collect-all",
            "PIL",
            str(BACKEND_ROOT / "app" / "main.py"),
        ]
    )

    TAURI_BIN_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DIST_EXE, TARGET_EXE)
    print(f"Sidecar 已生成：{TARGET_EXE}")


if __name__ == "__main__":
    main()
