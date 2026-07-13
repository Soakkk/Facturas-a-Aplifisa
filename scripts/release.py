"""Release en un comando: sincroniza version -> PyInstaller -> Inno Setup ->
sube el instalador a GitHub (repo -releases) para la auto-actualizacion.

Uso:  python scripts/release.py            (usa la version de __init__.py)
      python scripts/release.py --no-upload  (solo compilar, sin subir)
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = RAIZ / ".venv" / "Scripts" / "python.exe"
ISCC = Path(r"C:\Users\ASESORIA\AppData\Local\Programs\Inno Setup 6\ISCC.exe")
REPO_RELEASES = "Soakkk/Facturas-a-Aplifisa-releases"


def version_actual() -> str:
    texto = (RAIZ / "facturas_excel" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__ = "([^"]+)"', texto).group(1)


def sincronizar_iss(version: str):
    iss = RAIZ / "installer" / "FacturasAplifisa.iss"
    texto = iss.read_text(encoding="utf-8")
    texto = re.sub(r'#define MyAppVersion "[^"]+"',
                   f'#define MyAppVersion "{version}"', texto)
    iss.write_text(texto, encoding="utf-8")


def paso(nombre, cmd):
    print(f"\n== {nombre} ==")
    r = subprocess.run([str(c) for c in cmd], cwd=RAIZ)
    if r.returncode != 0:
        print(f"FALLO en: {nombre}")
        sys.exit(1)


def main():
    version = version_actual()
    print(f"Version: {version}")
    sincronizar_iss(version)

    # limpiar builds anteriores
    for d in ("build", "dist"):
        shutil.rmtree(RAIZ / d, ignore_errors=True)

    paso("Lint", [PY, "-m", "pyflakes", "facturas_excel"])
    paso("PyInstaller", [
        PY, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", "FacturasAplifisa",
        "--add-data", "config;config",
        "--collect-submodules", "keyring.backends",
        "run_app.py",
    ])
    paso("Inno Setup", [ISCC, RAIZ / "installer" / "FacturasAplifisa.iss"])

    instalador = RAIZ / "dist_installer" / f"FacturasAplifisa_Setup_{version}.exe"
    print(f"\nInstalador: {instalador}")
    if not instalador.exists():
        print("No se genero el instalador."); sys.exit(1)

    if "--no-upload" in sys.argv:
        print("(sin subir a GitHub)"); return

    paso("GitHub release", [
        "gh", "release", "create", f"v{version}",
        str(instalador),
        "--repo", REPO_RELEASES,
        "--title", f"Facturas a Aplifisa v{version}",
        "--notes", f"Version {version}. El programa se actualiza solo desde aqui.",
    ])
    print("\nRelease publicada. Las apps instaladas se actualizaran solas.")


if __name__ == "__main__":
    main()
