"""Convierte PDFs de facturas escaneadas en imagenes JPEG (una por pagina),
para mandarlas a Gemini. Tambien acepta imagenes sueltas (jpg/png).

Se usa JPEG (mas ligero que PNG) para que la subida a Gemini sea rapida.
"""

from __future__ import annotations

import io
import os
from typing import List, Tuple

import fitz  # PyMuPDF
from PIL import Image

EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
MIME = "image/jpeg"
CALIDAD = 80
MAX_LADO = 2000  # px; redimensiona si la imagen es mayor (suficiente para OCR)


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
