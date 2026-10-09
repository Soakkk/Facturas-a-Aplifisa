"""Lo que encontró la revisión de la 1.26 (memoria, tabla y exportar).

Cada prueba es un fallo que una persona notaría con los arreglos de
rendimiento y que antes no pasaba: un tipo Gasto/Ingreso que cambia en otra
factura, un aviso que desaparece, un taco que se queda en un sitio que ya no
existe… Solo datos inventados.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from facturas_excel.tabla_facturas import C_NOMBRE, C_TIPO

from test_tabla_rapida import CLIENTE, _bloques, _ventana

_app = QApplication.instance() or QApplication([])


# ------------------- la tabla aprovecha sus filas: sus desplegables también
def _tabla_ordenada_con_un_bloque(tmp_path):
    """Una ventana con un bloque leído, ordenada por nombre (como cuando se
    revisa mientras llega el resto), y el bloque que va a llegar."""
    v = _ventana(tmp_path)
    v.resize(1400, 800)
    v.show()
    v.activateWindow()
    _app.processEvents()
    primero, segundo = _bloques(tmp_path, 16, 8)
    v._on_terminado(primero[0], *CLIENTE, primero[1])
    v._ordenar_tabla_por(C_NOMBRE)
    return v, segundo


def _gastos_pasados_a_ingreso(v):
    """Las facturas de gasto que alguien ha puesto como ingreso a mano."""
    return sorted(x.factura.num_factura for x in v.filas
                  if x.factura.tipo_revision == "venta"
                  and not (x.factura.num_factura or "").startswith("V25"))


def test_el_desplegable_abierto_no_cambia_otra_factura_al_llegar_un_bloque(tmp_path):
    """Con el desplegable Gasto/Ingreso abierto llega otro bloque y la tabla
    se rehace (y se desordena). Antes ese desplegable desaparecía; al
    aprovechar la fila, seguía abierto y lo que se eligiera cambiaba la
    factura que ahora ocupa esa fila, sin que nadie la hubiera mirado."""
    v, segundo = _tabla_ordenada_con_un_bloque(tmp_path)
    combo = v.tabla.cellWidget(5, C_TIPO)
    combo.showPopup()
    _app.processEvents()
    assert combo.view().isVisible()

    v._on_terminado(segundo[0], *CLIENTE, segundo[1])
    _app.processEvents()
    if combo.view().isVisible():
        combo.setCurrentIndex(1)            # la persona elige «Ingreso»
        _app.processEvents()

    assert _gastos_pasados_a_ingreso(v) == []


def test_el_desplegable_con_el_foco_no_cambia_otra_factura_al_llegar_un_bloque(tmp_path):
    """Lo mismo con el desplegable solo con el foco (se acaba de usar): una
    flecha cambiaba el tipo de otra factura."""
    v, segundo = _tabla_ordenada_con_un_bloque(tmp_path)
    combo = v.tabla.cellWidget(5, C_TIPO)
    combo.setFocus(Qt.MouseFocusReason)
    _app.processEvents()
    assert QApplication.focusWidget() is combo

    v._on_terminado(segundo[0], *CLIENTE, segundo[1])
    _app.processEvents()
    QTest.keyClick(QApplication.focusWidget() or v, Qt.Key_Down)
    _app.processEvents()

    assert _gastos_pasados_a_ingreso(v) == []
