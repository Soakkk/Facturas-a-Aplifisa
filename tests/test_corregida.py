"""«✎ Corregida»: lo que corrige una persona cuenta como revisado.

El usuario lo pidió así: si ya ha corregido un dato mirando el documento, no
debería tener que pulsar además «Marcar revisada» para poder exportar. No sale
en verde (se ve que se tocó a mano), pero no frena la exportación. Si después
de la corrección la factura no cuadra, sigue pendiente: un dígito mal tecleado
no puede salir hacia Aplifisa sin que nadie lo vea.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from facturas_excel import sesion
from facturas_excel.app import (
    C_BASE, C_ESTADO, C_NOMBRE, C_TIPO, C_TOTAL, ICONO_CORREGIDO, ICONO_ESTADO,
    ICONO_REVISADO, VentanaPrincipal,
)
from facturas_excel.lote import CORREGIDA, POR_REVISAR
from facturas_excel.modelo import Factura
from facturas_excel.procesar import construir
from facturas_excel.validacion import REVISAR

_app = QApplication.instance() or QApplication([])


def _factura(**cambios):
    datos = dict(num_factura="F-1", fecha="03/09/2026", nombre="PROVEEDOR SL",
                 nif="B12345674", concepto="622", base_iva=100.0, pct_iva=21.0,
                 cuota_iva=21.0, total_impreso=121.0, confianza_ia="media")
    datos.update(cambios)
    return Factura(**datos)


def _ventana(*facturas):
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    for f in facturas:
        v._anadir_fila(b"", f, "gasto", "622", "G13", "")
    v._revalidar_todo()
    return v


def _exportables(v):
    por_tipo, _excluidas, errores, pendientes = v._clasificar_exportacion()
    return por_tipo["gasto"], errores, pendientes


def test_corregir_un_dato_de_una_ambar_la_deja_corregida_y_exportable():
    f = _factura()                         # confianza media: ámbar
    v = _ventana(f)
    assert v.tabla.item(0, C_ESTADO).text() == ICONO_ESTADO[REVISAR]
    assert _exportables(v)[2] == [0]

    v.tabla.item(0, C_NOMBRE).setText("PROVEEDOR CORREGIDO SL")

    assert v.tabla.item(0, C_ESTADO).text() == ICONO_CORREGIDO
    assert v.filas[0].presentacion == CORREGIDA
    assert f.revision_corregida and not f.revision_confirmada
    exportables, errores, pendientes = _exportables(v)
    assert exportables == [f] and not errores and not pendientes
    # No cuenta como incidencia ni la vuelve a señalar «Siguiente incidencia».
    v.tabla.selectRow(0)
    v._siguiente_incidencia()
    assert "listo para exportar" in v.lbl_estado.text()


def test_si_tras_corregir_no_cuadra_sigue_pendiente():
    f = _factura(confianza_ia="alta")
    v = _ventana(f)
    v.tabla.item(0, C_TOTAL).setText("125,00")     # 100 + 21 ≠ 125
    assert v.filas[0].presentacion == POR_REVISAR
    assert any("pero el total no cuadra" in m for m in v.filas[0]["mensajes"])
    assert _exportables(v)[2] == [0]
    # Si está bien así, «Marcar revisada» la deja salir.
    v.tabla.selectRow(0)
    v._marcar_revisada()
    assert v.tabla.item(0, C_ESTADO).text() == ICONO_REVISADO
    assert _exportables(v)[0] == [f]


def test_escribir_lo_mismo_que_habia_no_la_marca():
    f = _factura()
    v = _ventana(f)
    v.tabla.item(0, C_BASE).setText("100,00")
    assert not f.revision_corregida
    assert v.filas[0].presentacion == POR_REVISAR


def test_una_correccion_marca_la_factura_entera():
    datos = dict(emisor_nombre="PROVEEDOR PRUEBA SL", emisor_nif="B12345674",
                 receptor_nombre="CLIENTE PRUEBA", receptor_nif="12345678Z",
                 num_factura="F-9", fecha="03/09/2026", cuenta_gasto="622",
                 subclave_gxx="G13", confianza="media",
                 lineas_iva=[dict(base=100, tipo_iva=21, cuota_iva=21),
                             dict(base=100, tipo_iva=10, cuota_iva=10)],
                 total=231)
    pr = construir(datos, "12345678Z", "CLIENTE PRUEBA", "ficticio.pdf", 1)
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    for f in pr.facturas:
        v._anadir_fila(b"", f, pr.tipo, pr.cuenta, pr.gxx, pr.aviso)
    v._revalidar_todo()
    v.tabla.item(0, C_NOMBRE).setText("PROVEEDOR PRUEBA, S.L.")
    assert [x.presentacion for x in v.filas] == [CORREGIDA, CORREGIDA]
    exportables, errores, pendientes = _exportables(v)
    assert len(exportables) == 2 and not errores and not pendientes


def test_cambiar_gasto_o_ingreso_tambien_es_corregir():
    f = _factura()
    v = _ventana(f)
    control = v.tabla.cellWidget(0, C_TIPO)
    control.setCurrentIndex(control.findData("venta"))
    assert f.revision_corregida


def test_un_dato_copiado_a_otra_factura_no_la_da_por_revisada():
    """Al corregir el nombre se copia a las del mismo NIF: esas otras no las
    ha mirado nadie, así que siguen como estaban (pendientes)."""
    a = _factura(num_factura="F-1", documento_id="a")
    b = _factura(num_factura="F-2", documento_id="b")
    v = _ventana(a, b)
    v.tabla.item(0, C_NOMBRE).setText("PROVEEDOR BUENO SL")
    assert v.filas[0].presentacion == CORREGIDA
    assert v.filas[1]["factura"].nombre == "PROVEEDOR BUENO SL"
    assert not v.filas[1]["factura"].revision_corregida
    assert v.filas[1].presentacion == POR_REVISAR


def test_solo_correctas_incluye_las_corregidas():
    v = _ventana(_factura())
    v.tabla.item(0, C_NOMBRE).setText("OTRO NOMBRE SL")
    v.combo_filtro_estado.setCurrentIndex(3)            # «Solo correctas»
    assert not v.tabla.isRowHidden(0)
    v.combo_filtro_estado.setCurrentIndex(1)            # «Solo por revisar»
    assert v.tabla.isRowHidden(0)


def test_la_marca_se_conserva_al_cerrar_y_abrir(tmp_path, monkeypatch):
    ruta = tmp_path / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))
    v = _ventana(_factura())
    v._bloques = [{"nombre": "b1", "procesadas": [], "crudos": [],
                   "cliente": "CLIENTE", "nif": "12345678Z"}]
    v.tabla.item(0, C_NOMBRE).setText("OTRO NOMBRE SL")
    v.closeEvent(QCloseEvent())
    otra = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    assert otra.filas[0]["factura"].revision_corregida
    assert otra.tabla.item(0, C_ESTADO).text() == ICONO_CORREGIDO


def test_un_aviso_nuevo_por_la_correccion_la_deja_pendiente():
    """Un NIF mal tecleado al corregir no puede salir como «Corregida»."""
    from facturas_excel.app import C_NIF
    f = _factura()
    v = _ventana(f)
    v.tabla.item(0, C_NIF).setText("B12345675")       # dígito de control mal
    assert f.revision_corregida
    assert v.filas[0].presentacion == POR_REVISAR
    assert any("aviso nuevo" in m for m in v.filas[0]["mensajes"])
    assert _exportables(v)[2] == [0]
    # Si lo arregla, ya sí.
    v.tabla.item(0, C_NIF).setText("B12345674")
    assert v.filas[0].presentacion == CORREGIDA


def test_elegir_la_lectura_1_tras_escribir_otro_valor_lo_vuelve_a_poner():
    disc = {"campo": "total", "etiqueta": "Total", "valor_1": 121.0,
            "valor_2": 131.0, "campo_factura": "total_impreso",
            "texto": "Doble lectura: Total no coincide"}
    f = _factura(confianza_ia="alta", verificacion="doble", discrepancias=(disc,))
    v = _ventana(f)
    v.tabla.item(0, C_TOTAL).setText("999,00")
    v._resolver_discrepancia(0, 0, 1)
    assert v.tabla.item(0, C_TOTAL).text() == "121,00"
    assert f.total_impreso == 121.0
