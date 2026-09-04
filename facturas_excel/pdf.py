"""Convierte PDFs de facturas escaneadas en imagenes JPEG (una por pagina),
para mandarlas a Gemini. Tambien acepta imagenes sueltas (jpg/png).

Se usa JPEG (mas ligero que PNG) para que la subida a Gemini sea rapida.
"""

from __future__ import annotations

import io
import hashlib
import os
import re
from typing import List, Tuple

import fitz  # PyMuPDF
from PIL import Image

EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
MIME = "image/jpeg"
CALIDAD = 80
MAX_LADO = 2000  # px; redimensiona si la imagen es mayor (suficiente para OCR)
PAGINAS_POR_BLOQUE = 25


def _comprimir_pil(img: Image.Image) -> bytes:
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if max(img.size) > MAX_LADO:
        escala = MAX_LADO / max(img.size)
        img = img.resize((int(img.width * escala), int(img.height * escala)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=CALIDAD)
    return buf.getvalue()


def paginas_pdf_a_jpg(ruta_pdf: str, dpi: int = 150) -> List[bytes]:
    imagenes = []
    doc = fitz.open(ruta_pdf)
    try:
        for pagina in doc:
            pix = pagina.get_pixmap(dpi=dpi)
            imagenes.append(pix.pil_tobytes(format="JPEG", quality=CALIDAD))
    finally:
        doc.close()
    return imagenes


def numero_paginas(ruta_pdf: str) -> int:
    """Cuenta páginas sin rasterizar el documento completo."""
    with fitz.open(ruta_pdf) as doc:
        return len(doc)


def _carpeta_interna_cola(ruta_pdf: str) -> str:
    """Carpeta estable para las partes; no ensucia la documentación del cliente."""
    from .rutas import dir_datos

    estado = os.stat(ruta_pdf)
    huella = hashlib.sha1(
        f"{os.path.abspath(ruta_pdf)}|{estado.st_size}|{estado.st_mtime_ns}".encode()
    ).hexdigest()[:12]
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.splitext(
        os.path.basename(ruta_pdf))[0]).strip("._") or "documento"
    return os.path.join(dir_datos(), "cola_pdf", f"{base}_{huella}")


def dividir_pdf(ruta_pdf: str, paginas_por_parte: int = PAGINAS_POR_BLOQUE,
                carpeta_salida: str | None = None) -> List[str]:
    """Divide un PDF largo en partes independientes y devuelve sus rutas.

    Los archivos generados por la aplicación viven en su carpeta de datos: el
    PDF original sigue siendo el único documento que se archiva para el cliente.
    """
    if paginas_por_parte < 1:
        raise ValueError("Las páginas por parte deben ser al menos 1.")
    ruta_pdf = os.path.abspath(ruta_pdf)
    with fitz.open(ruta_pdf) as origen:
        total = len(origen)
        if total <= paginas_por_parte:
            return [ruta_pdf]
        carpeta = carpeta_salida or _carpeta_interna_cola(ruta_pdf)
        os.makedirs(carpeta, exist_ok=True)
        cantidad = (total + paginas_por_parte - 1) // paginas_por_parte
        base = os.path.splitext(os.path.basename(ruta_pdf))[0]
        salidas = []
        for indice, inicio in enumerate(range(0, total, paginas_por_parte), 1):
            fin = min(inicio + paginas_por_parte, total)
            destino = os.path.join(
                carpeta, f"{base}_parte_{indice:02d}_de_{cantidad:02d}.pdf")
            temporal = destino + ".tmp"
            parte = fitz.open()
            try:
                parte.insert_pdf(origen, from_page=inicio, to_page=fin - 1)
                parte.save(temporal, garbage=4, deflate=True)
                os.replace(temporal, destino)
            finally:
                parte.close()
                if os.path.exists(temporal):
                    try:
                        os.remove(temporal)
                    except OSError:
                        pass
            salidas.append(destino)
        return salidas


def cargar_imagenes(rutas: List[str], dpi: int = 150) -> List[Tuple[str, int, bytes]]:
    """A partir de rutas (PDFs y/o imagenes) devuelve (origen, pagina, jpeg_bytes)."""
    salida = []
    for ruta in rutas:
        ext = os.path.splitext(ruta)[1].lower()
        if ext == ".pdf":
            for i, jpg in enumerate(paginas_pdf_a_jpg(ruta, dpi), start=1):
                salida.append((ruta, i, jpg))
        elif ext in EXT_IMAGEN:
            with Image.open(ruta) as im:
                salida.append((ruta, 1, _comprimir_pil(im)))
    return salida
