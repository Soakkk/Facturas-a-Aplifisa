"""1.19: cuadrar con su suma, filtro por mes, revisar desde la factura y la
lectura plegable (lo que pidió el usuario tras ver la 1.18)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import QApplication

from facturas_excel import sesion
from facturas_excel.app import ICONO_REVISADO, VentanaPrincipal, C_ESTADO
from facturas_excel.lote import CON_ERROR, POR_REVISAR, REVISADA
from facturas_excel.modelo import Factura
from facturas_excel.su_suma import diferencia, leer_importe

_app = QApplication.instance() or QApplication([])


def _factura(**cambios):
    datos = dict(num_factura="F-1", fecha="03/07/2026", nombre="PROVEEDOR SL",
                 nif="B12345674", concepto="622", base_iva=100.0, pct_iva=21.0,
                 cuota_iva=21.0, total_impreso=121.0, confianza_ia="alta")
    datos.update(cambios)
    return Factura(**datos)


def _ventana(*facturas):
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    for f in facturas:
        v._anadir_fila(b"", f, "gasto", "622", "", "")
    v._revalidar_todo()
    return v


def _lote():
    return _ventana(
        _factura(num_factura="J-1", fecha="03/07/2026"),
        _factura(num_factura="J-2", fecha="20/07/2026", base_iva=50.0,
                 cuota_iva=10.5, total_impreso=60.5),
        _factura(num_factura="A-1", fecha="05/08/2026", base_iva=200.0,
                 cuota_iva=42.0, total_impreso=242.0),
        _factura(num_factura="S-1", fecha="", base_iva=10.0, cuota_iva=2.1,
                 total_impreso=12.1),
    )


def _visibles(v):
    return [v.filas[r].factura.num_factura for r in range(v.tabla.rowCount())
            if not v.tabla.isRowHidden(r)]


def _elegir_mes(v, texto):
    v.combo_filtro_mes.setCurrentIndex(v.combo_filtro_mes.findText(texto))


# ---------------------------------------------------------------- por mes
def test_el_filtro_por_mes_ofrece_los_meses_del_lote():
    v = _lote()
    opciones = [v.combo_filtro_mes.itemText(i)
                for i in range(v.combo_filtro_mes.count())]
    assert opciones == ["Todos los meses", "Julio 2026", "Agosto 2026",
                        "Sin fecha"]


def test_filtrar_por_mes_deja_solo_ese_mes_y_lo_suma_aparte():
    v = _lote()
    _elegir_mes(v, "Julio 2026")
    assert _visibles(v) == ["J-1", "J-2"]
    assert "julio 2026" in v.lbl_resumen_titulo.text()
    t = v.tabla_totales
    # Lo que se ve, primero (es lo que se cuadra con el listado del mes).
    assert t.item(0, 0).text() == "Gastos · Lo que se ve (filtro)"
    assert t.item(0, t.columnCount() - 1).text() == "181,50 €"  # 121 + 60,50
    assert any(t.item(r, 0).text() == "Gastos · Todo el lote"
               for r in range(1, t.rowCount()))
    _elegir_mes(v, "Sin fecha")
    assert _visibles(v) == ["S-1"]
    v._limpiar_filtros()
    assert v.combo_filtro_mes.currentData() is None
    assert len(_visibles(v)) == 4


def test_siguiente_incidencia_respeta_el_mes_si_la_pendiente_se_ve():
    v = _ventana(_factura(num_factura="J-1"),
                 _factura(num_factura="J-2", fecha="20/07/2026",
                          confianza_ia="media"))
    _elegir_mes(v, "Julio 2026")
    v.tabla.selectRow(0)
    v._siguiente_incidencia()
    assert v.tabla.currentRow() == 1
    assert v.combo_filtro_mes.currentData() == (2026, 7)


# ---------------------------------------------------------------- su suma
def test_leer_importe_entiende_como_se_escribe():
    assert leer_importe("4.347,51") == 4347.51
    assert leer_importe("4347,51 €") == 4347.51
    assert leer_importe("4347.51") == 4347.51
    assert leer_importe("−22,50") == -22.5
    assert leer_importe("") is None
    assert leer_importe("abc") is None
    # La retención se compara sin signo.
    assert diferencia("irpf", -22.5, 22.5) == 0
    assert diferencia("base", 100.0, 90.0) == 10.0


def _resultado(v, clave):
    return v.tabla_su_suma.resultado(clave)


def _teclear(v, clave, texto):
    v.tabla_su_suma.campo(clave).setText(texto)


def test_su_suma_dice_si_cuadra_y_cuanto_falta():
    v = _lote()                                      # base gastos: 360,00
    _teclear(v, "base", "360,00")
    assert _resultado(v, "base") == "✓ cuadra"
    _teclear(v, "total", "430")                     # programa: 435,60
    assert _resultado(v, "total") == "+5,60 €"
    assert "El programa da más" in v.tabla_su_suma.lbl_veredicto.text()
    _teclear(v, "total", "435,60")
    assert "Todo lo que ha escrito cuadra" in v.tabla_su_suma.lbl_veredicto.text()
    _teclear(v, "iva", "x")
    assert _resultado(v, "iva") == "¿cifra?"


def test_su_suma_compara_con_lo_filtrado():
    v = _lote()
    _elegir_mes(v, "Agosto 2026")
    assert "Lo que se ve" in v.tabla_su_suma.lbl_ambito.text()
    _teclear(v, "base", "200")
    assert _resultado(v, "base") == "✓ cuadra"
    v._limpiar_filtros()
    assert "Todo el lote" in v.tabla_su_suma.lbl_ambito.text()
    # El programa da 360 en el lote: 160 más que lo tecleado.
    assert _resultado(v, "base") == "+160,00 €"


def test_su_suma_guarda_lo_de_gastos_e_ingresos_por_separado():
    v = _lote()
    _teclear(v, "base", "360")
    v.tabla_su_suma.combo_tipo.setCurrentIndex(1)     # Ingresos
    assert v.tabla_su_suma.campo("base").text() == ""
    assert "No hay ingresos" in v.tabla_su_suma.lbl_ambito.text()
    v.tabla_su_suma.combo_tipo.setCurrentIndex(0)
    assert v.tabla_su_suma.campo("base").text() == "360"


def test_su_suma_se_conserva_al_cerrar_y_se_borra_al_vaciar(tmp_path, monkeypatch):
    ruta = tmp_path / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))
    v = _lote()
    v._bloques = [{"nombre": "b1", "procesadas": [], "crudos": [],
                   "cliente": "CLIENTE", "nif": "12345678Z"}]
    _teclear(v, "base", "360")
    v.closeEvent(QCloseEvent())
    otra = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    assert otra.tabla_su_suma.campo("base").text() == "360"
    assert _resultado(otra, "base") == "✓ cuadra"
    monkeypatch.setattr("facturas_excel.app.QMessageBox.question",
                        lambda *a, **k: __import__(
                            "PySide6.QtWidgets", fromlist=["QMessageBox"]
                        ).QMessageBox.Yes)
    otra._vaciar_todo()
    assert otra.tabla_su_suma.campo("base").text() == ""


# ------------------------------------------------- revisar desde la factura
def _pendientes():
    return _ventana(
        _factura(num_factura="F-1", confianza_ia="media"),          # ámbar
        _factura(num_factura="F-2"),                                 # verde
        _factura(num_factura="F-3", confianza_ia="media"),          # ámbar
    )


def test_correcta_y_siguiente_revisa_la_ambar_y_salta_a_la_siguiente():
    v = _pendientes()
    v.tabla.selectRow(0)
    v.btn_correcta_siguiente.click()
    assert v.filas[0].presentacion == REVISADA
    assert v.tabla.item(0, C_ESTADO).text() == ICONO_REVISADO
    assert v.tabla.currentRow() == 2
    v.btn_correcta_siguiente.click()
    assert v.filas[2].presentacion == REVISADA
    assert all(f.presentacion not in (POR_REVISAR, CON_ERROR) for f in v.filas)


def test_una_roja_no_se_da_por_buena():
    v = _ventana(_factura(num_factura="F-1", base_iva=None),        # error
                 _factura(num_factura="F-2", confianza_ia="media"))
    assert v.filas[0].presentacion == CON_ERROR
    v.tabla.selectRow(0)
    v._correcta_y_siguiente()
    assert v.tabla.currentRow() == 0
    assert v.filas[0].presentacion == CON_ERROR
    assert v.filas[1].presentacion == POR_REVISAR


def test_marcar_revisada_de_la_factura_solo_toca_la_que_se_ve():
    v = _pendientes()
    v.tabla.selectAll()
    v.tabla.setCurrentCell(2, 3)
    v.btn_revisada_factura.click()
    assert v.filas[2].presentacion == REVISADA
    assert v.filas[0].presentacion == POR_REVISAR


def _tecla(v, tecla, modificadores=Qt.NoModifier):
    evento = QKeyEvent(QEvent.KeyPress, tecla, modificadores)
    v.tabla.keyPressEvent(evento)


def test_intro_pasa_a_la_siguiente_sin_marcar_y_ctrl_intro_marca():
    v = _pendientes()
    v.tabla.setCurrentCell(0, 3)
    _tecla(v, Qt.Key_Return)
    assert v.tabla.currentRow() == 2
    assert v.filas[0].presentacion == POR_REVISAR       # no se ha marcado
    _tecla(v, Qt.Key_Return, Qt.ControlModifier)
    assert v.filas[2].presentacion == REVISADA
    assert v.tabla.currentRow() == 0                     # vuelve a la otra


# ------------------------------------------------------- lectura plegable
def test_la_lectura_se_pliega_a_una_linea_con_el_motivo(monkeypatch):
    from facturas_excel import ajustes
    guardado = {}
    monkeypatch.setattr(ajustes, "guardar",
                        lambda clave, valor: guardado.__setitem__(clave, valor))
    v = _ventana(_factura(num_factura="F-9",
                          tratamiento_manual="Factura con suplido"))
    v.resize(1600, 900)
    v.show()
    _app.processEvents()
    v.tabla.selectRow(0)
    _app.processEvents()
    ancho_abierta = v.visor_scroll.width()
    # En una pantalla de 1024 con la letra grande la tarjeta ya empieza por
    # debajo de su mínimo y al plegar Qt la recoloca: el ancho no se compara.
    apretada = v.factura_card.width() < v.factura_card.minimumSizeHint().width()
    v.btn_plegar_lectura.setChecked(True)
    _app.processEvents()
    assert v.panel_lectura.isHidden()
    assert v.lbl_lectura_resumen.isVisible()
    # La hoja se queda con el ancho de lo leído.
    assert v.visor_scroll.width() > ancho_abierta
    resumen = v.lbl_lectura_resumen.text()
    assert "Revisar" in resumen and "F-9" in resumen
    # El motivo, recortado a lo que quepa en la línea y entero en el globo.
    assert "suplido" in v.lbl_lectura_resumen.toolTip()
    assert guardado["lectura_plegada"] is True
    v.btn_plegar_lectura.setChecked(False)
    _app.processEvents()
    assert not v.panel_lectura.isHidden()
    assert not v.lbl_lectura_resumen.isVisible()
    if not apretada:
        assert abs(v.visor_scroll.width() - ancho_abierta) <= 10
    assert guardado["lectura_plegada"] is False


# ------------------------------------------- lo que encontró la revisión
def test_lo_que_no_es_un_importe_sale_como_cifra_dudosa():
    for texto in ("Inf", "inf", "nan", "1e400", "9" * 320, "4,347",
                  "4347.510", "1,23,4", "abc"):
        assert leer_importe(texto) is None, texto
    assert leer_importe("4,347.51") == 4347.51     # formato inglés
    assert leer_importe("1.234.567") == 1234567
    assert leer_importe("22,50-") == -22.5


def test_teclear_inf_no_rompe_nada_y_la_sesion_se_recupera(tmp_path, monkeypatch):
    ruta = tmp_path / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))
    v = _lote()
    v._bloques = [{"nombre": "b1", "procesadas": [], "crudos": [],
                   "cliente": "CLIENTE", "nif": "12345678Z"}]
    _teclear(v, "base", "Inf")
    assert _resultado(v, "base") == "¿cifra?"
    v._revalidar_todo()                                   # no lanza nada
    v.closeEvent(QCloseEvent())
    otra = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    assert len(otra.filas) == 4                           # el lote sigue ahí


def test_la_retencion_se_compara_con_el_signo_que_se_escriba():
    from facturas_excel.su_suma import comparar
    assert comparar("irpf", -22.5, 22.5) == (22.5, 0.0)
    assert comparar("irpf", -22.5, -22.5) == (-22.5, 0.0)
    # −22,50 es 7,50 más que −30: la diferencia y la ayuda lo dicen así.
    assert comparar("irpf", -22.5, -30.0) == (-22.5, 7.5)


def test_se_pueden_pedir_recargo_retencion_y_suplidos_aunque_valgan_cero():
    v = _lote()
    # Desde la 1.20 hay una casilla bajo cada columna, valga o no cero.
    for clave in ("requiv", "irpf", "suplidos"):
        assert not v.tabla_su_suma.campo(clave).isHidden()
    _teclear(v, "irpf", "22,50")
    assert _resultado(v, "irpf") == "−22,50 €"       # el programa no tiene


def test_vaciar_un_lote_ya_vacio_borra_lo_tecleado():
    v = _lote()
    _teclear(v, "base", "360")
    for _ in range(len(v.filas)):
        v.tabla.selectRow(0)
        v._eliminar_seleccion()
    v._vaciar_todo()
    assert v.tabla_su_suma.campo("base").text() == ""


def test_ctrl_intro_de_verdad_marca_la_que_se_ve():
    from PySide6.QtTest import QTest
    v = _pendientes()
    v.show()
    v.tabla.setCurrentCell(0, 3)
    v.tabla.selectRow(0)
    # Como en Windows: Ctrl pulsado mientras llega el Intro (y luego suelto,
    # para no dejar Ctrl «pulsado» a las pruebas siguientes).
    QTest.keyPress(v.tabla, Qt.Key_Control)
    QTest.keyClick(v.tabla, Qt.Key_Return, Qt.ControlModifier)
    QTest.keyRelease(v.tabla, Qt.Key_Control)
    assert v.filas[0].presentacion == REVISADA
    assert v.filas[2].presentacion == POR_REVISAR
    assert v.tabla.currentRow() == 2
    assert [i.row() for i in v.tabla.selectionModel().selectedRows()] == [2]


def test_la_siguiente_pendiente_del_mes_va_antes_que_quitar_el_filtro():
    v = _ventana(_factura(num_factura="J-1", fecha="03/07/2026", confianza_ia="media"),
                 _factura(num_factura="S-1", fecha="03/09/2026", confianza_ia="media"),
                 _factura(num_factura="J-2", fecha="20/07/2026", confianza_ia="media"))
    _elegir_mes(v, "Julio 2026")
    v.tabla.setCurrentCell(0, 3)
    v._siguiente_incidencia()
    assert v.filas[v.tabla.currentRow()].factura.num_factura == "J-2"
    assert v.combo_filtro_mes.currentData() == (2026, 7)


def test_correcta_y_siguiente_no_se_salta_ninguna_con_solo_por_revisar():
    v = _ventana(_factura(num_factura="F-1", confianza_ia="media"),
                 _factura(num_factura="F-2"),
                 _factura(num_factura="F-3", confianza_ia="media"),
                 _factura(num_factura="F-4", confianza_ia="media"))
    v.combo_filtro_estado.setCurrentIndex(1)              # Solo por revisar
    v.tabla.setCurrentCell(0, 3)
    v._correcta_y_siguiente()
    assert v.filas[v.tabla.currentRow()].factura.num_factura == "F-3"


def test_no_se_marca_una_factura_que_no_se_ve():
    v = _pendientes()
    v.tabla.setCurrentCell(0, 3)
    v.txt_buscar.setText("NO EXISTE")                     # ninguna a la vista
    v.btn_revisada_factura.click()
    assert v.filas[0].presentacion == POR_REVISAR
    v._correcta_y_siguiente()
    assert v.filas[0].presentacion == POR_REVISAR


def test_la_ultima_pendiente_conserva_el_deshacer():
    v = _ventana(_factura(num_factura="F-1", confianza_ia="media"),
                 _factura(num_factura="F-2"))
    v.tabla.setCurrentCell(0, 3)
    v._correcta_y_siguiente()
    assert v.filas[0].presentacion == REVISADA
    assert "No queda ninguna" in v.banda.lbl.text()
    assert v.banda._accion_deshacer is not None
    v.banda._deshacer()
    assert v.filas[0].presentacion == POR_REVISAR


def test_con_una_eleccion_pendiente_la_lectura_se_despliega_sola(monkeypatch):
    from facturas_excel import ajustes
    monkeypatch.setattr(ajustes, "guardar", lambda *_a: None)
    disc = {"campo": "total", "etiqueta": "Total", "valor_1": 121.0,
            "valor_2": 131.0, "campo_factura": "total_impreso",
            "texto": "Doble lectura: Total no coincide"}
    v = _ventana(_factura(num_factura="F-1"),
                 _factura(num_factura="F-2", verificacion="doble",
                          discrepancias=(disc,)))
    v.btn_plegar_lectura.setChecked(True)
    v.tabla.setCurrentCell(0, 3)
    assert v.panel_lectura.isHidden()
    v.tabla.setCurrentCell(1, 3)
    assert not v.panel_lectura.isHidden()                 # hay que elegir
    assert v.btn_plegar_lectura.isChecked()               # la preferencia sigue
    v.tabla.setCurrentCell(0, 3)
    assert v.panel_lectura.isHidden()


def test_plegada_el_motivo_entero_va_en_el_globo():
    v = _ventana(_factura(num_factura="F-9",
                          tratamiento_manual="Factura con suplido"))
    v.btn_plegar_lectura.setChecked(True)
    v.tabla.setCurrentCell(0, 3)
    assert "suplido" in v.lbl_lectura_resumen.toolTip()
