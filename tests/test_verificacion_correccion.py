"""Verificación de la revisión de corrección (d5eccde, 550814f, a594b4a,
d392f24): una prueba por hallazgo confirmado. Fallan con d392f24 y pasan con
los arreglos. Datos inventados: ni nombres ni NIF reales.
"""

import json
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from facturas_excel import clientes, procesar, proveedores, suite
from facturas_excel.modelo import Factura
from facturas_excel.texto import reparar, tiene_invisibles
from facturas_excel.validacion import (
    encontrar_duplicados, huecos_de_numeracion,
)

_app = QApplication.instance() or QApplication([])

CLIENTE = "12345678Z"
OTRO_CLIENTE = "B76543214"
PROVEEDOR = "B12345674"
ALMACEN = "A12345674"


@pytest.fixture(autouse=True)
def datos_aparte(tmp_path, monkeypatch):
    monkeypatch.setattr(proveedores, "dir_datos", lambda: str(tmp_path))
    monkeypatch.setattr(clientes, "dir_datos", lambda: str(tmp_path))
    suite._cache.update(mtime=None, ruta=None, datos=None)


def _compra(nombre, nif=PROVEEDOR, cliente=CLIENTE, **extra):
    d = dict(emisor_nombre=nombre, emisor_nif=nif,
             receptor_nombre="CLIENTE PRUEBA", receptor_nif=cliente,
             num_factura="F-1", fecha="03/09/2026", total=121.0,
             lineas_iva=[{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0}],
             cuenta_gasto="628", confianza="alta")
    d.update(extra)
    return d


def _lote(datos, cliente=CLIENTE, cliente_nombre="CLIENTE PRUEBA"):
    return procesar.preparar_lote([(b"", "taco.pdf", 1, datos)],
                                  cliente_nombre, cliente)[0][1]


# ------------------------------------------------------------ hallazgo 1
def test_la_cuenta_puesta_tras_corregir_el_nombre_se_recuerda():
    procesar.recordar_nif("ZETA PRUEBA SL", PROVEEDOR)          # exportada
    procesar.recordar_nombre_proveedor(PROVEEDOR, "ACME ZETA PRUEBA SL")
    assert procesar.recordar_cuenta_proveedor(
        PROVEEDOR, "ACME ZETA PRUEBA SL", "629", None, CLIENTE)
    assert _lote(_compra("ACME ZETA PRUEBA SL")).cuenta == "629"
    # Y si se cambia otra vez, vale la última.
    procesar.recordar_cuenta_proveedor(PROVEEDOR, "ACME ZETA PRUEBA SL",
                                       "622", None, CLIENTE)
    assert _lote(_compra("ACME ZETA PRUEBA SL")).cuenta == "622"


def test_memoria_ya_partida_en_dos_fichas_sigue_dando_la_cuenta():
    # Lo que dejó escrito la versión anterior: el nombre corregido en una
    # ficha y la cuenta en otra (la de la clave del nombre nuevo).
    proveedores.guardar_campos("PRUEBA ZETA", nif=PROVEEDOR,
                               nombre="ACME ZETA PRUEBA SL", nombre_manual=True)
    proveedores.guardar_campos("ACME PRUEBA ZETA", nif=PROVEEDOR,
                               nombre="ACME ZETA PRUEBA SL", cuenta="629",
                               cuenta_manual=True,
                               cuentas_cliente={CLIENTE: ["629", None]})
    assert _lote(_compra("ACME ZETA PRUEBA SL")).cuenta == "629"


# ------------------------------------------------------------ hallazgo 2
ROTO = "JOS\x01 GARC\x01A PRUEBA SL"
BUENO = "JOSÉ GARCÍA PRUEBA SL"


def test_un_nombre_sin_letra_exportado_no_se_aprende_ni_pasa_a_verde():
    primera = _lote(_compra(ROTO))
    assert "no se ve" in primera.aviso
    procesar.aprender_nifs_exportados(primera.facturas)   # se marca y exporta
    # La siguiente lectura rota sigue en ámbar…
    segunda = _lote(_compra(ROTO, num_factura="F-2"))
    assert "no se ve" in segunda.aviso
    # …y una lectura buena no se cambia por el nombre sin letras.
    buena = _lote(_compra(BUENO, num_factura="F-3"))
    assert buena.facturas[0].nombre == BUENO


def _ventana_leida(datos, monkeypatch):
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.dialogo_cliente import DialogoCliente
    monkeypatch.setattr(DialogoCliente, "exec", lambda self: 0)
    crudos = [(b"", "taco.pdf", 1, datos)]
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._rutas_actuales = ["taco.pdf"]
    v._on_terminado(procesar.preparar_lote(crudos, "CLIENTE PRUEBA", CLIENTE),
                    "CLIENTE PRUEBA", CLIENTE, crudos)
    return v


@pytest.mark.parametrize("como", ["cuenta", "nif"])
def test_corregir_otra_celda_de_la_fila_sin_letra_no_ensena_el_nombre(
        como, monkeypatch):
    from facturas_excel.app import C_CUENTA, C_GXX, C_NIF
    if como == "cuenta":
        v = _ventana_leida(_compra(ROTO), monkeypatch)
        v.tabla.item(0, C_GXX).setText("")
        v.tabla.item(0, C_CUENTA).setText("629")
    else:
        v = _ventana_leida(_compra(ROTO, nif=""), monkeypatch)
        v.tabla.item(0, C_NIF).setText(PROVEEDOR)
    assert proveedores.buscar_por_nif(PROVEEDOR)          # algo se recordó
    assert procesar.nombres_guardados().get(PROVEEDOR) != "JOS GARCA PRUEBA SL"
    buena = _lote(_compra(BUENO, num_factura="F-3"))
    assert buena.facturas[0].nombre == BUENO
    if como == "cuenta":
        assert buena.cuenta == "629"                       # la cuenta, sí


def test_reparar_no_da_por_bueno_el_propio_nombre_sin_la_letra():
    assert reparar(ROTO, ["JOS GARCA PRUEBA SL"]) is None
    assert reparar(ROTO, ["JOS GARCA PRUEBA SL", BUENO]) == BUENO


# ------------------------------------------------------------ hallazgo 3
CLIENTE_ROTO = "JOS\x01 P\x03REZ PRUEBA"


def _taco_del_cliente(nombre):
    return [
        dict(_compra(nombre, nif=CLIENTE, cliente=PROVEEDOR,
                     receptor_nombre="COMPRADOR UNO SL", num_factura="V-1")),
        dict(_compra(nombre, nif=CLIENTE, cliente=ALMACEN,
                     receptor_nombre="COMPRADOR DOS SA", num_factura="V-2")),
        dict(_compra("PROVEEDOR TRES SL", nif=OTRO_CLIENTE,
                     receptor_nombre=nombre, num_factura="G-1")),
    ]


def test_el_nombre_sin_letra_del_cliente_no_se_guarda_ni_va_a_la_suite(
        monkeypatch):
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.dialogo_cliente import DialogoCliente
    ruta = suite.ruta_directorio()
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump({"schema_version": 1, "clientes": {}}, fh)
    suite._cache.update(mtime=None, ruta=None, datos=None)
    monkeypatch.setattr(DialogoCliente, "exec", lambda self: 0)

    crudos = [(b"", "taco.pdf", i + 1, d)
              for i, d in enumerate(_taco_del_cliente(CLIENTE_ROTO))]
    nombre, nif = procesar.detectar_cliente([d for *_, d in crudos])
    assert nif == CLIENTE and not tiene_invisibles(nombre)
    v = VentanaPrincipal(comprobar_updates=False)
    v._rutas_actuales = ["taco.pdf"]
    v._on_terminado(procesar.preparar_lote(crudos, nombre, nif), nombre, nif,
                    crudos)
    assert "JOS PREZ PRUEBA" not in clientes.nombres_conocidos()

    def elegir(self):                     # la persona confirma el cliente
        for i, c in enumerate(self._candidatos):
            if c.nif == CLIENTE:
                self.grupo.button(i).setChecked(True)
        return 1
    monkeypatch.setattr(DialogoCliente, "exec", elegir)
    v._cambiar_cliente()
    assert clientes.es_cliente_confirmado(CLIENTE)
    assert clientes.nombre_confirmado(CLIENTE) != "JOS PREZ PRUEBA"
    suite._cache.update(mtime=None, ruta=None, datos=None)
    assert suite.nombre_de(CLIENTE) != "JOS PREZ PRUEBA"
    # Una lectura buena después da el nombre bueno.
    assert procesar.detectar_cliente(
        _taco_del_cliente("JOSÉ PÉREZ PRUEBA"))[0] == "JOSÉ PÉREZ PRUEBA"


# ------------------------------------------------------------ hallazgo 4
def test_la_cuenta_de_un_lote_sin_nif_no_va_en_verde_a_otro_cliente():
    procesar.recordar_nif("ALMACENES PRUEBA SA", ALMACEN)
    procesar.recordar_cuenta_proveedor(ALMACEN, "ALMACENES PRUEBA SA", "600",
                                       None, CLIENTE)
    procesar.recordar_cuenta_proveedor(ALMACEN, "ALMACENES PRUEBA SA", "629",
                                       None, "")
    tercero = _lote(_compra("ALMACENES PRUEBA SA", nif=ALMACEN,
                            cliente=OTRO_CLIENTE, cuenta_gasto="602"),
                    cliente=OTRO_CLIENTE)
    assert "en otro cliente" in tercero.aviso
    # El lote sin NIF y el cliente que tiene la suya, como estaban.
    assert _lote(_compra("ALMACENES PRUEBA SA", nif=ALMACEN, cliente=""),
                 cliente="").cuenta == "629"
    assert _lote(_compra("ALMACENES PRUEBA SA", nif=ALMACEN)).cuenta == "600"


# ------------------------------------------------------------ hallazgo 5
def _facturas(*numeros):
    return [Factura(num_factura=n, nombre="ACME PRUEBA SL", nif=PROVEEDOR)
            for n in numeros]


def test_huecos_con_un_contador_de_diez_cifras():
    [aviso] = huecos_de_numeracion(
        _facturas("FV2026000001", "FV2026000002", "FV2026000004"),
        ["venta"] * 3, "CLIENTE PRUEBA")
    assert "FV2026000003" in aviso
    [aviso] = huecos_de_numeracion(
        _facturas("4000123451", "4000123452", "4000123454"), None, "X")
    assert "4000123453" in aviso
    # Con las ventas ya exportadas: falta la segunda del trimestre.
    [aviso] = huecos_de_numeracion(
        _facturas("2026000003", "2026000004", "2026000005"), ["venta"] * 3,
        "CLIENTE PRUEBA", ventas_anteriores=["2026000001"])
    assert "2026000002" in aviso
    # Un número desbocado (o de 9 cifras) sigue sin tapar el hueco real.
    for raro in ("T-123456789", "T-9000000000123"):
        [aviso] = huecos_de_numeracion(_facturas("T-10", "T-11", "T-13", raro),
                                       ["venta"] * 4, "X")
        assert "T-12" in aviso


# ------------------------------------------------------------ hallazgo 6
def test_venta_sin_nif_del_cliente_con_su_nombre_roto_sigue_siendo_venta():
    nombre, nif = procesar.detectar_cliente(_taco_del_cliente(CLIENTE_ROTO))
    venta = _compra(CLIENTE_ROTO, nif="", cliente=PROVEEDOR,
                    receptor_nombre="COMPRADOR UNO SL", num_factura="V-9")
    pr = procesar.construir(venta, nif, nombre)
    assert pr.tipo == "venta"
    tique = _compra("GASOLINERA PRUEBA SL", nif=OTRO_CLIENTE, cliente="",
                    receptor_nombre=CLIENTE_ROTO, num_factura="T-1")
    pr = procesar.construir(tique, nif, nombre)
    assert pr.tipo == "gasto" and "dudoso" not in pr.aviso


# ------------------------------------------------------------ hallazgo 7
def test_un_numero_muy_largo_no_junta_facturas_distintas_ni_va_en_verde():
    largo = " MANTENIMIENTO ASCENSOR COMUNIDAD DE PROPIETARIOS CALLE PRUEBA 12"
    a = _lote(_compra("ASCENSORES PRUEBA SL", num_factura="0007/2026" + largo,
                      fecha="01/07/2026"))
    b = _lote(_compra("ASCENSORES PRUEBA SL", num_factura="0008/2026" + largo,
                      fecha="01/08/2026"))
    fa, fb = a.facturas[0], b.facturas[0]
    assert fa.num_factura != fb.num_factura
    assert len(fa.num_factura) <= procesar.MAX_NUMERO
    assert encontrar_duplicados([fa, fb]) == {}
    assert "muy largo" in a.aviso                 # ámbar: hay que mirarlo
    assert procesar.acotar_numero("FV24-000123") == "FV24-000123"


# ------------------------------------------------------------ hallazgo 8
def test_reparar_no_se_cuelga_con_muchos_invisibles_seguidos():
    # Con d392f24: 28 seguidos, unos 5 s; cada uno más, el doble.
    for roto in ("\x01" * 28 + "X",
                 "".join(chr(1 + (i % 2) * 3 + (i % 5)) for i in range(40))):
        inicio = time.perf_counter()
        assert reparar(roto, ["DISTRIBUCIONES ALIMENTARIAS DEL MEDITERRANEO SL"]) \
            is None
        assert time.perf_counter() - inicio < 1.0, repr(roto)
    # Lo de siempre se sigue recuperando.
    assert reparar("PRUEBA JES\x03S SOL", ["PRUEBA JESÚS SOL"]) == \
        "PRUEBA JESÚS SOL"


# ------------------------------------------------------------ hallazgo 9
def test_un_nombre_largo_guardado_entero_se_sigue_encontrando():
    largo = ("COMUNIDAD DE PROPIETARIOS EDIFICIO LOS ALMENDROS FASE SEGUNDA "
             "PORTAL TRES")
    procesar.recordar_nif(largo, PROVEEDOR)
    pr = procesar.construir(_compra(largo, nif="", cuenta_gasto="621"),
                            CLIENTE, "CLIENTE PRUEBA")
    procesar.completar_desde_memoria([pr], CLIENTE)
    assert pr.facturas[0].nif == PROVEEDOR
