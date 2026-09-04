import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

import facturas_excel.app as modulo_app
from facturas_excel.app import VentanaPrincipal
from facturas_excel.modelo import Factura

_app = QApplication.instance() or QApplication([])


def _factura(numero):
    return Factura(
        num_factura=numero, fecha="03/09/2026", nombre="PROVEEDOR SL",
        nif="B86561412", concepto="622", base_iva=100.0, pct_iva=21.0,
        cuota_iva=21.0, total_impreso=121.0, confianza_ia="alta",
    )


def test_exporta_consolidado_y_un_excel_por_bloque(tmp_path, monkeypatch):
    ventana = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    ventana._cliente_nombre = "CLIENTE PRUEBA"
    ventana._bloques = [
        {"nombre": "lote_parte_01", "cliente": "CLIENTE PRUEBA", "nif": "X"},
        {"nombre": "lote_parte_02", "cliente": "CLIENTE PRUEBA", "nif": "X"},
    ]
    ventana._anadir_fila(b"", _factura("F-1"), "gasto", "622", "G13", "",
                         "lote_parte_01")
    ventana._anadir_fila(b"", _factura("F-2"), "gasto", "622", "G13", "",
                         "lote_parte_02")
    ventana._revalidar_todo()

    class Orden:
        def __init__(self, parent):
            pass

        def exec(self):
            return QDialog.Accepted

        def recordar(self):
            pass

        def orden(self):
            return modulo_app.ORDEN_PDF

    escritos = []
    monkeypatch.setattr(modulo_app, "DialogoOrden", Orden)
    monkeypatch.setattr(modulo_app.QFileDialog, "getExistingDirectory",
                        lambda *args: str(tmp_path))
    monkeypatch.setattr(modulo_app, "leer_config", lambda ruta: object())
    monkeypatch.setattr(modulo_app, "exportar_excel",
                        lambda facturas, config, ruta: escritos.append(ruta))
    monkeypatch.setattr(modulo_app, "verificar_excel", lambda *args: [])
    monkeypatch.setattr(modulo_app, "totales_del_excel",
                        lambda *args: {"base_iva": 200, "cuota_iva": 42})
    monkeypatch.setattr(modulo_app.QMessageBox, "information", lambda *args: None)

    ventana._exportar_todo()

    nombres = [os.path.basename(ruta) for ruta in escritos]
    assert nombres == [
        "CLIENTE PRUEBA_gastos.xlsx",
        "CLIENTE PRUEBA_gastos_parte_01_de_02.xlsx",
        "CLIENTE PRUEBA_gastos_parte_02_de_02.xlsx",
    ]
