"""La imagen que se manda a leer, sacada de la foto del escaneo.

Una hoja escaneada es una sola foto JPEG que ocupa la página. Antes MuPDF la
volvía a dibujar entera (sin soltar el bloqueo de Python: la ventana se
paraba) y la reducía emborronando. Ahora se saca la foto del PDF y se reduce
con PIL. Lo que se manda a Gemini tiene que salir del mismo tamaño y con la
misma orientación que antes (el coste y los recuadros dependen de eso), y
cualquier hoja que no sea solo una foto sigue por MuPDF como siempre.
"""

import io
import threading
import time

import fitz
import pytest
from PIL import Image, ImageDraw

from facturas_excel import pdf

A6 = (297.64, 419.53)         # puntos
A5 = (419.53, 595.28)


def _foto(ancho, alto, modo="RGB", calidad=85, **guardar):
    """Una «factura» que no es simétrica: un bloque negro arriba a la
    izquierda y rayas de texto, para ver si sale girada o volteada."""
    blanco = 255 if modo == "L" else (255, 255, 255) if modo == "RGB" else (0, 0, 0, 0)
    negro = 0 if modo == "L" else (0, 0, 0) if modo == "RGB" else (0, 0, 0, 255)
    imagen = Image.new(modo, (ancho, alto), blanco)
    dibujo = ImageDraw.Draw(imagen)
    dibujo.rectangle((0, 0, ancho * 2 // 5, alto // 5), fill=negro)
    for fila in range(alto // 3, alto - 20, max(6, alto // 40)):
        dibujo.line((ancho // 10, fila, ancho * 9 // 10, fila), fill=negro, width=2)
    buf = io.BytesIO()
    imagen.save(buf, format="JPEG", quality=calidad, **guardar)
    return buf.getvalue()


def _escaneo(ruta, hoja=A6, ppp=200, modo="RGB", giro=0, paginas=1, **foto):
    """Un PDF como el del escáner: cada hoja, una foto que la ocupa entera
    (la hoja mide lo que la foto a esos ppp, como la hace NAPS2)."""
    ancho, alto = round(hoja[0] / 72 * ppp), round(hoja[1] / 72 * ppp)
    documento = fitz.open()
    for _ in range(paginas):
        pagina = documento.new_page(width=ancho * 72 / ppp, height=alto * 72 / ppp)
        pagina.insert_image(pagina.rect, stream=_foto(ancho, alto, modo, **foto),
                            keep_proportion=False)
        if giro:
            pagina.set_rotation(giro)
    documento.save(str(ruta))
    documento.close()
    return str(ruta)


def _como_antes(ruta, numero=0, dpi=150):
    """Lo que salía antes: la hoja dibujada por MuPDF."""
    with fitz.open(ruta) as documento:
        return documento[numero].get_pixmap(dpi=dpi).pil_tobytes(format="JPEG", quality=80)


def _gris(jpg, tam=None):
    imagen = Image.open(io.BytesIO(jpg)).convert("L")
    return imagen.resize(tam or (60, 84), Image.BILINEAR)


def _diferencia(a, b):
    """Diferencia media (0-255) entre dos imágenes de lectura, en pequeño."""
    tam = Image.open(io.BytesIO(a)).size
    tam = (60, 84) if tam[0] < tam[1] else (84, 60)
    pa, pb = _gris(a, tam).tobytes(), _gris(b, tam).tobytes()
    return sum(abs(x - y) for x, y in zip(pa, pb)) / len(pa)


@pytest.fixture
def sin_mupdf(monkeypatch):
    """Cuenta las hojas que dibuja MuPDF."""
    dibujadas = []
    original = fitz.Page.get_pixmap

    def contar(self, *a, **k):
        dibujadas.append(self.number)
        return original(self, *a, **k)
    monkeypatch.setattr(fitz.Page, "get_pixmap", contar)
    return dibujadas


# ------------------------------------------------ la foto, sin MuPDF
@pytest.mark.parametrize("modo,ppp,hoja", [
    ("RGB", 200, A6),          # «hpscan»: color a 200 ppp
    ("L", 200, A6),            # «naps2_gris»: grises a 200 ppp, JPEG 75
    ("RGB", 300, A5),          # «hpscan300»: libjpeg la reduce a la mitad
    ("RGB", 100, A6),          # «grande»: la foto tiene menos puntos que la lectura
])
def test_la_hoja_escaneada_sale_igual_que_antes_sin_dibujarla(
        tmp_path, sin_mupdf, modo, ppp, hoja):
    ruta = _escaneo(tmp_path / "escaneo.pdf", hoja=hoja, ppp=ppp, modo=modo,
                    calidad=75 if modo == "L" else 85)
    antes = _como_antes(ruta)
    sin_mupdf.clear()
    jpg = pdf.pagina_a_jpg(ruta, 1, 150)
    assert sin_mupdf == []                                  # sin MuPDF
    nueva, vieja = Image.open(io.BytesIO(jpg)), Image.open(io.BytesIO(antes))
    assert nueva.format == "JPEG" and nueva.size == vieja.size
    assert nueva.mode == modo            # la de grises se queda en grises
    assert _diferencia(jpg, antes) < 6


@pytest.mark.parametrize("giro", [90, 180, 270])
def test_la_hoja_girada_sale_girada_igual_que_antes(tmp_path, sin_mupdf, giro):
    ruta = _escaneo(tmp_path / "girada.pdf", giro=giro)
    antes = _como_antes(ruta)
    sin_mupdf.clear()
    jpg = pdf.pagina_a_jpg(ruta, 1, 150)
    assert sin_mupdf == []
    assert Image.open(io.BytesIO(jpg)).size == Image.open(io.BytesIO(antes)).size
    assert _diferencia(jpg, antes) < 6
    # Y no por casualidad: la hoja sin girar (o girada al revés) no se parece.
    otra = pdf.pagina_a_jpg(_escaneo(tmp_path / "derecha.pdf",
                                     giro=(giro + 180) % 360), 1, 150)
    assert _diferencia(otra, antes) > 20


def test_el_tamano_de_lectura_es_el_de_mupdf(tmp_path):
    """Los mismos redondeos que get_pixmap, también en hojas raras y giradas."""
    documento = fitz.open()
    for ancho, alto, giro in [(595.2756, 841.8898, 0), (612, 792, 90),
                              (300.3, 433.71, 270), (841.89, 595.28, 180),
                              (100.01, 1000.49, 90)]:
        hoja = documento.new_page(width=ancho, height=alto)
        hoja.set_rotation(giro)
        for dpi in (96, 150, 200, 300):
            pix = hoja.get_pixmap(dpi=dpi)
            assert pdf.tam_lectura(hoja, dpi) == (pix.width, pix.height)


def test_si_ya_tiene_el_tamano_de_lectura_se_manda_la_foto_tal_cual(tmp_path):
    """Escaneada a los mismos ppp que se lee: ni se reduce ni se recomprime."""
    ruta = _escaneo(tmp_path / "escaneo.pdf", ppp=200)
    with fitz.open(ruta) as documento:
        foto = documento.xref_stream_raw(documento[0].get_images()[0][0])
    assert pdf.pagina_a_jpg(ruta, 1, 200) == foto
    # Girada sí hay que rehacerla, del mismo tamaño que la dibuja MuPDF.
    girada = _escaneo(tmp_path / "girada.pdf", ppp=200, giro=90)
    jpg = pdf.pagina_a_jpg(girada, 1, 200)
    assert jpg != foto
    assert Image.open(io.BytesIO(jpg)).size == Image.open(
        io.BytesIO(_como_antes(girada, dpi=200))).size


def test_la_foto_se_reduce_fuera_del_cerrojo_y_no_mas_de_dos_a_la_vez(
        tmp_path, monkeypatch):
    """El visor dibuja con el mismo cerrojo: mientras se reduce una foto no
    tiene que esperar. Y como mucho dos fotos decodificadas a la vez."""
    ruta = _escaneo(tmp_path / "taco.pdf", paginas=6)
    original = pdf._reducir_foto
    con_cerrojo, a_la_vez, maximo = [], [0], [0]
    candado = threading.Lock()

    def reducir(*args):
        con_cerrojo.append(pdf.CERROJO.locked())
        with candado:
            a_la_vez[0] += 1
            maximo[0] = max(maximo[0], a_la_vez[0])
        time.sleep(0.05)
        try:
            return original(*args)
        finally:
            with candado:
                a_la_vez[0] -= 1
    monkeypatch.setattr(pdf, "_reducir_foto", reducir)
    with pdf.CERROJO:
        documento = fitz.open(ruta)
    try:
        hilos = [threading.Thread(target=pdf.hoja_a_jpg, args=(documento, n, 150))
                 for n in range(6)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(30)
    finally:
        with pdf.CERROJO:
            documento.close()
    assert len(con_cerrojo) == 6 and not any(con_cerrojo)
    assert 1 <= maximo[0] <= pdf.REDUCCIONES_A_LA_VEZ


def test_la_hoja_escaneada_tambien_vacia_la_cache_de_mupdf(tmp_path, monkeypatch):
    ruta = _escaneo(tmp_path / "taco.pdf", paginas=2)
    vaciados = []
    monkeypatch.setattr(fitz.TOOLS, "store_shrink", lambda porcentaje: vaciados.append(
        (porcentaje, pdf.CERROJO.locked())))
    assert len(pdf.paginas_pdf_a_jpg(ruta)) == 2
    assert vaciados == [(100, True)] * 2


# -------------------------------- lo que no es solo una foto: por MuPDF
def _modificar(ruta, cambio):
    documento = fitz.open(ruta)
    cambio(documento, documento[0])
    salida = ruta.replace(".pdf", "_b.pdf")
    documento.save(salida)
    documento.close()
    return salida


def _contenido(texto):
    def cambio(documento, hoja):
        documento.update_stream(hoja.get_contents()[0], texto.encode())
    return cambio


def _foto_mascara(documento, hoja):
    """La misma foto, ahora con una máscara de transparencia."""
    mascara = Image.new("L", (40, 40), 128)
    buf = io.BytesIO()
    mascara.save(buf, format="PNG")
    nueva = fitz.open()
    pagina = nueva.new_page(width=hoja.rect.width, height=hoja.rect.height)
    pagina.insert_image(pagina.rect, stream=_foto(400, 566), mask=buf.getvalue(),
                        keep_proportion=False)
    documento.delete_page(0)
    documento.insert_pdf(nueva)


def _cmyk(documento, hoja):
    nueva = fitz.open()
    pagina = nueva.new_page(width=hoja.rect.width, height=hoja.rect.height)
    pagina.insert_image(pagina.rect, stream=_foto(400, 566, "CMYK"), keep_proportion=False)
    documento.delete_page(0)
    documento.insert_pdf(nueva)


def _rota(documento, hoja):
    """La foto con la mitad de sus datos: MuPDF la dibuja igual (a medias)."""
    xref = hoja.get_images()[0][0]
    datos = documento.xref_stream_raw(xref)
    documento.update_stream(xref, datos[:len(datos) // 2], compress=False)
    documento.xref_set_key(xref, "Filter", "/DCTDecode")


W, H = A6
CASOS_MUPDF = {
    "texto encima": lambda d, h: h.insert_text((20, 40), "FACTURA 1"),
    "trazos encima": lambda d, h: h.draw_rect(fitz.Rect(10, 10, 60, 60)),
    "dos fotos": lambda d, h: h.insert_image(fitz.Rect(0, 0, 50, 50), stream=_foto(80, 80)),
    "nota": lambda d, h: h.add_text_annot((20, 20), "ojo"),
    "recortada": lambda d, h: h.set_cropbox(fitz.Rect(10, 10, 200, 300)),
    "con margen": _contenido(f"q {W - 40} 0 0 {H - 40} 20 20 cm /fzImg0 Do Q"),
    "volteada": _contenido(f"q {W} 0 0 {-H} 0 {H} cm /fzImg0 Do Q"),
    "en espejo": _contenido(f"q {-W} 0 0 {H} {W} 0 cm /fzImg0 Do Q"),
    "girada dentro": _contenido(f"q 0 {H} {-W} 0 {W} 0 cm /fzImg0 Do Q"),
    "con recorte": _contenido(f"q 0 0 100 100 re W n {W} 0 0 {H} 0 0 cm /fzImg0 Do Q"),
    "texto invisible": _contenido(
        f"q {W} 0 0 {H} 0 0 cm /fzImg0 Do Q BT 3 Tr 10 10 Td (x) Tj ET"),
    "con máscara": _foto_mascara,
    "CMYK": _cmyk,
    "foto rota": _rota,
}


@pytest.mark.parametrize("caso", sorted(CASOS_MUPDF))
def test_lo_que_no_es_solo_una_foto_se_dibuja_como_siempre(tmp_path, sin_mupdf, caso):
    ruta = _modificar(_escaneo(tmp_path / "escaneo.pdf"), CASOS_MUPDF[caso])
    antes = _como_antes(ruta)
    sin_mupdf.clear()
    jpg = pdf.pagina_a_jpg(ruta, 1, 150)
    assert sin_mupdf == [0]                          # la dibuja MuPDF
    assert Image.open(io.BytesIO(jpg)).size == Image.open(io.BytesIO(antes)).size


def test_blanco_y_negro_de_un_bit_va_por_mupdf(tmp_path, sin_mupdf):
    """CCITT de 1 bit (el modo B/N del escáner): no es un JPEG."""
    imagen = Image.new("1", (827, 1169), 1)
    ImageDraw.Draw(imagen).rectangle((0, 0, 300, 200), fill=0)
    buf = io.BytesIO()
    imagen.save(buf, format="PNG")
    documento = fitz.open()
    hoja = documento.new_page(width=A6[0], height=A6[1])
    hoja.insert_image(hoja.rect, stream=buf.getvalue(), keep_proportion=False)
    ruta = str(tmp_path / "bn.pdf")
    documento.save(ruta)
    documento.close()
    sin_mupdf.clear()
    assert pdf.pagina_a_jpg(ruta, 1, 150).startswith(b"\xff\xd8")
    assert sin_mupdf == [0]


def test_una_foto_con_orientacion_exif_va_por_mupdf(tmp_path, sin_mupdf):
    exif = Image.Exif()
    exif[0x0112] = 6
    ruta = _escaneo(tmp_path / "exif.pdf", exif=exif.tobytes())
    sin_mupdf.clear()
    pdf.pagina_a_jpg(ruta, 1, 150)
    assert sin_mupdf == [0]


def test_si_reducir_la_foto_falla_se_dibuja_como_siempre(tmp_path, sin_mupdf, monkeypatch):
    def falla(*_a):
        raise OSError("sin memoria")
    monkeypatch.setattr(pdf, "_reducir_foto", falla)
    ruta = _escaneo(tmp_path / "escaneo.pdf")
    sin_mupdf.clear()
    assert pdf.pagina_a_jpg(ruta, 1, 150).startswith(b"\xff\xd8")
    assert sin_mupdf == [0]
