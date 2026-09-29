# PyInstaller spec for the desktop app's backend (one-folder build).
# Build it with:  uv run --with "pyinstaller>=6.10,<7" python packaging/scripts/build_backend.py
# ruff: noqa
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).resolve().parents[1]

# Alembic reads the migration scripts from disk, so ship them as files.
datas = collect_data_files("multicam_api", include_py_files=True, subdir="db/migrations")
for model in ("silero_vad.onnx", "face_detection_yunet_2023mar.onnx"):
    datas.append((str(ROOT / "packaging" / "models" / model), "models"))
for dist in ("multicam-api", "multicam-engine", "fastapi", "starlette", "uvicorn", "pydantic",
             "sse-starlette", "sqlalchemy", "alembic", "huey", "onnxruntime", "numpy", "scipy"):
    try:
        datas += copy_metadata(dist)  # importlib.metadata.version() works when frozen
    except Exception:  # not installed as a distribution (e.g. source checkout)
        pass

hiddenimports = (
    collect_submodules("uvicorn")  # loaded by name at runtime
    + collect_submodules("multicam_api")
    + collect_submodules("multicam_engine")
    + ["sqlalchemy.dialects.sqlite"]
)

a = Analysis(
    [str(ROOT / "packaging" / "pyinstaller" / "entry.py")],
    pathex=[str(ROOT / "engine" / "src"), str(ROOT / "apps" / "api" / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "mypy", "ruff", "PyInstaller"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="multicam-api",
    console=True,  # the app reads the ready line from stdout
    upx=False,
    strip=False,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="multicam-api", upx=False, strip=False)
