"""Rutas de recursos y datos, validas tanto en desarrollo como empaquetado
con PyInstaller (.exe).

- Recursos de solo lectura (config XML de Aplifisa): junto al codigo en
  desarrollo; dentro del bundle (sys._MEIPASS) en el .exe.
- Datos del usuario (ajustes, logs): %APPDATA%\\FacturasAplifisa.
"""

from __future__ import annotations

import os
import re
import sys


def es_frozen() -> bool:
    return getattr(sys, "frozen", False)


def dir_recursos() -> str:
    """Carpeta que contiene config/ (XML de columnas de Aplifisa)."""
    if es_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ruta_config(nombre_xml: str) -> str:
    return os.path.join(dir_recursos(), "config", nombre_xml)


_CARPETAS_DE_WINDOWS = (r"Software\Microsoft\Windows\CurrentVersion"
                        r"\Explorer\User Shell Folders")


def escritorio() -> str:
    """El Escritorio que se ve.

    Con OneDrive («copia de seguridad» de carpetas), Windows lo lleva a
    «OneDrive\\Escritorio» y «~\\Desktop» sigue existiendo pero no se ve: lo
    que el programa dejaba ahí (el Excel, la carpeta de documentación)
    «desaparecía». Se pregunta a Windows dónde está; solo se acepta si queda
    dentro de la carpeta del usuario (si no, el de siempre).
    """
    casa = os.path.expanduser("~")
    por_defecto = os.path.join(casa, "Desktop")
    if sys.platform != "win32":
        return por_defecto
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CARPETAS_DE_WINDOWS) as clave:
            valor, _tipo = winreg.QueryValueEx(clave, "Desktop")
        # Viene como «%USERPROFILE%\\OneDrive\\Escritorio».
        ruta = re.sub(r"%([^%]+)%",
                      lambda m: os.environ.get(m.group(1), m.group(0)),
                      str(valor or ""))
        ruta = os.path.normpath(ruta)
    except OSError:
        return por_defecto
    dentro = os.path.normcase(ruta).startswith(os.path.normcase(casa) + os.sep)
    return ruta if dentro and os.path.isdir(ruta) else por_defecto


def dir_datos() -> str:
    """Carpeta de datos del usuario (se crea si no existe)."""
    base = os.environ.get("APPDATA", os.path.expanduser("~"))
    ruta = os.path.join(base, "FacturasAplifisa")
    os.makedirs(ruta, exist_ok=True)
    return ruta
