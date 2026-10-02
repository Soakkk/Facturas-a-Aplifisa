"""Columnas que se ajustan a su contenido y se pueden personalizar (1.19.1).

El usuario lo pidió así: el nombre ocupaba todo el hueco (más de 500 px para
«WÜRTH ESPAÑA, S.A.») mientras el número de factura salía cortado. Cada
columna tiene que medir lo que su texto más largo, con aire para leerlo bien,
y lo que se ajusta a mano arrastrando un borde se respeta y se recuerda.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication, QTableWidgetItem

from facturas_excel import ajustes
from facturas_excel.tabla_facturas import (
    AIRE_CELDA, ANCHO_MIN_NOMBRE, C_NOMBRE, C_NUM, COLUMNAS_IRPF, LIMITES_ANCHO,
    TablaFacturas,
)

_app = QApplication.instance() or QApplication([])

NOMBRES = ["WÜRTH ESPAÑA, S.A.",
           "ESCAYOLAS LÓPEZ OTROS ENTES ATRIBUCIÓN DE RENTAS",
           "PETROSELF, S.L."]
NUMEROS = ["4735945459", "E2001352619800417", "R - 2976"]


def _tabla(ancho=1800):
    t = TablaFacturas()
    # Como en la mesa de revisión cuando el cliente no lleva retenciones.
    for columna in COLUMNAS_IRPF:
        t.setColumnHidden(columna, True)
    t.setRowCount(len(NOMBRES))
    for r, (nombre, numero) in enumerate(zip(NOMBRES, NUMEROS)):
        t.setItem(r, C_NOMBRE, QTableWidgetItem(nombre))
        t.setItem(r, C_NUM, QTableWidgetItem(numero))
    t.resize(ancho, 300)
    t.show()
    _app.processEvents()
    return t


def _visibles(t):
    return [c for c in range(t.columnCount()) if not t.isColumnHidden(c)]


def _medida(t, texto, columna):
    """Lo que debe medir una columna para `texto`: el texto y su aire."""
    minimo, maximo = LIMITES_ANCHO[columna]
    ancho = QFontMetrics(t.font()).horizontalAdvance(texto) + AIRE_CELDA
    return max(minimo, min(maximo, ancho))


def test_cada_columna_mide_su_texto_mas_largo_con_aire():
    t = _tabla()
    assert t.columnWidth(C_NOMBRE) == _medida(t, NOMBRES[1], C_NOMBRE)
    assert t.columnWidth(C_NUM) == _medida(t, NUMEROS[1], C_NUM)
    # El hueco que sobra se queda a la derecha, no dentro del nombre.
    assert sum(t.columnWidth(c) for c in _visibles(t)) < t.viewport().width()


def test_al_cambiar_los_datos_se_vuelve_a_medir():
    t = _tabla()
    t.setItem(1, C_NOMBRE, QTableWidgetItem("PETROSELF, S.L."))
    _app.processEvents()
    assert t.columnWidth(C_NOMBRE) == _medida(t, NOMBRES[0], C_NOMBRE)


def test_sin_sitio_se_estrechan_nombre_y_numero_sin_desplazar_la_tabla():
    t = _tabla()
    natural = sum(t.columnWidth(c) for c in _visibles(t))
    nombre, numero = t.columnWidth(C_NOMBRE), t.columnWidth(C_NUM)
    minimo = (natural - (nombre - ANCHO_MIN_NOMBRE)
              - (numero - LIMITES_ANCHO[C_NUM][0]))
    marco = t.width() - t.viewport().width()
    t.resize((natural + minimo) // 2 + marco, 300)
    _app.processEvents()
    assert sum(t.columnWidth(c) for c in _visibles(t)) == t.viewport().width()
    assert ANCHO_MIN_NOMBRE < t.columnWidth(C_NOMBRE) < nombre
    assert LIMITES_ANCHO[C_NUM][0] < t.columnWidth(C_NUM) < numero
    # Con poquísimo sitio el nombre no baja de su mínimo: la tabla se desplaza.
    t.resize(500, 300)
    _app.processEvents()
    assert t.columnWidth(C_NOMBRE) == ANCHO_MIN_NOMBRE


def test_arrastrar_un_borde_fija_ese_ancho_y_avisa_para_recordarlo():
    t = _tabla()
    avisos = []
    t.anchos_cambiados.connect(avisos.append)
    t.horizontalHeader().resizeSection(C_NOMBRE, 260)   # como al arrastrar
    assert t.anchos_usuario() == {"Nombre": 260}
    assert avisos[-1] == {"Nombre": 260}
    # Ni un nombre más largo ni otro tamaño de ventana lo mueven.
    t.setItem(0, C_NOMBRE, QTableWidgetItem(
        "UN NOMBRE TODAVÍA MUCHO MÁS LARGO QUE CUALQUIERA DE LOS ANTERIORES"))
    t.resize(1900, 300)
    _app.processEvents()
    assert t.columnWidth(C_NOMBRE) == 260


def test_ocultar_y_mostrar_columnas_no_cuenta_como_ajuste_a_mano():
    """Recargo y retenciones se esconden solos cuando no tocan: Qt las deja a
    0 px y eso no puede guardarse (volverían a salir invisibles)."""
    t = _tabla()
    avisos = []
    t.anchos_cambiados.connect(avisos.append)
    for columna in COLUMNAS_IRPF:
        t.setColumnHidden(columna, False)
        t.setColumnHidden(columna, True)
    assert t.anchos_usuario() == {}
    assert avisos == []
    t.setColumnHidden(COLUMNAS_IRPF[0], False)
    _app.processEvents()
    assert t.columnWidth(COLUMNAS_IRPF[0]) >= LIMITES_ANCHO[COLUMNAS_IRPF[0]][0]


def test_doble_clic_en_el_borde_vuelve_a_medir_el_contenido():
    t = _tabla()
    automatico = t.columnWidth(C_NOMBRE)
    t.horizontalHeader().resizeSection(C_NOMBRE, 500)
    t.horizontalHeader().sectionHandleDoubleClicked.emit(C_NOMBRE)
    _app.processEvents()
    assert t.anchos_usuario() == {}
    assert t.columnWidth(C_NOMBRE) == automatico


def test_lo_guardado_se_recupera_y_se_puede_deshacer():
    t = _tabla()
    automatico = t.columnWidth(C_NOMBRE)
    # Lo que no encaje (columna que no existe, valor raro) se ignora.
    t.poner_anchos_usuario({"Nombre": 230, "Nº Factura": "mal",
                            "Inventada": 50, "Total": True})
    _app.processEvents()
    assert t.anchos_usuario() == {"Nombre": 230}
    assert t.columnWidth(C_NOMBRE) == 230
    t.restablecer_anchos()
    assert t.anchos_usuario() == {}
    assert t.columnWidth(C_NOMBRE) == automatico


def test_un_texto_cortado_se_lee_entero_al_pasar_el_raton():
    t = _tabla(ancho=500)   # el nombre está en su mínimo: el largo no cabe
    assert t.texto_recortado(t.model().index(1, C_NOMBRE)) == NOMBRES[1]
    assert t.texto_recortado(t.model().index(2, C_NOMBRE)) == ""


def test_la_ventana_recuerda_los_anchos_fijados_a_mano():
    from facturas_excel.app import VentanaPrincipal
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v.tabla.horizontalHeader().resizeSection(C_NOMBRE, 250)
    assert v._timer_anchos_columnas.isActive()
    v._guardar_anchos_columnas()   # lo que hace el temporizador al terminar
    assert ajustes.leer("anchos_columnas") == {"Nombre": 250}

    otra = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    assert otra.tabla.anchos_usuario() == {"Nombre": 250}
    assert otra.tabla.columnWidth(C_NOMBRE) == 250
    # Ver → «Ajustar las columnas al contenido» (también en la cabecera).
    otra.accion_ajustar_columnas.trigger()
    otra._guardar_anchos_columnas()
    assert ajustes.leer("anchos_columnas") == {}
