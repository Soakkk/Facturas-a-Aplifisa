"""Abonos: proveedores que imprimen el signo menos DETRAS del numero.

Coca-Cola imprime "TOTAL: 15,51- EUROS" para un abono. Perder ese menos
registra como compra lo que habia que devolver al cliente.
"""

from facturas_excel.extraccion import _num
from facturas_excel.procesar import a_total_factura, construir
from facturas_excel.resumen import resumir
from facturas_excel.validacion import OK, validar

CLIENTE = "12345678Z"


def abono(**extra):
    d = dict(emisor_nombre="COCA-COLA EUROPACIFIC PARTNERS IBERIA, S.L.U.",
             emisor_nif="B86561412", receptor_nif=CLIENTE,
             num_factura="4533583066", fecha="04/06/2026",
             lineas_iva=[{"base": "12,29-", "tipo_iva": 21.0, "cuota_iva": "2,58-",
                          "pct_requiv": 5.20, "cuota_requiv": "0,64-"}],
             total="15,51-", cuenta_gasto="600")
    d.update(extra)
    return construir(d, CLIENTE, "CLIENTE DE PRUEBA", "lote.pdf", 9)


def test_num_entiende_el_signo_detras():
    assert _num("15,51-") == -15.51
    assert _num("12,29-") == -12.29
    assert _num("1.234,56-") == -1234.56


def test_num_sigue_leyendo_lo_normal():
    assert _num("15,51") == 15.51
    assert _num("1.234,56") == 1234.56
    assert _num(-15.51) == -15.51
    assert _num(15.51) == 15.51
    assert _num(None) is None
    assert _num("") is None
    assert _num("no es un numero") is None


def test_el_abono_se_lee_entero_y_en_negativo():
    # Antes float("15,51-") petaba y _num devolvia None: el importe se perdia.
    f = abono().facturas[0]
    assert (f.base_iva, f.cuota_iva, f.cuota_requiv) == (-12.29, -2.58, -0.64)
    assert f.total_impreso == -15.51
    assert validar(f).estado == OK


def test_el_total_factura_de_un_abono_es_negativo():
    assert a_total_factura(abono()).facturas[0].base_iva == -15.51


def test_un_abono_con_el_signo_perdido_en_el_desglose_se_corrige():
    pr = abono(lineas_iva=[{"base": 12.29, "tipo_iva": 21.0, "cuota_iva": 2.58,
                            "pct_requiv": 5.20, "cuota_requiv": 0.64}])
    f = pr.facturas[0]
    assert (f.base_iva, f.cuota_iva, f.cuota_requiv) == (-12.29, -2.58, -0.64)
    assert validar(f).estado == OK


def test_abono_emitido_es_ingreso_negativo_y_reduce_las_ventas():
    cliente = "12345678Z"
    datos = dict(
        emisor_nombre="CLIENTE DE PRUEBA", emisor_nif=cliente,
        receptor_nombre="COMPRADOR DE PRUEBA SL", receptor_nif="B30048276",
        num_factura="AB-VENTA-1", fecha="16/04/2026",
        lineas_iva=[{"base": 50, "tipo_iva": 21, "cuota_iva": 10.5}],
        total=-60.5, cuenta_ingreso="700", subclave_ingreso="I01",
    )
    pr = construir(datos, cliente, "CLIENTE DE PRUEBA")

    assert pr.tipo == "venta"
    assert (pr.cuenta, pr.gxx) == ("700", "I01")
    assert (pr.facturas[0].base_iva, pr.facturas[0].cuota_iva,
            pr.facturas[0].total_impreso) == (-50, -10.5, -60.5)

    venta_normal = construir({**datos, "num_factura": "VENTA-2",
                              "lineas_iva": [{"base": 100, "tipo_iva": 21,
                                               "cuota_iva": 21}],
                              "total": 121}, cliente).facturas[0]
    total = resumir([venta_normal, pr.facturas[0]])
    assert (total.base, total.iva, total.total) == (50, 10.5, 60.5)
