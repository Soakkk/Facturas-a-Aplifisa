"""Archivo local de originales, lecturas y revisiones; nunca envía datos.

Los snapshots se deduplican por contenido. Cada escritura y el ZIP se
publican con reemplazo atómico; los errores de disco llegan a la interfaz.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from threading import RLock
from zipfile import ZIP_DEFLATED, ZipFile

import facturas_excel

_CERROJO = RLock()
_SCHEMA_VERSION = 1
_EXT_ORIGINALES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".bin"}


def carpeta() -> Path:
    ruta = Path(os.environ.get("APPDATA") or Path.home()) / "FacturasAplifisa" / "muestras_revision"
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def _hash(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def _json(valor) -> bytes:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False).encode("utf-8")


def _atomico(destino: Path, contenido: bytes) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(dir=destino.parent, prefix=".tmp-", delete=False) as fichero:
            temporal = Path(fichero.name)
            fichero.write(contenido)
            fichero.flush()
            os.fsync(fichero.fileno())
        os.replace(temporal, destino)
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


def _snapshot(tipo: str, contenido: dict) -> None:
    contenido = {**contenido, "schema_version": _SCHEMA_VERSION,
                 "version_app": facturas_excel.__version__}
    identificador = _hash(_json(contenido))
    destino = carpeta() / tipo / (identificador + ".json")
    if not destino.exists():
        _atomico(destino, _json({**contenido, "guardado_utc": datetime.now(timezone.utc).isoformat()}))


def _alias(ruta: str) -> Path:
    normalizada = os.path.normcase(os.path.abspath(ruta))
    return carpeta() / "rutas_locales" / (_hash(normalizada.encode("utf-8")) + ".json")


def guardar_original(ruta: str) -> str:
    """Copia inmutable deduplicada y devuelve su SHA256; recuerda la ruta."""
    with _CERROJO:
        origen = Path(ruta)
        contenido = origen.read_bytes()
        identificador = _hash(contenido)
        sufijo = origen.suffix.lower()
        if sufijo not in _EXT_ORIGINALES:
            sufijo = ".bin"
        existentes = list((carpeta() / "originales").glob(identificador + ".*"))
        destino = existentes[0] if existentes else carpeta() / "originales" / (identificador + sufijo)
        if not destino.exists():
            _atomico(destino, contenido)
        _snapshot("documentos", {"original_id": identificador, "nombre": origen.name,
                                  "archivo": destino.relative_to(carpeta()).as_posix()})
        _atomico(_alias(ruta), _json({"original_id": identificador}))
        return identificador


def _original(ruta: str) -> str | None:
    if not ruta:
        return None
    alias = _alias(ruta)
    if alias.exists():
        return json.loads(alias.read_text(encoding="utf-8"))["original_id"]
    if Path(ruta).is_file():
        return guardar_original(ruta)
    return None


def guardar_lecturas(registros: list, originales: dict[str, str] | None = None) -> None:
    """Guarda cada página y cada lectura distinta, sin sustituir tandas previas.

    ``originales`` puede fijar origen→SHA256 capturado antes de leer con IA;
    permite conservar la asociación aunque se mueva o reutilice la ruta.
    Llame a guardar_original antes de IA si vuelve a usar una misma ruta
    para otro documento; así su alias apunta al nuevo contenido.
    Si no se dispone del documento completo, se conserva la imagen de página.
    """
    with _CERROJO:
        resueltos = {}
        for imagen, origen, pagina, datos in registros:
            if origen not in resueltos:
                resueltos[origen] = (originales or {}).get(origen) or _original(origen)
                if resueltos[origen]:
                    _atomico(_alias(origen), _json({"original_id": resueltos[origen]}))
            original_id = resueltos[origen]
            imagen_id = None
            if imagen:
                imagen_id = _hash(imagen)
                sufijo = ".png" if imagen.startswith(b"\x89PNG") else ".jpg" if imagen.startswith(b"\xff\xd8") else ".bin"
                destino = carpeta() / "imagenes" / (imagen_id + sufijo)
                if not destino.exists():
                    _atomico(destino, imagen)
            _snapshot("lecturas", {"original_id": original_id, "origen": origen,
                                    "pagina": pagina, "imagen_id": imagen_id, "datos": datos})


def _factura(valor) -> dict:
    return asdict(valor) if is_dataclass(valor) else dict(valor)


def guardar_revision(filas: list[dict]) -> None:
    """Conserva versiones sin duplicar imágenes.

    El ID capturado en fila/factura/fuentes prevalece sobre el alias de ruta,
    que puede apuntar a otro documento si se reutilizó el nombre del archivo.
    """
    if not filas:
        return
    with _CERROJO:
        salida = []
        for fila in filas:
            factura = _factura(fila["factura"])
            fuentes = [_factura(f) for f in fila.get("fuentes", [])]
            salida.append({"factura": factura,
                           "original_id": (fila.get("original_id") or factura.get("original_id")
                                           or _original(factura.get("origen_imagen") or "")),
                           "tipo": fila.get("tipo"), "aviso": fila.get("aviso"),
                           "mensajes": fila.get("mensajes", []), "bloque": fila.get("bloque"),
                           "fuentes": fuentes,
                           "originales_fuentes": [f.get("original_id")
                                                  or _original(f.get("origen_imagen") or "")
                                                  for f in fuentes]})
        _snapshot("revisiones", {"filas": salida})


def exportar_zip(destino: str) -> str:
    """Exporta únicamente el archivo de muestras, sin ajustes ni claves API."""
    with _CERROJO:
        salida = Path(destino)
        salida.parent.mkdir(parents=True, exist_ok=True)
        temporal = None
        try:
            with tempfile.NamedTemporaryFile(dir=salida.parent, prefix=".tmp-", delete=False) as fichero:
                temporal = Path(fichero.name)
            with ZipFile(temporal, "w", ZIP_DEFLATED) as archivo:
                archivo.writestr("LEEME.txt", "Muestras locales de FacturasAplifisa.\nOriginales: documentos completos. Imagenes: paginas leidas.\nLecturas: respuestas crudas. Revisiones: versiones corregidas.\nLos identificadores son SHA256; documentos relaciona nombres con originales.\n")
                raiz = carpeta()
                extensiones = {"originales": _EXT_ORIGINALES,
                               "imagenes": {".png", ".jpg", ".bin"},
                               "documentos": {".json"}, "lecturas": {".json"},
                               "revisiones": {".json"}}
                for tipo, permitidas in extensiones.items():
                    for ruta in sorted((raiz / tipo).glob("*")):
                        if (ruta.is_file() and not ruta.is_symlink()
                                and ruta.suffix.lower() in permitidas
                                and not ruta.name.startswith(".")
                                and ruta.resolve() != salida.resolve()):
                            archivo.write(ruta, ruta.relative_to(raiz).as_posix())
            os.replace(temporal, salida)
        finally:
            if temporal is not None:
                temporal.unlink(missing_ok=True)
        return str(salida)
