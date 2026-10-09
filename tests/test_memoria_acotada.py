"""Memoria acotada con PDF de 100-200 MB (200-450 hojas).

Lo que medía el banco de estrés con 450 hojas: la caché de MuPDF no se
vaciaba nunca (unos 250 MB fijos), la imagen de cada hoja vivía en memoria y
en cada guardado de la sesión (80 MB), la huella del original leía el PDF
entero de una vez (+200 MB) y «Vaciar todo» no soltaba nada. Estas pruebas
fijan cada arreglo; ninguno cambia lo que se ve ni lo que se decide.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
from PySide6.QtWidgets import QApplication

from facturas_excel import imagen_visor, pdf

_app = QApplication.instance() or QApplication([])


def _pdf(ruta, paginas=3):
    documento = fitz.open()
    for numero in range(paginas):
        hoja = documento.new_page(width=300, height=420)
        hoja.insert_text((30, 60), f"FACTURA DE PRUEBA {numero + 1}", fontsize=9)
    documento.save(str(ruta))
    documento.close()
    return str(ruta)


def _apuntar_vaciados(monkeypatch):
    """Cada vaciado de la caché de MuPDF, y si se hizo con el cerrojo."""
    vaciados = []
    monkeypatch.setattr(fitz.TOOLS, "store_shrink", lambda porcentaje: vaciados.append(
        (porcentaje, pdf.CERROJO.locked())))
    return vaciados


# ------------------------------------------------- la caché de MuPDF (P1)
def test_cada_hoja_que_se_lee_vacia_la_cache_de_mupdf(tmp_path, monkeypatch):
    ruta = _pdf(tmp_path / "taco.pdf", 3)
    vaciados = _apuntar_vaciados(monkeypatch)
    imagenes = pdf.paginas_pdf_a_jpg(ruta)
    assert len(imagenes) == 3 and all(i.startswith(b"\xff\xd8") for i in imagenes)
    # Una vez por hoja, entera y siempre con el cerrojo: MuPDF no admite dos
    # llamadas a la vez y el visor puede estar dibujando en otro hilo.
    assert vaciados == [(100, True)] * 3


def test_una_hoja_suelta_y_la_del_visor_tampoco_se_quedan_en_la_cache(
        tmp_path, monkeypatch):
    ruta = _pdf(tmp_path / "taco.pdf", 2)
    vaciados = _apuntar_vaciados(monkeypatch)
    assert pdf.pagina_a_jpg(ruta, 2).startswith(b"\xff\xd8")
    hoja = imagen_visor.hoja(ruta, 1, 600, 840)
    assert hoja is not None and hoja.ancho == 600
    assert vaciados == [(100, True), (100, True)]


def test_vaciar_la_cache_desde_fuera_no_espera_a_la_lectura(monkeypatch):
    vaciados = _apuntar_vaciados(monkeypatch)
    with pdf.CERROJO:
        # La lectura está dibujando: no se para la ventana esperándola (ella
        # vacía la caché al acabar su hoja).
        assert pdf.vaciar_cache() is False
    assert vaciados == []
    assert pdf.vaciar_cache() is True
    assert vaciados == [(100, True)]
    assert not pdf.CERROJO.locked()
