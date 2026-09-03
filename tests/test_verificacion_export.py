"""Doble contraste del archivo final.

El Excel es el ultimo paso antes de que los apuntes entren en la contabilidad,
y era el unico que nadie comprobaba: se vuelve a LEER lo escrito y se compara
con lo que hay en pantalla, linea por linea.
"""

from pathlib import Path

from openpyxl import load_workbook

from facturas_excel.config_columnas import leer_config
from facturas_excel.exportar import (
    exportar_excel, totales_del_excel, verificar_excel,
)
from facturas_excel.modelo import Factura

RAIZ = Path(__file__).resolve().parents[1]


def config():
    return leer_config(RAIZ / "config" / "gastos.xml")


def factura(num="FA-1", base=100.0, iva=21.0):
    return Factura(num_factura=num, fecha="31/01/2025", nombre="PROVEEDOR SL",
                   nif="B12345674", concepto="628", subclave="G16",
                   base_iva=base, pct_iva=21.0, cuota_iva=iva,
                   total_impreso=round(base + iva, 2))


def test_un_archivo_recien_escrito_no_tiene_ninguna_diferencia(tmp_path):
    facturas = [factura("FA-1"), factura("FA-2", 50.0, 10.5)]
    ruta = str(tmp_path / "gastos.xlsx")
    exportar_excel(facturas, config(), ruta)

    assert verificar_excel(facturas, config(), ruta) == []


def test_se_caza_un_importe_cambiado_en_el_archivo(tmp_path):
    facturas = [factura("FA-1")]
    ruta = str(tmp_path / "gastos.xlsx")
    exportar_excel(facturas, config(), ruta)

    # Alguien (o algo) toca el archivo por detras
    libro = load_workbook(ruta)
    columna = config().columnas["base_iva"]
    libro.active[f"{columna}2"] = "999,99"
    libro.save(ruta)

    fallos = verificar_excel(facturas, config(), ruta)
    assert len(fallos) == 1
    assert "999,99" in fallos[0] and "100,00" in fallos[0]


def test_se_caza_una_linea_que_falta(tmp_path):
    facturas = [factura("FA-1"), factura("FA-2")]
    ruta = str(tmp_path / "gastos.xlsx")
    exportar_excel(facturas[:1], config(), ruta)      # se escribe solo una

    fallos = verificar_excel(facturas, config(), ruta)
    assert any("deberían ser 2" in f for f in fallos)


def test_si_el_archivo_no_se_puede_leer_se_dice(tmp_path):
    fallos = verificar_excel([factura()], config(),
                             str(tmp_path / "no_existe.xlsx"))
    assert fallos and "no se pudo" in fallos[0].lower()


def test_los_totales_del_archivo_son_los_de_la_pantalla(tmp_path):
    from facturas_excel.resumen import resumir

    facturas = [factura("FA-1", 100.0, 21.0), factura("FA-2", 200.0, 42.0)]
    ruta = str(tmp_path / "gastos.xlsx")
    exportar_excel(facturas, config(), ruta)

    del_archivo = totales_del_excel(config(), ruta)
    en_pantalla = resumir(facturas)

    assert del_archivo["lineas"] == 2
    assert del_archivo["base_iva"] == en_pantalla.base == 300.0
    assert del_archivo["cuota_iva"] == en_pantalla.iva == 63.0


# ---------------------------------------------- orden de los apuntes ---------
def _f(num, fecha, base=100.0):
    return Factura(num_factura=num, fecha=fecha, nombre="PROVEEDOR SL",
                   nif="B12345674", concepto="628", subclave="G16",
                   base_iva=base, pct_iva=21.0, cuota_iva=round(base * .21, 2))


def test_por_orden_del_pdf_se_respeta_el_escaneo():
    """Aplifisa numera segun entran: asi el apunte nº 3 es la hoja 3."""
    from facturas_excel.exportar import ordenar_para_exportar

    lote = [_f("C", "31/12/2025"), _f("A", "31/01/2025"), _f("B", "30/06/2025")]
    assert [f.num_factura for f in ordenar_para_exportar(lote, "pdf")] == \
        ["C", "A", "B"]


def test_por_fecha_se_ordenan_de_la_mas_antigua_a_la_mas_nueva():
    from facturas_excel.exportar import ordenar_para_exportar

    lote = [_f("C", "31/12/2025"), _f("A", "31/01/2025"), _f("B", "30/06/2025")]
    assert [f.num_factura for f in ordenar_para_exportar(lote, "fecha")] == \
        ["A", "B", "C"]


def test_al_ordenar_por_fecha_no_se_separan_las_lineas_de_una_factura():
    """Una factura con dos tipos de IVA (o con suplido) son varias lineas del
    MISMO apunte: separarlas lo partiria en dos."""
    from facturas_excel.exportar import ordenar_para_exportar

    linea1 = _f("B", "30/06/2025", 100.0)
    linea2 = _f("B", "30/06/2025", 50.0)
    linea2.pct_iva = 10.0
    lote = [linea1, _f("A", "31/01/2025"), linea2]

    orden = ordenar_para_exportar(lote, "fecha")
    assert [f.num_factura for f in orden] == ["A", "B", "B"]
    assert [f.base_iva for f in orden[1:]] == [100.0, 50.0]


def test_las_facturas_sin_fecha_valida_van_al_final():
    from facturas_excel.exportar import ordenar_para_exportar

    lote = [_f("A", "sin fecha"), _f("B", "31/01/2025")]
    assert [f.num_factura for f in ordenar_para_exportar(lote, "fecha")] == \
        ["B", "A"]
