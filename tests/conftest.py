"""Aislar datos y ventanas: las pruebas no escriben en el perfil del asesor."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest


@pytest.fixture(autouse=True)
def perfil_aislado(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path / 'perfil'))
    from facturas_excel import __version__, notas_version
    notas_version.marcar_vistas(__version__)
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
