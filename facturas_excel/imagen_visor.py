"""La hoja original, sacada justo al tamaño en que se va a ver.

La imagen que se manda a Gemini (150 ppp en JPEG) basta para leer, pero al
acercarla en el visor se veía borrosa y con manchas: se ampliaba una foto
pequeña. El visor pide aquí la misma hoja, sacada del PDF (o de la imagen)
original al tamaño exacto de la pantalla.

Si el original ya no está, o no es la misma hoja, devuelve None y el visor
sigue con la imagen de lectura, como antes. Aquí no se importa Qt.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .pdf import CERROJO, EXT_IMAGEN, soltar_cache

# Lo más grande que se saca de una vez (unos 48 MB en memoria). Más allá,
# el visor amplía esta imagen, que ya es mucho más fina que la de lectura.
MAX_PIXELES = 16_000_000
# Los recuadros se dibujan sobre la imagen de lectura: el original solo se
# usa si tiene su misma forma (si no, no es la misma hoja o está girada).
TOLERANCIA_PROPORCION = 0.02


class Ocupado(Exception):
    """Otro hilo está sacando hojas del PDF: se vuelve a intentar enseguida."""


@dataclass
class Hoja:
    ancho: int
    alto: int
    muestras: bytes     # RGB, tres bytes por punto
    linea: int          # bytes por fila


def tamano_posible(ancho: int, alto: int) -> tuple:
    """El tamaño que se puede sacar, con la misma forma, sin pasar del tope."""
    ancho, alto = max(1, int(ancho)), max(1, int(alto))
    if ancho * alto <= MAX_PIXELES:
        return ancho, alto
    escala = (MAX_PIXELES / (ancho * alto)) ** 0.5
    return max(1, int(ancho * escala)), max(1, int(alto * escala))


def misma_forma(ancho: float, alto: float, proporcion: Optional[float]) -> bool:
    if not proporcion:
        return True
    if ancho <= 0 or alto <= 0:
        return False
    return abs((ancho / alto) / proporcion - 1) <= TOLERANCIA_PROPORCION


def hoja(ruta: str, pagina: int, ancho: int, alto: int,
         proporcion: Optional[float] = None) -> Optional[Hoja]:
    """La hoja `pagina` (desde 1) de `ruta` a `ancho` × `alto` puntos.

    Lanza `Ocupado` si el PDF lo está usando la lectura en ese momento.
    """
    if not ruta or not os.path.isfile(ruta):
        return None
    extension = os.path.splitext(ruta)[1].lower()
    ancho, alto = tamano_posible(ancho, alto)
    try:
        if extension == ".pdf":
            return _de_pdf(ruta, pagina, ancho, alto, proporcion)
        if extension in EXT_IMAGEN:
            return _de_imagen(ruta, ancho, alto, proporcion)
    except Ocupado:
        raise
    except Exception:
        # Un original dañado o bloqueado nunca impide ver la factura.
        return None
    return None


def _de_pdf(ruta, pagina, ancho, alto, proporcion) -> Optional[Hoja]:
    import fitz

    if not CERROJO.acquire(blocking=False):
        raise Ocupado()
    try:
        with fitz.open(ruta) as documento:
            total = len(documento)
            numero = int(pagina or 0)
            if numero < 1 and total == 1:
                numero = 1           # sesiones antiguas sin página apuntada
            if not 1 <= numero <= total:
                return None
            hoja_pdf = documento[numero - 1]
            marco = hoja_pdf.rect    # ya con el giro de la página
            if not misma_forma(marco.width, marco.height, proporcion):
                return None
            matriz = fitz.Matrix(ancho / marco.width, alto / marco.height)
            pix = hoja_pdf.get_pixmap(matrix=matriz, alpha=False,
                                      colorspace=fitz.csRGB)
            sacada = Hoja(pix.width, pix.height, bytes(pix.samples), pix.stride)
            del pix
        # Lo que el visor dibuja tampoco se queda en la caché de MuPDF (cada
        # zoom de una hoja a 300 ppp dejaba allí sus 26 MB).
        soltar_cache()
        return sacada
    finally:
        CERROJO.release()


def _de_imagen(ruta, ancho, alto, proporcion) -> Optional[Hoja]:
    from PIL import Image

    with Image.open(ruta) as imagen:
        # Igual que la imagen de lectura (pdf._comprimir_pil): sin girarla.
        if not misma_forma(imagen.width, imagen.height, proporcion):
            return None
        imagen.draft("RGB", (ancho, alto))   # JPEG grande: decodifica menos
        rgb = imagen.convert("RGB")
    if rgb.size != (ancho, alto):
        rgb = rgb.resize((ancho, alto), Image.LANCZOS)
    return Hoja(ancho, alto, rgb.tobytes(), ancho * 3)
