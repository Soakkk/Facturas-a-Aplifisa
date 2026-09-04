"""Que una pagina colgada no deje el lote parado para siempre.

Con 70 hojas paso esto (04/09/2026): el lote se quedo en "69/70" y ahi se
quedaba. Una peticion a Gemini sin tiempo limite bloquea su hilo indefinidamente
y nunca llega el "terminado". Ahora cada pagina tiene su tiempo maximo, se
reintenta una vez y, si no, se marca esa pagina y el lote continua.
"""

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from facturas_excel import extraccion
from facturas_excel.app import VentanaPrincipal

_app = QApplication.instance() or QApplication([])


def test_se_le_pone_tiempo_limite_a_gemini(monkeypatch):
    capturado = {}
    monkeypatch.setattr(extraccion.genai, "Client",
                        lambda **kw: capturado.update(kw))

    extraccion.Extractor("clave-de-prueba")

    # El SDK lo quiere en milisegundos.
    assert capturado["http_options"].timeout == extraccion.TIEMPO_LIMITE * 1000


def test_una_pagina_colgada_se_deja_tras_un_reintento(monkeypatch):
    """Sin esto se probaban 3 modelos x 3 intentos, cada uno sin limite."""
    intentos = []

    def cuelga(**kw):
        intentos.append(kw.get("model"))
        raise TimeoutError("read timed out")

    monkeypatch.setattr(extraccion.genai, "Client", lambda **kw: None)
    extractor = extraccion.Extractor("clave-de-prueba")
    extractor.client = SimpleNamespace(
        models=SimpleNamespace(generate_content=cuelga))

    with pytest.raises(extraccion.TiempoAgotado):
        extractor._generar(b"imagen")

    assert len(intentos) == 2                 # el original y un reintento
    assert intentos[0] == intentos[1]         # no se cambia de modelo por esto


def test_un_503_sigue_reintentando(monkeypatch):
    """El corte por tiempo no puede cargarse el reintento de siempre."""
    intentos = []

    def caido(**kw):
        intentos.append(kw.get("model"))
        raise RuntimeError("503 UNAVAILABLE")

    monkeypatch.setattr(extraccion.time, "sleep", lambda s: None)
    monkeypatch.setattr(extraccion.genai, "Client", lambda **kw: None)
    extractor = extraccion.Extractor("clave-de-prueba")
    extractor.client = SimpleNamespace(
        models=SimpleNamespace(generate_content=caido))

    with pytest.raises(RuntimeError):
        extractor._generar(b"imagen")

    assert len(intentos) == 3 * len(extractor.modelos)


def test_se_dice_que_paginas_no_se_han_leido(monkeypatch):
    v = VentanaPrincipal(comprobar_updates=False)
    v.worker = SimpleNamespace(fallos=[
        (r"C:\facturas\bloque 1.pdf", 17, "Gemini no contestó en 90 segundos"),
    ])
    dicho = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: dicho.append(a[2])))

    v._avisar_paginas_no_leidas()

    assert dicho and "bloque 1.pdf" in dicho[0] and "17" in dicho[0]


def test_si_todo_se_leyo_no_molesta(monkeypatch):
    v = VentanaPrincipal(comprobar_updates=False)
    v.worker = SimpleNamespace(fallos=[])
    dicho = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: dicho.append(a[2])))

    v._avisar_paginas_no_leidas()

    assert not dicho
