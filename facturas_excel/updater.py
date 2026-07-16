"""Comprobador de actualizaciones via GitHub Releases.

Consulta la ultima release de Soakkk/Facturas-a-Aplifisa-releases, compara con
la version instalada y, si hay una nueva, descarga el instalador (asset .exe)
y lo lanza. El instalador (Inno Setup, mismo AppId) actualiza in-place.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import __version__

REPO_RELEASES = "Soakkk/Facturas-a-Aplifisa"
URL_API = f"https://api.github.com/repos/{REPO_RELEASES}/releases/latest"
TIMEOUT = 8


@dataclass
class Actualizacion:
    version: str
    url_instalador: str
    url_sha256: str = ""
    size: int = 0
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
    instalador = None
    sha256 = ""
    for asset in datos.get("assets", []):
        nombre = asset.get("name", "")
        nombre_min = nombre.lower()
        if nombre_min.endswith(".exe") and "setup" in nombre_min:
            instalador = asset
        elif nombre_min.endswith(".sha256"):
            sha256 = asset.get("browser_download_url", "")
    if not instalador:
        return None
    return Actualizacion(
        version=tag,
        url_instalador=instalador["browser_download_url"],
        url_sha256=sha256,
        size=int(instalador.get("size") or 0),
        notas=datos.get("body") or "",
    )


def _hash_esperado(url: str) -> str | None:
    if not url:
        return None
    req = urllib.request.Request(url, headers={"User-Agent": "FacturasAplifisa"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        texto = r.read().decode("utf-8", "replace")
    encontrado = re.search(r"\b([0-9a-fA-F]{64})\b", texto)
    return encontrado.group(1).lower() if encontrado else None


def descargar(act: Actualizacion,
              progreso: Callable[[int], None] | None = None) -> str:
    """Descarga y verifica el instalador, devolviendo su ruta temporal."""
    destino = Path(tempfile.gettempdir()) / f"FacturasAplifisa-Setup-{act.version}.exe"
    esperado = _hash_esperado(act.url_sha256)
    req = urllib.request.Request(
        act.url_instalador, headers={"User-Agent": "FacturasAplifisa"})
    bajado = 0
    digestor = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as r, open(destino, "wb") as f:
        total = act.size or int(r.headers.get("Content-Length", 0))
        while True:
            trozo = r.read(1024 * 256)
            if not trozo:
                break
            f.write(trozo)
            digestor.update(trozo)
            bajado += len(trozo)
            if progreso and total:
                progreso(min(100, int(bajado * 100 / total)))
    if act.size and destino.stat().st_size != act.size:
        destino.unlink(missing_ok=True)
        raise ValueError("La descarga del instalador está incompleta")
    if esperado and digestor.hexdigest() != esperado:
        destino.unlink(missing_ok=True)
        raise ValueError("La verificación de integridad SHA-256 no coincide")
    return str(destino)


def lanzar_instalador(ruta: str) -> None:
    subprocess.Popen(
        [ruta, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
        close_fds=True,
    )


def descargar_y_lanzar(act: Actualizacion) -> None:
    """Compatibilidad con el flujo anterior."""
    lanzar_instalador(descargar(act))
