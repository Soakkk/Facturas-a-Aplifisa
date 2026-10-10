"""Cancelar la lectura vale también mientras se dibujan las hojas.

Al cerrar el programa la ventana cancela la lectura, pero la lectura solo
existía después de dibujar el bloque entero (de 2 a 5 s): cancelar durante
el dibujo no hacía nada y después se mandaban las 25 hojas a Gemini con la
ventana ya cerrada. Ahora cada hoja se dibuja justo antes de leerla
(pdf.Hojas) y se mira antes de dibujarla y antes de pedirla: lo ya leído se
queda, y nada se pide después de cancelar. Datos inventados.
"""

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
from PySide6.QtWidgets import QApplication

from facturas_excel import hilos
from facturas_excel.extraccion import DatosFactura
from facturas_excel.ventana_lectura import LecturaMixin

_app = QApplication.instance() or QApplication([])


def _taco(ruta, paginas):
    documento = fitz.open()
    for numero in range(1, paginas + 1):
        documento.new_page(width=300, height=420).insert_text(
            (30, 60), f"FACTURA DE PRUEBA {numero}", fontsize=9)
    documento.save(str(ruta))
    documento.close()
    return str(ruta)


def _lectura(monkeypatch, ruta, al_dibujar=None, a_la_vez=1):
    pedidas, dibujadas = [], []

    class ExtractorFalso:
        # No mira si se ha cancelado (el de verdad sí): así se ve que la
        # lectura no se lo pide.
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
    monkeypatch.setattr(hilos, "hilos_lectura", lambda: a_la_vez)
    monkeypatch.setattr(hilos.costes, "registrar", lambda *a, **k: 0.0)
    worker = hilos.Worker([ruta], "clave")
    entregado = []
    worker.terminado.connect(lambda *datos: entregado.append(("bloque", datos)))
    worker.fallo.connect(lambda mensaje: entregado.append(("fallo", mensaje)))
    return worker, pedidas, dibujadas, entregado


def test_cancelar_mientras_se_dibuja_no_pide_nada_mas_a_gemini(tmp_path, monkeypatch):
    ruta = _taco(tmp_path / "taco.pdf", 10)
    trabajo = {}

    def al_dibujar(pagina):
        if pagina == 3:              # se cierra el programa mientras se dibuja
            trabajo["worker"].cancelar()
    worker, pedidas, dibujadas, entregado = _lectura(monkeypatch, ruta, al_dibujar)
    trabajo["worker"] = worker

    worker.run()

    assert dibujadas == [1, 2, 3]            # no se dibuja ninguna más…
    # …ni se pide nada a Gemini después de cancelar: tampoco la hoja que se
    # estaba dibujando. Las de antes ya estaban leídas (cada hoja se lee
    # nada más dibujarla) y se quedan.
    assert pedidas == [1, 2]
    [(tipo, datos)] = entregado
    assert tipo == "bloque"
    crudos = datos[3]
    assert [d.get("num_factura") for *_, d in crudos[:2]] == ["F-1", "F-2"]
    assert {d["_error"] for *_, d in crudos[2:]} == {hilos.NO_LEIDA_AL_CERRAR}
    # La ventana sabe así que el bloque se quedó a medias (al cerrar vuelve
    # a la cola, que se guarda con la sesión).
    assert LecturaMixin._lectura_cortada(datos)


def test_cancelar_antes_de_pedir_deja_las_hojas_sin_pedir(tmp_path, monkeypatch):
    # Cancelada justo al contar las hojas: ninguna se dibuja ni se pide, el
    # PDF se suelta, y quedan marcadas para que la ventana sepa que el bloque
    # se quedó a medias.
    from facturas_excel import pdf
    ruta = _taco(tmp_path / "taco.pdf", 4)
    worker, pedidas, dibujadas, entregado = _lectura(monkeypatch, ruta)
    contadas = []

    class HojasYCancelada(pdf.Hojas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            contadas.append(self)
            worker.cancelar()
    monkeypatch.setattr(hilos, "Hojas", HojasYCancelada)

    worker.run()

    assert pedidas == [] and dibujadas == []
    assert not contadas[0]._abiertos
    [(tipo, (_procesadas, _nombre, _nif, crudos))] = entregado
    assert tipo == "bloque"
    assert {d["_error"] for *_, d in crudos} == {hilos.NO_LEIDA_AL_CERRAR}


def test_sin_cancelar_cada_hoja_sale_como_antes(tmp_path, monkeypatch):
    from facturas_excel import pdf
    ruta = _taco(tmp_path / "taco.pdf", 3)
    worker, pedidas, _dibujadas, entregado = _lectura(monkeypatch, ruta, a_la_vez=10)

    worker.run()

    assert sorted(pedidas) == [1, 2, 3]
    [(tipo, (_procesadas, _nombre, _nif, crudos))] = entregado
    assert tipo == "bloque"
    # La misma imagen que daba pdf.paginas_pdf_a_jpg (lo que ve Gemini).
    assert [bytes(c[0]) for c in crudos] == pdf.paginas_pdf_a_jpg(ruta, 150)
