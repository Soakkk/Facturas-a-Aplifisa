"""Trimestre que se trabaja y cuadre del lote."""

from facturas_excel.modelo import Factura
from facturas_excel.resumen import describir, resumir
from facturas_excel.validacion import (
    OK, REVISAR, detectar_periodo, periodo_de, validar,
)


def factura(fecha, base=100.0, iva=21.0, irpf=None):
    f = Factura(nombre="PROVEEDOR", nif="B86561412", fecha=fecha, num_factura="1",
                concepto="601", base_iva=base, pct_iva=21.0, cuota_iva=iva,
                total_impreso=round(base + iva - (irpf or 0), 2))
    if irpf:
        f.base_irpf, f.pct_irpf, f.cuota_irpf = base, 15.0, irpf
    return f


def test_periodo_de_reconoce_el_trimestre():
    assert periodo_de("04/06/2026") == (2026, 2)
    assert periodo_de("31/03/2026") == (2026, 1)
    assert periodo_de("01/10/2026") == (2026, 4)
    assert periodo_de("2026-06-04") == (2026, 2)
    assert periodo_de("no es fecha") is None
    assert periodo_de(None) is None


def test_detectar_periodo_coge_el_mayoritario():
    lote = [factura("04/06/2026"), factura("12/05/2026"), factura("15/03/2026")]
    assert detectar_periodo(lote) == (2026, 2)
    assert detectar_periodo([]) is None


def test_factura_de_otro_trimestre_se_marca_para_revisar():
    res = validar(factura("15/03/2026"), (2026, 2))
    assert res.estado == REVISAR
    assert any("FUERA DEL 2T 2026" in m for m in res.mensajes)


def test_factura_del_trimestre_no_se_marca():
    assert validar(factura("04/06/2026"), (2026, 2)).estado == OK


def test_sin_periodo_no_se_comprueba_el_trimestre():
    assert validar(factura("15/03/2026")).estado == OK


def test_resumen_suma_base_iva_y_retencion():
    t = resumir([factura("04/06/2026", 53.02, 11.13),
                 factura("12/05/2026", 200.0, 42.0),
                 factura("30/06/2026", 100.0, 21.0, irpf=15.0)])
    assert (t.base, t.iva, t.irpf) == (353.02, 74.13, 15.0)
    assert t.total == 412.15  # base + IVA - retencion


def test_el_texto_del_resumen_omite_el_irpf_si_no_lo_hay():
    texto = describir(resumir([factura("04/06/2026", 53.02, 11.13)]))
    assert "IRPF" not in texto
    assert "total factura 64,15 €" in texto


def test_modo_total_factura_para_recargo_de_equivalencia():
    t = resumir([factura("04/06/2026", 53.02, 11.13)])
    assert describir(t, solo_total=True) == "total factura 64,15 €"
