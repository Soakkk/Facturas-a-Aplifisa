"""Cancelar la lectura vale también mientras se dibujan las hojas.

Al cerrar el programa la ventana cancela la lectura, pero la lectura solo
existía después de dibujar el bloque entero (de 2 a 5 s): cancelar durante
el dibujo no hacía nada y después se mandaban las 25 hojas a Gemini con la
ventana ya cerrada. Ahora se mira entre hoja y hoja. Datos inventados.
"""

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
from PySide6.QtWidgets import QApplication

from facturas_excel import hilos
from facturas_excel.extraccion import DatosFactura

_app = QApplication.instance() or QApplication([])


def _taco(ruta, paginas):
    documento = fitz.open()
    for numero in range(1, paginas + 1):
        documento.new_page(width=300, height=420).insert_text(
            (30, 60), f"FACTURA DE PRUEBA {numero}", fontsize=9)
    documento.save(str(ruta))
    documento.close()
    return str(ruta)


def _lectura(monkeypatch, ruta, al_dibujar=None):
    pedidas, dibujadas = [], []

    class ExtractorFalso:
        def __init__(self, api_key):
            self.cancelado = threading.Event()

        def extraer(self, img, origen, pagina):
            pedidas.append(pagina)
            return DatosFactura(crudo={"lineas_iva": [{}], "num_factura": f"F-{pagina}"},
                                pagina=pagina, consumos=[("gemini-falso", 1, 1)])
    dibujar = fitz.Page.get_pixmap

    def dibujando(self, *a, **k):
        dibujadas.append(self.number + 1)
        if al_dibujar:
            al_dibujar(self.number + 1)
        return dibujar(self, *a, **k)
    monkeypatch.setattr(fitz.Page, "get_pixmap", dibujando)
    monkeypatch.setattr(hilos, "Extractor", ExtractorFalso)
    monkeypatch.setattr(hilos.costes, "registrar", lambda *a, **k: 0.0)
    worker = hilos.Worker([ruta], "clave")
    entregado = []
    worker.terminado.connect(lambda *datos: entregado.append(("bloque", datos)))
    worker.fallo.connect(lambda mensaje: entregado.append(("fallo", mensaje)))
    return worker, pedidas, dibujadas, entregado


def test_cancelar_mientras_se_dibuja_no_pide_nada_a_gemini(tmp_path, monkeypatch):
    ruta = _taco(tmp_path / "taco.pdf", 10)
    trabajo = {}

    def al_dibujar(pagina):
        if pagina == 3:              # se cierra el programa mientras se dibuja
            trabajo["worker"].cancelar()
    worker, pedidas, dibujadas, entregado = _lectura(monkeypatch, ruta, al_dibujar)
    trabajo["worker"] = worker

    worker.run()

    assert dibujadas == [1, 2, 3]            # no se dibuja ninguna más…
    assert pedidas == []                     # …ni se pide nada a Gemini
    assert entregado == [("fallo", hilos.NO_LEIDA_AL_CERRAR)]


def test_cancelar_antes_de_pedir_deja_las_hojas_sin_pedir(tmp_path, monkeypatch):
    # Cancelada justo al acabar de dibujar: ninguna hoja se pide, y quedan
    # marcadas para que la ventana sepa que el bloque se quedó a medias.
    ruta = _taco(tmp_path / "taco.pdf", 4)
    worker, pedidas, _dibujadas, entregado = _lectura(monkeypatch, ruta)

    def dibujadas_y_cancelada(rutas, dpi, cancelado):
        worker.cancelar()
        return [(ruta, n, b"hoja") for n in range(1, 5)]
    monkeypatch.setattr(hilos, "dibujar_hojas", dibujadas_y_cancelada)

    worker.run()

    assert pedidas == []
    [(tipo, (_procesadas, _nombre, _nif, crudos))] = entregado
    assert tipo == "bloque"
    assert {d["_error"] for *_, d in crudos} == {hilos.NO_LEIDA_AL_CERRAR}


def test_sin_cancelar_cada_hoja_sale_como_antes(tmp_path, monkeypatch):
    from facturas_excel import pdf
    ruta = _taco(tmp_path / "taco.pdf", 3)
    worker, pedidas, _dibujadas, entregado = _lectura(monkeypatch, ruta)

    worker.run()

    assert sorted(pedidas) == [1, 2, 3]
    [(tipo, (_procesadas, _nombre, _nif, crudos))] = entregado
    assert tipo == "bloque"
    # La misma imagen que daba pdf.paginas_pdf_a_jpg (lo que ve Gemini).
    assert [bytes(c[0]) for c in crudos] == pdf.paginas_pdf_a_jpg(ruta, 150)
