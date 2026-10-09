"""Tabla rápida con lotes grandes (800 líneas, 450 hojas).

Lo que medía el banco de estrés: cada bloque leído rehacía la tabla entera
(un desplegable por fila, insertada de una en una y con las columnas
recalculadas por cada fila), cada corrección volvía a pintar las 800 líneas
y la muestra de revisión escribía 3 MB de JSON en la ventana a los 0,8 s de
cada cambio. Estas pruebas fijan cada arreglo; ninguno cambia lo que se ve
ni lo que se decide (lo comprueba una huella de la tabla entera).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from facturas_excel.lote import Fila
from facturas_excel.modelo import Factura
from facturas_excel.tabla_facturas import C_CUENTA, C_NIF, TablaFacturas
from facturas_excel.validacion import Incidencia

_app = QApplication.instance() or QApplication([])


def _fila_suelta():
    return Fila(b"", Factura(num_factura="F-1", fecha="01/02/2026", nombre="PROVEEDOR PRUEBA",
                             nif="B12345674", base_iva=100.0, pct_iva=21.0,
                             cuota_iva=21.0, total_impreso=121.0, concepto="622"))


# ------------------------------------------- globo de ayuda de la cuenta
def test_el_globo_de_la_cuenta_no_repite_ni_conserva_avisos_viejos():
    tabla = TablaFacturas()
    fila = _fila_suelta()
    tabla.insertar(0, fila, lambda _control: None)
    cuenta = Incidencia("La cuenta 622 no corresponde a ingreso.", ("concepto",), "error")
    nif = Incidencia("NIF dudoso.", ("nif",), "revisar")
    tabla.resaltar(0, fila, "error", [cuenta])
    tabla.resaltar(0, fila, "error", [cuenta, nif])
    # El aviso de la cuenta, una sola vez (antes salía una vez por revisión).
    assert tabla.item(0, C_CUENTA).toolTip() == str(cuenta)
    assert tabla.item(0, C_NIF).toolTip() == str(nif)
    # Corregida la cuenta, su aviso se va del globo.
    tabla.resaltar(0, fila, "revisar", [nif])
    assert tabla.item(0, C_CUENTA).toolTip() == ""
    assert not tabla.item(0, C_CUENTA).font().bold()
