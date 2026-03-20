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


def main() -> None:
    subprocess.run(
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
            str(BACKEND_ROOT / "app" / "main.py"),
        ],
        cwd=BACKEND_ROOT,
        check=True,
    )

    TAURI_BIN_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DIST_EXE, TARGET_EXE)
    print(f"Sidecar 已生成：{TARGET_EXE}")


if __name__ == "__main__":
    main()
