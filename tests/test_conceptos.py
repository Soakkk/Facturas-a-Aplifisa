"""Cuenta del PGC y subclave GXX: lo que mas problemas da (gasoleo, agua,
telefonia). En Aplifisa la 628 NO se puede dejar sin subclave.
"""

from facturas_excel.conceptos import (
    SUBCLAVES_628, asignar_concepto, subclave_628,
)
from facturas_excel.modelo import Factura
from facturas_excel.validacion import REVISAR, validar


def test_el_gasoleo_no_se_va_al_gas():
    # "gas" cazaba dentro de "gasoleo" y el combustible acababa en G16.
    assert subclave_628("Gasoleo A del mes") == "G18"
    assert subclave_628("Repsol gasolina 95") == "G18"
    assert subclave_628("Gas natural Redexis") == "G16"


def test_los_suministros_tipicos_van_a_su_subclave():
    assert subclave_628("HIDROGEA consumo de agua") == "G15"
    assert subclave_628("IBERDROLA energia electrica") == "G14"
    assert subclave_628("ORANGE cuota fija movil") == "G17"
    assert subclave_628("Telefonica fibra e internet") == "G17"


def test_una_gasolinera_es_combustible_aunque_no_diga_gasoleo():
    assert asignar_concepto("gasto", "AREA DE SERVICIO DE EJEMPLO SL") == "628"
    assert subclave_628("AREA DE SERVICIO DE EJEMPLO SL") == "G18"


def test_la_628_sin_subclave_se_marca_para_revisar():
    f = Factura(nombre="PROVEEDOR", nif="B12345674", fecha="31/01/2025",
                num_factura="1", concepto="628", base_iva=100.0, pct_iva=21.0,
                cuota_iva=21.0, total_impreso=121.0)
    res = validar(f)
    assert res.estado == REVISAR
    assert any("628 necesita subclave" in m for m in res.mensajes)

    f.subclave = "G18"
    assert not any("subclave" in m for m in validar(f).mensajes)


def test_las_subclaves_son_las_que_pide_aplifisa():
    assert list(SUBCLAVES_628) == ["G14", "G15", "G16", "G17", "G18"]
