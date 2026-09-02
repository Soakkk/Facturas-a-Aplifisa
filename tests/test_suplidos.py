"""Suplidos: importes pagados por cuenta del cliente, sin base ni IVA."""

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
        "cuenta_gasto": "623",
        "subclave_gxx": "G19",
    }
    datos.update(cambios)
    return datos


def test_extrae_el_suplido_y_hace_cuadrar_la_factura():
    pr = construir(datos_suplidos(), CLIENTE, "CLIENTE DE PRUEBA")
    f = pr.facturas[0]

    assert f.suplidos == 109.08
    assert validar(f).estado == OK


def test_en_varios_tipos_el_suplido_solo_se_registra_una_vez():
    datos = datos_suplidos(
        lineas_iva=[
            {"base": 50.0, "tipo_iva": 21.0, "cuota_iva": 10.5},
            {"base": 50.0, "tipo_iva": 10.0, "cuota_iva": 5.0},
        ],
        total=224.58,
    )
    pr = construir(datos, CLIENTE, "CLIENTE DE PRUEBA")

    assert [f.suplidos for f in pr.facturas] == [109.08, None]
    assert not pr.aviso


def test_en_recargo_el_suplido_se_incluye_en_el_apunte_por_total_sin_duplicarlo():
    pr = construir(datos_suplidos(), CLIENTE, "CLIENTE DE PRUEBA")
    total = a_total_factura(pr).facturas[0]

    assert total.base_iva == 230.08
    assert total.suplidos is None


def test_el_suplido_llega_a_la_columna_configurada_de_aplifisa(tmp_path):
    from openpyxl import load_workbook

    from facturas_excel.config_columnas import ConfigColumnas
    from facturas_excel.exportar import exportar_excel

    f = construir(datos_suplidos(), CLIENTE, "CLIENTE DE PRUEBA").facturas[0]
    ruta = tmp_path / "gastos.xlsx"
    config = ConfigColumnas(
        tipo="COMPRAS/GASTOS", columnas={"suplidos": "A"})

    exportar_excel([f], config, str(ruta))

    hoja = load_workbook(ruta).active
    assert hoja["A2"].value == "109,08"


def test_la_configuracion_de_aplifisa_reserva_la_columna_l_para_suplidos():
    from facturas_excel.config_columnas import leer_config

    raiz = Path(__file__).resolve().parents[1]
    assert leer_config(raiz / "config" / "gastos.xml").columnas["suplidos"] == "L"
