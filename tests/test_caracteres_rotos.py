"""Nombres con un carácter invisible en lugar de una letra con tilde.

Es lo que da el texto copiado de un PDF cuya letra no trae su tabla de
caracteres: «JOSÉ» llega como «JOS\\x01». Tumbaba la exportación (errores.log
del usuario, 08-09/10/2026) y la memoria de proveedores lo imponía a todas
las facturas de ese NIF. Datos inventados.
"""

import json
import os

import pytest

from facturas_excel import clientes, procesar, proveedores, suite
from facturas_excel.texto import (
    escapar_invisibles, limpiar, reparar, sin_invisibles, tiene_invisibles,
)

NIF = "B12345674"
CLIENTE = "12345678Z"
BUENO = "TTES. PRUEBA JOSÉ SOL S.L."
ROTO = "TTES. PRUEBA JOS\x01 SOL S.L."


@pytest.fixture(autouse=True)
def datos_aparte(tmp_path, monkeypatch):
    monkeypatch.setattr(proveedores, "dir_datos", lambda: str(tmp_path))
    monkeypatch.setattr(clientes, "dir_datos", lambda: str(tmp_path))
    suite._cache.update(mtime=None, ruta=None, datos=None)


def _compra(nombre=BUENO, **extra):
    d = dict(emisor_nombre=nombre, emisor_nif=NIF,
             receptor_nombre="CLIENTE PRUEBA", receptor_nif=CLIENTE,
             num_factura="F-1", fecha="03/09/2026", total=121.0,
             lineas_iva=[{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0}])
    d.update(extra)
    return d


def _lote(datos):
    return procesar.preparar_lote([(b"", "taco.pdf", 1, datos)],
                                  "CLIENTE PRUEBA", CLIENTE)[0][1]


# ------------------------------------------------------------- la limpieza
def test_limpiar_quita_lo_invisible_y_deja_los_separadores_como_espacio():
    assert limpiar(ROTO) == ("TTES. PRUEBA JOS SOL S.L.", True)
    assert limpiar("OTRO\x0bPROVEEDOR")[0] == "OTRO PROVEEDOR"   # como la 1.24
    assert limpiar(BUENO) == (BUENO, False)
    assert limpiar("MAL\ud800DITO")[0] == "MALDITO"               # mitad suelta
    assert not tiene_invisibles(sin_invisibles("A\x00B￾C\x1fD"))
    assert limpiar(None) == (None, False)


@pytest.mark.parametrize("roto,conocidos,esperado", [
    (ROTO, [BUENO, "OTRA EMPRESA SL"], BUENO),
    ("GRUPO PRUEBA JES\x03S SOL", ["GRUPO PRUEBA JESÚS SOL"], "GRUPO PRUEBA JESÚS SOL"),
    ("TTES. PRUEBA ANDR\x00ES S.L.U.", ["TTES. PRUEBA ANDRÉS S.L.U."],
     "TTES. PRUEBA ANDRÉS S.L.U."),
    # Con y sin tilde son el mismo: gana el que la lleva.
    (ROTO, ["TTES. PRUEBA JOSE SOL S.L.", BUENO], BUENO),
    # Dos nombres distintos encajan: no se elige.
    ("PRUEBA JOS\x01 SL", ["PRUEBA JOSÉ SL", "PRUEBA JOSU SL"], None),
    ("PRUEBA JOS\x01 SL", ["PRUEBA MARIA SL"], None),
])
def test_reparar_con_los_nombres_conocidos(roto, conocidos, esperado):
    assert reparar(roto, conocidos) == esperado


# ------------------------------------------------- la memoria de proveedores
def test_la_memoria_no_guarda_un_nombre_roto_encima_de_uno_bueno():
    procesar.recordar_nif(BUENO, NIF, manual=True)
    procesar.recordar_nif(ROTO, NIF, manual=True)
    assert not any(tiene_invisibles(f.get("nombre"))
                   for f in proveedores.leer_todo().values())
    assert procesar.nombres_guardados().get(NIF) == BUENO


def test_un_nombre_roto_ya_guardado_no_se_impone_a_lo_leido():
    # Memoria contaminada por una versión anterior.
    proveedores._col().guardar("ROTO", {"nif": NIF, "nombre": ROTO,
                                        "manual": True, "nombre_manual": True})
    assert NIF not in procesar.nombres_guardados()
    pr = _lote(_compra(BUENO))
    assert pr.facturas[0].nombre == BUENO


def test_cambiar_la_cuenta_no_pisa_el_nombre_puesto_a_mano():
    procesar.recordar_nombre_proveedor(NIF, BUENO)
    procesar.recordar_cuenta_proveedor(NIF, "OTRO NOMBRE LEIDO SL", "628",
                                       "G16", CLIENTE)
    assert proveedores.buscar_por_nif(NIF)["nombre"] == BUENO


def test_buscar_por_nif_prefiere_la_ficha_buena():
    proveedores._col().guardar("A", {"nif": NIF, "nombre": ROTO})
    proveedores._col().guardar("B", {"nif": NIF, "nombre": BUENO,
                                     "nombre_manual": True})
    assert proveedores.buscar_por_nif(NIF)["nombre"] == BUENO


# ---------------------------------------------------------------- al leer
def test_al_leer_se_recupera_la_letra_con_lo_que_ya_se_conoce():
    procesar.recordar_nombre_proveedor(NIF, BUENO)
    pr = procesar.construir(_compra(ROTO), CLIENTE, "CLIENTE PRUEBA")
    assert pr.facturas[0].nombre == BUENO
    assert "no se ve" not in (pr.aviso or "")


def test_al_leer_sin_nada_conocido_se_quita_y_sale_en_ambar():
    pr = procesar.construir(_compra(ROTO), CLIENTE, "CLIENTE PRUEBA")
    f = pr.facturas[0]
    assert not tiene_invisibles(f.nombre) and f.nombre.startswith("TTES.")
    assert "JOS· SOL" in pr.aviso and "no se ve" in pr.aviso


def test_el_numero_de_factura_tampoco_lleva_invisibles():
    pr = procesar.construir(_compra(num_factura="F\x02-77"), CLIENTE, "X")
    assert pr.facturas[0].num_factura == "F-77"


def test_el_candidato_a_cliente_sale_limpio():
    analisis = procesar.analizar_cliente([_compra(receptor_nombre="CLIENTE\x01 PRUEBA")])
    assert all(not tiene_invisibles(c.nombre) for c in analisis.candidatos)


# ------------------------------------------------------- suite y clientes
def _directorio(datos):
    ruta = suite.ruta_directorio()
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(datos, fh)
    suite._cache.update(mtime=None, ruta=None, datos=None)


def test_un_nombre_roto_en_el_directorio_de_la_suite_no_se_usa_ni_se_escribe():
    _directorio({"schema_version": 1, "clientes": {
        CLIENTE: {"nif": CLIENTE, "nombre": "CLIENTE\x02 PRUEBA"}}})
    assert suite.nombre_de(CLIENTE) == ""
    assert not suite.registrar_cliente("A12345674", "OTRO\x01 CLIENTE")
    clientes.recordar_nombre("A12345674", "OTRO\x01 CLIENTE")
    clientes.marcar_cliente("A12345674", "OTRO\x01 CLIENTE")
    assert not tiene_invisibles(clientes.nombre_confirmado("A12345674"))


# ------------------------------------------------------------- las salidas
def test_lo_pegado_en_una_celda_sale_limpio():
    from facturas_excel.tabla_facturas import C_NOMBRE, valor_de_celda
    assert valor_de_celda(C_NOMBRE, ROTO) == ("nombre", "TTES. PRUEBA JOS SOL S.L.")


def test_los_nombres_de_fichero_no_llevan_caracteres_de_control():
    from facturas_excel.escaner import sanear
    assert not any(ord(c) < 32 for c in sanear(ROTO))


def test_errores_log_deja_ver_el_caracter():
    assert escapar_invisibles("JOS\x01 SOL\nlinea") == "JOS\\x01 SOL\nlinea"
    from facturas_excel import errores
    from facturas_excel.rutas import dir_datos
    errores.apuntar(f"IllegalCharacterError: {ROTO}")
    with open(os.path.join(dir_datos(), errores.FICHERO), encoding="utf-8") as fh:
        assert "JOS\\x01 SOL" in fh.read()


def test_el_registro_no_apunta_nombres_rotos():
    from facturas_excel import historial, registro_facturas
    from facturas_excel.modelo import Factura
    f = Factura(num_factura="F-1", fecha="03/09/2026", nombre=ROTO, nif=NIF,
                base_iva=100.0, total_impreso=121.0)
    historial.registrar(CLIENTE, {"gasto": [f]}, {"gasto": "x.xlsx"}, "CLIENTE PRUEBA")
    fichas = registro_facturas.consultar(CLIENTE) if hasattr(
        registro_facturas, "consultar") else []
    assert all(not tiene_invisibles(str(x)) for ficha in fichas
               for x in (ficha.values() if isinstance(ficha, dict) else [ficha]))


def test_un_excel_con_una_mitad_suelta_se_vuelve_a_abrir(tmp_path):
    from pathlib import Path
    from facturas_excel.config_columnas import leer_config
    from facturas_excel.exportar import exportar_excel, verificar_excel
    from facturas_excel.modelo import Factura
    cfg = leer_config(Path(__file__).resolve().parent.parent / "config" / "gastos.xml")
    f = Factura(num_factura="F-1", fecha="03/09/2026", nombre="PRUEBA\ud800 SL",
                nif=NIF, concepto="628", subclave="G16", base_iva=100.0,
                pct_iva=21.0, cuota_iva=21.0, total_impreso=121.0)
    ruta = str(tmp_path / "g.xlsx")
    exportar_excel([f], cfg, ruta)
    assert verificar_excel([f], cfg, ruta) == []
