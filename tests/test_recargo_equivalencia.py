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
    assert validar(f, (2026, 2)).estado == OK


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
    assert all(validar(f, (2026, 2)).estado == OK for f in pr.facturas)
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
    assert validar(f, (2026, 2)).estado == OK


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


def test_avisa_de_las_anotaciones_a_mano():
    pr = procesar(datos_coca(hay_anotaciones_manuscritas=True))
    assert "escrito a mano" in pr.aviso
    assert pr.facturas[0].base_iva == 114.98  # manda lo impreso
