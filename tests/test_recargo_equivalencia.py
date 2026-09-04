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


def test_total_factura_respeta_los_gastos_con_retencion():
    d = datos_coca(num="A1", base=100.0, iva=21.0, requiv=None, total=106.0)
    d.update(base_requiv=None, pct_requiv=None, base_irpf=100.0, pct_irpf=15.0,
             cuota_irpf=15.0, cuenta_gasto="623")
    pr = a_total_factura(procesar(d))
    assert pr.facturas[0].base_iva == 100.0   # sin colapsar: el IRPF se declara
    assert "retención" in pr.aviso


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
    assert any("es 5,2%, no 1,4%" in m for m in res.mensajes)


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


def test_el_minorista_registra_por_el_total(monkeypatch, tmp_path):
    from facturas_excel.app import C_BASE, C_CUOTA, C_PCT
    from facturas_excel.clientes import TOTAL

    v = _ventana_con_recargo(monkeypatch, tmp_path, TOTAL)

    assert v._por_el_total()
    assert not v.fila_recargo.isHidden()
    assert v.chk_hay_recargo.isChecked()
    assert v.tabla.rowCount() == 1                     # un solo apunte
    assert v.tabla.item(0, C_PCT).text() == ""         # sin desglose de IVA
    assert v.tabla.item(0, C_CUOTA).text() == ""
    assert v.tabla.item(0, C_BASE).text() == "145,11"  # base + IVA + recargo


def test_el_mayorista_registra_con_desglose(monkeypatch, tmp_path):
    from facturas_excel.app import C_BASE, C_PCT
    from facturas_excel.clientes import DESGLOSE

    v = _ventana_con_recargo(monkeypatch, tmp_path, DESGLOSE)

    assert not v._por_el_total()
    assert v.tabla.item(0, C_PCT).text() == "21,00"
    assert v.tabla.item(0, C_BASE).text() == "114,98"


def test_cambiar_de_regimen_rehace_el_lote_sin_volver_a_leer(monkeypatch, tmp_path):
    from facturas_excel.app import C_BASE
    from facturas_excel.clientes import DESGLOSE, TOTAL

    v = _ventana_con_recargo(monkeypatch, tmp_path, DESGLOSE)
    assert v.tabla.item(0, C_BASE).text() == "114,98"

    v.combo_recargo.setCurrentIndex(v.combo_recargo.findData(TOTAL))

    assert v.tabla.item(0, C_BASE).text() == "145,11"
    assert v._hay_recargo
