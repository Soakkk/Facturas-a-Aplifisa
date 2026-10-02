"""Columnas a la medida de lo que ponen, y anchos que elige el usuario.

Antes la columna «Nombre» se quedaba con todo el sitio que sobraba: con
nombres cortos, media tabla en blanco al lado del nombre y los números de
factura cortados. Ahora cada columna mide lo que su contenido con aire para
leerse, lo que sobra se reparte entre todas, y lo que una persona ensancha
a mano se queda así (por distribución). Los divisores entre la tabla, la
factura y los totales se ven, se arrastran y con doble clic vuelven a como
venían.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QFontMetrics, QMouseEvent
from PySide6.QtWidgets import QApplication

from facturas_excel import ajustes
from facturas_excel.app import VentanaPrincipal
from facturas_excel.lote import Fila
from facturas_excel.modelo import Factura
from facturas_excel.tabla_facturas import (
    AIRE_MAXIMO, ANCHO_MIN_NOMBRE, C_BASE, C_ESTADO, C_NIF, C_NOMBRE, C_NUM,
    C_TOTAL, COLS, HOLGURA, TablaFacturas,
)
from facturas_excel.ventana_comun import Divisor

_app = QApplication.instance() or QApplication([])

NOMBRES = ("PROVEEDOR CORTO, S.L.", "OTRO PROVEEDOR DE PRUEBA, S.A.")


def _procesar(veces=6):
    for _ in range(veces):
        _app.processEvents()


def _tabla(nombres=NOMBRES, ancho=None):
    """Sin `ancho`, el que piden sus columnas y 600 px de sobra (en Windows
    sin el estilo del programa la letra mide mucho más que aquí)."""
    t = TablaFacturas()
    for r, nombre in enumerate(nombres):
        f = Factura(num_factura=f"F-{r}", fecha="09/07/2026", nombre=nombre,
                    nif="B12345674", base_iva=100.0, pct_iva=21.0,
                    cuota_iva=21.0, total_impreso=121.0)
        t.insertar(r, Fila(png=b"", factura=f, tipo="gasto"), lambda _c: None)
    t.medir()
    if ancho is None:
        ancho = 600 + sum(t.ancho_natural(c) for c in range(t.columnCount())
                          if not t.isColumnHidden(c))
    t.resize(ancho, 400)
    t.show()
    _procesar()
    return t


def _texto(t, texto):
    return QFontMetrics(t.font()).horizontalAdvance(texto)


def test_el_nombre_mide_lo_que_su_texto_y_no_se_come_la_tabla():
    t = _tabla()
    largo = max(_texto(t, n) for n in NOMBRES)
    # Se lee entero, con aire…
    assert t.columnWidth(C_NOMBRE) >= largo + HOLGURA
    # …pero no se queda con todo lo que sobra (antes, más de 900 px aquí).
    libres = sum(1 for c in range(t.columnCount()) if not t.isColumnHidden(c))
    assert t.columnWidth(C_NOMBRE) <= largo + HOLGURA + AIRE_MAXIMO + libres
    # El aire se reparte: todas las columnas se llevan lo mismo de más.
    aire = {c: t.columnWidth(c) - t.ancho_natural(c) for c in (C_ESTADO, C_NIF, C_BASE)}
    assert len(set(aire.values())) == 1 and aire[C_BASE] > 0
    t.close()


def test_sin_sitio_se_estrechan_el_nombre_y_el_numero_no_los_importes():
    t = _tabla(ancho=700)
    assert t.columnWidth(C_NOMBRE) == ANCHO_MIN_NOMBRE
    for c in (C_BASE, C_TOTAL):
        assert t.columnWidth(c) == t.ancho_natural(c)
    assert t.horizontalScrollBar().maximum() > 0
    t.close()


def test_filtrar_no_mueve_las_columnas():
    t = _tabla()
    antes = [t.columnWidth(c) for c in range(t.columnCount())]
    t.setRowHidden(1, True)          # el nombre más largo, oculto por un filtro
    t.medir()
    assert [t.columnWidth(c) for c in range(t.columnCount())] == antes
    t.close()


def _arrastrar(t, columna, ancho):
    """Lo que hace el ratón: apretar en el borde, mover y soltar."""
    vista = t.horizontalHeader().viewport()
    punto = QPointF(5, 5)
    for tipo in (QEvent.MouseButtonPress, None, QEvent.MouseButtonRelease):
        if tipo is None:
            t.setColumnWidth(columna, ancho)
            continue
        evento = QMouseEvent(tipo, punto, punto, Qt.LeftButton,
                             Qt.LeftButton if tipo == QEvent.MouseButtonPress
                             else Qt.NoButton, Qt.NoModifier)
        t.eventFilter(vista, evento)


def test_lo_ensanchado_a_mano_se_queda_y_doble_clic_lo_ajusta():
    t = _tabla()
    guardados = []
    t.anchos_a_mano_cambiados.connect(guardados.append)
    _arrastrar(t, C_NUM, 260)
    assert t.columnWidth(C_NUM) == 260
    assert guardados[-1] == {"Nº Factura": 260}
    # Al cambiar el contenido o el tamaño, sigue como lo dejó.
    t.resize(1500, 400)
    t.medir()
    _procesar()
    assert t.columnWidth(C_NUM) == 260
    # Lo que Qt cambia por su cuenta (ocultar, repartir) no cuenta como «a mano».
    t.setColumnHidden(C_NIF, True)
    t.setColumnHidden(C_NIF, False)
    assert t.anchos_a_mano() == {"Nº Factura": 260}
    # Doble clic en el borde: vuelve a lo que pone.
    t.horizontalHeader().sectionHandleDoubleClicked.emit(C_NUM)
    assert guardados[-1] == {}
    assert t.columnWidth(C_NUM) < 260
    t.close()


def test_los_titulos_van_alineados_con_su_contenido():
    t = TablaFacturas()
    assert t.horizontalHeaderItem(C_BASE).textAlignment() & Qt.AlignRight
    assert t.horizontalHeaderItem(C_NOMBRE).textAlignment() & Qt.AlignLeft
    assert t.horizontalHeaderItem(C_ESTADO).textAlignment() & Qt.AlignHCenter


# ------------------------------------------------------------ la ventana

def _ventana():
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    for i, nombre in enumerate(NOMBRES):
        v._anadir_fila(b"", Factura(
            num_factura=f"F-{i}", fecha="09/07/2026", nombre=nombre,
            nif=("B12345674", "A12345674")[i], base_iva=100.0, pct_iva=21.0,
            cuota_iva=21.0, total_impreso=121.0), "gasto", "628", "G17", "")
    v._revalidar_todo()
    v.resize(1600, 900)
    v.show()
    _procesar()
    return v


def test_los_anchos_a_mano_se_recuerdan_por_distribucion():
    v = _ventana()
    v._elegir_distribucion("tabla_arriba")
    _procesar()
    _arrastrar(v.tabla, C_NOMBRE, 333)
    assert ajustes.leer("columnas_tabla_arriba") == {"Nombre": 333}
    v._elegir_distribucion("cuadre")
    _procesar()
    assert v.tabla.anchos_a_mano() == (ajustes.leer("columnas_cuadre") or {})
    v._elegir_distribucion("tabla_arriba")
    _procesar()
    assert v.tabla.columnWidth(C_NOMBRE) == 333
    # Ver → «Ajustar las columnas a lo que ponen» lo olvida.
    v.accion_ajustar_columnas.trigger()
    assert v.tabla.anchos_a_mano() == {}
    assert not ajustes.leer("columnas_tabla_arriba")
    v.close()


def test_los_divisores_se_ven_y_doble_clic_vuelve_a_como_venian():
    v = _ventana()
    v._elegir_distribucion("columnas")
    _procesar()
    divisor = v.split_revision
    assert isinstance(divisor, Divisor)
    asa = divisor.handle(1)
    assert "Arrastre" in asa.toolTip()
    inicial = divisor.sizes()
    minimos = [divisor.widget(i).minimumSizeHint().width()
               for i in range(divisor.count())]
    holgura = sum(inicial) - sum(minimos)
    if holgura < 60:
        pytest.skip("pantalla sin sitio para mover el divisor")
    # Todo lo que se pueda, a los totales.
    divisor.setSizes(minimos[:2] + [minimos[2] + holgura])
    divisor.splitterMoved.emit(0, 1)
    _procesar()
    assert divisor.sizes() != inicial
    # Doble clic en el asa: como venía en la distribución (en proporción).
    from PySide6.QtTest import QTest
    QTest.mouseDClick(asa, Qt.LeftButton)
    _procesar()
    assert all(abs(a - b) <= 3 for a, b in zip(divisor.sizes(), inicial))
    v.close()


def test_volver_al_reparto_deja_tambien_los_totales_a_su_medida():
    v = _ventana()
    v._elegir_distribucion("cuadre")
    _procesar()
    total = sum(v.split_principal.sizes())
    v.split_principal.setSizes([total - 400, 400])
    v.split_principal.splitterMoved.emit(total - 400, 1)
    assert v._alto_totales_a_mano
    v.accion_restablecer.trigger()
    _procesar()
    assert not v._alto_totales_a_mano
    assert v.split_principal.sizes()[1] < 400
    v.close()


def test_los_titulos_de_columnas_conocidos():
    # Se guardan por título: si cambia el orden, no se mezclan.
    t = TablaFacturas()
    t.poner_anchos_a_mano({"Nombre": 300, "Columna que ya no existe": 90,
                           "Total": "mucho"})
    assert t.anchos_a_mano() == {"Nombre": 300}
    assert COLS[C_NOMBRE] == "Nombre"


def test_ocultar_columnas_con_el_raton_apretado_no_cuenta_como_a_mano():
    """Termina una lectura (y salen o se van columnas) mientras se tiene el
    botón apretado en la cabecera: eso no es ensanchar a mano, y una
    columna nunca se queda a 0 px."""
    from facturas_excel.tabla_facturas import C_BASE_IRPF, C_BASE_RE
    t = _tabla()
    t._arrastrando = True
    t.setColumnHidden(C_BASE_IRPF, True)
    t.setColumnHidden(C_BASE_RE, False)
    t._arrastrando = False
    assert t.anchos_a_mano() == {}
    t.setColumnHidden(C_BASE_IRPF, False)
    assert t.columnWidth(C_BASE_IRPF) > 0
    t.close()


def test_al_estrechar_las_columnas_caben_justas_sin_barra():
    """Nombre y nº de factura a un píxel de su mínimo y la tabla un píxel
    corta: quitando medio píxel a cada una, el redondeo lo dejaba en nada y
    salía la barra horizontal."""
    from facturas_excel.tabla_facturas import MINIMO
    t = _tabla()
    t._naturales[C_NOMBRE] = MINIMO[C_NOMBRE] + 1
    t._naturales[C_NUM] = MINIMO[C_NUM] + 1
    visibles = [c for c in range(t.columnCount()) if not t.isColumnHidden(c)]
    naturales = sum(t.ancho_natural(c) for c in visibles)
    extra = t.width() - t.viewport().width()
    t.resize(naturales - 1 + extra, 400)
    _procesar(2)
    t.repartir()
    assert sum(t.columnWidth(c) for c in visibles) <= t.viewport().width()
    assert t.columnWidth(C_NOMBRE) == MINIMO[C_NOMBRE]
    t.close()
