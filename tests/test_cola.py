"""La cola de documentos: se leen por turnos, no todos de golpe.

Un taco de 70 hojas de una vez no se veia hasta el final, Google frena las
peticiones seguidas y hasta ahora, mientras se leia un lote, soltar otro PDF
solo daba un "espera a que termine". Ahora cada documento espera su turno.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from facturas_excel import app as app_mod
from facturas_excel.app import VentanaPrincipal

_app = QApplication.instance() or QApplication([])


class WorkerFalso(QObject):
    """Un Worker que no llama a Gemini ni arranca hilo ninguno."""
    progreso = Signal(int, int)
    terminado = Signal(object, str, str, object)
    gasto = Signal(str, float)
    fallo = Signal(str)
    creados = []

    def __init__(self, rutas, api_key):
        super().__init__()
        self.rutas = rutas
        self.fallos = []
        self._corriendo = False
        WorkerFalso.creados.append(self)

    def start(self):
        self._corriendo = True

    def isRunning(self):
        return self._corriendo

    def acabar(self):
        self._corriendo = False


@pytest.fixture
def ventana(tmp_path, monkeypatch):
    WorkerFalso.creados = []
    monkeypatch.setattr(app_mod, "Worker", WorkerFalso)
    monkeypatch.setattr(app_mod, "leer_api_key", lambda: "clave-de-prueba")
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    v = VentanaPrincipal(comprobar_updates=False)
    v._cola = []
    return v


def pdfs(tmp_path, cuantos):
    rutas = []
    for i in range(cuantos):
        ruta = tmp_path / f"taco {i + 1}.jpg"
        ruta.write_bytes(b"no importa: no se llega a leer")
        rutas.append(str(ruta))
    return rutas


def test_varios_documentos_se_leen_de_uno_en_uno(ventana, tmp_path):
    rutas = pdfs(tmp_path, 3)

    ventana.procesar_rutas(rutas)

    assert len(WorkerFalso.creados) == 1          # solo arranca el primero
    assert WorkerFalso.creados[0].rutas == [rutas[0]]
    assert len(ventana._cola) == 2                 # los otros dos, esperando


def test_soltar_mas_mientras_lee_los_pone_en_cola(ventana, tmp_path):
    primeros = pdfs(tmp_path, 1)
    ventana.procesar_rutas(primeros)
    assert WorkerFalso.creados[0].isRunning()

    (tmp_path / "otro.jpg").write_bytes(b"x")
    ventana.procesar_rutas([str(tmp_path / "otro.jpg")])

    # Antes esto era un "espera a que termine el lote actual" y se perdia.
    assert len(WorkerFalso.creados) == 1
    assert len(ventana._cola) == 1
    assert "cola" in ventana.lbl_estado.text().lower()


def test_al_acabar_uno_arranca_el_siguiente(ventana, tmp_path):
    rutas = pdfs(tmp_path, 2)
    ventana.procesar_rutas(rutas)
    WorkerFalso.creados[0].acabar()

    ventana._on_terminado([], "CLIENTE DE EJEMPLO", "B12345674", [])

    assert len(WorkerFalso.creados) == 2
    assert WorkerFalso.creados[1].rutas == [rutas[1]]
    assert ventana._cola == []


def test_un_documento_que_falla_no_para_la_cola(ventana, tmp_path):
    rutas = pdfs(tmp_path, 2)
    ventana.procesar_rutas(rutas)
    WorkerFalso.creados[0].acabar()

    ventana._on_fallo("no se pudo abrir el PDF")

    assert len(WorkerFalso.creados) == 2
    assert WorkerFalso.creados[1].rutas == [rutas[1]]


def test_vaciar_todo_tira_tambien_lo_que_esperaba_turno(ventana, tmp_path,
                                                        monkeypatch):
    ventana.procesar_rutas(pdfs(tmp_path, 3))
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    ventana._bloques = [{"nombre": "b", "procesadas": [], "crudos": [],
                         "cliente": "", "nif": "", "tipo_declarado": ""}]

    ventana._vaciar_todo()

    assert ventana._cola == []
