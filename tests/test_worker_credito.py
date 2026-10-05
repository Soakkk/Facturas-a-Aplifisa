"""El lote se corta al acabarse el crédito y se cuenta todo lo pagado."""
import pytest
from facturas_excel import hilos
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

    monkeypatch.setattr(hilos, "Extractor", ExtractorFalso)
    monkeypatch.setattr(hilos, "hilos_lectura", lambda: 1)
    monkeypatch.setattr(hilos, "cargar_imagenes", lambda rutas, dpi: [
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
    monkeypatch.setattr(hilos, "Extractor", ExtractorFalso)
    monkeypatch.setattr(hilos, "cargar_imagenes", lambda rutas, dpi: [
        ("a.pdf", 1, b"img"), ("a.pdf", 2, b"img")])
    monkeypatch.setattr(modulo_app.costes, "registrar",
                        lambda m, e, s: registrados.append(m) or 0.001)
    w = modulo_app.Worker(["a.pdf"], "clave")
    w.run()
    assert len(registrados) == 2
    assert w.fallos and w.fallos[0][1] == 1


# ------------------- 1.23: un «vas muy deprisa» no es «sin crédito»
CUOTA_POR_MINUTO = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded "
    "your current quota, please check your plan and billing details.', "
    "'status': 'RESOURCE_EXHAUSTED', 'details': [{'retryDelay': '7s'}]}}")
PREPAGO_AGOTADO = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Your "
    "prepayment credits are depleted. Please go to AI Studio to manage your "
    "project and billing.'}}")


class _Cliente:
    """Un cliente de Gemini que contesta lo que se le diga, en orden."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.models = self
        self.pedidas = 0

    def generate_content(self, **_k):
        self.pedidas += 1
        r = self.respuestas.pop(0) if self.respuestas else "ok"
        if isinstance(r, Exception):
            raise r
        return r


def _extractor(monkeypatch, respuestas):
    from facturas_excel import extraccion
    esperas = []
    monkeypatch.setattr(extraccion.time, "sleep", esperas.append)
    e = extraccion.Extractor("clave", modelos=["gemini-3.8-flash"], modo_doble="no")
    e.client = _Cliente(respuestas)
    return e, esperas


def test_el_429_por_ir_deprisa_espera_y_vuelve_a_pedir(monkeypatch):
    e, esperas = _extractor(monkeypatch, [Exception(CUOTA_POR_MINUTO)] * 2)
    assert e._llamar("gemini-3.8-flash", b"img") == "ok"
    assert e.client.pedidas == 3
    assert len(esperas) == 2 and esperas[0] >= 7     # lo que pide Google


def test_el_prepago_agotado_si_es_sin_credito(monkeypatch):
    e, _ = _extractor(monkeypatch, [Exception(PREPAGO_AGOTADO)])
    with pytest.raises(SinCredito):
        e._llamar("gemini-3.8-flash", b"img")


def test_si_no_basta_con_esperar_las_demas_hojas_no_se_piden(monkeypatch):
    from facturas_excel import extraccion
    e, _ = _extractor(monkeypatch, [Exception(CUOTA_POR_MINUTO)] * 50)
    with pytest.raises(extraccion.DemasiadasPeticiones):
        e._llamar("gemini-3.8-flash", b"img")
    pedidas = e.client.pedidas
    assert pedidas == extraccion.ESPERAS_POR_CUOTA + 1
    with pytest.raises(extraccion.DemasiadasPeticiones):
        e._llamar("gemini-3.8-flash", b"otra")
    assert e.client.pedidas == pedidas                # ni una más


def test_la_cuota_del_dia_no_se_espera(monkeypatch):
    from facturas_excel import extraccion
    diaria = Exception(CUOTA_POR_MINUTO.replace(
        "'details'", "'quotaId': 'GenerateRequestsPerDayPerProjectPerModel', 'details'"))
    e, esperas = _extractor(monkeypatch, [diaria])
    with pytest.raises(extraccion.DemasiadasPeticiones, match="hoy"):
        e._llamar("gemini-3.8-flash", b"img")
    assert not esperas


def test_si_se_acaba_el_credito_se_queda_lo_ya_leido(monkeypatch):
    """Antes se tiraba el bloque entero, con las hojas ya leídas y pagadas."""
    class ExtractorFalso:
        def __init__(self, api_key):
            pass

        def extraer(self, img, origen, pagina):
            if pagina >= 3:
                raise SinCredito("Tu API key no tiene crédito")
            return DatosFactura(crudo={"lineas_iva": [{}], "num_factura": str(pagina)},
                                pagina=pagina, consumos=[("gemini-3.8-flash", 10, 1)])

    monkeypatch.setattr(hilos, "Extractor", ExtractorFalso)
    monkeypatch.setattr(hilos, "hilos_lectura", lambda: 1)
    monkeypatch.setattr(hilos, "cargar_imagenes", lambda rutas, dpi: [
        ("a.pdf", n, b"img") for n in range(1, 6)])
    monkeypatch.setattr(modulo_app.costes, "registrar", lambda m, e, s: 0.001)
    w = modulo_app.Worker(["a.pdf"], "clave")
    terminados, fallos = [], []
    w.terminado.connect(lambda *a: terminados.append(a))
    w.fallo.connect(fallos.append)
    w.run()

    assert not fallos and terminados
    crudos = terminados[0][3]
    assert [d.get("num_factura") for *_, d in crudos[:2]] == ["1", "2"]
    assert all("sin crédito" in d["_error"] for *_, d in crudos[2:])
    assert "crédito" in w.sin_credito
    assert len(w.fallos) == 3
