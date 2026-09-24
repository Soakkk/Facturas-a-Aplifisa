"""Ficha de la factura, resolución de la doble lectura y ajustes de modelos."""
from PySide6.QtWidgets import QApplication, QLabel

from facturas_excel import ajustes, extraccion
from facturas_excel.app import (
    C_ESTADO, C_NIF, C_TOTAL, ICONO_ESTADO, ICONO_SIN_VERIFICAR, VentanaPrincipal,
)
from facturas_excel.dialogo_modelos import DialogoModelos
from facturas_excel.modelo import Factura
from facturas_excel.validacion import OK, REVISAR

_app = QApplication.instance() or QApplication([])

DISC_TOTAL = {"campo": "total", "etiqueta": "Total", "valor_1": 121.0,
              "valor_2": 131.0, "campo_factura": "total_impreso",
              "modelo_1": "gemini-3.8-flash", "modelo_2": "gemini-3.7-flash",
              "texto": "Doble lectura: Total no coincide — gemini-3.8-flash: "
                       "121,00 · gemini-3.7-flash: 131,00"}


def _factura(**cambios):
    datos = dict(num_factura="F-1", fecha="10/02/2026", nombre="PROVEEDOR PRUEBA",
                 nif="B12345674", concepto="629", subclave="G22", base_iva=100.0,
                 pct_iva=21.0, cuota_iva=21.0, total_impreso=121.0,
                 documento_id="d1")
    datos.update(cambios)
    return Factura(**datos)


def _ventana(*facturas):
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    for f in facturas:
        v._anadir_fila(b"", f, "gasto", f.concepto, f.subclave, "", "b1")
    v._revalidar_todo()
    v.tabla.selectRow(0)
    return v


def _textos(v):
    return " ".join(l.text() for l in v.ficha.findChildren(QLabel))


def test_estados_verificada_y_sin_verificar():
    v = _ventana(_factura(verificacion="doble"),
                 _factura(num_factura="F-2", documento_id="d2",
                          verificacion="simple"))
    assert v.tabla.item(0, C_ESTADO).text() == ICONO_ESTADO[OK]
    assert v.tabla.item(1, C_ESTADO).text() == ICONO_SIN_VERIFICAR
    assert v.filas[1]["estado"] == OK         # se puede exportar igual


def test_la_ficha_ensena_datos_y_cuadre():
    v = _ventana(_factura(verificacion="doble"))
    texto = _textos(v)
    assert "PROVEEDOR PRUEBA" in texto and "B12345674" in texto
    assert "100,00 + 21,00" in texto and "121,00" in texto
    assert "coinciden en todo" in texto
    assert "OTROS SERVICIOS" in texto


def test_discrepancia_se_ve_y_se_resuelve_con_la_segunda_lectura():
    v = _ventana(_factura(verificacion="doble", discrepancias=(DISC_TOTAL,)))
    assert v.tabla.item(0, C_ESTADO).text() == ICONO_ESTADO[REVISAR]
    assert v.tabla.item(0, C_TOTAL).background().color().name() == "#fff3cd"
    texto = _textos(v)
    assert "Total" in texto and "131,00" in texto and "121,00" in texto
    usar_segunda = v.ficha.botones_discrepancia[1]
    usar_segunda.click()
    assert v.tabla.item(0, C_TOTAL).text() == "131,00"
    assert not v.filas[0]["factura"].discrepancias
    # Con el total de la segunda lectura ya no cuadra: queda para revisar.
    assert v.filas[0]["estado"] == REVISAR


def test_discrepancia_se_descarta_si_la_primera_es_buena():
    v = _ventana(_factura(verificacion="doble", discrepancias=(DISC_TOTAL,)))
    v.ficha.botones_discrepancia[0].click()
    assert v.tabla.item(0, C_TOTAL).text() == "121,00"
    assert v.tabla.item(0, C_ESTADO).text() == ICONO_ESTADO[OK]


def test_nif_de_la_segunda_lectura_se_aplica():
    disc = {"campo": "emisor_nif", "etiqueta": "NIF del emisor",
            "valor_1": "B12345670", "valor_2": "B-12345674",
            "campo_factura": "nif", "texto": "Doble lectura: NIF"}
    v = _ventana(_factura(nif="B12345670", verificacion="doble",
                          discrepancias=(disc,)))
    v.ficha.botones_discrepancia[1].click()
    assert v.tabla.item(0, C_NIF).text() == "B12345674"


def test_dialogo_de_modelos_guarda_y_no_admite_alias():
    d = DialogoModelos()
    d.combo_principal.setCurrentText("gemini-flash-latest")
    d.combo_respaldo.setCurrentText("gemini-3.7-flash")
    next(b for b in d.botones_modo.buttons()
         if b.property("modo") == "dudosas").setChecked(True)
    d.tarifas["gemini-3.8-flash"][0].setValue(1.0)
    d.tarifas["gemini-3.8-flash"][1].setValue(5.0)
    d.guardar()
    assert extraccion.modelos_configurados() == ["gemini-3.8-flash",
                                                 "gemini-3.7-flash"]
    assert extraccion.modo_doble_lectura() == "dudosas"
    from facturas_excel import costes
    assert costes.precio_de("gemini-3.8-flash") == ((1.0, 5.0), True)
    assert ajustes.leer("modelo_principal") == "gemini-3.8-flash"
