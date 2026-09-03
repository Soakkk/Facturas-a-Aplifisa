"""Suplidos: importes pagados por cuenta del cliente.

CRITERIO DEL USUARIO (2026-09-02, con su pantalla de Aplifisa delante): el
suplido se registra como una SEGUNDA LINEA DE BASE IMPONIBLE del mismo apunte,
sin % ni cuota de IVA. No va en la columna Suplidos.

    Base   %    Cuota
    100    21   21
    109,08  -    -        <- el suplido
    Importe neto: 230,08
"""

from pathlib import Path

from facturas_excel.procesar import a_total_factura, construir
from facturas_excel.validacion import OK, validar

CLIENTE = "12345678Z"


def datos_suplidos(**cambios):
    datos = {
        "emisor_nombre": "GESTORIA DE PRUEBA SL",
        "emisor_nif": "B86561412",
        "receptor_nombre": "CLIENTE DE PRUEBA",
        "receptor_nif": CLIENTE,
        "num_factura": "25/5887",
        "fecha": "13/11/2025",
        "lineas_iva": [{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0}],
        "suplidos": 109.08,
        "total": 230.08,
        "cuenta_gasto": "629",
        "subclave_gxx": "G22",
    }
    datos.update(cambios)
    return datos


def test_el_suplido_es_una_linea_mas_con_base_y_sin_iva():
    pr = construir(datos_suplidos(), CLIENTE, "CLIENTE DE PRUEBA")

    assert len(pr.facturas) == 2
    normal, suplido = pr.facturas
    assert (normal.base_iva, normal.pct_iva, normal.cuota_iva) == (100.0, 21.0, 21.0)
    assert suplido.base_iva == 109.08
    assert suplido.pct_iva is None and suplido.cuota_iva is None
    assert suplido.es_suplido
    # Y repite lo que identifica al apunte, como cualquier otra linea
    assert suplido.num_factura == normal.num_factura
    assert suplido.fecha == normal.fecha
    assert suplido.nombre == normal.nombre
    assert suplido.concepto == normal.concepto


def test_la_factura_cuadra_con_el_suplido_dentro():
    pr = construir(datos_suplidos(), CLIENTE, "CLIENTE DE PRUEBA")
    assert not pr.aviso                       # 100 + 21 + 109,08 = 230,08
    assert all(validar(f).estado == OK for f in pr.facturas)


def test_el_suplido_no_va_en_la_columna_suplidos():
    # Antes se exportaba en el campo Suplidos de Aplifisa; ya no.
    pr = construir(datos_suplidos(), CLIENTE, "CLIENTE DE PRUEBA")
    assert all(f.suplidos is None for f in pr.facturas)


def test_con_varios_tipos_de_iva_el_suplido_sigue_siendo_una_sola_linea():
    datos = datos_suplidos(
        lineas_iva=[
            {"base": 50.0, "tipo_iva": 21.0, "cuota_iva": 10.5},
            {"base": 50.0, "tipo_iva": 10.0, "cuota_iva": 5.0},
        ],
        total=224.58,
    )
    pr = construir(datos, CLIENTE, "CLIENTE DE PRUEBA")

    assert len(pr.facturas) == 3
    assert [f.es_suplido for f in pr.facturas] == [False, False, True]
    assert not pr.aviso                       # 50+10,5 + 50+5 + 109,08 = 224,58


def test_sin_suplido_no_se_añade_ninguna_linea():
    pr = construir(datos_suplidos(suplidos=None, total=121.0),
                   CLIENTE, "CLIENTE DE PRUEBA")
    assert len(pr.facturas) == 1
    assert not pr.facturas[0].es_suplido


def test_en_recargo_el_suplido_se_incluye_en_el_apunte_por_total():
    pr = construir(datos_suplidos(), CLIENTE, "CLIENTE DE PRUEBA")
    total = a_total_factura(pr).facturas[0]

    assert total.base_iva == 230.08           # 100 + 21 + 109,08
    assert total.suplidos is None and not total.es_suplido


def test_al_exportar_la_linea_del_suplido_lleva_base_y_deja_iva_vacio(tmp_path):
    from openpyxl import load_workbook

    from facturas_excel.config_columnas import leer_config
    from facturas_excel.exportar import exportar_excel

    raiz = Path(__file__).resolve().parents[1]
    config = leer_config(raiz / "config" / "gastos.xml")
    pr = construir(datos_suplidos(), CLIENTE, "CLIENTE DE PRUEBA")
    ruta = tmp_path / "gastos.xlsx"

    exportar_excel(pr.facturas, config, str(ruta))

    hoja = load_workbook(ruta).active
    base, pct, cuota = (config.columnas["base_iva"], config.columnas["pct_iva"],
                        config.columnas["cuota_iva"])
    assert hoja[f"{base}2"].value == "100,00"      # la linea normal
    assert hoja[f"{base}3"].value == "109,08"      # el suplido
    assert hoja[f"{pct}3"].value in (None, "")     # sin % ni cuota
    assert hoja[f"{cuota}3"].value in (None, "")
    # y la columna Suplidos se queda vacia
    assert hoja[f"{config.columnas['suplidos']}3"].value in (None, "")
