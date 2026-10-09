"""Fallos vistos en el errores.log del usuario (1.24.0), con datos inventados.

- Exportar se rompía entero si un nombre traía un carácter de control en
  lugar de una letra con tilde («JOS?» por «JOSÉ»): openpyxl no lo admite.
- Un número de factura enorme en la serie de ventas hacía que el control de
  huecos recorriera miles de millones de números: MemoryError.
- La ventana de error salía con un hueco en blanco si el error no traía
  mensaje (el de memoria no lo trae).
"""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from facturas_excel.modelo import Factura
from facturas_excel.validacion import REVISAR, huecos_de_numeracion, validar

RAIZ = Path(__file__).resolve().parent.parent
NOMBRE_ROTO = "TTES. PEPE JOS\x01 PRUEBA S.L."      # «JOSÉ» mal leído


def _factura(**cambios):
    datos = dict(num_factura="F-1", fecha="03/09/2026", nombre="PROVEEDOR SL",
                 nif="B12345674", concepto="628", subclave="G16",
                 base_iva=100.0, pct_iva=21.0, cuota_iva=21.0,
                 total_impreso=121.0)
    datos.update(cambios)
    return Factura(**datos)


# ------------------------------------------------- caracteres que no se ven
def test_un_caracter_de_control_en_el_nombre_no_rompe_la_exportacion(tmp_path):
    from facturas_excel.config_columnas import leer_config
    from facturas_excel.exportar import exportar_excel, verificar_excel
    for xml in ("gastos.xml", "ingresos.xml"):
        cfg = leer_config(RAIZ / "config" / xml)
        facturas = [_factura(nombre=NOMBRE_ROTO),
                    _factura(num_factura="F-2", nombre="OTRO\x0bPROVEEDOR SL")]
        ruta = str(tmp_path / xml.replace(".xml", ".xlsx"))
        exportar_excel(facturas, cfg, ruta)
        assert verificar_excel(facturas, cfg, ruta) == []
        from openpyxl import load_workbook
        hoja = load_workbook(ruta).active
        textos = [str(c.value) for fila in hoja.iter_rows() for c in fila
                  if c.value is not None]
        assert any("TTES. PEPE JOS PRUEBA" in t for t in textos)
        assert not any("\x01" in t or "\x0b" in t for t in textos)


def test_el_nombre_con_un_caracter_que_no_se_ve_sale_en_ambar():
    res = validar(_factura(nombre=NOMBRE_ROTO))
    assert res.estado == REVISAR
    assert any("carácter que no se ve" in str(m) for m in res.mensajes)
    # Con tildes de verdad, nada.
    limpio = validar(_factura(nombre="TTES. PEPE JOSÉ PRUEBA S.L."))
    assert not any("carácter que no se ve" in str(m) for m in limpio.mensajes)


# -------------------------------------------------- huecos de numeración
def _ventas(*numeros):
    return [_factura(num_factura=n, nombre=f"COMPRADOR {i}")
            for i, n in enumerate(numeros)]


def test_un_numero_enorme_en_la_serie_no_agota_la_memoria():
    facturas = _ventas("1", "2", "4", "900000000000000")
    inicio = time.monotonic()
    avisos = huecos_de_numeracion(facturas, ["venta"] * len(facturas),
                                  "CLIENTE PRUEBA")
    assert time.monotonic() - inicio < 2
    # El número desbocado no cuenta para la serie; el hueco real sí se ve.
    assert len(avisos) == 1 and "factura 3 " in avisos[0]
    assert "900000000" not in avisos[0]


def test_un_numero_enorme_entre_las_ya_exportadas_tampoco():
    facturas = _ventas("101", "102", "104")
    inicio = time.monotonic()
    avisos = huecos_de_numeracion(facturas, ["venta"] * 3, "CLIENTE PRUEBA",
                                  ventas_anteriores=["7", "100"])
    assert time.monotonic() - inicio < 2
    assert len(avisos) == 1 and "103" in avisos[0]


def test_los_huecos_normales_se_siguen_viendo():
    facturas = _ventas("A-10", "A-11", "A-13", "A-14")
    [aviso] = huecos_de_numeracion(facturas, ["venta"] * 4, "CLIENTE PRUEBA")
    assert "A-12" in aviso
    # Con un tramo de más de MAXIMO_HUECO, nada (otra serie).
    assert huecos_de_numeracion(_ventas("1", "2", "40"), ["venta"] * 3) == []


# -------------------------------------------------------- ventana de error
def test_la_ventana_de_error_nunca_sale_en_blanco():
    from facturas_excel.app import _texto_del_error
    assert "sin memoria" in _texto_del_error(MemoryError, MemoryError())
    assert "TimeoutError" in _texto_del_error(TimeoutError, TimeoutError())
    assert _texto_del_error(ValueError, ValueError("dato raro")) == "dato raro"


# ---------------------------------------- campos acotados (criterio del usuario)
def test_un_numero_o_un_nombre_larguisimo_se_acota_al_leer():
    from facturas_excel.procesar import MAX_NOMBRE_LEIDO, MAX_NUMERO, construir
    datos = dict(emisor_nombre="PROVEEDOR DE PRUEBA " * 10,
                 emisor_nif="B12345674" + "9" * 40,
                 receptor_nombre="CLIENTE", receptor_nif="12345678Z",
                 num_factura="FACTURA SIMPLIFICADA NUMERO " + "0" * 40 + "1234",
                 sustituye_a="X" * 80 + "-77",
                 fecha="03/09/2026", total=121.0,
                 lineas_iva=[{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0}])
    pr = construir(datos, "12345678Z", "CLIENTE")
    f = pr.facturas[0]
    assert len(f.num_factura) <= MAX_NUMERO and f.num_factura.endswith("1234")
    assert len(f.nombre) <= MAX_NOMBRE_LEIDO
    assert f.nombre.startswith("PROVEEDOR DE PRUEBA")
    assert len(f.nif) <= 20
    assert f.rectifica_a.endswith("-77") and len(pr.sustituye_a) <= MAX_NUMERO
    # Lo normal queda tal cual.
    normal = construir(dict(datos, emisor_nombre="PROVEEDOR SL",
                            emisor_nif="B12345674", num_factura="FV24-000123",
                            sustituye_a=None), "12345678Z", "CLIENTE")
    g = normal.facturas[0]
    assert (g.num_factura, g.nombre, g.nif) == ("FV24-000123", "PROVEEDOR SL",
                                                "B12345674")


def test_un_contador_de_mas_de_9_cifras_no_cuenta_para_la_serie():
    facturas = _ventas("T-10", "T-11", "T-13", "T-9000000000123")
    [aviso] = huecos_de_numeracion(facturas, ["venta"] * 4, "CLIENTE PRUEBA")
    assert "T-12" in aviso and "9000000000" not in aviso
    # Aunque el raro sea el primero, el aviso se escribe con los normales.
    facturas = _ventas("T-9000000000123", "T-10", "T-11", "T-13")
    [aviso] = huecos_de_numeracion(facturas, ["venta"] * 4, "CLIENTE PRUEBA")
    assert "T-12" in aviso
    # Ni un número de miles de cifras entre las ya exportadas lo rompe.
    assert huecos_de_numeracion(_ventas("1", "2", "4"), ["venta"] * 3, "X",
                                ventas_anteriores=["9" * 5000]) is not None
