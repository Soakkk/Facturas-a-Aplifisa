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
    totales = v.vista_totales.toPlainText()
    assert totales.index("Lo que se ve") < totales.index("Todo el lote")
    assert "181,50 €" in totales                     # 121 + 60,50
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
    return v.caja_su_suma._filas[clave][2].text()


def _teclear(v, clave, texto):
    v.caja_su_suma._filas[clave][1].setText(texto)


def test_su_suma_dice_si_cuadra_y_cuanto_falta():
    v = _lote()                                      # base gastos: 360,00
    _teclear(v, "base", "360,00")
    assert _resultado(v, "base") == "✓ cuadra"
    _teclear(v, "total", "430")                     # programa: 435,60
    assert _resultado(v, "total") == "+5,60 €"
    assert "no cuadran" in v.caja_su_suma.lbl_veredicto.text()
    _teclear(v, "total", "435,60")
    assert "Todo lo que ha escrito cuadra" in v.caja_su_suma.lbl_veredicto.text()
    _teclear(v, "iva", "x")
    assert _resultado(v, "iva") == "¿cifra?"


def test_su_suma_compara_con_lo_filtrado():
    v = _lote()
    _elegir_mes(v, "Agosto 2026")
    assert "Lo que se ve" in v.caja_su_suma.lbl_ambito.text()
    _teclear(v, "base", "200")
    assert _resultado(v, "base") == "✓ cuadra"
    v._limpiar_filtros()
    assert "Todo el lote" in v.caja_su_suma.lbl_ambito.text()
    # El programa da 360 en el lote: 160 más que lo tecleado.
    assert _resultado(v, "base") == "+160,00 €"


def test_su_suma_guarda_lo_de_gastos_e_ingresos_por_separado():
    v = _lote()
    _teclear(v, "base", "360")
    v.caja_su_suma.combo_tipo.setCurrentIndex(1)     # Ingresos
    assert v.caja_su_suma._filas["base"][1].text() == ""
    assert "No hay ingresos" in v.caja_su_suma.lbl_ambito.text()
    v.caja_su_suma.combo_tipo.setCurrentIndex(0)
    assert v.caja_su_suma._filas["base"][1].text() == "360"


def test_su_suma_se_conserva_al_cerrar_y_se_borra_al_vaciar(tmp_path, monkeypatch):
    ruta = tmp_path / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))
    v = _lote()
    v._bloques = [{"nombre": "b1", "procesadas": [], "crudos": [],
                   "cliente": "CLIENTE", "nif": "12345678Z"}]
    _teclear(v, "base", "360")
    v.closeEvent(QCloseEvent())
    otra = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    assert otra.caja_su_suma._filas["base"][1].text() == "360"
    assert _resultado(otra, "base") == "✓ cuadra"
    monkeypatch.setattr("facturas_excel.app.QMessageBox.question",
                        lambda *a, **k: __import__(
                            "PySide6.QtWidgets", fromlist=["QMessageBox"]
                        ).QMessageBox.Yes)
    otra._vaciar_todo()
    assert otra.caja_su_suma._filas["base"][1].text() == ""


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
    v.btn_plegar_lectura.setChecked(True)
    _app.processEvents()
    assert v.ficha.isHidden()
    assert v.lbl_lectura_resumen.isVisible()
    resumen = v.lbl_lectura_resumen.text()
    assert "Revisar" in resumen and "F-9" in resumen and "suplido" in resumen
    assert guardado["lectura_plegada"] is True
    alto_plegada = v.panel_lectura.height()
    v.btn_plegar_lectura.setChecked(False)
    _app.processEvents()
    assert not v.ficha.isHidden()
    assert v.panel_lectura.height() > alto_plegada
    assert guardado["lectura_plegada"] is False
