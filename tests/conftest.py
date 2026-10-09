"""Aislar datos y ventanas: las pruebas no escriben en el perfil del asesor."""
import faulthandler
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest

# Una prueba que se cuelga (una ventana que espera respuesta, un reparto de
# tamaños que no se para) no puede tener parado el CI horas: a los cinco
# minutos se escribe en CUELGUE dónde está cada hilo y se corta. Va a un
# fichero porque lo que la prueba escribe en pantalla lo guarda pytest y se
# perdería al cortar (el CI lo enseña si falla).
MINUTOS_POR_PRUEBA = 5
CUELGUE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "cuelgue_pruebas.txt")


@pytest.fixture(autouse=True)
def vigilante_de_cuelgues(request):
    with open(CUELGUE, "w", encoding="utf-8") as fh:
        fh.write(f"Prueba colgada más de {MINUTOS_POR_PRUEBA} minutos: "
                 f"{request.node.nodeid}\n\n")
        fh.flush()
        faulthandler.dump_traceback_later(MINUTOS_POR_PRUEBA * 60, exit=True, file=fh)
        try:
            yield
        finally:
            faulthandler.cancel_dump_traceback_later()
    try:
        os.remove(CUELGUE)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def sin_ventanas_que_esperan(monkeypatch):
    """Una ventana que espera respuesta deja una prueba colgada para siempre:
    nadie la pulsa. Pasó en Windows con «Novedades de la versión», que el
    programa abre a los 500 ms de arrancar: en una máquina lenta saltaba en
    mitad de otra prueba. Si una prueba no ha previsto la ventana
    (sustituyéndola), no se abre y la prueba falla diciendo cuál era."""
    from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox
    abiertas = []

    def sin_prever(nombre, devuelve):
        def ventana(*_a, **_k):
            abiertas.append(nombre)
            return devuelve
        return ventana

    monkeypatch.setattr(QDialog, "exec", lambda self: sin_prever(
        type(self).__name__, 0)())
    for nombre in ("critical", "warning", "information", "question", "about"):
        monkeypatch.setattr(QMessageBox, nombre, staticmethod(
            sin_prever(f"QMessageBox.{nombre}", QMessageBox.No)))
    for nombre in ("getText", "getItem", "getInt", "getDouble", "getMultiLineText"):
        monkeypatch.setattr(QInputDialog, nombre, staticmethod(
            sin_prever(f"QInputDialog.{nombre}", ("", False))))
    for nombre in ("getOpenFileName", "getOpenFileNames", "getSaveFileName"):
        monkeypatch.setattr(QFileDialog, nombre, staticmethod(
            sin_prever(f"QFileDialog.{nombre}", ("", ""))))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(
        sin_prever("QFileDialog.getExistingDirectory", "")))
    yield abiertas
    assert not abiertas, ("Se abrió una ventana que espera respuesta sin "
                          f"preverla en la prueba: {', '.join(abiertas)}")


@pytest.fixture(autouse=True)
def perfil_aislado(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path / 'perfil'))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    # Tampoco el Escritorio real: ahí van los Excel y el archivo documental.
    monkeypatch.setenv('HOME', str(tmp_path / 'casa'))
    monkeypatch.setenv('USERPROFILE', str(tmp_path / 'casa'))
    from facturas_excel import __version__, localizar, notas_version
    notas_version.marcar_vistas(__version__)

    # Ninguna prueba llama de verdad a Gemini para señalar datos.
    def sin_red(*_a, **_k):
        raise RuntimeError("sin red en las pruebas")
    monkeypatch.setattr(localizar, "pedir", sin_red)
    yield
    # Las ventanas de tests que no se mostraron también tienen QTimers.
    # Destruirlas antes de quitar el perfil evita diálogos en el siguiente test.
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    if QApplication.instance():
        for ventana in QApplication.topLevelWidgets():
            # Lo que se archiva en segundo plano tras exportar acaba aquí,
            # con el perfil de la prueba todavía puesto.
            if hasattr(ventana, '_esperar_archivo'):
                ventana._esperar_archivo()
            if hasattr(ventana, '_timer_muestras'):
                ventana._timer_muestras.stop()
            ventana.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    # Y los hilos del archivo cuya ventana ya no está.
    from facturas_excel import hilos
    for hilo in list(hilos.VIVOS):
        hilo.wait()
        hilos.soltar_hilo(hilo)
