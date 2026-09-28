"""Aislar datos y ventanas: las pruebas no escriben en el perfil del asesor."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest


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
            if hasattr(ventana, '_timer_muestras'):
                ventana._timer_muestras.stop()
            ventana.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
