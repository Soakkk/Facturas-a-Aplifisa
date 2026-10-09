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


# ---------------- «Vaciar todo» quita los «Deshacer» del lote, no los demás
def _ventana_con_lote(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    v = _ventana(tmp_path)
    for procesadas, crudos in _bloques(tmp_path, 6, 6):
        v._on_terminado(procesadas, *CLIENTE, crudos)
    return v


def test_vaciar_todo_no_quita_el_aviso_de_la_recogida(tmp_path, monkeypatch):
    """«Recoger sueltos» deja un aviso fijo con lo que no se pudo mover y su
    «Deshacer» (devuelve los PDF a su sitio: nada del lote). Vaciar el lote
    lo quitaba, con su texto."""
    from facturas_excel.banda_avisos import AVISO
    v = _ventana_con_lote(tmp_path, monkeypatch)
    texto = "Recogidos 12 archivo(s). No se pudieron mover 2: a.pdf; b.pdf."
    # Lo que deja ArchivoMixin._recoger_sueltos al terminar.
    v._avisar(texto, AVISO, deshacer=v._deshacer_recogida, segundos=0)

    v._vaciar_todo()

    assert not v.filas
    assert v.banda.isVisibleTo(v) and v.banda.lbl.text() == texto
    assert v.banda.btn_deshacer.isVisibleTo(v)


def test_vaciar_todo_no_quita_el_deshacer_de_olvidar_una_exportacion(tmp_path, monkeypatch):
    """Deshacer «Olvidar exportación» vuelve a apuntarlas en el registro: no
    depende del lote, y vaciarlo no lo quita."""
    from facturas_excel import historial
    v = _ventana_con_lote(tmp_path, monkeypatch)
    monkeypatch.setattr(historial, "olvidar", lambda *a, **k: 1)
    v.filas[0]["ya_exportada"] = {"exportada": "01/03/2026 10:00"}
    v.tabla.selectRow(0)
    v._olvidar_exportacion()
    assert v.banda.btn_deshacer.isVisibleTo(v)

    v._vaciar_todo()

    assert v.banda.isVisibleTo(v) and v.banda.btn_deshacer.isVisibleTo(v)
    assert "quitadas del historial" in v.banda.lbl.text()
