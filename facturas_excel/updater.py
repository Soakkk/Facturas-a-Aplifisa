"""Comprobador de actualizaciones via GitHub Releases.

Consulta la ultima release de Soakkk/Facturas-a-Aplifisa-releases, compara con
la version instalada y, si hay una nueva, descarga el instalador (asset .exe)
y lo lanza. El instalador (Inno Setup, mismo AppId) actualiza in-place.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.request
from dataclasses import dataclass
from typing import Optional

from . import __version__

REPO_RELEASES = "Soakkk/Facturas-a-Aplifisa-releases"
URL_API = f"https://api.github.com/repos/{REPO_RELEASES}/releases/latest"
TIMEOUT = 8


@dataclass
class Actualizacion:
    version: str
    url_instalador: str
    notas: str = ""


def _tupla(version: str):
    nums = re.findall(r"\d+", version)
    return tuple(int(n) for n in nums[:3]) or (0,)


def comprobar() -> Optional[Actualizacion]:
    """Devuelve la actualizacion disponible, o None si ya estamos al dia.
    Lanza excepcion si no hay red (el llamador decide silenciarla)."""
    req = urllib.request.Request(URL_API, headers={"User-Agent": "FacturasAplifisa"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        datos = json.load(r)
    tag = (datos.get("tag_name") or "").lstrip("vV")
    if not tag or _tupla(tag) <= _tupla(__version__):
        return None
    for asset in datos.get("assets", []):
        nombre = asset.get("name", "")
        if nombre.lower().endswith(".exe"):
            return Actualizacion(version=tag,
                                 url_instalador=asset["browser_download_url"],
                                 notas=datos.get("body") or "")
    return None


def descargar_y_lanzar(act: Actualizacion) -> None:
    """Descarga el instalador a temp y lo ejecuta. El llamador cierra la app."""
    destino = os.path.join(tempfile.gettempdir(),
                           f"FacturasAplifisa-Setup-{act.version}.exe")
    req = urllib.request.Request(act.url_instalador,
                                 headers={"User-Agent": "FacturasAplifisa"})
    with urllib.request.urlopen(req, timeout=60) as r, open(destino, "wb") as f:
        while True:
            trozo = r.read(65536)
            if not trozo:
                break
            f.write(trozo)
    os.startfile(destino)  # noqa: S606 - instalador descargado de nuestro repo
