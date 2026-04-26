# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — backend.exe 단일 디렉토리 배포.

빌드:
    cd backend
    uv run pyinstaller backend.spec --noconfirm

결과: backend/dist/backend/backend.exe
"""

import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# ────────────────────────────────────────────────────────────────
# 의존성 패키지 모두 수집 (data, binaries, hidden imports)
# ────────────────────────────────────────────────────────────────
datas = []
binaries = []
hiddenimports = []

for pkg in (
    "pydantic",
    "pydantic_core",
    "pydantic_settings",
    "notion_client",
    "jose",
    "bcrypt",
    "email_validator",
    "sqlalchemy",
    "alembic",
    "uvicorn",
    "starlette",
    "fastapi",
    "anyio",
    "httpx",
    "httpcore",
    "h11",
    "httptools",
    "websockets",
    "watchfiles",
):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# 정적 frontend 포함 (frontend/out 이 존재할 때만)
_HERE = os.path.dirname(os.path.abspath(SPEC))
_FRONTEND_OUT = os.path.normpath(os.path.join(_HERE, "..", "frontend", "out"))
if os.path.isdir(_FRONTEND_OUT):
    datas.append((_FRONTEND_OUT, "frontend_out"))

# Alembic 마이그레이션 (운영에서는 init_db로 충분하지만 함께 번들)
_ALEMBIC = os.path.join(_HERE, "alembic")
if os.path.isdir(_ALEMBIC):
    datas.append((_ALEMBIC, "alembic"))
    datas.append((os.path.join(_HERE, "alembic.ini"), "."))


a = Analysis(
    ["run.py"],
    pathex=[_HERE],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["app.main"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # 번들 크기 절감 — 우리 앱이 안 쓰는 무거운 패키지
        "matplotlib",
        "scipy",
        "numpy",
        "pandas",
        "PIL",
        "tkinter",
        "test",
        "tests",
    ],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # 디버깅 편의 — release 시 False 검토
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="backend",
)
