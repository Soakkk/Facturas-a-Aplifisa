"""Búsqueda y periodo del lote cargado, sin consultar históricos."""

from facturas_excel.consulta import (
    detectar_periodo, facturas_unicas, coincide_busqueda, periodo_manual,
)
from facturas_excel.modelo import Factura


def factura(numero="F-1", fecha="15/02/2026", nombre="TALLERES ÁGUILA, S.L.",
            nif="B12345674", base=100.0, iva=21.0):
    return Factura(
        num_factura=numero, fecha=fecha, nombre=nombre, nif=nif,
        base_iva=base, cuota_iva=iva, total_impreso=base + iva,
    )


def test_busca_contraparte_sin_importar_acentos_puntuacion_o_forma_juridica():
    f = factura()

    assert coincide_busqueda(f, "talleres aguila")
    assert coincide_busqueda(f, "ÁGUILA sociedad limitada")
    assert not coincide_busqueda(f, "otro proveedor")


def test_busca_tambien_por_nif_numero_e_importe_espanol_exacto():
    f = factura(numero="FV/2026-004", base=1234.56, iva=259.26)

    assert coincide_busqueda(f, "b12345674")
    assert coincide_busqueda(f, "2026 004")
    assert coincide_busqueda(f, "1.234,56 €")
    assert not coincide_busqueda(f, "1.234,55")


def test_un_despiste_fuera_del_trimestre_no_convierte_el_lote_en_anual():
    lote = [
        factura("F-1", "15/01/2026"),
        factura("F-2", "15/02/2026"),
        factura("F-3", "15/03/2026"),
        factura("F-4", "02/04/2026"),
    ]

    periodo = detectar_periodo(lote)

    assert periodo.etiqueta == "1T 2026"
    assert periodo.contiene(lote[0])
    assert not periodo.contiene(lote[-1])


def test_un_lote_repartido_por_el_ejercicio_se_considera_anual():
    lote = [factura(f"F-{t}", f"15/{mes:02d}/2026")
            for t, mes in enumerate((1, 4, 7, 10), 1)]

    assert detectar_periodo(lote).etiqueta == "Anual 2026"
    assert periodo_manual(2026, "2").etiqueta == "2T 2026"


def test_una_factura_multi_iva_cuenta_una_factura_y_dos_lineas():
    lote = [
        factura("F-9", base=100, iva=21),
        factura("F-9", base=50, iva=5),
    ]
    for f in lote:
        f.documento_id = "documento-9"
        f.lineas_factura = 2

    assert facturas_unicas(lote) == 1
