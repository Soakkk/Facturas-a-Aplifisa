"""El lote se corta al acabarse el crédito y se cuenta todo lo pagado."""
import threading

from PySide6.QtWidgets import QApplication

import facturas_excel.app as modulo_app
from facturas_excel.extraccion import DatosFactura, ErrorLectura, SinCredito

_app = QApplication.instance() or QApplication([])


def test_sin_credito_no_se_siguen_pidiendo_hojas(monkeypatch):
    pedidas = []
    candado = threading.Lock()

    class ExtractorFalso:
        def __init__(self, api_key):
            pass

        def extraer(self, img, origen, pagina):
            with candado:
                pedidas.append(pagina)
            raise SinCredito("sin saldo")

    monkeypatch.setattr(modulo_app, "Extractor", ExtractorFalso)
    monkeypatch.setattr(modulo_app, "hilos_lectura", lambda: 1)
    monkeypatch.setattr(modulo_app, "cargar_imagenes", lambda rutas, dpi: [
        ("a.pdf", n, b"img") for n in range(1, 21)])
    w = modulo_app.Worker(["a.pdf"], "clave")
    fallos = []
    w.fallo.connect(fallos.append)
    w.run()
    assert fallos and "sin saldo" in fallos[0]
    assert len(pedidas) < 20


def test_lo_pagado_por_una_hoja_fallida_se_cuenta(monkeypatch):
    class ExtractorFalso:
        def __init__(self, api_key):
            pass

        def extraer(self, img, origen, pagina):
            if pagina == 1:
                raise ErrorLectura("json roto", [("gemini-3.7-flash", 1000, 100)])
            return DatosFactura(crudo={"lineas_iva": [{}]}, pagina=pagina,
                                consumos=[("gemini-3.7-flash", 1000, 100)])

    registrados = []
    monkeypatch.setattr(modulo_app, "Extractor", ExtractorFalso)
    monkeypatch.setattr(modulo_app, "cargar_imagenes", lambda rutas, dpi: [
        ("a.pdf", 1, b"img"), ("a.pdf", 2, b"img")])
    monkeypatch.setattr(modulo_app.costes, "registrar",
                        lambda m, e, s: registrados.append(m) or 0.001)
    w = modulo_app.Worker(["a.pdf"], "clave")
    w.run()
    assert len(registrados) == 2
    assert w.fallos and w.fallos[0][1] == 1
