"""Fecha de la factura y cuadre del lote.

El programa NO trabaja por trimestres: se usa igual para un trimestre que para
un requerimiento de varios años, asi que la fecha solo se comprueba para saber
si la lectura es buena, y el resumen suma TODO lo cargado.
"""

from datetime import date

from facturas_excel.modelo import Factura
from facturas_excel.resumen import describir, iva_desglosado, resumir
from facturas_excel.validacion import OK, REVISAR, fecha_de, validar


def factura(fecha, base=100.0, iva=21.0, irpf=None):
    f = Factura(nombre="PROVEEDOR", nif="B86561412", fecha=fecha, num_factura="1",
                concepto="601", base_iva=base, pct_iva=21.0, cuota_iva=iva,
                total_impreso=round(base + iva - (irpf or 0), 2))
    if irpf:
        f.base_irpf, f.pct_irpf, f.cuota_irpf = base, 15.0, irpf
    return f


def test_fecha_de_entiende_los_formatos_habituales():
    assert fecha_de("04/06/2026") == date(2026, 6, 4)
    assert fecha_de("04-06-2026") == date(2026, 6, 4)
    assert fecha_de("2026-06-04") == date(2026, 6, 4)
    assert fecha_de("no es fecha") is None
    assert fecha_de(None) is None


def test_una_factura_vieja_no_se_marca():
    # Antes salia en ambar por "fuera del trimestre" y confundia: en un
    # requerimiento las facturas son de cualquier fecha y todas valen.
    assert validar(factura("15/03/2019")).estado == OK


def test_fecha_ilegible_se_marca_para_revisar():
    res = validar(factura("1//2026"))
    assert res.estado == REVISAR
    assert any("No se entiende la fecha" in m for m in res.mensajes)


def test_resumen_suma_base_iva_y_retencion():
    t = resumir([factura("04/06/2026", 53.02, 11.13),
                 factura("12/05/2025", 200.0, 42.0),
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


def test_varios_tipos_de_iva_se_desglosan_en_una_sola_celda():
    diez = factura("04/06/2026", 100.0, 10.0)
    diez.pct_iva = 10.0
    veintiuno = factura("05/06/2026", 200.0, 42.0)
    veintiuno.pct_iva = 21.0

    t = resumir([diez, veintiuno])

    assert t.iva == 52.0
    assert t.iva_por_tipo == {10.0: 10.0, 21.0: 42.0}
    assert iva_desglosado(t) == "10%: 10,00 € · 21%: 42,00 €"


def test_un_solo_tipo_de_iva_mantiene_el_total_sencillo():
    t = resumir([factura("04/06/2026", 100.0, 21.0)])
    assert iva_desglosado(t) == "21,00 €"

