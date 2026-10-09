"""Fallos encontrados al poner la red a los arreglos del 09/10/2026 (fallan
en d392f24). Datos inventados.

1) Corregir el nombre de un proveedor y después su cuenta: la cuenta no entra
   en el siguiente lote. recordar_cuenta_proveedor guardaba en
   clave_proveedor(ficha["nombre"]), que no es la clave de la ficha
   encontrada por NIF (esa está guardada con el nombre LEÍDO): nacía otra
   ficha con la cuenta, y buscar_por_nif, que desde d392f24 prefiere la del
   nombre puesto a mano, devolvía la otra (sin cuenta, o con la de antes).
   La 1.24 dejó la memoria así en muchos proveedores: la cuenta que entonces
   entraba tiene que seguir entrando.

2) La lista de clientes de Escanear (clientes.nombres_conocidos) sacaba los
   nombres rotos que guardó la 1.24.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from facturas_excel import clientes, procesar, proveedores, suite

_app = QApplication.instance() or QApplication([])

CLIENTE = "12345678Z"
NIF = "A12345674"
LEIDO_1, BUENO_1 = "ALMACENES PRUEBA LEIDO SA", "ALMACENES DE PRUEBA SA"
LEIDO_2, BUENO_2 = "ALMACENES DE PRUEBA SA", "ALMACENES PRUEBA BUENO SA"
CASOS = [(LEIDO_1, BUENO_1), (LEIDO_2, BUENO_2)]   # la clave buena, antes y después


@pytest.fixture(autouse=True)
def datos_aparte(tmp_path, monkeypatch):
    monkeypatch.setattr(proveedores, "dir_datos", lambda: str(tmp_path))
    monkeypatch.setattr(clientes, "dir_datos", lambda: str(tmp_path))
    suite._cache.update(mtime=None, ruta=None, datos=None)


def _crudos(leido):
    d = dict(emisor_nombre=leido, emisor_nif=NIF, receptor_nombre="CLIENTE PRUEBA",
             receptor_nif=CLIENTE, num_factura="M-1", fecha="03/09/2026",
             lineas_iva=[{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0}],
             total=121.0, cuenta_gasto="622", subclave_gxx="G13", confianza="alta")
    return [(b"", "taco.pdf", 1, d)]


def _lote(leido):
    return procesar.preparar_lote(_crudos(leido), "CLIENTE PRUEBA", CLIENTE)[0][1]


# ------------------------------------------- 1) la cuenta tras el nombre
@pytest.mark.parametrize("leido,bueno", CASOS)
def test_la_cuenta_corregida_despues_del_nombre_es_la_que_entra(leido, bueno):
    procesar.recordar_nif(leido, NIF)                    # lote anterior
    procesar.recordar_cuenta_proveedor(NIF, leido, "600", "G01", CLIENTE)
    procesar.recordar_nombre_proveedor(NIF, bueno)       # corrige el nombre
    procesar.recordar_cuenta_proveedor(NIF, bueno, "629", "G22", CLIENTE)
    procesar.recordar_nif(bueno, NIF)                    # y lo exporta
    pr = _lote(leido)
    assert (pr.cuenta, pr.gxx) == ("629", "G22")
    assert pr.facturas[0].nombre == bueno


@pytest.mark.parametrize("leido,bueno", CASOS)
def test_la_primera_cuenta_puesta_tras_corregir_el_nombre_entra(leido, bueno):
    procesar.recordar_nif(leido, NIF)
    procesar.recordar_nombre_proveedor(NIF, bueno)
    procesar.recordar_cuenta_proveedor(NIF, bueno, "629", "G22", CLIENTE)
    procesar.recordar_nif(bueno, NIF)
    pr = _lote(leido)
    assert (pr.cuenta, pr.gxx) == ("629", "G22")


@pytest.mark.parametrize("leido,bueno", CASOS)
def test_corregir_nombre_y_cuenta_en_la_tabla_vale_para_el_siguiente_lote(leido, bueno):
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.tabla_facturas import C_CUENTA, C_GXX, C_NOMBRE
    procesar.recordar_nif(leido, NIF)                    # lote anterior
    crudos = _crudos(leido)
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._rutas_actuales = ["taco.pdf"]
    v._on_terminado(procesar.preparar_lote(crudos, "CLIENTE PRUEBA", CLIENTE),
                    "CLIENTE PRUEBA", CLIENTE, crudos)
    v.tabla.item(0, C_NOMBRE).setText(bueno)
    v.tabla.item(0, C_GXX).setText("G22")
    v.tabla.item(0, C_CUENTA).setText("629")
    pr = _lote(leido)
    assert (pr.cuenta, pr.gxx) == ("629", "G22")


# La memoria tal como la deja la v1.24.0 al corregir el nombre y DESPUÉS poner
# la cuenta (volcada ejecutando la 1.24): la cuenta va en otra ficha, sin
# «nombre_manual».
def _memoria_124(clave_leido, clave_bueno, bueno, cuenta_antes):
    a_mano = {"manual": False, "nif": NIF, "nombre": bueno, "nombre_manual": True}
    if cuenta_antes:
        a_mano.update(cuenta="600", gxx="G01", cuenta_manual=True)
    proveedores._col().guardar(clave_leido, a_mano)
    proveedores._col().guardar(clave_bueno, {
        "manual": False, "nif": NIF, "nombre": bueno,
        "cuenta": "629", "gxx": "G22", "cuenta_manual": True})


@pytest.mark.parametrize("cuenta_antes", [False, True], ids=["primera", "cambiada"])
def test_la_cuenta_que_ponia_la_1_24_sigue_entrando(cuenta_antes):
    # Claves en el orden en que la 1.24 acertaba (la de la cuenta, primero).
    _memoria_124("ALMACENES PRUEBA", "ALMACENES BUENO PRUEBA", BUENO_2, cuenta_antes)
    assert _lote(LEIDO_2).cuenta == "629"


def test_la_cuenta_de_la_1_24_que_no_entraba_ahora_si():
    # Orden contrario, primera cuenta tras corregir el nombre: la 1.24 no
    # ponía ninguna. Prefiriendo la ficha que tiene la cuenta, entra.
    _memoria_124("ALMACENES LEIDO PRUEBA", "ALMACENES PRUEBA", BUENO_1, False)
    assert _lote(LEIDO_1).cuenta == "629"


def test_volver_a_poner_la_cuenta_arregla_la_memoria_de_la_1_24():
    # El caso que la 1.24 ya dejaba mal (la cuenta de antes en la primera
    # ficha por clave) da lo mismo que en la 1.24; al volver a ponerla, se
    # queda (en la 1.24 no había manera).
    _memoria_124("ALMACENES LEIDO PRUEBA", "ALMACENES PRUEBA", BUENO_1, True)
    procesar.recordar_cuenta_proveedor(NIF, BUENO_1, "629", "G22", CLIENTE)
    assert _lote(LEIDO_1).cuenta == "629"


def test_deshacer_la_cuenta_repone_la_ficha_que_se_toco():
    procesar.recordar_nif(LEIDO_1, NIF)
    procesar.recordar_nombre_proveedor(NIF, BUENO_1)
    antes = proveedores.leer_todo()
    clave, ficha = procesar.ficha_de_cuenta(NIF, BUENO_1)
    procesar.recordar_cuenta_proveedor(NIF, BUENO_1, "629", "G22", CLIENTE)
    proveedores.reponer(clave, ficha)
    assert proveedores.leer_todo() == antes


# ------------------------------------- 2) nombres rotos de la 1.24 en Escanear
def test_los_nombres_rotos_guardados_por_la_1_24_no_salen_al_escanear():
    from facturas_excel.texto import tiene_invisibles
    todo = clientes._leer_todo()
    todo[CLIENTE] = {"confirmado": True, "nombre": "TTES. PRUEBA JOS\x01 SOL S.L."}
    clientes._guardar_ficha(CLIENTE, todo[CLIENTE])
    assert not any(tiene_invisibles(n) for n in clientes.nombres_conocidos())
