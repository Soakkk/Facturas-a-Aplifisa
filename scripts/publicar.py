"""Publica una version sin pisar el trabajo del otro asistente.

En este proyecto trabajan dos IA a la vez sobre la misma rama. Publicar a mano
salio mal el 2026-09-02: los dos etiquetaron v1.10.1 con minutos de diferencia.
Este script hace siempre lo mismo y en el mismo orden, y se planta si algo no
cuadra:

  1. Se trae lo que haya subido el otro y se pone ENCIMA (rebase, nunca force).
  2. Pasa los tests. Si fallan, no publica.
  3. Elige el siguiente numero de version LIBRE mirando las etiquetas de GitHub.
  4. Sube el numero, commit, etiqueta y push. El CI compila el instalador.

Uso:
    .venv\\Scripts\\python scripts\\publicar.py "resumen del cambio"
    .venv\\Scripts\\python scripts\\publicar.py "resumen" --menor   # sube 1.11.0
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIT = os.path.join(RAIZ, "facturas_excel", "__init__.py")


def git(*args, capturar=True):
    r = subprocess.run(["git", *args], cwd=RAIZ, text=True,
                       capture_output=capturar)
    if r.returncode != 0:
        salida = (r.stderr or r.stdout or "").strip()
        raise SystemExit(f"[X] Fallo en 'git {' '.join(args)}':\n{salida}")
    return (r.stdout or "").strip()


def version_actual() -> tuple:
    with open(INIT, encoding="utf-8") as fh:
        encaje = re.search(r'__version__\s*=\s*"([^"]+)"', fh.read())
    if not encaje:
        raise SystemExit("[X] No se encuentra __version__ en facturas_excel/__init__.py")
    return tuple(int(p) for p in encaje.group(1).split("."))


def etiquetas_publicadas() -> set:
    salida = git("ls-remote", "--tags", "origin")
    return set(re.findall(r"refs/tags/v(\d+\.\d+\.\d+)(?:\^\{\})?$", salida,
                          re.MULTILINE))


def siguiente_version(menor: bool) -> str:
    """El primer numero libre: el otro puede haber cogido el que tocaba."""
    mayor, med, parche = version_actual()
    if menor:
        med, parche = med + 1, 0
    else:
        parche += 1
    publicadas = etiquetas_publicadas()
    while f"{mayor}.{med}.{parche}" in publicadas:
        parche += 1
    return f"{mayor}.{med}.{parche}"


def escribir_version(version: str) -> None:
    with open(INIT, encoding="utf-8") as fh:
        texto = fh.read()
    texto = re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{version}"', texto)
    with open(INIT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(texto)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("resumen", help="Que cambia esta version, en una linea")
    parser.add_argument("--menor", action="store_true",
                        help="Version menor (1.10.x -> 1.11.0) en vez de parche")
    parser.add_argument("--solo-comprobar", action="store_true",
                        help="Comprueba y dice que haria, sin publicar nada")
    args = parser.parse_args()

    print("1) Buscando trabajo del otro asistente…")
    git("fetch", "--tags")
    pendiente = git("log", "--oneline", "HEAD..origin/master")
    if pendiente:
        print("   Hay cosas nuevas, me pongo encima:")
        for linea in pendiente.splitlines():
            print("     ", linea)
        if git("status", "--porcelain"):
            raise SystemExit(
                "[X] Hay cambios sin guardar y el otro ha subido trabajo.\n"
                "    Haz commit de lo tuyo y vuelve a lanzarlo.")
        git("rebase", "origin/master")
    else:
        print("   Nada nuevo: seguimos.")

    print("2) Pasando los tests…")
    r = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"],
                       cwd=RAIZ, text=True, capture_output=True)
    print("  ", (r.stdout or "").strip().splitlines()[-1] if r.stdout else "")
    if r.returncode != 0:
        raise SystemExit("[X] Los tests fallan: no se publica nada.")

    version = siguiente_version(args.menor)
    print(f"3) Version libre elegida: v{version}")
    if args.solo_comprobar:
        print("   (--solo-comprobar: no se publica)")
        return

    escribir_version(version)
    git("add", "-A")
    git("commit", "-m", f"v{version}: {args.resumen}\n\n"
                        "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>")
    git("tag", "-a", f"v{version}", "-m", f"v{version}: {args.resumen}")

    print("4) Subiendo…")
    git("push", "origin", "master")
    git("push", "origin", f"v{version}")
    print(f"[OK] v{version} publicada. El CI compila el instalador "
          f"(unos 5 minutos).")


if __name__ == "__main__":
    main()
