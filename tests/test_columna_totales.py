"""La columna de totales: el desglose completo para cuadrar la suma a mano.

El usuario lo pidió así: base imponible, IVA, recargo de equivalencia,
retención de profesional, etc., todo a la vista para comparar con lo que ha
sumado él y con el listado de Aplifisa. Lo que vale cero también se enseña.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from facturas_excel.app import VentanaPrincipal
from facturas_excel.modelo import Factura

_app = QApplication.instance() or QApplication([])


def _factura(**cambios):
    datos = dict(num_factura="F-1", fecha="03/09/2026", nombre="PROVEEDOR SL",
                 nif="B12345674", concepto="622", base_iva=100.0, pct_iva=21.0,
                 cuota_iva=21.0, total_impreso=121.0, confianza_ia="alta")
    datos.update(cambios)
    return Factura(**datos)


def _ventana():
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    gastos = [
        _factura(num_factura="G-1"),
        _factura(num_factura="G-2", base_iva=50.0, pct_iva=10.0, cuota_iva=5.0,
                 total_impreso=55.0),
        # Profesional con retención.
        _factura(num_factura="G-3", nif="12345678Z", base_iva=150.0,
                 cuota_iva=31.5, base_irpf=150.0, pct_irpf=15.0,
                 cuota_irpf=22.5, total_impreso=159.0),
    ]
    for f in gastos:
        v._anadir_fila(b"", f, "gasto", "622", "", "")
    v._anadir_fila(b"", _factura(num_factura="V-1", base_iva=200.0,
                                 cuota_iva=42.0, total_impreso=242.0),
                   "venta", "700", "", "")
    v._revalidar_todo()
    return v


def _texto(v):
    return v.vista_totales.toPlainText()


def _importes(bloque):
    """{concepto: texto del importe} de un bloque (cada celda, una línea)."""
    lineas = [l.strip() for l in bloque.splitlines() if l.strip()]
    return {concepto: importe for concepto, importe in zip(lineas, lineas[1:])
            if importe.endswith("€")}


def _euros(texto):
    texto = texto.rstrip("€").strip().replace("−", "-")
    return float(texto.replace(".", "").replace(",", "."))


def test_sale_el_desglose_completo_de_gastos_e_ingresos():
    v = _ventana()
    texto = _texto(v)
    for concepto in ("Base imponible", "IVA 21 %", "IVA 10 %", "Total IVA",
                     "Recargo de equivalencia", "Retención IRPF",
                     "Suplidos (sin IVA)", "Total"):
        assert concepto in texto
    gastos, ingresos = texto.split("Ingresos · Todo el lote")
    assert "Gastos · Todo el lote" in gastos
    assert "3 factura(s) · 3 línea(s)" in gastos
    assert "300,00 €" in gastos                       # base
    assert "57,50 €" in gastos                        # 21 + 5 + 31,50
    assert "−22,50 €" in gastos                       # la retención, restando
    assert "335,00 €" in gastos                       # 300 + 57,50 − 22,50
    assert "242,00 €" in ingresos


def test_lo_que_vale_cero_tambien_se_ve():
    v = _ventana()
    ingresos = _importes(_texto(v).split("Ingresos · Todo el lote")[1])
    # Sin recargo, sin retención y sin suplidos: se ven a 0,00.
    for concepto in ("Recargo de equivalencia", "Retención IRPF",
                     "Suplidos (sin IVA)"):
        assert ingresos[concepto] == "0,00 €"


def test_el_iva_va_de_mayor_a_menor_tipo():
    texto = _texto(_ventana())
    assert texto.index("IVA 21 %") < texto.index("IVA 10 %")


def test_las_lineas_suman_el_total():
    """Lo que el usuario suma a mano con el desglose da el total que sale."""
    v = _ventana()
    gastos = _importes(_texto(v).split("Ingresos · Todo el lote")[0])
    assert gastos["Retención IRPF"] == "−22,50 €"
    suma = sum(_euros(gastos[c]) for c in (
        "Base imponible", "Total IVA", "Recargo de equivalencia",
        "Retención IRPF", "Suplidos (sin IVA)"))
    assert round(suma, 2) == _euros(gastos["Total"]) == 335.0
    # Y el IVA por tipos suma el total IVA.
    assert round(_euros(gastos["IVA 21 %"]) + _euros(gastos["IVA 10 %"]), 2) \
        == _euros(gastos["Total IVA"])


def test_ocultar_quita_la_columna_y_el_menu_la_devuelve():
    v = _ventana()
    v.show()
    _app.processEvents()
    v._ver_resumen(False)
    _app.processEvents()
    assert not v.lado_card.isVisible()
    assert not v.accion_resumen.isChecked()
    v.accion_resumen.setChecked(True)
    _app.processEvents()
    assert v.lado_card.isVisible()
    assert v.split_revision.sizes()[2] >= 200


def test_un_abono_con_retencion_no_sale_con_doble_signo():
    v = _ventana()
    v._anadir_fila(b"", _factura(num_factura="AB-1", nif="12345678Z",
                                 base_iva=-150.0, cuota_iva=-31.5,
                                 base_irpf=-150.0, pct_irpf=15.0,
                                 cuota_irpf=-22.5, total_impreso=-159.0),
                   "gasto", "622", "", "")
    v._revalidar_todo()
    copiado = [v.tabla_resumen.item(r, c).text()
               for r in range(v.tabla_resumen.rowCount())
               for c in range(v.tabla_resumen.columnCount())
               if v.tabla_resumen.item(r, c)]
    assert not any("−-" in t or "--" in t for t in copiado)
    assert "−-" not in _texto(v)


def test_el_iva_sin_tipo_tiene_su_linea_y_el_desglose_suma():
    v = _ventana()
    v._anadir_fila(b"", _factura(num_factura="G-9", base_iva=100.0,
                                 pct_iva=None, cuota_iva=10.0,
                                 total_impreso=110.0),
                   "gasto", "622", "", "")
    v._revalidar_todo()
    gastos = _importes(_texto(v).split("Ingresos · Todo el lote")[0])
    por_tipo = sum(_euros(i) for c, i in gastos.items()
                   if c.startswith("IVA "))
    assert gastos["IVA sin tipo (falta el %)"] == "10,00 €"
    assert round(por_tipo, 2) == _euros(gastos["Total IVA"])


def test_con_filtro_lo_que_se_ve_va_primero():
    v = _ventana()
    v.txt_buscar.setText("G-3")
    texto = _texto(v)
    assert texto.index("Lo que se ve") < texto.index("Gastos · Todo el lote")
    v.txt_buscar.setText("")
    assert "Lo que se ve" not in _texto(v)


def test_el_periodo_no_se_parte_en_el_titulo():
    v = _ventana()
    if "3T" in v.lbl_resumen_titulo.text():
        assert "3T 2026" in v.lbl_resumen_titulo.text()


def test_el_ancho_de_los_totales_se_guarda_aunque_esten_ocultos(monkeypatch):
    from facturas_excel import ajustes
    guardado = {}
    monkeypatch.setattr(ajustes, "guardar",
                        lambda clave, valor: guardado.__setitem__(clave, valor))
    monkeypatch.setattr(ajustes, "leer",
                        lambda clave, defecto=None: guardado.get(clave, defecto))
    v = _ventana()
    v.resize(1600, 900)
    v.show()
    _app.processEvents()
    v.split_revision.setSizes([900, 400, 380])
    _app.processEvents()
    ancho = v.split_revision.sizes()[2]
    v._guardar_divisores()
    v._ver_resumen(False)
    _app.processEvents()
    v._guardar_divisores()
    assert guardado["split_revision_v4"][2] == ancho
    v._ver_resumen(True)
    _app.processEvents()
    assert abs(v.split_revision.sizes()[2] - ancho) <= 10


def test_el_nombre_vuelve_a_su_minimo_al_estrechar_de_golpe():
    from facturas_excel.tabla_facturas import (
        ANCHO_MIN_NOMBRE, C_NOMBRE, TablaFacturas,
    )
    t = TablaFacturas()
    t.resize(2200, 300)
    t.show()
    _app.processEvents()
    assert t.columnWidth(C_NOMBRE) > ANCHO_MIN_NOMBRE
    t.resize(900, 300)
    _app.processEvents()
    assert t.columnWidth(C_NOMBRE) == ANCHO_MIN_NOMBRE


def test_un_nombre_de_cliente_largo_se_ve_entero_si_hay_sitio():
    v = _ventana()
    v.resize(1920, 1000)
    v.show()
    _app.processEvents()
    nombre = "COMERCIAL DE SUMINISTROS INDUSTRIALES DEL MEDITERRANEO SL"
    v._poner_cliente(f"{nombre}  ·  B12345674")
    _app.processEvents()
    etiqueta = v.lbl_cliente
    assert etiqueta._visible(etiqueta.contentsRect().width()) == etiqueta.text()
