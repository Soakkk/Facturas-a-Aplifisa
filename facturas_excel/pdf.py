"""Convierte PDFs de facturas escaneadas en imagenes JPEG (una por pagina),
para mandarlas a Gemini. Tambien acepta imagenes sueltas (jpg/png).

Se usa JPEG (mas ligero que PNG) para que la subida a Gemini sea rapida.
"""

from __future__ import annotations

import io
import hashlib
import os
import re
import threading
import time
from typing import List, Tuple

import fitz  # PyMuPDF
from PIL import Image

EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
MIME = "image/jpeg"
# Calidad del JPEG que se manda a leer. Con 80 la letra pequeña perdía en
# cada vuelta (el escaneo ya viene en JPEG: NAPS2 lo guarda a 75). Gemini
# cobra por los píxeles, no por los bytes, así que 90 cuesta lo mismo; solo
# pesa casi el doble en la carpeta de ejemplos (unos 300 KB por hoja en vez
# de 160). Las imágenes de antes se siguen encontrando: cada una se guarda
# con su propia huella.
CALIDAD = 90
MAX_LADO = 2000  # px; redimensiona si la imagen es mayor (suficiente para OCR)
PAGINAS_POR_BLOQUE = 25
# Las partes de la cola más nuevas que esto no se tocan al arrancar: pueden
# ser de otra copia del programa abierta que aún las está leyendo.
HORAS_PARTES_RECIENTES = 6

# PyMuPDF no admite dos llamadas a la vez desde hilos distintos. La lectura
# rasteriza en segundo plano mientras el visor dibuja la hoja en pantalla:
# cada hoja se saca con este cerrojo, y el visor no espera (si está cogido,
# enseña la imagen de lectura y lo vuelve a intentar al momento).
CERROJO = threading.Lock()

# La hoja de un escaneo es una sola foto JPEG que ocupa la página entera. En
# vez de que MuPDF la dibuje, se saca la foto del PDF y se reduce con PIL al
# tamaño de lectura (los mismos píxeles que daría MuPDF: lo mismo en Gemini).
# Dos razones: MuPDF no suelta el bloqueo de Python mientras dibuja (la
# ventana se quedaba parada hasta 150 ms por hoja) y PIL sí; y MuPDF reduce
# emborronando, PIL lo hace con LANCZOS. Cualquier otra hoja (con texto o
# trazos, varias fotos, recortes, máscaras, CMYK, 1 bit…) sigue por MuPDF.
#
# Lo que la foto puede quedarse corta de la hoja (en puntos) y aun así
# tomarse por la hoja entera: un escáner la pone justa, con décimas de error.
HOLGURA_PT = 1.0
# libjpeg sabe reducir al decodificar (a 1/2, 1/4 o 1/8), mucho más deprisa
# que decodificar entera y reducir después. Se le deja quedarse hasta un 1 %
# corto: un A4 a 300 ppp da 2480 puntos y a 150 ppp hacen falta 1241, no 1240.
HOLGURA_BORRADOR = 0.01
# Fotos que se reducen a la vez. Fuera del cerrojo de MuPDF varias hojas
# pueden estar reduciéndose en paralelo, y cada una ocupa decodificada hasta
# 26 MB (A4 a 300 ppp): con diez hilos de lectura serían 260 MB de golpe.
REDUCCIONES_A_LA_VEZ = 2
_REDUCIENDO = threading.BoundedSemaphore(REDUCCIONES_A_LA_VEZ)
# El giro de la hoja (/Rotate, en el sentido de las agujas del reloj) en PIL,
# que gira al revés.
_GIROS = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180,
          270: Image.Transpose.ROTATE_90}
# Espacios de color de la foto que PIL entiende igual que MuPDF.
_COLORES = {"DeviceRGB": "RGB", "DeviceGray": "L",
            "ICCBased(RGB": "RGB", "ICCBased(Gray": "L"}
_NUMERO = re.compile(rb"[+-]?(?:\d+\.?\d*|\.\d+)\Z")
_NOMBRE = re.compile(rb"/[^/\[\]()<>{}%]+\Z")


def soltar_cache() -> None:
    """Vacía la caché de imágenes de MuPDF. Solo con el CERROJO cogido.

    Cada hoja dibujada deja su imagen descomprimida en una caché global de
    MuPDF que llega a unos 256 MB y no se vacía nunca: con un PDF de más de
    30 hojas eran 250 MB de memoria fijos (26 MB por hoja escaneada a 300
    ppp). Aquí no sirve: cada hoja se dibuja una vez y se convierte en JPEG.
    Vaciarla tras cada hoja hasta dibuja algo más deprisa.
    """
    fitz.TOOLS.store_shrink(100)


def vaciar_cache() -> bool:
    """Vacía la caché de MuPDF desde fuera (al vaciar el lote).

    No espera: si la lectura está dibujando una hoja, ella misma la vacía al
    acabarla. Devuelve si se ha podido vaciar ahora.
    """
    if not CERROJO.acquire(blocking=False):
        return False
    try:
        soltar_cache()
    finally:
        CERROJO.release()
    return True


def _comprimir_pil(img: Image.Image) -> bytes:
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if max(img.size) > MAX_LADO:
        escala = MAX_LADO / max(img.size)
        img = img.resize((int(img.width * escala), int(img.height * escala)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=CALIDAD)
    return buf.getvalue()


def tam_lectura(hoja, dpi: int) -> Tuple[int, int]:
    """Ancho y alto en píxeles de la hoja dibujada a `dpi`, ya girada.

    Son los de `get_pixmap(dpi=dpi)` (los mismos redondeos de MuPDF), sin
    dibujarla. Solo con el CERROJO cogido."""
    zoom = dpi / 72
    marco = (hoja.rect * fitz.Matrix(zoom, zoom)).round()
    return marco.width, marco.height


def _solo_una_foto(contenido: bytes, nombre: str) -> bool:
    """Si lo que dibuja la hoja es solo la foto `nombre`, colocada con `cm`.

    Se mira el contenido a mano porque MuPDF no dice si hay recortes (un
    recorte deja ver solo una parte de la foto y MuPDF no lo cuenta en el
    sitio que ocupa). Cualquier otra orden (texto, trazos, recortes, estados
    gráficos…) y la hoja va por MuPDF."""
    if re.search(rb"[\[\]()<>{}%]", contenido):
        return False
    operandos, fotos = [], 0
    for ficha in contenido.split():
        if _NUMERO.match(ficha) or _NOMBRE.match(ficha):
            operandos.append(ficha)
            continue
        if ficha in (b"q", b"Q"):
            valido = not operandos
        elif ficha == b"cm":
            valido = len(operandos) == 6 and all(_NUMERO.match(o) for o in operandos)
        elif ficha == b"Do":
            fotos += 1
            valido = operandos == [b"/" + nombre.encode("latin-1")]
        else:
            valido = False
        if not valido:
            return False
        operandos = []
    return fotos == 1 and not operandos


def _foto_del_escaneo(doc, hoja, dpi: int):
    """Si la hoja es solo la foto JPEG de un escaneo, lo que hace falta para
    reducirla sin MuPDF: (jpeg, modo, ancho y alto de la foto, ancho y alto
    de lectura sin girar, giro). Si no, None. Solo con el CERROJO cogido."""
    if not doc.is_pdf or hoja.first_annot is not None or hoja.first_widget is not None:
        return None
    fotos = hoja.get_images(full=True)
    if len(fotos) != 1:
        return None
    xref, mascara, ancho_foto, alto_foto, bits, _cs, _alt, nombre, filtro, dentro = fotos[0]
    if mascara or dentro or bits != 8 or filtro != "DCTDecode":
        return None
    # Un solo filtro (DCT, el JPEG tal cual), sin parámetros que cambien
    # los colores ni máscaras de ningún tipo.
    if doc.xref_get_key(xref, "Filter") != ("name", "/DCTDecode"):
        return None
    for clave in ("DecodeParms", "Decode", "Mask", "SMask", "ImageMask"):
        if doc.xref_get_key(xref, clave)[0] != "null":
            return None
    if not _solo_una_foto(hoja.read_contents(), nombre):
        return None
    colocadas = hoja.get_image_info()
    if len(colocadas) != 1:
        return None
    colocada = colocadas[0]
    modo = next((m for prefijo, m in _COLORES.items()
                 if str(colocada.get("cs-name", "")).startswith(prefijo)), None)
    if modo is None or (colocada["width"], colocada["height"]) != (ancho_foto, alto_foto):
        return None
    # Derecha: ni girada, ni volteada, ni en espejo dentro de la hoja (eso
    # lo dice su matriz); el giro de la hoja (/Rotate) sí se hace aquí.
    a, b, c, d, _e, _f = colocada["transform"]
    if abs(b) > 1e-3 or abs(c) > 1e-3 or a <= 0 or d <= 0:
        return None
    giro = hoja.rotation % 360
    if giro not in (0, 90, 180, 270):
        return None
    ancho, alto = tam_lectura(hoja, dpi)
    marco = hoja.rect                       # girada; la foto se mide sin girar
    if giro in (90, 270):
        ancho, alto = alto, ancho
        marco = fitz.Rect(0, 0, marco.height, marco.width)
    # Que cubra la hoja entera: si deja un margen, MuPDF lo pinta en blanco.
    sitio = fitz.Rect(colocada["bbox"])
    if max(abs(sitio.x0 - marco.x0), abs(sitio.y0 - marco.y0),
           abs(sitio.x1 - marco.x1), abs(sitio.y1 - marco.y1)) > HOLGURA_PT:
        return None
    if ancho < 1 or alto < 1:
        return None
    return (doc.xref_stream_raw(xref), modo, ancho_foto, alto_foto,
            ancho, alto, giro)


def _reducir_foto(jpeg: bytes, modo: str, ancho_foto: int, alto_foto: int,
                  ancho: int, alto: int, giro: int):
    """La foto del escaneo al tamaño de lectura, sin MuPDF (suelta el
    bloqueo de Python mientras decodifica y reduce). None si no se puede."""
    with Image.open(io.BytesIO(jpeg)) as foto:
        if (foto.format != "JPEG" or foto.mode != modo
                or foto.size != (ancho_foto, alto_foto)):
            return None
        # MuPDF no hace caso de la orientación EXIF de una foto dentro de un
        # PDF; PIL tampoco, pero mejor no fiarse si la trae.
        if foto.getexif().get(0x0112, 1) != 1:
            return None
        if foto.size == (ancho, alto) and not giro:
            # Ya tiene el tamaño de lectura: se manda la foto del escáner tal
            # cual, sin volver a comprimirla (cada vuelta pierde algo). Se
            # decodifica entera antes, por si viene rota (MuPDF la tolera).
            foto.load()
            return jpeg
        foto.draft(modo, (max(1, int(ancho * (1 - HOLGURA_BORRADOR))),
                          max(1, int(alto * (1 - HOLGURA_BORRADOR)))))
        reducida = foto.resize((ancho, alto), Image.LANCZOS)
    if giro:
        reducida = reducida.transpose(_GIROS[giro])
    buf = io.BytesIO()
    reducida.save(buf, format="JPEG", quality=CALIDAD)
    return buf.getvalue()


def _dibujar(hoja, dpi: int) -> bytes:
    """La hoja dibujada por MuPDF. Solo con el CERROJO cogido."""
    pix = hoja.get_pixmap(dpi=dpi)
    try:
        return pix.pil_tobytes(format="JPEG", quality=CALIDAD)
    finally:
        del pix


def hoja_a_jpg(doc, numero: int, dpi: int = 150) -> bytes:
    """La hoja `numero` (desde 0) de un PDF ya abierto, como se manda a leer.

    Lo de MuPDF va con el CERROJO; reducir la foto de un escaneo, fuera (y
    como mucho REDUCCIONES_A_LA_VEZ a la vez). Si algo falla con la foto, la
    hoja se dibuja como siempre."""
    foto = jpg = None
    with CERROJO:
        hoja = doc[numero]
        try:
            try:
                foto = _foto_del_escaneo(doc, hoja, dpi)
            except Exception:
                foto = None
            if foto is None:
                jpg = _dibujar(hoja, dpi)
        finally:
            # La hoja se suelta aquí, con el cerrojo: MuPDF tampoco admite
            # que otro hilo la libere mientras dibuja.
            del hoja
            soltar_cache()
    if foto is not None:
        try:
            with _REDUCIENDO:
                jpg = _reducir_foto(*foto)
        except Exception:
            jpg = None
        if jpg is None:
            with CERROJO:
                hoja = doc[numero]
                try:
                    jpg = _dibujar(hoja, dpi)
                finally:
                    del hoja
                    soltar_cache()
    return jpg


def paginas_pdf_a_jpg(ruta_pdf: str, dpi: int = 150) -> List[bytes]:
    with CERROJO:
        doc = fitz.open(ruta_pdf)
        total = len(doc)
    try:
        return [hoja_a_jpg(doc, numero, dpi) for numero in range(total)]
    finally:
        with CERROJO:
            doc.close()


def pagina_a_jpg(ruta: str, pagina: int = 1, dpi: int = 150) -> bytes:
    """Una sola hoja de un PDF (o la imagen suelta), como se manda a leer."""
    if os.path.splitext(ruta)[1].lower() != ".pdf":
        with Image.open(ruta) as im:
            return _comprimir_pil(im)
    with CERROJO:
        doc = fitz.open(ruta)
    try:
        return hoja_a_jpg(doc, max(1, int(pagina)) - 1, dpi)
    finally:
        with CERROJO:
            doc.close()


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


def limpiar_partes_huerfanas(horas: float = HORAS_PARTES_RECIENTES) -> int:
    """Borra las partes de la cola que se quedaron de otra vez.

    Las partes de un PDF largo se borran al leer cada bloque; si el programa
    se cerraba o se caía a mitad de la cola, se quedaban para siempre (200 MB
    por cada PDF de 200 MB). La cola no pasa de una apertura a otra, así que
    al arrancar ya no sirven. Devuelve cuántos ficheros se han borrado.
    """
    from .rutas import dir_datos

    raiz = os.path.join(dir_datos(), "cola_pdf")
    if not os.path.isdir(raiz):
        return 0
    limite = time.time() - horas * 3600
    borrados = 0
    for carpeta, _subcarpetas, ficheros in os.walk(raiz, topdown=False):
        try:
            # Antes de borrar nada dentro (borrar cambia su fecha).
            antigua = os.path.getmtime(carpeta) < limite
        except OSError:
            antigua = False
        for nombre in ficheros:
            ruta = os.path.join(carpeta, nombre)
            try:
                if os.path.getmtime(ruta) < limite:
                    os.remove(ruta)
                    borrados += 1
            except OSError:
                pass            # en uso o sin permiso: otra vez será
        if carpeta != raiz and antigua:
            # Solo si se ha quedado vacía y no es de ahora mismo (otra copia
            # del programa puede estar a punto de dejar ahí sus partes).
            try:
                os.rmdir(carpeta)
            except OSError:
                pass
    return borrados


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
