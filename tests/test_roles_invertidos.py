"""Ventas leídas al revés: el cliente como destinatario de su propia factura.

Hay facturas que el propio cliente hace con sus datos en un recuadro pequeño,
sin la etiqueta «N.I.F.», y los del comprador en el recuadro grande del sobre,
con «N.I.F.». Gemini a veces toma al comprador por emisor y la venta acababa
en gastos (paquete de facturas emitidas de un transportista, 14/10/2026). Si
el número es de la serie que numera el propio cliente, se corrige y se avisa.
"""
import pytest

from facturas_excel import procesar
from facturas_excel.procesar import corregir_roles_invertidos, preparar_lote

CLIENTE = "12345678Z"
COMPRADOR = "B12345674"
OTRO = "A12345674"


def _lectura(num, emisor, receptor, total=121.0):
    return {"emisor_nombre": f"EMPRESA {emisor}", "emisor_nif": emisor,
            "receptor_nombre": f"EMPRESA {receptor}", "receptor_nif": receptor,
            "num_factura": num, "fecha": "31/07/2026", "total": total,
            "lineas_iva": [{"base": 100.0, "tipo_iva": 21, "cuota_iva": 21.0}],
            "cuenta_ingreso": "705", "subclave_ingreso": "I01",
            "cuenta_gasto": "629", "subclave_gxx": "G44"}


def _registros(*lecturas):
    return [(b"", "paquete.pdf", i + 1, d) for i, d in enumerate(lecturas)]


@pytest.fixture(autouse=True)
def sin_registro(monkeypatch):
    monkeypatch.setattr(procesar, "_lo_exportado", lambda *a, **k: ((), set()))


def test_una_venta_de_la_serie_leida_al_reves_vuelve_a_ser_ingreso():
    regs = _registros(_lectura("000065", CLIENTE, COMPRADOR),
                      _lectura("000066", CLIENTE, OTRO),
                      _lectura("000067", COMPRADOR, CLIENTE),     # al revés
                      _lectura("000068", CLIENTE, OTRO))
    tipos = [pr.tipo for _, pr in preparar_lote(regs, "CLIENTE PRUEBA", CLIENTE)]
    assert tipos == ["venta"] * 4
    pr = preparar_lote(regs, "CLIENTE PRUEBA", CLIENTE)[2][1]
    assert pr.facturas[0].nif == COMPRADOR
    assert "LEÍDO AL REVÉS" in pr.aviso and "000065–000068" in pr.aviso


def test_los_datos_de_gemini_no_se_tocan():
    al_reves = _lectura("000067", COMPRADOR, CLIENTE)
    regs = _registros(_lectura("000065", CLIENTE, OTRO),
                      _lectura("000066", CLIENTE, OTRO), al_reves)
    corregir_roles_invertidos(regs, CLIENTE)
    assert al_reves["emisor_nif"] == COMPRADOR and "_roles_corregidos" not in al_reves


@pytest.mark.parametrize("num", ["F-000067", "000300", "2026/123", "", None])
def test_un_gasto_de_otra_serie_sigue_siendo_gasto(num):
    regs = _registros(_lectura("000065", CLIENTE, OTRO),
                      _lectura("000066", CLIENTE, OTRO),
                      _lectura(num, COMPRADOR, CLIENTE))
    assert preparar_lote(regs, "CLIENTE PRUEBA", CLIENTE)[2][1].tipo == "gasto"


def test_con_una_sola_venta_no_hay_serie_de_la_que_fiarse():
    regs = _registros(_lectura("000065", CLIENTE, OTRO),
                      _lectura("000066", COMPRADOR, CLIENTE))
    assert preparar_lote(regs, "CLIENTE PRUEBA", CLIENTE)[1][1].tipo == "gasto"


def test_la_serie_tambien_sale_de_las_ventas_ya_exportadas(monkeypatch):
    monkeypatch.setattr(procesar, "_lo_exportado",
                        lambda *a, **k: (["000063", "000064"], set()))
    regs = _registros(_lectura("000065", COMPRADOR, CLIENTE))
    assert preparar_lote(regs, "CLIENTE PRUEBA", CLIENTE)[0][1].tipo == "venta"


def test_un_proveedor_conocido_con_numero_parecido_sigue_siendo_gasto(monkeypatch):
    monkeypatch.setattr(procesar, "_lo_exportado",
                        lambda *a, **k: (["000063", "000064"], {COMPRADOR}))
    regs = _registros(_lectura("000065", COMPRADOR, CLIENTE))
    assert preparar_lote(regs, "CLIENTE PRUEBA", CLIENTE)[0][1].tipo == "gasto"


def test_un_numero_ya_emitido_no_se_da_la_vuelta():
    # El mismo número que una venta del lote: es otra cosa (un duplicado, una
    # factura del proveedor con el mismo número), no la venta al revés.
    regs = _registros(_lectura("000065", CLIENTE, OTRO),
                      _lectura("000066", CLIENTE, OTRO),
                      _lectura("000066", COMPRADOR, CLIENTE))
    assert preparar_lote(regs, "CLIENTE PRUEBA", CLIENTE)[2][1].tipo == "gasto"


def test_la_lectura_le_explica_a_gemini_quien_es_el_emisor():
    from facturas_excel.extraccion import _PROMPT
    assert "NO te fies de la posicion" in _PROMPT and "N.I.F." in _PROMPT
