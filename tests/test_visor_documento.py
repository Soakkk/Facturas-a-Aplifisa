"""El documento original en el visor: nítido al acercarlo y sin tapar nada."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
import pytest
from PIL import Image
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from facturas_excel import imagen_visor
from facturas_excel.app import VentanaPrincipal
from facturas_excel.modelo import Factura
from facturas_excel.pdf import CERROJO, pagina_a_jpg
from facturas_excel.visor import VisorDocumento

_app = QApplication.instance() or QApplication([])

# Una hoja más pequeña que un A4, como las que deja el escáner al recortar.
ANCHO_PT, ALTO_PT = 300, 420


def _pdf(ruta, paginas=1):
    documento = fitz.open()
    for numero in range(paginas):
        hoja = documento.new_page(width=ANCHO_PT, height=ALTO_PT)
        hoja.insert_text((30, 60), f"FACTURA DE PRUEBA {numero + 1}", fontsize=9)
        hoja.insert_text((30, 380), "TOTAL 121,00", fontsize=7)
    documento.save(str(ruta))
    documento.close()
    return str(ruta)


def _factura(origen, pagina=1):
    return Factura(num_factura="F-1", fecha="10/03/2026", nombre="PROVEEDOR PRUEBA SL",
                   nif="B12345674", concepto="600", base_iva=100.0, pct_iva=21.0,
                   cuota_iva=21.0, total_impreso=121.0, origen_imagen=origen,
                   pagina_origen=pagina)


def _ventana(tmp_path, origen=None, pagina=1):
    """Ventana con una factura cuya imagen de lectura es la de siempre."""
    pdf = _pdf(tmp_path / "taco.pdf", 2)
    png = pagina_a_jpg(pdf, pagina or 1, 150)      # lo que se manda a Gemini
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v.resize(1500, 900)
    v.show()
    v._anadir_fila(png, _factura(pdf if origen is None else origen, pagina),
                   "gasto", "600", "", "")
    v._revalidar_todo()
    v.tabla.selectRow(0)
    v._mostrar_miniatura()
    QApplication.processEvents()
    return v, pdf


# ------------------------------------------------------- la hoja original
def test_se_saca_la_hoja_del_pdf_al_tamano_pedido(tmp_path):
    pdf = _pdf(tmp_path / "taco.pdf", 2)
    hoja = imagen_visor.hoja(pdf, 2, 900, 1260, ANCHO_PT / ALTO_PT)
    assert (hoja.ancho, hoja.alto) == (900, 1260)
    assert len(hoja.muestras) == hoja.linea * hoja.alto
    # Mucho más que la imagen de lectura (150 ppp = 625 puntos de ancho).
    assert hoja.ancho > ANCHO_PT * 150 / 72


def test_sin_original_o_con_otra_hoja_no_se_inventa_nada(tmp_path):
    pdf = _pdf(tmp_path / "taco.pdf")
    assert imagen_visor.hoja(str(tmp_path / "no-esta.pdf"), 1, 500, 700) is None
    assert imagen_visor.hoja(pdf, 7, 500, 700) is None           # no hay página 7
    assert imagen_visor.hoja(pdf, 1, 700, 500, 700 / 500) is None  # otra forma
    assert imagen_visor.hoja("", 1, 500, 700) is None


def test_tambien_vale_una_imagen_suelta(tmp_path):
    ruta = tmp_path / "ticket.jpg"
    Image.new("RGB", (1200, 1600), "white").save(ruta)
    hoja = imagen_visor.hoja(str(ruta), 1, 600, 800, 0.75)
    assert (hoja.ancho, hoja.alto) == (600, 800)


def test_no_pasa_del_tope_de_memoria():
    ancho, alto = imagen_visor.tamano_posible(8000, 11000)
    assert ancho * alto <= imagen_visor.MAX_PIXELES
    assert abs(ancho / alto - 8000 / 11000) < 0.01


def test_si_la_lectura_esta_usando_el_pdf_no_se_espera(tmp_path):
    pdf = _pdf(tmp_path / "taco.pdf")
    with CERROJO:
        with pytest.raises(imagen_visor.Ocupado):
            imagen_visor.hoja(pdf, 1, 500, 700)


# ------------------------------------------------------------------ visor
def test_al_acercar_la_hoja_sale_nitida_del_original(tmp_path):
    v, pdf = _ventana(tmp_path)
    assert v._fuente_visor == (pdf, 1)
    v._zoom_en(1.0, zoom=v._zoom_maximo())
    v._pintar_nitida()            # lo que hace el temporizador al pararse
    tam = v._tamano_hoja()
    pix = v.lbl_img.pixmap()
    escala = pix.devicePixelRatio()
    assert pix.width() == round(tam.width() * escala)
    # La imagen en pantalla es la sacada del PDF a ese tamaño, no la de
    # lectura ampliada.
    assert v._nitida[0] == (pdf, 1, pix.width(), pix.height())
    assert pix.width() > v._pixmap_documento.width()


def test_sin_el_original_se_sigue_viendo_la_imagen_de_lectura(tmp_path):
    v, _pdf_ = _ventana(tmp_path, origen=str(tmp_path / "movido.pdf"))
    assert not v.lbl_img.pixmap().isNull()
    v._zoom_en(2.0)
    v._pintar_nitida()
    assert v._nitida is None
    assert (str(tmp_path / "movido.pdf"), 1) in v._sin_nitida


def test_un_clic_ya_no_abre_una_ventana_que_lo_tape_todo(tmp_path, monkeypatch):
    abiertas = []
    monkeypatch.setattr(QDialog, "exec", lambda dialogo: abiertas.append(dialogo))
    v, _pdf_ = _ventana(tmp_path)
    QTest.mouseClick(v.lbl_img, Qt.LeftButton)
    assert not abiertas
    assert not hasattr(v, "_abrir_vista_previa")
    acciones = [a.text() for a in v.btn_opciones_visor.menu().actions()]
    assert acciones == ["Ver la hoja entera", "Ajustar al ancho"]


def test_el_zoom_deja_quieto_el_punto_senalado(tmp_path):
    v, _pdf_ = _ventana(tmp_path)
    v._zoom_en(1.0, zoom=2.0)
    horizontal = v.visor_scroll.horizontalScrollBar()
    vertical = v.visor_scroll.verticalScrollBar()
    antes = v.lbl_img.rect_imagen()
    vista = v.visor_scroll.viewport().size()
    # La hoja ya no cabe ni a lo ancho ni a lo alto: el punto puede quedarse.
    assert antes.width() > vista.width() and antes.height() > vista.height()
    punto = QPointF(antes.x() + antes.width() * 0.7, antes.y() + antes.height() * 0.8)
    en_vista = (punto.x() - horizontal.value(), punto.y() - vertical.value())
    v.lbl_img.zoom_pedido.emit(1.25, punto)            # Ctrl + rueda
    despues = v.lbl_img.rect_imagen()
    assert v._zoom_visor == pytest.approx(2.5)
    x = despues.x() + despues.width() * 0.7 - horizontal.value()
    y = despues.y() + despues.height() * 0.8 - vertical.value()
    assert abs(x - en_vista[0]) <= 2 and abs(y - en_vista[1]) <= 2


def test_el_zoom_tiene_tope_y_no_baja_de_la_hoja_entera(tmp_path):
    v, _pdf_ = _ventana(tmp_path)
    v._zoom_en(100.0)
    assert v._zoom_visor == pytest.approx(v._zoom_maximo())
    v._zoom_en(0.001)
    assert v._zoom_visor == 1.0
    tam = v._tamano_hoja()
    sitio = v.visor_scroll.maximumViewportSize()
    assert tam.width() <= sitio.width() and tam.height() <= sitio.height()


def test_doble_clic_acerca_y_otro_vuelve_a_la_hoja_entera(tmp_path):
    v, _pdf_ = _ventana(tmp_path)
    centro = v.lbl_img.rect_imagen().center().toPoint()
    QTest.mouseDClick(v.lbl_img, Qt.LeftButton, Qt.NoModifier, centro)
    assert v._zoom_visor >= 2.5
    QTest.mouseDClick(v.lbl_img, Qt.LeftButton, Qt.NoModifier, centro)
    assert v._zoom_visor == 1.0


def test_arrastrando_se_mueve_por_la_hoja(tmp_path):
    v, _pdf_ = _ventana(tmp_path)
    v._zoom_en(1.0, zoom=4.0)
    vertical = v.visor_scroll.verticalScrollBar()
    vertical.setValue(vertical.maximum() // 2)
    antes = vertical.value()
    QTest.mousePress(v.lbl_img, Qt.LeftButton, Qt.NoModifier, QPoint(200, 300))
    QTest.mouseMove(v.lbl_img, QPoint(200, 220))
    QTest.mouseRelease(v.lbl_img, Qt.LeftButton, Qt.NoModifier, QPoint(200, 220))
    assert vertical.value() == antes + 80


def test_los_recuadros_caen_en_su_sitio_en_pantallas_con_escala():
    visor = VisorDocumento()
    visor.resize(400, 600)
    pix = QPixmap(600, 800)
    pix.setDevicePixelRatio(2.0)       # pantalla al 200 %: 300 × 400 en pantalla
    visor.setPixmap(pix)
    caja = visor.rect_imagen()
    assert (caja.width(), caja.height()) == (300, 400)
    assert (caja.x(), caja.y()) == (50, 100)
