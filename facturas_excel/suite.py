"""Directorio comun de clientes de la suite de la asesoria.

Los programas de la asesoria (Generador de avisos fiscales, Escaner...)
comparten %LOCALAPPDATA%\\AsesoriaEMarin\\Suite\\clientes.json con el NIF, el
nombre y otros datos de cada cliente. Aqui se usa para dos cosas:

  - reconocer al cliente del lote al momento: si un NIF esta en el directorio,
    es cliente de la asesoria (no hay que preguntarlo) y se usa su nombre;
  - apuntar alli el cliente que una persona confirma en este programa, con el
    mismo formato y las mismas reglas que los demas: nunca se pisa un valor
    distinto, se guarda como alternativa en conflicto.

Si el fichero no existe, no se entiende o no se puede escribir, el programa
sigue igual que antes: el directorio es una ayuda, no un requisito.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from typing import Dict, Optional

ORIGEN = "facturas"


def ruta_directorio() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "AsesoriaEMarin", "Suite", "clientes.json")


def _normaliza(nif) -> str:
    return re.sub(r"[\s.\-]+", "", str(nif or "")).upper()


_cache: dict = {"mtime": None, "ruta": None, "datos": None}


def _leer_crudo() -> Optional[dict]:
    """El fichero tal cual, o None si no existe o no es del formato comun."""
    ruta = ruta_directorio()
    try:
        mtime = os.path.getmtime(ruta)
    except OSError:
        return None
    if _cache["ruta"] == ruta and _cache["mtime"] == mtime:
        return _cache["datos"]
    try:
        with open(ruta, encoding="utf-8") as fh:
            datos = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(datos, dict) or datos.get("schema_version") != 1 \
            or not isinstance(datos.get("clientes"), dict):
        datos = None
    _cache.update(mtime=mtime, ruta=ruta, datos=datos)
    return datos


def clientes() -> Dict[str, dict]:
    """{NIF: ficha} del directorio comun (vacio si no hay)."""
    datos = _leer_crudo()
    if not datos:
        return {}
    salida = {}
    for clave, ficha in datos["clientes"].items():
        if isinstance(ficha, dict):
            salida[_normaliza(ficha.get("nif") or clave)] = ficha
    return salida


def es_cliente(nif) -> bool:
    nif = _normaliza(nif)
    return bool(nif) and nif in clientes()


def nombre_de(nif) -> str:
    """Nombre del cliente en el directorio. Vacio si no esta o si hay dos
    nombres en conflicto sin resolver (entonces no se elige ninguno)."""
    ficha = clientes().get(_normaliza(nif))
    if not ficha:
        return ""
    if (ficha.get("conflictos") or {}).get("nombre"):
        return ""
    nombre = ficha.get("nombre")
    return nombre.strip() if isinstance(nombre, str) else ""


def nombres() -> list:
    return sorted({n for n in (nombre_de(nif) for nif in clientes()) if n})


def registrar_cliente(nif, nombre: str) -> bool:
    """Apunta en el directorio un cliente confirmado por una persona.

    Igual que en los demas programas: un campo nuevo se añade; uno que ya
    tiene OTRO valor no se pisa, los dos quedan como conflicto para que se
    resuelva donde corresponda. Devuelve True si se ha escrito algo.
    """
    nif = _normaliza(nif)
    nombre = str(nombre or "").strip()
    if not nif or not nombre:
        return False
    ruta = ruta_directorio()
    if os.path.exists(ruta):
        datos = _leer_crudo()
        if datos is None:
            return False          # formato desconocido: no se toca
        datos = json.loads(json.dumps(datos))
    else:
        datos = {"schema_version": 1, "clientes": {}}
    ahora = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    clave = next((k for k, f in datos["clientes"].items()
                  if _normaliza((f or {}).get("nif") or k) == nif), nif)
    ficha = datos["clientes"].setdefault(clave, {"nif": nif})
    ficha.setdefault("nif", nif)
    metadatos = ficha.setdefault("metadatos", {})
    actual = ficha.get("nombre")
    if actual == nombre:
        return False
    if isinstance(actual, str) and actual.strip():
        conflictos = ficha.setdefault("conflictos", {}).setdefault("nombre", [])
        meta = ficha.setdefault("conflictos_metadatos", {}).setdefault("nombre", {})
        cambiado = False
        for valor, origen in ((actual, (metadatos.get("nombre") or {})),
                              (nombre, {"origen": ORIGEN, "fecha": ahora})):
            if valor not in conflictos:
                conflictos.append(valor)
                meta[valor] = {"origen": origen.get("origen", ""),
                               "fecha": origen.get("fecha", "")}
                cambiado = True
        if not cambiado:
            return False
    else:
        ficha["nombre"] = nombre
        metadatos["nombre"] = {"origen": ORIGEN, "fecha": ahora}
    datos["actualizado_en"] = ahora
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        fd, temporal = tempfile.mkstemp(dir=os.path.dirname(ruta),
                                        suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(datos, fh, indent=2, ensure_ascii=False)
        os.replace(temporal, ruta)
    except OSError:
        return False
    _cache.update(mtime=None, ruta=None, datos=None)
    return True
