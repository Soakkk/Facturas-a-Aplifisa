"""Ver → Distribución de la pantalla: los cinco prototipos del lienzo.

El usuario quería elegirlos en el propio programa para quedarse con el que
mejor le vaya. Todas usan las mismas piezas (facturas, factura y totales);
cambia dónde va cada una y su forma. Lo que no puede pasar al cambiar: que
se pierda lo tecleado en «Su suma», que una casilla quede en la fila de otro
importe, o que una pieza se quede fuera de la ventana.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from facturas_excel import ajustes, distribucion
from facturas_excel.app import VentanaPrincipal
from facturas_excel.modelo import Factura
from facturas_excel.su_suma import PRIMERA_FILA_IMPORTE
from facturas_excel.tabla_facturas import (
    C_CUENTA, C_ESTADO, C_NOMBRE, C_NUM, C_TOTAL,
)

_app = QApplication.instance() or QApplication([])
CLAVES = [d.clave for d in distribucion.DISTRIBUCIONES]


@pytest.fixture
def guardado(monkeypatch):
    """Lo que se guarda en la prueba, aparte; lo demás, lo de verdad de la
    prueba. Antes lo leía todo de aquí y no veía que «Novedades de la
    versión» ya estaban vistas: en Windows, con la máquina lenta, se abrían
    a los 500 ms en mitad de una prueba y la dejaban colgada."""
    datos = {}
    leer = ajustes.leer
    monkeypatch.setattr(ajustes, "guardar",
                        lambda clave, valor: datos.__setitem__(clave, valor))
    monkeypatch.setattr(ajustes, "leer",
                        lambda clave, defecto=None: datos[clave] if clave in datos
                        else leer(clave, defecto))
    return datos


@pytest.fixture
def tema_real():
    """Con el aspecto del programa (letra, estilo y hoja de estilo): las
    medidas mínimas dependen de él y, sin él, los botones de Windows piden
    mucho más que en el programa de verdad. Se deja todo como estaba."""
    from facturas_excel.estilo import aplicar_tema
    antes = (_app.style().name(), QFont(_app.font()), QPalette(_app.palette()),
             _app.styleSheet())
    aplicar_tema(_app)
    yield
    estilo, letra, paleta, hoja = antes
    _app.setStyleSheet(hoja)
    _app.setPalette(paleta)
    _app.setFont(letra)
    _app.setStyle(estilo)


def _factura(**cambios):
    datos = dict(num_factura="F-1", fecha="03/09/2026", nombre="PROVEEDOR SL",
                 nif="B12345674", concepto="622", base_iva=100.0, pct_iva=21.0,
                 cuota_iva=21.0, total_impreso=121.0, confianza_ia="alta")
    datos.update(cambios)
    return Factura(**datos)


def _procesar(veces=4):
    for _ in range(veces):
        _app.processEvents()


def _ventana(ancho=1600, alto=950):
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    for f in (_factura(num_factura="G-1"),
              _factura(num_factura="G-2", base_iva=50.0, pct_iva=10.0,
                       cuota_iva=5.0, total_impreso=55.0),
              _factura(num_factura="G-3", nif="12345678Z", base_iva=150.0,
                       cuota_iva=31.5, base_irpf=150.0, pct_irpf=15.0,
                       cuota_irpf=22.5, total_impreso=159.0)):
        v._anadir_fila(b"", f, "gasto", "622", "", "")
    v._anadir_fila(b"", _factura(num_factura="V-1", base_iva=200.0,
                                 cuota_iva=42.0, total_impreso=242.0),
                   "venta", "700", "", "")
    v._revalidar_todo()
    v.resize(ancho, alto)
    v.show()
    _procesar()
    return v


def test_el_menu_ofrece_las_cinco_y_marca_la_elegida(guardado):
    v = _ventana()
    # Cada una, con su número del lienzo y para qué va mejor.
    assert [a.text().split(" — ")[0] for a in v.acciones_distribucion.values()] == [
        "1 · Tres columnas", "2 · Lectura sobre la hoja", "3 · Tabla arriba",
        "4 · Cuadre con su suma", "5 · Una a una"]
    assert all(" — " in a.text() and a.toolTip()
               for a in v.acciones_distribucion.values())
    # Por defecto, la de la 1.20 (la que eligió el usuario).
    assert v._distribucion.clave == "cuadre"
    assert v.acciones_distribucion["cuadre"].isChecked()
    v.acciones_distribucion["tabla_arriba"].trigger()
    _procesar()
    assert v._distribucion.clave == "tabla_arriba"
    assert v.acciones_distribucion["tabla_arriba"].isChecked()
    assert not v.acciones_distribucion["cuadre"].isChecked()
    assert guardado["distribucion"] == "tabla_arriba"
    # Y la siguiente vez que se abre el programa sale la misma.
    otra = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    assert otra._distribucion.clave == "tabla_arriba"
    assert otra.split_principal.widget(0) is otra.tabla_card
    v.close()
    otra.close()


@pytest.mark.parametrize("clave", CLAVES)
def test_cada_pieza_va_en_su_sitio_y_se_ve(guardado, clave):
    v = _ventana()
    v._elegir_distribucion(clave)
    _procesar()
    d = v._distribucion
    principal = v.split_principal
    if d.colocacion == distribucion.TABLA_ARRIBA:
        assert [principal.widget(i) for i in range(principal.count())] == [
            v.tabla_card, v.split_inferior]
        assert [v.split_inferior.widget(i) for i in range(2)] == [
            v.factura_card, v.totales_card]
    elif d.colocacion == distribucion.COLUMNAS:
        assert [principal.widget(i) for i in range(principal.count())] == [
            v.split_revision]
        assert [v.split_revision.widget(i) for i in range(3)] == [
            v.tabla_card, v.factura_card, v.totales_card]
    else:
        assert [principal.widget(i) for i in range(principal.count())] == [
            v.split_revision, v.totales_card]
        assert [v.split_revision.widget(i) for i in range(2)] == [
            v.tabla_card, v.factura_card]
    for pieza in (v.tabla_card, v.factura_card, v.totales_card, v.tabla,
                  v.visor_scroll, v.tabla_totales, v.tabla_su_suma):
        assert pieza.isVisible(), pieza.objectName()
        # Si cabe en la ventana (la 5, con la factura a lo ancho, pide una
        # pantalla ancha), nada se queda en una tira.
        if v.minimumSizeHint().width() <= v.width():
            assert pieza.width() > 60 and pieza.height() > 40, pieza.objectName()
    # La factura y los totales con su forma.
    assert v.split_factura.orientation() == (
        Qt.Vertical if d.factura_vertical else Qt.Horizontal)
    assert v.tabla_su_suma.vertical == d.totales_en_columna
    v.close()


def test_su_suma_no_se_pierde_al_cambiar_de_distribucion(guardado):
    v = _ventana()
    v.tabla_su_suma.campo("base").setText("300")
    v.tabla_su_suma.campo("total").setText("330")
    for clave in CLAVES + ["cuadre"]:
        v._elegir_distribucion(clave)
        _procesar()
        assert v.tabla_su_suma.campo("base").text() == "300", clave
        assert v.tabla_su_suma.resultado("base") == "✓ cuadra", clave
        assert v.tabla_su_suma.resultado("total") == "+5,00 €", clave
    v.close()


def _celda_totales(v, concepto, ambito):
    t = v.tabla_totales
    fila = next(r for r in range(t.rowCount()) if t.item(r, 0).text() == concepto)
    columna = next(c for c in range(1, t.columnCount())
                   if t.horizontalHeaderItem(c).text() == ambito)
    return t.item(fila, columna)


def test_en_columna_cada_casilla_va_en_la_fila_de_su_importe(guardado):
    v = _ventana()
    v._elegir_distribucion("columnas")
    _procesar()
    t, suma = v.tabla_totales, v.tabla_su_suma
    # Un importe por fila; una columna por ámbito.
    assert t.item(0, 0).text() == "Nº facturas"
    assert _celda_totales(v, "Base imponible", "Gastos\nTodo el lote").text() == "300,00 €"
    assert _celda_totales(v, "Retención", "Gastos\nTodo el lote").text() == "−22,50 €"
    assert _celda_totales(v, "Total", "Ingresos\nTodo el lote").text() == "242,00 €"
    # Mismo alto de cabecera y de filas: cada casilla a la altura de su fila.
    assert t.horizontalHeader().height() == suma.horizontalHeader().height()
    for i, (clave, _titulo, _importe) in enumerate(suma._columnas):
        fila = PRIMERA_FILA_IMPORTE + i
        campo = suma.campo(clave)
        assert suma.cellWidget(fila, 0) is campo
        y_campo = campo.mapTo(v, campo.rect().center()).y()
        y_fila = t.viewport().mapTo(v, t.viewport().rect().topLeft()).y() \
            + t.rowViewportPosition(fila) + t.rowHeight(fila) // 2
        assert abs(y_campo - y_fila) <= 2, clave
    # Se ven todas las filas (hay sitio de sobra en la columna).
    assert t.verticalScrollBar().maximum() == 0
    assert suma.verticalScrollBar().maximum() == 0
    # La columna comparada, en negrita; el total, también.
    assert _celda_totales(v, "Base imponible", "Gastos\nTodo el lote").font().bold()
    assert not _celda_totales(v, "Base imponible", "Ingresos\nTodo el lote").font().bold()
    assert _celda_totales(v, "Total", "Ingresos\nTodo el lote").font().bold()
    suma.combo_tipo.setCurrentIndex(1)                     # Ingresos
    assert _celda_totales(v, "Base imponible", "Ingresos\nTodo el lote").font().bold()
    v.close()


def test_en_columna_baja_las_dos_tablas_se_desplazan_juntas(guardado):
    """En la caja de abajo (tabla arriba) y con poco alto, las filas se
    desplazan: la casilla sigue en la fila de su importe también al final."""
    v = _ventana(1366, 700)
    v._elegir_distribucion("tabla_arriba")
    v.split_principal.setSizes([600, 150])
    _procesar(6)
    t, suma = v.tabla_totales, v.tabla_su_suma
    barra_suma, barra_tabla = suma.verticalScrollBar(), t.verticalScrollBar()
    assert barra_suma.maximum() > 0
    assert barra_suma.maximum() == barra_tabla.maximum()
    for barra in (barra_suma, barra_tabla):
        barra.setValue(barra.maximum())
        _procesar(2)
        assert barra_tabla.value() == barra_suma.value() == barra.maximum()
        campo = suma.campo("total")
        fila = PRIMERA_FILA_IMPORTE + len(suma._columnas) - 1
        y_campo = campo.mapTo(v, campo.rect().center()).y()
        y_fila = t.viewport().mapTo(v, t.viewport().rect().topLeft()).y() \
            + t.rowViewportPosition(fila) + t.rowHeight(fila) // 2
        assert abs(y_campo - y_fila) <= 2
        barra.setValue(0)
        _procesar(2)
    v.close()


def test_lectura_sobre_la_hoja_pliega_lo_leido_y_las_demas_lo_despliegan(guardado):
    v = _ventana()
    v._elegir_distribucion("sobre_hoja")
    _procesar()
    assert v.panel_lectura.isHidden()
    assert v.lbl_lectura_resumen.isVisible()
    assert v._datos_sobre_hoja
    v._elegir_distribucion("columnas")
    _procesar()
    assert not v.panel_lectura.isHidden()
    assert not v._datos_sobre_hoja
    v.close()


def test_lectura_sobre_la_hoja_senala_lo_que_ya_se_sabe_donde_esta(guardado):
    """Sin pulsar «¿De dónde sale?» (que pregunta a Gemini): solo con lo que
    ya se localizó, se señalan todos los datos sobre la hoja."""
    from facturas_excel import localizar
    v = _ventana()
    v.filas[0].png = b"hoja-de-prueba"
    clave = localizar.clave_imagen(b"hoja-de-prueba")
    v._localizaciones[clave] = [
        localizar.Caja("nif", "B12345674", 0.10, 0.10, 0.15, 0.40),
        localizar.Caja("total_impreso", "121,00", 0.80, 0.60, 0.85, 0.90),
    ]
    v._columna_senalada = None
    sin = {x.texto for x in v._recuadros_de_fila(0, None)}
    v._elegir_distribucion("sobre_hoja")
    con = {x.texto for x in v._recuadros_de_fila(0, None)}
    assert len(con) > len(sin)
    v.close()


def test_una_a_una_deja_la_tabla_con_lo_justo_y_al_salir_vuelve_todo(guardado):
    v = _ventana()
    v._elegir_distribucion("una_a_una")
    _procesar()
    visibles = [c for c in range(v.tabla.columnCount()) if not v.tabla.isColumnHidden(c)]
    assert visibles == [C_ESTADO, C_NOMBRE, C_TOTAL]
    v._revalidar_todo()                    # sigue así al rehacer la tabla
    assert v.tabla.isColumnHidden(C_CUENTA)
    v._elegir_distribucion("cuadre")
    _procesar()
    for columna in (C_ESTADO, C_CUENTA, C_NUM, C_NOMBRE, C_TOTAL):
        assert not v.tabla.isColumnHidden(columna)
    v.close()


def test_cada_distribucion_recuerda_sus_divisores(guardado):
    v = _ventana()
    v._elegir_distribucion("columnas")
    _procesar()
    v.split_revision.setSizes([500, 500, 500])
    v.split_revision.splitterMoved.emit(500, 1)
    v._guardar_divisores()
    tamanos = v.split_revision.sizes()
    assert guardado["divisor_columnas_revision"] == tamanos
    v._elegir_distribucion("cuadre")
    _procesar()
    assert v.split_revision.count() == 2
    v._elegir_distribucion("columnas")
    _procesar()
    assert all(abs(a - b) <= 3 for a, b in zip(v.split_revision.sizes(), tamanos))
    v.close()


def test_los_totales_ocultos_siguen_ocultos_al_cambiar(guardado):
    v = _ventana()
    v._ver_resumen(False)
    _procesar()
    for clave in CLAVES:
        v._elegir_distribucion(clave)
        _procesar()
        assert not v.totales_card.isVisible(), clave
        assert v.factura_card.isVisible() and v.tabla_card.isVisible(), clave
    v._ver_resumen(True)
    _procesar()
    assert v.totales_card.isVisible()
    v.close()


def test_sin_su_suma_en_columna_los_totales_llevan_su_barra(guardado):
    v = _ventana(1366, 700)
    v._elegir_distribucion("tabla_arriba")
    v.split_principal.setSizes([600, 150])
    v.btn_ver_su_suma.setChecked(False)
    _procesar(6)
    assert v.tabla_su_suma.isHidden()
    assert v.tabla_totales.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert v.tabla_totales.verticalScrollBar().maximum() > 0
    v.btn_ver_su_suma.setChecked(True)
    _procesar()
    assert v.tabla_totales.verticalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    v.close()


def _medidas(v) -> str:
    """Qué pide más ancho en cada tarjeta (para saber qué ajustar si una
    distribución no cabe en una máquina con otra letra)."""
    from PySide6.QtWidgets import QLabel, QAbstractButton, QComboBox, QLineEdit
    lineas = []
    for tarjeta in (v.tabla_card, v.factura_card, v.totales_card):
        piezas = []
        for hijo in tarjeta.findChildren(QWidget):
            if not hijo.isVisible():
                continue
            minimo = max(hijo.minimumSizeHint().width(), hijo.minimumWidth())
            texto = ""
            if isinstance(hijo, (QLabel, QAbstractButton, QLineEdit)):
                texto = hijo.text()[:30]
            elif isinstance(hijo, QComboBox):
                texto = hijo.currentText()[:30]
            piezas.append((minimo, type(hijo).__name__, hijo.objectName(), texto))
        piezas.sort(reverse=True)
        lineas.append(f"{tarjeta.objectName()} min={tarjeta.minimumSizeHint().width()} "
                      f"ancho={tarjeta.width()}: {piezas[:8]}")
    lineas.append(f"letra={_app.font().family()} {_app.font().pointSizeF()}")
    return "\n".join(lineas)


def _caben_las_piezas(v, clave) -> None:
    """Las tres piezas caben en su sitio (la cinta de arriba se adapta sola
    al ancho: no cuenta). Si no, dice qué pide más ancho en cada tarjeta."""
    v._elegir_distribucion(clave)
    _procesar()
    principal = v.split_principal
    if principal.minimumSizeHint().width() > principal.width():
        print(clave, principal.minimumSizeHint().width(), principal.width())
        print(_medidas(v))                 # sale entero en el registro
    assert principal.minimumSizeHint().width() <= principal.width(), (
        clave, principal.minimumSizeHint().width(), principal.width())


@pytest.mark.parametrize("ancho, claves", [
    # En un portátil, las cuatro primeras.
    (1366, ["columnas", "sobre_hoja", "tabla_arriba", "cuadre"]),
    # La 5 (lista, factura con lo leído al lado y totales) es para
    # pantallas anchas, como dice su descripción.
    (1600, ["una_a_una"]),
])
def test_cada_distribucion_cabe_en_su_pantalla(guardado, tema_real, ancho, claves):
    """Con el aspecto del programa."""
    v = _ventana(ancho, 740)
    if v.width() < ancho:
        v.close()
        pytest.skip(f"la pantalla de esta máquina no llega a {ancho} de ancho")
    for clave in claves:
        _caben_las_piezas(v, clave)
    v.close()


def test_una_a_una_dice_cuantas_quedan(guardado):
    v = _ventana()
    assert not v.panel_progreso.isVisible()
    v._elegir_distribucion("una_a_una")
    _procesar()
    assert v.panel_progreso.isVisible()
    # 4 facturas; las de prueba se leen bien, así que todas están listas.
    from facturas_excel.lote import CON_ERROR, POR_REVISAR
    pendientes = sum(r.presentacion in (POR_REVISAR, CON_ERROR) for r in v.filas)
    listas = len(v.filas) - pendientes
    assert v.lbl_progreso.text() == f"{listas} de {len(v.filas)} listas"
    assert v.barra_progreso.value() == listas
    assert v.barra_progreso.maximum() == len(v.filas)
    v._elegir_distribucion("cuadre")
    _procesar()
    assert not v.panel_progreso.isVisible()
    v.close()


def test_los_titulos_de_las_tarjetas_van_a_la_misma_altura(guardado):
    v = _ventana()
    for clave in ("columnas", "una_a_una"):
        v._elegir_distribucion(clave)
        _procesar()
        titulos = [v.tabla_card.findChildren(type(v.titulo_visor))[0], v.titulo_visor]
        alturas = {t.mapTo(v, t.rect().topLeft()).y() for t in titulos}
        alturas.add(v.lbl_resumen_titulo.mapTo(v, v.lbl_resumen_titulo.rect().topLeft()).y()
                    if not v.panel_progreso.isVisible() else min(alturas))
        assert max(alturas) - min(alturas) <= 2, (clave, alturas)
    v.close()


# ------------------------------------------- lo que encontró la revisión
def test_en_columna_una_columna_nueva_no_deja_la_casilla_del_total_aplastada(guardado):
    """Con la barra horizontal de los totales hay una fila de relleno en «Su
    suma»; si sale otro tipo de IVA, esa fila pasa a ser la del total y no
    puede quedarse con el alto de la barra."""
    from facturas_excel.su_suma import ALTO_FILA_COLUMNA
    from facturas_excel.tabla_facturas import C_PCT
    v = _ventana(1366, 740)
    v._elegir_distribucion("columnas")
    _procesar()
    v.txt_buscar.setText("G-")                   # cuatro ámbitos: barra
    _procesar(6)
    suma, t = v.tabla_su_suma, v.tabla_totales
    assert suma._hueco > 0
    fila = next(i for i, f in enumerate(v.filas) if f.factura.num_factura == "G-3")
    v.tabla.item(fila, C_PCT).setText("4")        # sale el IVA del 4 %
    _procesar(6)
    assert "iva_4" in suma._campos
    importes = PRIMERA_FILA_IMPORTE + len(suma._columnas)
    assert all(suma.rowHeight(r) == ALTO_FILA_COLUMNA for r in range(importes))
    campo = suma.campo("total")
    y_campo = campo.mapTo(v, campo.rect().center()).y()
    y_fila = t.viewport().mapTo(v, t.viewport().rect().topLeft()).y() \
        + t.rowViewportPosition(importes - 1) + t.rowHeight(importes - 1) // 2
    assert abs(y_campo - y_fila) <= 2
    v.close()


def test_el_listado_pdf_lleva_el_recargo_aunque_la_lista_vaya_con_lo_justo(guardado):
    v = _ventana()
    v._anadir_fila(b"", _factura(num_factura="R-1", base_requiv=100.0,
                                 pct_requiv=5.2, cuota_requiv=5.2,
                                 total_impreso=126.2),
                   "gasto", "600", "", "")
    v._revalidar_todo()
    for clave in ("cuadre", "una_a_una"):
        v._elegir_distribucion(clave)
        _procesar()
        html = v._html_listado_totales()
        assert "Base RE" in html and "Cuota RE" in html, clave
    v.close()


def test_al_abrir_los_divisores_guardados_van_en_proporcion(guardado, tema_real):
    """Guardados con la ventana maximizada, al abrirla más pequeña se
    reparten en proporción (no se deja la factura en su mínimo)."""
    guardado["distribucion"] = "columnas"
    guardado["divisor_columnas_revision"] = [700, 560, 620]
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v.resize(1420, 820)
    v.show()
    _procesar()
    tamanos = v.split_revision.sizes()
    total = sum(tamanos)
    minimos = [v.split_revision.widget(i).minimumSizeHint().width() for i in range(3)]
    if any(t * total / 1880 < m for t, m in zip([700, 560, 620], minimos)):
        v.close()
        pytest.skip("en esta pantalla alguna pieza no cabe en su proporción")
    for tamano, guardado_ in zip(tamanos, [700, 560, 620]):
        assert abs(tamano / total - guardado_ / 1880) < 0.03, (tamanos, _medidas(v))
    v.close()


def test_la_cabecera_de_los_totales_no_arrastra_globos_de_la_otra_forma(guardado):
    v = _ventana()
    v._elegir_distribucion("columnas")
    _procesar()
    v._elegir_distribucion("cuadre")
    _procesar()
    t = v.tabla_totales
    globos = {t.horizontalHeaderItem(c).text(): t.horizontalHeaderItem(c).toolTip()
              for c in range(t.columnCount())}
    assert globos["Nº"] == "" and globos["Base imponible"] == ""
    assert globos["Total"].startswith("Total = base")
    v.close()


def test_las_novedades_al_arrancar_no_cuelgan_las_pruebas(guardado):
    """Lo que colgó el CI de Windows: con la máquina lenta, la prueba seguía
    procesando eventos pasados los 500 ms y saltaba «Novedades de la
    versión», que espera un clic. Vistas en esta versión, no salen."""
    import time
    from PySide6.QtCore import QCoreApplication, QEventLoop
    v = _ventana()
    fin = time.monotonic() + 0.9
    while time.monotonic() < fin:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 20)
    v.close()


def test_una_ventana_que_espera_respuesta_no_cuelga_una_prueba(sin_ventanas_que_esperan):
    """Si aun así salta una ventana que la prueba no ha previsto, no se abre
    (no se queda esperando un clic) y la prueba falla diciendo cuál es."""
    from facturas_excel import notas_version
    notas_version.ajustes.guardar("notas_version_vistas", "")
    v = _ventana()
    v._mostrar_notas_version_al_arrancar()
    assert sin_ventanas_que_esperan == ["DialogoNotasVersion"]
    sin_ventanas_que_esperan.clear()          # esta vez, prevista
    v.close()
