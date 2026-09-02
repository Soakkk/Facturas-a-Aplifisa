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
    from facturas_excel.conceptos import catalogo, tabla_textos, texto_para
    textos = [t for _, _, t in tabla_textos()]
    assert len(textos) == len(set(textos))     # dos conceptos no pueden compartir
    assert len(textos) == len(catalogo())
    # El texto es el nombre que usa el propio Aplifisa.
    assert texto_para("628", "G16") == "SUMINISTROS GAS"
    assert texto_para("628", "G15") == "SUMINISTROS AGUA"
    assert texto_para("600", "G01") == "COMPRAS MERCADERIAS"
    # Lo que no existe en Aplifisa no se inventa: va el codigo de siempre.
    assert texto_para("628", "G99") is None
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
    assert salida[0].concepto == "SUMINISTROS GAS"
    assert f.concepto == "628"          # el original no se toca


# ------------------------------- catalogo real de Aplifisa -------------------
def test_el_catalogo_es_el_de_aplifisa():
    from facturas_excel.conceptos import catalogo, descripcion_de, subclaves_de
    assert ("628", "G16", "SUMINISTROS GAS") in catalogo()
    assert descripcion_de("646", "G47") == "REGULARIZACION RETA (A INGRESAR)"
    # Una cuenta con varias subclaves: hay que elegir
    assert len(subclaves_de("623")) == 4
    assert len(subclaves_de("681")) == 6


def test_una_pareja_que_no_existe_en_aplifisa_se_avisa():
    f = Factura(nombre="X", nif="B12345674", fecha="31/01/2025", num_factura="1",
                concepto="628", base_iva=100.0, pct_iva=21.0, cuota_iva=21.0,
                total_impreso=121.0)
    f.subclave = "G99"
    assert any("no existe en Aplifisa" in m for m in validar(f).mensajes)

    f.concepto, f.subclave = "615", None      # cuenta que Aplifisa no ofrece
    assert any("no está en la lista" in m for m in validar(f).mensajes)


def test_si_la_cuenta_solo_tiene_una_subclave_no_se_pregunta():
    from facturas_excel.validacion import OK
    f = Factura(nombre="X", nif="B12345674", fecha="31/01/2025", num_factura="1",
                concepto="622", base_iva=100.0, pct_iva=21.0, cuota_iva=21.0,
                total_impreso=121.0)
    assert validar(f).estado == OK            # la 622 solo tiene G13


def test_la_subclave_unica_se_rellena_sola():
    from facturas_excel.procesar import construir
    datos = {"emisor_nif": "B12345674", "emisor_nombre": "TALLER EJEMPLO",
             "receptor_nif": "12345678Z", "receptor_nombre": "CLIENTE",
             "num_factura": "1", "fecha": "31/01/2025",
             "lineas_iva": [{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0}],
             "total": 121.0, "cuenta_gasto": "622", "subclave_gxx": None}
    pr = construir(datos, "12345678Z", "CLIENTE")
    assert pr.gxx == "G13"
