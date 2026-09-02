"""Cuenta del PGC y subclave GXX: lo que mas problemas da (gasoleo, agua,
telefonia). En Aplifisa la 628 NO se puede dejar sin subclave.
"""

from facturas_excel.conceptos import (
    SUBCLAVES_628, asignar_concepto, subclave_628,
)
from facturas_excel.modelo import Factura
from facturas_excel.validacion import REVISAR, validar


def test_el_gasoleo_va_al_gas_por_criterio_de_la_asesoria():
    # Criterio del usuario (2026-09-02): "gas es gasoleo y derivados", asi que
    # el combustible va a G16, no a otros suministros. Asi lo tiene ademas
    # configurado en Aplifisa.
    assert subclave_628("Gasoleo A del mes") == "G16"
    assert subclave_628("Repsol gasolina 95") == "G16"
    assert subclave_628("Gas natural Redexis") == "G16"


def test_los_suministros_tipicos_van_a_su_subclave():
    assert subclave_628("HIDROGEA consumo de agua") == "G15"
    assert subclave_628("IBERDROLA energia electrica") == "G14"
    assert subclave_628("ORANGE cuota fija movil") == "G17"
    assert subclave_628("Telefonica fibra e internet") == "G17"


def test_una_gasolinera_es_combustible_aunque_no_diga_gasoleo():
    assert asignar_concepto("gasto", "AREA DE SERVICIO DE EJEMPLO SL") == "628"
    assert subclave_628("AREA DE SERVICIO DE EJEMPLO SL") == "G16"


def test_la_628_sin_subclave_se_marca_para_revisar():
    f = Factura(nombre="PROVEEDOR", nif="B12345674", fecha="31/01/2025",
                num_factura="1", concepto="628", base_iva=100.0, pct_iva=21.0,
                cuota_iva=21.0, total_impreso=121.0)
    res = validar(f)
    assert res.estado == REVISAR
    assert any("628 necesita subclave" in m for m in res.mensajes)

    f.subclave = "G16"
    assert not any("subclave" in m for m in validar(f).mensajes)


def test_las_subclaves_son_las_que_pide_aplifisa():
    assert list(SUBCLAVES_628) == ["G14", "G15", "G16", "G17", "G18"]


# ------------------------------- textos parametrizados en Aplifisa -----------
def test_cada_concepto_tiene_su_texto_y_no_se_repite():
    from facturas_excel.conceptos import TEXTOS_APLIFISA, texto_para
    textos = list(TEXTOS_APLIFISA.values())
    assert len(textos) == len(set(textos))     # dos conceptos no pueden compartir
    assert texto_para("628", "G16") == "GASOLEO"
    assert texto_para("628", "G15") == "AGUA"
    assert texto_para("600") == "COMPRAS"
    # Sin subclave en una 628 no se inventa nada: mejor el codigo de siempre.
    assert texto_para("628") is None
    assert texto_para("999") is None


def test_al_exportar_se_cambia_el_codigo_por_el_texto(monkeypatch, tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from facturas_excel import ajustes
    from facturas_excel.app import VentanaPrincipal

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(ajustes, "dir_datos", lambda: str(tmp_path))
    v = VentanaPrincipal(comprobar_updates=False)

    f = Factura(nombre="GASOLINERA", nif="B12345674", fecha="31/01/2025",
                num_factura="1", concepto="628", base_iva=100.0, pct_iva=21.0,
                cuota_iva=21.0, total_impreso=121.0)
    f.subclave = "G16"

    # Sin configurar: va el codigo, como siempre.
    ajustes.guardar("concepto_texto", False)
    assert v._para_aplifisa([f])[0].concepto == "628"

    # Configurado: va el texto, y Aplifisa le pone la subclave sola.
    ajustes.guardar("concepto_texto", True)
    salida = v._para_aplifisa([f])
    assert salida[0].concepto == "GASOLEO"
    assert f.concepto == "628"          # el original no se toca
