"""Tope de píxeles al dibujar una hoja para leer.

Una foto de móvil (4032×3024) metida en un PDF a 72 ppp se dibujaba a 150 ppp
como 8400×6300 (más de 500 MB por hoja); una hoja de 100 pulgadas pasaba de
2 GB y una de 200 ni se dibujaba («Overly large image»), y se perdía el bloque
entero. Ahora esas hojas se dibujan enteras con menos ppp, sin pasar de
pdf.MAX_PIXELES; lo normal (un A4 a 300 ppp) sale igual que siempre.
"""

import io

import fitz
import pytest
from PIL import Image

from facturas_excel import pdf

A4 = (595.28, 841.89)          # puntos


def _tam(jpg):
    with Image.open(io.BytesIO(jpg)) as imagen:
        return imagen.size


def _hoja_de_texto(ruta, ancho, alto):
    documento = fitz.open()
    pagina = documento.new_page(width=ancho, height=alto)
    pagina.insert_text((36, 72), "FACTURA 1 - B12345674", fontsize=24)
    documento.save(str(ruta))
    documento.close()
    return str(ruta)


def _foto_a_72_ppp(ruta, ancho=1008, alto=756):
    """Una foto que ocupa la hoja entera, metida a 72 ppp (un punto por
    píxel), como la deja quien convierte la foto del móvil en PDF."""
    imagen = Image.new("RGB", (ancho, alto), (255, 255, 255))
    imagen.paste((0, 0, 0), (0, 0, ancho // 3, alto // 5))
    buf = io.BytesIO()
    imagen.save(buf, format="JPEG", quality=85)
    documento = fitz.open()
    pagina = documento.new_page(width=ancho * 4, height=alto * 4)
    pagina.insert_image(pagina.rect, stream=buf.getvalue(), keep_proportion=False)
    documento.save(str(ruta))
    documento.close()
    return str(ruta)


def _leer(ruta, dpi=150):
    with fitz.open(ruta) as documento:
        return pdf.hoja_a_jpg(documento, 0, dpi)


def test_un_a4_a_300_ppp_sale_igual_que_siempre(tmp_path):
    ruta = _hoja_de_texto(tmp_path / "a4.pdf", *A4)
    with fitz.open(ruta) as documento:
        antes = documento[0].get_pixmap(dpi=300).pil_tobytes(
            format="JPEG", quality=pdf.CALIDAD)
    assert _leer(ruta, 300) == antes
    ancho, alto = _tam(antes)
    assert ancho * alto < pdf.MAX_PIXELES


def test_hoja_de_100_pulgadas_sale_con_el_tope(tmp_path):
    ruta = _hoja_de_texto(tmp_path / "grande.pdf", 100 * 72, 30 * 72)
    ancho, alto = _tam(_leer(ruta))
    assert ancho * alto <= pdf.MAX_PIXELES
    # Entera y con su forma: no se recorta.
    assert ancho / alto == pytest.approx(100 / 30, rel=0.01)
    assert ancho * alto > pdf.MAX_PIXELES * 0.98


def test_hoja_de_200_pulgadas_no_tira_el_bloque(tmp_path):
    ruta = _hoja_de_texto(tmp_path / "enorme.pdf", 200 * 72, 200 * 72)
    ancho, alto = _tam(_leer(ruta))
    assert ancho * alto <= pdf.MAX_PIXELES


def test_foto_de_movil_a_72_ppp_sale_con_el_tope_por_el_camino_rapido(tmp_path):
    ruta = _foto_a_72_ppp(tmp_path / "movil.pdf")
    with fitz.open(ruta) as documento:
        assert pdf._foto_del_escaneo(documento, documento[0], 150) is not None
    ancho, alto = _tam(_leer(ruta))
    assert ancho * alto <= pdf.MAX_PIXELES
    assert ancho / alto == pytest.approx(1008 / 756, rel=0.01)


def test_el_camino_rapido_y_mupdf_dan_el_mismo_tamano_con_el_tope(tmp_path):
    ruta = _foto_a_72_ppp(tmp_path / "movil.pdf")
    with fitz.open(ruta) as documento:
        hoja = documento[0]
        dibujada = pdf._dibujar(hoja, 150)
        assert pdf.tam_lectura(hoja, 150) == _tam(dibujada)
    assert _tam(_leer(ruta)) == _tam(dibujada)
