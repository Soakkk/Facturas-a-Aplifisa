"""El contraste fiscal no se queda en un cartel: permite ir al fallo."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from facturas_excel.dialogo_registro import DialogoRegistro
from facturas_excel.modelo import Factura
from facturas_excel.registro import Apunte, Registro, contrastar

_app = QApplication.instance() or QApplication([])


def factura(numero, fecha, base, iva):
    return Factura(
        num_factura=numero, fecha=fecha, nombre="PROVEEDOR DE PRUEBA SL",
        nif="B12345674", base_iva=base, cuota_iva=iva,
        total_impreso=base + iva,
    )


def test_detalla_diferencias_y_permite_volver_a_su_fila():
    facturas = [factura("F-1", "15/01/2026", 100, 21),
                factura("F-2", "20/01/2026", 200, 42)]
    registro = Registro(apuntes=[
        Apunte(numero="1", num_factura_proveedor="F-1", fecha="15/01/2026",
               nif="B12345674", nombre="PROVEEDOR DE PRUEBA SL",
               base=100, cuota=21, neto=121),
        Apunte(numero="3", num_factura_proveedor="F-3", fecha="25/01/2026",
               nif="B12345675", nombre="OTRO PROVEEDOR DE PRUEBA SA",
               base=50, cuota=10.5, neto=60.5),
    ])
    informe = contrastar(facturas, registro)

    dialogo = DialogoRegistro(informe, registro, facturas=facturas)

    assert dialogo.tabla_totales.rowCount() == 7
    assert dialogo.tabla_detalle.rowCount() == 2
    assert dialogo.tabla_detalle.item(0, 0).text() == "No registrada"
    assert dialogo.tabla_detalle.item(1, 0).text() == "Solo en Aplifisa"
    dialogo.tabla_detalle.selectRow(0)
    _app.processEvents()
    assert dialogo.boton_ver.isEnabled()
    dialogo._aceptar_seleccion()
    assert dialogo.fila_seleccionada() == 1
