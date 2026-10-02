"""Los totales: el desglose completo para cuadrar la suma a mano.

El usuario lo pidió así: base imponible, IVA, recargo de equivalencia,
retención de profesional, etc., todo a la vista para comparar con lo que ha
sumado él y con el listado de Aplifisa. Lo que vale cero también se enseña.
Desde la 1.20 van abajo, a lo ancho, como el listado de Aplifisa: una fila
por ámbito y una columna por importe.
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


def _filas(v):
    """{«Gastos · Todo el lote»: {cabecera: texto}} de la tabla de totales."""
    t = v.tabla_totales
    cabeceras = [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
    return {t.item(r, 0).text(): {cabeceras[c]: t.item(r, c).text()
                                  for c in range(1, t.columnCount())}
            for r in range(t.rowCount())}


def _ambitos(v):
    return [v.tabla_totales.item(r, 0).text()
            for r in range(v.tabla_totales.rowCount())]


def _euros(texto):
    texto = texto.rstrip("€").strip().replace("−", "-")
    return float(texto.replace(".", "").replace(",", "."))


def test_sale_el_desglose_completo_de_gastos_e_ingresos():
    v = _ventana()
    filas = _filas(v)
    gastos = filas["Gastos · Todo el lote"]
    ingresos = filas["Ingresos · Todo el lote"]
    for concepto in ("Base imponible", "IVA 21 %", "IVA 10 %", "Total IVA",
                     "Recargo", "Retención", "Suplidos", "Total"):
        assert concepto in gastos
    assert gastos["Nº"] == "3"
    fila = _ambitos(v).index("Gastos · Todo el lote")
    assert v.tabla_totales.item(fila, 1).toolTip() == "3 factura(s) · 3 línea(s)"
    assert gastos["Base imponible"] == "300,00 €"
    assert gastos["Total IVA"] == "57,50 €"            # 21 + 5 + 31,50
    assert gastos["Retención"] == "−22,50 €"           # la retención, restando
    assert gastos["Total"] == "335,00 €"               # 300 + 57,50 − 22,50
    assert ingresos["Total"] == "242,00 €"


def test_lo_que_vale_cero_tambien_se_ve():
    v = _ventana()
    ingresos = _filas(v)["Ingresos · Todo el lote"]
    # Sin recargo, sin retención y sin suplidos: se ven a 0,00.
    for concepto in ("Recargo", "Retención", "Suplidos"):
        assert ingresos[concepto] == "0,00 €"


def test_el_iva_va_de_mayor_a_menor_tipo():
    cabeceras = list(_filas(_ventana())["Gastos · Todo el lote"])
    assert cabeceras.index("IVA 21 %") < cabeceras.index("IVA 10 %")


def test_las_lineas_suman_el_total():
    """Lo que el usuario suma a mano con el desglose da el total que sale."""
    gastos = _filas(_ventana())["Gastos · Todo el lote"]
    assert gastos["Retención"] == "−22,50 €"
    suma = sum(_euros(gastos[c]) for c in (
        "Base imponible", "Total IVA", "Recargo", "Retención", "Suplidos"))
    assert round(suma, 2) == _euros(gastos["Total"]) == 335.0
    # Y el IVA por tipos suma el total IVA.
    assert round(_euros(gastos["IVA 21 %"]) + _euros(gastos["IVA 10 %"]), 2) \
        == _euros(gastos["Total IVA"])


def test_ocultar_quita_los_totales_y_el_menu_los_devuelve():
    v = _ventana()
    v.show()
    _app.processEvents()
    v._ver_resumen(False)
    _app.processEvents()
    assert not v.totales_card.isVisible()
    assert not v.accion_resumen.isChecked()
    v.accion_resumen.setChecked(True)
    _app.processEvents()
    _app.processEvents()
    assert v.totales_card.isVisible()
    assert v.split_principal.sizes()[1] >= 150


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
    en_pantalla = [t for fila in _filas(v).values() for t in fila.values()]
    assert not any("−-" in t or "--" in t for t in en_pantalla)


def test_el_iva_sin_tipo_tiene_su_columna_y_el_desglose_suma():
    v = _ventana()
    v._anadir_fila(b"", _factura(num_factura="G-9", base_iva=100.0,
                                 pct_iva=None, cuota_iva=10.0,
                                 total_impreso=110.0),
                   "gasto", "622", "", "")
    v._revalidar_todo()
    gastos = _filas(v)["Gastos · Todo el lote"]
    por_tipo = sum(_euros(i) for c, i in gastos.items()
                   if c.startswith("IVA "))
    assert gastos["IVA sin tipo"] == "10,00 €"
    assert round(por_tipo, 2) == _euros(gastos["Total IVA"])


def test_con_filtro_lo_que_se_ve_va_primero():
    v = _ventana()
    v.txt_buscar.setText("12345678Z")             # solo el profesional
    ambitos = _ambitos(v)
    assert ambitos[0] == "Gastos · Lo que se ve (filtro)"
    assert ambitos.index("Gastos · Lo que se ve (filtro)") \
        < ambitos.index("Gastos · Todo el lote")
    assert _filas(v)["Gastos · Lo que se ve (filtro)"]["Total"] == "159,00 €"
    # Copiar y el listado PDF siguen con el orden de siempre.
    assert v.tabla_resumen.item(0, 0).text() == "TOTAL LOTE"
    v.txt_buscar.setText("")
    assert not any("Lo que se ve" in a for a in _ambitos(v))


def test_el_periodo_no_se_parte_en_el_titulo():
    v = _ventana()
    if "3T" in v.lbl_resumen_titulo.text():
        assert "3T 2026" in v.lbl_resumen_titulo.text()


def test_el_alto_de_los_totales_se_guarda_aunque_esten_ocultos(monkeypatch):
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
    # Como si lo arrastrara el usuario: desde ahí manda su alto.
    v.split_principal.setSizes([500, 260])
    v.split_principal.splitterMoved.emit(500, 1)
    _app.processEvents()
    alto = v.split_principal.sizes()[1]
    assert guardado["alto_totales_a_mano"] is True
    v._guardar_divisores()
    v._ver_resumen(False)
    _app.processEvents()
    v._guardar_divisores()
    assert guardado["split_principal"][1] == alto
    v._ver_resumen(True)
    _app.processEvents()
    _app.processEvents()
    assert abs(v.split_principal.sizes()[1] - alto) <= 10


def test_su_suma_va_bajo_cada_columna_de_los_totales():
    """Cada casilla de «Su suma» bajo su columna, del mismo ancho, aunque
    la ventana sea estrecha y los totales se desplacen."""
    from facturas_excel.su_suma import PRIMERA_COLUMNA_IMPORTE
    for ancho in (1920, 1024):
        v = _ventana()
        v.resize(ancho, 760)
        v.show()
        for _ in range(3):
            _app.processEvents()
        arriba, abajo = v.tabla_totales, v.tabla_su_suma
        assert arriba.columnCount() == abajo.columnCount()
        for c in range(arriba.columnCount()):
            assert arriba.columnWidth(c) == abajo.columnWidth(c)
        assert arriba.mapTo(v, arriba.viewport().pos()).x() \
            == abajo.mapTo(v, abajo.viewport().pos()).x()
        # El ámbito se lee entero y la base tiene sitio para su cifra.
        medida = arriba.fontMetrics()
        assert arriba.columnWidth(0) >= medida.horizontalAdvance(
            "Ingresos · Todo el lote")
        campo = v.tabla_su_suma.campo("base")
        assert abajo.columnWidth(PRIMERA_COLUMNA_IMPORTE) \
            >= campo.fontMetrics().horizontalAdvance("99.999,99")
        v.close()


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


def test_un_nombre_de_cliente_largo_no_se_corta_si_sobra_sitio():
    """Si el nombre sale recortado, es que no había más sitio: nunca con un
    hueco vacío al lado (antes se cortaba a 260 px aunque sobrara cinta).
    No depende del tamaño de la pantalla de quien pase la prueba."""
    v = _ventana()
    v.resize(1920, 1000)
    v.show()
    _app.processEvents()
    nombre = "COMERCIAL DE SUMINISTROS INDUSTRIALES DEL MEDITERRANEO SL"
    v._poner_cliente(f"{nombre}  ·  B12345674")
    for _ in range(3):
        _app.processEvents()
    etiqueta = v.lbl_cliente
    recortado = (etiqueta._visible(etiqueta.contentsRect().width())
                 != etiqueta.text())
    hueco = etiqueta.parentWidget().layout().cellRect(0, 3).width()
    assert not (recortado and hueco > 4)


def test_con_filtro_de_tipo_la_fila_vacia_no_va_delante():
    """Con «Gastos» marcado, lo que se ve de ingresos es cero: va con las
    demás filas, no la primera (la primera es lo que se está cuadrando)."""
    v = _ventana()
    v.botones_tipo["gasto"].click()
    ambitos = _ambitos(v)
    assert ambitos[0] == "Gastos · Lo que se ve (filtro)"
    assert ambitos.index("Ingresos · Lo que se ve (filtro)") \
        > ambitos.index("Gastos · Todo el lote")


def test_en_recargo_los_gastos_con_retencion_dicen_por_que_llevan_desglose():
    from facturas_excel.resumen import resumir
    v = _ventana()
    profesional = _factura(num_factura="G-3", nif="12345678Z", base_iva=150.0,
                           cuota_iva=31.5, base_irpf=150.0, pct_irpf=15.0,
                           cuota_irpf=22.5, total_impreso=159.0)
    t = resumir([profesional])
    v._pintar_tabla_totales([("TOTAL LOTE", "Gastos", t, True)], True, [21.0])
    assert "las que llevan retención, con su desglose" \
        in v.tabla_totales.item(0, 0).toolTip()
    assert _filas(v)["Gastos · Todo el lote"]["Base imponible"] == "150,00 €"


def _ventana_grande(monkeypatch):
    from facturas_excel import ajustes
    guardado = {}
    monkeypatch.setattr(ajustes, "guardar",
                        lambda clave, valor: guardado.__setitem__(clave, valor))
    monkeypatch.setattr(ajustes, "leer",
                        lambda clave, defecto=None: guardado.get(clave, defecto))
    v = _ventana()
    v.resize(1600, 1000)
    v.show()
    for _ in range(3):
        _app.processEvents()
    return v


def test_los_totales_se_ajustan_a_sus_filas_al_filtrar(monkeypatch):
    """Sin mover el divisor, al filtrar salen más filas y se ven todas
    (hasta el 40 % del alto); al quitar el filtro, vuelve a lo justo."""
    v = _ventana_grande(monkeypatch)
    tabla = v.tabla_totales
    sin_filtro = v.split_principal.sizes()[1]
    assert tabla.height() >= tabla.maximumHeight() - 2
    v.txt_buscar.setText("12345678Z")
    for _ in range(3):
        _app.processEvents()
    assert tabla.rowCount() == 4
    tamanos = v.split_principal.sizes()
    tope = int(0.4 * sum(tamanos))
    assert tamanos[1] > sin_filtro
    assert tamanos[1] <= tope + 2
    # Todas a la vista, salvo que no quepan en el 40 % (pantalla pequeña).
    assert tabla.height() >= tabla.maximumHeight() - 2 or tamanos[1] >= tope - 2
    v.txt_buscar.setText("")
    for _ in range(3):
        _app.processEvents()
    assert abs(v.split_principal.sizes()[1] - sin_filtro) <= 2


def test_movido_a_mano_el_alto_de_los_totales_no_cambia_solo(monkeypatch):
    v = _ventana_grande(monkeypatch)
    v.split_principal.setSizes([600, 300])
    v.split_principal.splitterMoved.emit(600, 1)
    _app.processEvents()
    alto = v.split_principal.sizes()[1]
    v.txt_buscar.setText("12345678Z")
    for _ in range(3):
        _app.processEvents()
    assert v.split_principal.sizes()[1] == alto
