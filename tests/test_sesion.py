"""El lote solo se reinicia al pulsar Vaciar todo, no al cerrar la app."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QCloseEvent

from facturas_excel import sesion
from facturas_excel.app import C_BASE, C_TIPO, VentanaPrincipal
from facturas_excel.modelo import Factura
from facturas_excel.procesar import FacturaProcesada

_app = QApplication.instance() or QApplication([])


def _procesada(numero="F-1", base=100.0):
    f = Factura(
        num_factura=numero, fecha="16/07/2026", nombre="PROVEEDOR SL",
        nif="B30048276", concepto="600", base_iva=base, pct_iva=21.0,
        cuota_iva=round(base * .21, 2), total_impreso=round(base * 1.21, 2),
    )
    return FacturaProcesada(
        tipo="gasto", facturas=[f], cuenta="600", gxx=None,
        origen=f"{numero}.pdf", pagina=1)


def _anadir_bloque(v, numero="F-1", base=100.0):
    v._rutas_actuales = [f"C:\\tmp\\{numero}.pdf"]
    v._on_terminado(
        [(b"imagen", _procesada(numero, base))],
        "CLIENTE DE PRUEBA", "12345678Z")


def test_se_recuperan_correcciones_y_se_pueden_anadir_mas_bloques(
        tmp_path, monkeypatch):
    ruta = tmp_path / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))

    primera = VentanaPrincipal(
        comprobar_updates=False, restaurar_sesion=False)
    _anadir_bloque(primera)
    primera.tabla.item(0, C_BASE).setText("99,00")
    tipo = primera.tabla.cellWidget(0, C_TIPO)
    tipo.setCurrentIndex(tipo.findData("venta"))
    primera.closeEvent(QCloseEvent())
    assert ruta.exists()

    recuperada = VentanaPrincipal(
        comprobar_updates=False, restaurar_sesion=True)
    assert recuperada.tabla.rowCount() == 1
    assert recuperada.tabla.item(0, C_BASE).text() == "99,00"
    assert recuperada._tipo_fila(0) == "venta"
    assert len(recuperada._bloques) == 1

    _anadir_bloque(recuperada, "F-2", 50.0)
    assert recuperada.tabla.rowCount() == 2
    assert recuperada.tabla.item(0, C_BASE).text() == "99,00"
    assert recuperada._tipo_fila(0) == "venta"


def test_una_fila_eliminada_no_reaparece_al_anadir_otro_bloque(
        tmp_path, monkeypatch):
    ruta = tmp_path / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))
    primera = VentanaPrincipal(
        comprobar_updates=False, restaurar_sesion=False)
    _anadir_bloque(primera)
    primera.tabla.selectRow(0)
    primera._eliminar_seleccion()
    primera._guardar_sesion()

    recuperada = VentanaPrincipal(
        comprobar_updates=False, restaurar_sesion=True)
    assert recuperada.tabla.rowCount() == 0

    _anadir_bloque(recuperada, "F-2", 50.0)
    assert recuperada.tabla.rowCount() == 1
    assert recuperada.filas[0]["factura"].num_factura == "F-2"
    assert len(recuperada._bloques) == 2


def test_vaciar_todo_borra_tambien_la_sesion(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    ruta = tmp_path / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    _anadir_bloque(v)
    v._guardar_sesion()
    assert ruta.exists()

    v._vaciar_todo()

    assert not ruta.exists()
    assert not v._bloques and v.tabla.rowCount() == 0


def test_una_sesion_corrupta_no_impide_abrir(tmp_path, monkeypatch):
    ruta = tmp_path / "sesion.pkl.gz"
    ruta.write_bytes(b"no es una sesion")
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))

    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)

    assert not v._bloques and v.tabla.rowCount() == 0
