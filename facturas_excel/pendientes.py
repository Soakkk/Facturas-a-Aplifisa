"""Canal de ida y vuelta entre el programa y quien lo mantiene.

- IDA: `config/pendientes.md` viaja dentro del .exe y trae lo que hace falta
  saber para seguir afinando el programa (dudas, que mirar en esta version).
- VUELTA: lo que el usuario apunte se guarda en
  %APPDATA%\\FacturasAplifisa\\notas-para-claude.md, que se lee en la siguiente
  sesion de trabajo.

El panel solo salta una vez por version: si molesta, deja de usarse.
"""

from __future__ import annotations

import json
import os
from datetime import date

from .rutas import dir_datos, ruta_config

_NOTAS = "notas-para-claude.md"
_AJUSTES = "ajustes.json"

CABECERA_NOTAS = (
    "# Notas para quien mantiene el programa\n\n"
    "Escribe aquí lo que veas: respuestas a las dudas, fallos, ideas.\n"
    "Se lee en la siguiente sesión de trabajo.\n"
)


def leer_pendientes() -> str:
    """Lo que hace falta saber, tal y como viaja en esta version del programa."""
    try:
        with open(ruta_config("pendientes.md"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def ruta_notas() -> str:
    return os.path.join(dir_datos(), _NOTAS)


def leer_notas() -> str:
    try:
        with open(ruta_notas(), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return CABECERA_NOTAS


def guardar_notas(texto: str) -> bool:
    try:
        with open(ruta_notas(), "w", encoding="utf-8") as fh:
            fh.write(texto.rstrip() + "\n")
        return True
    except OSError:
        return False


def apuntar(texto: str) -> bool:
    """Anade una nota fechada al final, sin tocar lo que ya hubiera."""
    texto = (texto or "").strip()
    if not texto:
        return False
    previo = leer_notas().rstrip()
    return guardar_notas(f"{previo}\n\n## {date.today():%d/%m/%Y}\n\n{texto}\n")


# --- ajustes menudos (que version del panel se ha visto ya) ---
def _ruta_ajustes() -> str:
    return os.path.join(dir_datos(), _AJUSTES)


def _leer_ajustes() -> dict:
    try:
        with open(_ruta_ajustes(), encoding="utf-8") as fh:
            datos = json.load(fh)
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def ya_visto(version: str) -> bool:
    return _leer_ajustes().get("pendientes_vistos") == version


def marcar_visto(version: str) -> None:
    datos = _leer_ajustes()
    datos["pendientes_vistos"] = version
    try:
        with open(_ruta_ajustes(), "w", encoding="utf-8") as fh:
            json.dump(datos, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass  # no poder recordarlo no debe tumbar la app
