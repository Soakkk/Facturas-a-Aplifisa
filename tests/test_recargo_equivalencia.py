"""Recargo de equivalencia (gastos por el total) y post-facturaciones.

Los importes son los de una factura real de Coca-Cola, pero el cliente es
inventado: los datos personales de clientes no entran en el repo.
"""

from facturas_excel.procesar import a_total_factura, construir, marcar_sustituidas
from facturas_excel.validacion import OK, validar

CLIENTE = "12345678Z"          # DNI de ejemplo, no es de nadie
PROVEEDOR = "B86561412"


def datos_coca(num="4532677314", base=114.98, iva=24.15, requiv=5.98,
               total=145.11, **extra):
    d = dict(emisor_nombre="COCA-COLA EUROPACIFIC PARTNERS IBERIA, S.L.U.",
             emisor_nif=PROVEEDOR, receptor_nombre="CLIENTE DE PRUEBA",
             receptor_nif=CLIENTE, num_factura=num, fecha="07/05/2026",
             lineas_iva=[{"base": base, "tipo_iva": 21.0, "cuota_iva": iva}],
             base_requiv=base, pct_requiv=5.20, cuota_requiv=requiv,
             total=total, cuenta_gasto="600")
    d.update(extra)
    return d


def procesar(datos):
    return construir(datos, CLIENTE, "CLIENTE DE PRUEBA", "lote.pdf", 1)


def test_el_recargo_se_extrae_y_el_total_cuadra():
    # Sin leer el recargo, base+cuota daba 139,13 frente a los 145,11 impresos
    # y toda factura de un cliente en recargo salia con un descuadre falso.
    f = procesar(datos_coca()).facturas[0]
    assert (f.base_requiv, f.pct_requiv, f.cuota_requiv) == (114.98, 5.2, 5.98)
    assert validar(f).estado == OK


def test_cada_tipo_de_iva_lleva_su_propio_recargo():
    # Las facturas pequenas (BIMBO, Antonio y Canizares) mezclan tipos y cada
    # uno tiene su recargo: 21->5,2 / 10->1,4 / 4->0,5.
    d = datos_coca(total=31.06)
    d["lineas_iva"] = [
        {"base": 19.96, "tipo_iva": 10.0, "cuota_iva": 2.00,
         "pct_requiv": 1.4, "cuota_requiv": 0.28},
        {"base": 8.44, "tipo_iva": 4.0, "cuota_iva": 0.34,
         "pct_requiv": 0.5, "cuota_requiv": 0.04},
    ]
    l1, l2 = procesar(d).facturas
    assert (l1.pct_requiv, l1.cuota_requiv, l1.base_requiv) == (1.4, 0.28, 19.96)
    assert (l2.pct_requiv, l2.cuota_requiv, l2.base_requiv) == (0.5, 0.04, 8.44)


def test_el_recargo_a_nivel_factura_sigue_valiendo_con_un_solo_tipo():
    # Respaldo por si Gemini lo devuelve al estilo viejo (Coca-Cola, todo al 21%).
    f = procesar(datos_coca()).facturas[0]
    assert (f.base_requiv, f.pct_requiv, f.cuota_requiv) == (114.98, 5.2, 5.98)


def test_con_varios_tipos_de_iva_ninguna_fila_descuadra_ella_sola():
    # Cada fila es un trozo de la factura: comprobarla contra el total impreso
    # daba un descuadre falso en TODAS las lineas.
    d = datos_coca(total=31.06)
    d["lineas_iva"] = [{"base": 19.96, "tipo_iva": 10.0, "cuota_iva": 2.00,
                        "pct_requiv": 1.4, "cuota_requiv": 0.28},
                       {"base": 8.44, "tipo_iva": 4.0, "cuota_iva": 0.34,
                        "pct_requiv": 0.5, "cuota_requiv": 0.04}]
    pr = procesar(d)
    assert all(validar(f).estado == OK for f in pr.facturas)
    assert not pr.aviso          # 19,96+2,00+0,28+8,44+0,34+0,04 = 31,06


def test_con_varios_tipos_el_cuadre_se_hace_sumando_todas_las_lineas():
    d = datos_coca(total=99.99)   # total mal leido
    d["lineas_iva"] = [{"base": 19.96, "tipo_iva": 10.0, "cuota_iva": 2.00,
                        "pct_requiv": 1.4, "cuota_requiv": 0.28},
                       {"base": 8.44, "tipo_iva": 4.0, "cuota_iva": 0.34,
                        "pct_requiv": 0.5, "cuota_requiv": 0.04}]
    assert "no cuadra" in procesar(d).aviso


def test_total_factura_suma_el_recargo_de_todos_los_tipos():
    d = datos_coca(total=31.06)
    d["lineas_iva"] = [{"base": 19.96, "tipo_iva": 10.0, "cuota_iva": 2.00,
                        "pct_requiv": 1.4, "cuota_requiv": 0.28},
                       {"base": 8.44, "tipo_iva": 4.0, "cuota_iva": 0.34,
                        "pct_requiv": 0.5, "cuota_requiv": 0.04}]
    pr = a_total_factura(procesar(d))
    assert len(pr.facturas) == 1
    assert pr.facturas[0].base_iva == 31.06


def test_total_factura_deja_un_solo_apunte_por_el_total():
    pr = a_total_factura(procesar(datos_coca()))
    assert len(pr.facturas) == 1
    f = pr.facturas[0]
    assert f.base_iva == 145.11          # 114,98 + 24,15 + 5,98
    assert f.pct_iva is None and f.cuota_iva is None
    assert f.cuota_requiv is None
    assert validar(f).estado == OK


def test_total_factura_no_toca_el_lote_original():
    pr = procesar(datos_coca())
    a_total_factura(pr)
    assert pr.facturas[0].base_iva == 114.98  # se puede desmarcar la casilla


def test_total_factura_conserva_la_retencion():
    """El IVA no deducible va al gasto, pero la retención se declara aparte
    (111/115) y no se puede perder (1.24; antes no se resumía)."""
    d = datos_coca(num="A1", base=100.0, iva=21.0, requiv=None, total=106.0)
    d.update(base_requiv=None, pct_requiv=None, base_irpf=100.0, pct_irpf=15.0,
             cuota_irpf=15.0, cuenta_gasto="623")
    [f] = a_total_factura(procesar(d)).facturas
    assert f.base_iva == 121.0 and f.iva_incluido_en_base
    assert (f.base_irpf, f.pct_irpf, f.cuota_irpf) == (100.0, 15.0, 15.0)
    # 121 − 15 = 106: cuadra con el total impreso.
    assert not any("no cuadra" in str(m) for m in validar(f).mensajes)


def test_total_factura_no_toca_las_ventas():
    pr = procesar(datos_coca())
    pr.tipo = "venta"
    assert a_total_factura(pr).facturas[0].base_iva == 114.98


def test_la_postfacturacion_marca_la_factura_sustituida():
    vieja = procesar(datos_coca(num="4532023141", base=65.12, iva=13.68,
                                requiv=3.39, total=82.19))
    nueva = procesar(datos_coca(num="5907798669", base=52.83, iva=11.09,
                                requiv=2.75, total=66.67,
                                sustituye_a="4532023141"))
    assert marcar_sustituidas([vieja, nueva]) == 1
    assert vieja.sustituida_por == "5907798669"
    assert "SUSTITUIDA" in vieja.aviso
    assert not nueva.aviso


def test_no_marca_nada_si_la_sustituida_no_esta_en_el_lote():
    nueva = procesar(datos_coca(num="5907798669", sustituye_a="9999999999"))
    assert marcar_sustituidas([nueva]) == 0
    assert not nueva.aviso


def test_avisa_solo_si_lo_escrito_a_mano_toca_a_los_importes():
    # El asesor anota el CIF y numera las facturas para los requerimientos de
    # Hacienda: avisar de eso pondria TODAS en ambar y el semaforo no serviria.
    pr = procesar(datos_coca(manuscrito_en_importes=True))
    assert "escritos a mano" in pr.aviso
    assert pr.facturas[0].base_iva == 114.98  # manda lo impreso

    tranquila = procesar(datos_coca(manuscrito_en_importes=False))
    assert not tranquila.aviso


# --------------------------------------- pares tipo -> recargo (2026-09-02)
def test_el_recargo_que_no_toca_a_su_tipo_de_iva_se_avisa():
    """El regimen fija los pares: 21->5,2 / 10->1,4 / 4->0,5, siempre."""
    from facturas_excel.modelo import Factura
    from facturas_excel.validacion import REVISAR, validar

    def con(pct_iva, pct_req, base=100.0):
        f = Factura(nombre="PROVEEDOR", nif="B12345674", fecha="31/01/2025",
                    num_factura="1", concepto="600", subclave="G01",
                    base_iva=base, pct_iva=pct_iva,
                    cuota_iva=round(base * pct_iva / 100, 2),
                    base_requiv=base, pct_requiv=pct_req,
                    cuota_requiv=round(base * pct_req / 100, 2))
        f.total_impreso = round(base + (f.cuota_iva or 0) + (f.cuota_requiv or 0), 2)
        return f

    for tipo, recargo in ((21.0, 5.2), (10.0, 1.4), (4.0, 0.5)):
        assert validar(con(tipo, recargo)).estado == "ok"

    res = validar(con(21.0, 1.4))
    assert res.estado == REVISAR
    assert any("es 5,2% (o 1,75% en el tabaco), no 1,4%" in m
               for m in res.mensajes)
    res = validar(con(10.0, 5.2))
    assert any("es 1,4%, no 5,2%" in m for m in res.mensajes)


def test_los_recargos_que_marca_la_ley_no_se_avisan():
    """Ley del IVA, art. 161: el tabaco (al 21 %) lleva el 1,75 %, y entre
    2022 y 2024 lo que iba al 5 % (luz, gas, algunos alimentos) el 0,62 %."""
    from facturas_excel.modelo import Factura
    from facturas_excel.validacion import validar

    for tipo, recargo in ((21.0, 1.75), (5.0, 0.62)):
        f = Factura(nombre="PROVEEDOR", nif="B12345674", fecha="31/01/2024",
                    num_factura="1", concepto="600", subclave="G01",
                    base_iva=100.0, pct_iva=tipo, cuota_iva=tipo,
                    base_requiv=100.0, pct_requiv=recargo, cuota_requiv=recargo)
        f.total_impreso = round(100.0 + tipo + recargo, 2)
        assert validar(f).estado == "ok", (tipo, recargo)


def test_una_cuota_de_recargo_mal_calculada_es_error():
    from facturas_excel.modelo import Factura
    from facturas_excel.validacion import ERROR, validar

    f = Factura(nombre="PROVEEDOR", nif="B12345674", fecha="31/01/2025",
                num_factura="1", concepto="600", subclave="G01", base_iva=100.0,
                pct_iva=21.0, cuota_iva=21.0, base_requiv=100.0, pct_requiv=5.2,
                cuota_requiv=9.99)
    assert validar(f).estado == ERROR


# ------------------------- minorista o mayorista: como se registra el recargo
def _preparar_ventana(monkeypatch, tmp_path, regimen_guardado=""):
    """Ventana lista para probar, sin que salte ningun dialogo modal."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from facturas_excel import clientes
    from facturas_excel.dialogo_cliente import DialogoCliente
    from facturas_excel.dialogo_recargo import DialogoRecargo

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(clientes, "dir_datos", lambda: str(tmp_path))
    monkeypatch.setattr(DialogoRecargo, "exec", lambda self: 0)
    monkeypatch.setattr(DialogoCliente, "exec", lambda self: 0)
    if regimen_guardado:
        clientes.guardar_regimen_recargo("12345678Z", regimen_guardado, "TIENDA")


def _ventana_con_recargo(monkeypatch, tmp_path, regimen_guardado=""):
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.procesar import preparar_lote

    _preparar_ventana(monkeypatch, tmp_path, regimen_guardado)

    crudos = [(b"", "taco.pdf", 1, datos_coca())]
    v = VentanaPrincipal(comprobar_updates=False)
    v._rutas_actuales = ["taco.pdf"]
    v._on_terminado(preparar_lote(crudos, "TIENDA", "12345678Z"),
                    "TIENDA", "12345678Z", crudos)
    return v


def test_sin_facturas_con_recargo_la_eleccion_ni_aparece(monkeypatch, tmp_path):
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.procesar import preparar_lote

    _preparar_ventana(monkeypatch, tmp_path)
    datos = dict(datos_coca())
    datos["lineas_iva"] = [{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0}]
    datos["total"] = 121.0
    for campo in ("base_requiv", "pct_requiv", "cuota_requiv"):
        datos[campo] = None
    crudos = [(b"", "taco.pdf", 1, datos)]
    v = VentanaPrincipal(comprobar_updates=False)
    v._rutas_actuales = ["taco.pdf"]
    v._on_terminado(preparar_lote(crudos, "TIENDA", "12345678Z"),
                    "TIENDA", "12345678Z", crudos)

    assert not v._hay_recargo
    assert v._facturas_con_recargo() == 0
    assert v.fila_recargo.isHidden()


def _totales(v):
    """{ámbito: {cabecera: (texto, globo)}} de la tabla de totales."""
    t = v.tabla_totales
    cabeceras = [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
    return {t.item(r, 0).text(): {
                cabeceras[c]: (t.item(r, c).text(), t.item(r, c).toolTip())
                for c in range(1, t.columnCount())}
            for r in range(t.rowCount())}


def test_el_minorista_registra_por_el_total(monkeypatch, tmp_path):
    from facturas_excel.app import C_BASE, C_CUOTA, C_PCT
    from facturas_excel.clientes import TOTAL

    v = _ventana_con_recargo(monkeypatch, tmp_path, TOTAL)

    assert v._por_el_total()
    assert not v.fila_recargo.isHidden()
    assert v.lbl_hay_recargo.text() == "Factura(s) con recargo detectado"
    assert v.tabla.rowCount() == 1                     # un solo apunte
    assert v.tabla.item(0, C_PCT).text() == ""         # sin desglose de IVA
    assert v.tabla.item(0, C_CUOTA).text() == ""
    assert v.tabla.item(0, C_BASE).text() == "145,11"  # base + IVA + recargo
    # En los totales, solo el total y por qué (no un desglose a cero).
    gastos = _totales(v)["Gastos · Todo el lote"]
    assert gastos["Total"] == ("145,11 €", "")
    texto, globo = gastos["Base imponible"]
    assert texto == "—" and "por el total factura" in globo
    assert "recargo de equivalencia" in v.lbl_resumen_titulo.text()


def test_el_mayorista_registra_con_desglose(monkeypatch, tmp_path):
    from facturas_excel.app import C_BASE, C_PCT
    from facturas_excel.clientes import DESGLOSE

    v = _ventana_con_recargo(monkeypatch, tmp_path, DESGLOSE)

    assert not v._por_el_total()
    assert v.tabla.item(0, C_PCT).text() == "21,00"
    assert v.tabla.item(0, C_BASE).text() == "114,98"
    # El recargo sale en su columna de los totales, con su importe.
    recargo, _globo = _totales(v)["Gastos · Todo el lote"]["Recargo"]
    assert recargo not in ("", "—", "0,00 €")


def test_cambiar_de_regimen_rehace_el_lote_sin_volver_a_leer(monkeypatch, tmp_path):
    from facturas_excel.app import C_BASE
    from facturas_excel.clientes import DESGLOSE, TOTAL

    v = _ventana_con_recargo(monkeypatch, tmp_path, DESGLOSE)
    assert v.tabla.item(0, C_BASE).text() == "114,98"

    v.combo_recargo.setCurrentIndex(v.combo_recargo.findData(TOTAL))

    assert v.tabla.item(0, C_BASE).text() == "145,11"
    assert v._hay_recargo


def test_por_el_total_lo_corregido_no_se_pierde_ni_queda_corregido_sin_dato(
        monkeypatch, tmp_path):
    """La línea a la vista es un resumen que se rehace desde las originales:
    el nº corregido tiene que llegar a ellas, y un importe (que no tiene a
    qué línea ir) no puede dejar la factura «Corregida» con el dato leído."""
    from facturas_excel.app import C_BASE, C_NUM
    from facturas_excel.clientes import TOTAL
    v = _ventana_con_recargo(monkeypatch, tmp_path, TOTAL)
    v.tabla.item(0, C_NUM).setText("NUEVO-1")
    v._rellenar_tabla()
    v._revalidar_todo()
    assert v.tabla.item(0, C_NUM).text() == "NUEVO-1"
    assert v.filas[0]["factura"].revision_corregida

    # Otra factura igual, corrigiendo los importes de la línea resumida: al
    # rehacer la tabla (otro taco, quitar un bloque…) la corrección sigue
    # ahí, no vuelve en silencio lo que leyó la IA.
    from facturas_excel.app import C_TOTAL
    otra = _ventana_con_recargo(monkeypatch, tmp_path, TOTAL)
    otra.tabla.item(0, C_BASE).setText("150,00")
    otra.tabla.item(0, C_TOTAL).setText("150,00")
    assert otra.filas[0].presentacion == "corregida"
    otra._rellenar_tabla()
    otra._revalidar_todo()
    assert otra.tabla.item(0, C_BASE).text() == "150,00"
    assert otra.filas[0].presentacion == "corregida"
    assert _totales(otra)["Gastos · Todo el lote"]["Total"][0] == "150,00 €"


def test_por_el_total_una_venta_mal_clasificada_recupera_su_iva(
        monkeypatch, tmp_path):
    """Si la IA la tomó por gasto (y se resumió por el total), al pasarla a
    ingreso vuelve su desglose: una venta no se registra por el total."""
    from facturas_excel.app import C_BASE, C_CUOTA, C_PCT, C_TIPO
    from facturas_excel.clientes import TOTAL
    v = _ventana_con_recargo(monkeypatch, tmp_path, TOTAL)
    assert v.tabla.item(0, C_PCT).text() == ""             # resumida
    control = v.tabla.cellWidget(0, C_TIPO)
    control.setCurrentIndex(control.findData("venta"))
    f = v.filas[0]["factura"]
    assert v.filas[0].tipo == "venta"
    assert v.tabla.item(0, C_BASE).text() == "114,98"
    assert v.tabla.item(0, C_PCT).text() == "21,00"
    assert v.tabla.item(0, C_CUOTA).text() == "24,15"
    assert not f.iva_incluido_en_base
    assert f.revision_corregida
    # Y de vuelta a gasto, otra vez por el total.
    control = v.tabla.cellWidget(0, C_TIPO)
    control.setCurrentIndex(control.findData("gasto"))
    assert v.tabla.item(0, C_BASE).text() == "145,11"


# --------------- 1.22.1: manda la ley (el régimen del cliente), no lo impreso
TELEFONO = "A12345674"        # CIF de ejemplo
SOCIEDAD = "B76543214"        # cliente S.L. de ejemplo


def datos_telefono(num="T-1", base=100.0, receptor=CLIENTE, **extra):
    """Un servicio (teléfono): no lleva recargo aunque el cliente esté en él."""
    extra.setdefault("total", round(base * 1.21, 2))
    d = datos_coca(num=num, base=base, iva=round(base * 0.21, 2), requiv=None,
                   receptor_nif=receptor,
                   emisor_nombre="TELEFONIA DE PRUEBA, S.A.",
                   emisor_nif=TELEFONO, cuenta_gasto="628", **extra)
    for campo in ("base_requiv", "pct_requiv", "cuota_requiv"):
        d[campo] = None
    return d


def _ventana_lote(monkeypatch, tmp_path, lista, regimen="", cliente=CLIENTE):
    from facturas_excel import clientes
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.procesar import preparar_lote

    _preparar_ventana(monkeypatch, tmp_path)
    if regimen:
        clientes.guardar_regimen_recargo(cliente, regimen, "TIENDA")
    crudos = [(b"", "taco.pdf", i + 1, d) for i, d in enumerate(lista)]
    v = VentanaPrincipal(comprobar_updates=False)
    v._rutas_actuales = ["taco.pdf"]
    v._on_terminado(preparar_lote(crudos, "TIENDA", cliente),
                    "TIENDA", cliente, crudos)
    return v


def _bases(v):
    from facturas_excel.app import C_BASE, C_PCT
    return [(v.tabla.item(r, C_BASE).text(), v.tabla.item(r, C_PCT).text())
            for r in range(v.tabla.rowCount())]


def test_el_minorista_lleva_por_el_total_tambien_lo_que_no_trae_recargo(
        monkeypatch, tmp_path):
    """No presenta el 303: no paga ni deduce IVA. Su teléfono va por el total
    aunque en el lote no haya ni una factura con recargo impreso."""
    from facturas_excel.clientes import TOTAL

    v = _ventana_lote(monkeypatch, tmp_path, [datos_telefono()], TOTAL)

    assert v._facturas_con_recargo() == 0
    assert v._por_el_total()
    assert not v.fila_recargo.isHidden()
    assert v.lbl_hay_recargo.text() == "Cliente en recargo"
    assert _bases(v) == [("121,00", "")]
    assert v.filas[0].factura.iva_incluido_en_base
    assert "recargo de equivalencia" in v.lbl_resumen_titulo.text()


def test_el_minorista_con_lote_mezclado_lo_lleva_todo_por_el_total(
        monkeypatch, tmp_path):
    from facturas_excel.clientes import TOTAL

    v = _ventana_lote(monkeypatch, tmp_path,
                      [datos_coca(), datos_telefono()], TOTAL)

    assert v._por_el_total()
    assert v.lbl_hay_recargo.text() == "Factura(s) con recargo detectado"
    assert sorted(_bases(v)) == [("121,00", ""), ("145,11", "")]


def test_el_minorista_lleva_el_alquiler_por_el_total_con_su_retencion(
        monkeypatch, tmp_path):
    """El alquiler del local de un minorista en recargo: su IVA tampoco se
    deduce (va al gasto), y la retención se conserva para el 115."""
    from facturas_excel.app import C_CUOTA_IRPF, C_PCT_IRPF

    alquiler = datos_telefono(num="ALQ-1", base_irpf=100.0, pct_irpf=19.0,
                              cuota_irpf=19.0, total=102.0)
    from facturas_excel.clientes import TOTAL
    v = _ventana_lote(monkeypatch, tmp_path, [alquiler], TOTAL)

    assert v._por_el_total()
    assert _bases(v) == [("121,00", "")]
    assert v.tabla.item(0, C_PCT_IRPF).text() == "19,00"
    assert v.tabla.item(0, C_CUOTA_IRPF).text() == "19,00"
    assert v.filas[0]["estado"] != "error"


def test_sin_estar_en_recargo_lo_que_no_trae_recargo_no_cambia(
        monkeypatch, tmp_path):
    from facturas_excel import clientes

    v = _ventana_lote(monkeypatch, tmp_path, [datos_telefono()],
                      clientes.DESGLOSE)
    assert not v._por_el_total() and v.fila_recargo.isHidden()
    assert _bases(v) == [("100,00", "21,00")]

    # Sin régimen guardado y sin recargo en el lote no se pregunta nada.
    otra = _ventana_lote(monkeypatch, tmp_path / "otro", [datos_telefono()])
    assert not otra._por_el_total() and otra.fila_recargo.isHidden()
    assert clientes.regimen_recargo(CLIENTE) == ""


def test_la_ley_no_deja_a_una_sociedad_estar_en_recargo():
    """Art. 148 de la Ley del IVA: solo personas físicas y comunidades de
    bienes. Una S.L. o una S.A., nunca."""
    from facturas_excel.clientes import puede_estar_en_recargo

    for nif in ("12345678Z", "X1234567L", "E12345674", "J12345674", ""):
        assert puede_estar_en_recargo(nif), nif
    for nif in ("B12345674", "A12345674", "F12345674", "ESB12345674"):
        assert not puede_estar_en_recargo(nif), nif


def test_una_sociedad_registra_con_desglose_aunque_le_cobren_recargo(
        monkeypatch, tmp_path):
    from facturas_excel import clientes
    from facturas_excel.dialogo_recargo import DialogoRecargo

    def no_se_pregunta(self):
        raise AssertionError("a una sociedad no se le pregunta el régimen")

    def sin_la_opcion_de_recargo(self):
        from PySide6.QtWidgets import QRadioButton
        [recargo] = [b for b in self.findChildren(QRadioButton)
                     if "recargo" in b.text().lower()]
        assert not recargo.isEnabled()
        return 0                                      # cancelar

    # Aunque se hubiera guardado «por el total» (versiones de antes).
    v = _ventana_lote(monkeypatch, tmp_path, [datos_coca(receptor_nif=SOCIEDAD)],
                      clientes.TOTAL, cliente=SOCIEDAD)
    assert not v._por_el_total()
    assert not v.fila_recargo.isHidden()
    assert "sociedad" in v.lbl_hay_recargo.text()
    # El recargo no se puede elegir (sí la actividad exenta).
    opcion = v.combo_recargo.model().item(
        v.combo_recargo.findData(clientes.TOTAL))
    assert not opcion.isEnabled()
    assert _bases(v) == [("114,98", "21,00")]

    # Y si no tiene nada guardado, ni se pregunta ni se guarda nada.
    monkeypatch.setattr(DialogoRecargo, "exec", no_se_pregunta)
    otra = _ventana_lote(monkeypatch, tmp_path / "otro",
                         [datos_coca(receptor_nif=SOCIEDAD)], cliente=SOCIEDAD)
    # Desde el menú sí se puede decir que tiene una actividad exenta, pero
    # el recargo no se ofrece.
    monkeypatch.setattr(DialogoRecargo, "exec", sin_la_opcion_de_recargo)
    otra._elegir_regimen_recargo()
    assert clientes.regimen_recargo(SOCIEDAD) == ""
    assert not otra._por_el_total()


def test_desde_el_menu_se_dice_que_esta_en_recargo_sin_esperar_a_una_factura(
        monkeypatch, tmp_path):
    """Configuración → Recargo de equivalencia de este cliente."""
    from facturas_excel import clientes
    from facturas_excel.dialogo_recargo import DialogoRecargo

    v = _ventana_lote(monkeypatch, tmp_path, [datos_telefono()])
    assert _bases(v) == [("100,00", "21,00")]

    elegido = {"valor": clientes.TOTAL}
    monkeypatch.setattr(DialogoRecargo, "exec", lambda self: 1)
    monkeypatch.setattr(DialogoRecargo, "elegido", lambda self: elegido["valor"])
    v._elegir_regimen_recargo()
    assert clientes.regimen_recargo(CLIENTE) == clientes.TOTAL
    assert v._por_el_total() and not v.fila_recargo.isHidden()
    assert _bases(v) == [("121,00", "")]

    elegido["valor"] = clientes.DESGLOSE
    v._elegir_regimen_recargo()
    assert not v._por_el_total() and v.fila_recargo.isHidden()
    assert _bases(v) == [("100,00", "21,00")]


def test_el_dialogo_desde_el_menu_explica_que_va_todo_por_el_total():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QLabel

    from facturas_excel.dialogo_recargo import DialogoRecargo

    QApplication.instance() or QApplication([])
    d = DialogoRecargo("TIENDA", 0)
    textos = " ".join(x.text() for x in d.findChildren(QLabel))
    assert "0 factura" not in textos
    assert "también las que no traen recargo impreso" in textos


def test_un_lote_guardado_antes_se_abre_con_el_criterio_de_la_ley(
        monkeypatch, tmp_path):
    """Una sesión de antes de la 1.22.1 (el teléfono de un minorista con su
    desglose) se rehace por el total al abrirla."""
    from facturas_excel import clientes, sesion
    from facturas_excel.app import VentanaPrincipal

    guardada = {}
    monkeypatch.setattr(sesion, "guardar", guardada.update)
    v = _ventana_lote(monkeypatch, tmp_path, [datos_telefono()])
    v._guardar_sesion()
    assert not guardada["hay_recargo"]
    assert _bases(v) == [("100,00", "21,00")]

    clientes.guardar_regimen_recargo(CLIENTE, clientes.TOTAL, "TIENDA")
    monkeypatch.setattr(sesion, "cargar", lambda: guardada)
    nueva = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    nueva._restaurar_sesion()
    assert nueva._por_el_total()
    assert _bases(nueva) == [("121,00", "")]
