"""Red para los arreglos del 09/10/2026 que no tenían una prueba que fallase sin
ellos (comprobado deshaciendo cada arreglo en una copia). Datos inventados.

Cada prueba dice qué arreglo protege: si alguien lo deshace, falla.
"""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from facturas_excel import clientes, procesar, proveedores, suite
from facturas_excel.modelo import Factura
from facturas_excel.texto import tiene_invisibles
from facturas_excel.validacion import huecos_de_numeracion

_app = QApplication.instance() or QApplication([])

CLIENTE_A = "12345678Z"
CLIENTE_B = "B76543214"
ALMACEN = "A12345674"
ALMACEN_NOMBRE = "ALMACENES DE PRUEBA SA"
NIF = "B12345674"
BUENO = "TTES. PRUEBA JOSÉ SOL S.L."
ROTO = "TTES. PRUEBA JOS\x01 SOL S.L."


@pytest.fixture(autouse=True)
def datos_aparte(tmp_path, monkeypatch):
    monkeypatch.setattr(proveedores, "dir_datos", lambda: str(tmp_path))
    monkeypatch.setattr(clientes, "dir_datos", lambda: str(tmp_path))
    suite._cache.update(mtime=None, ruta=None, datos=None)


def _datos(cliente=CLIENTE_A, **extra):
    d = dict(emisor_nombre=ALMACEN_NOMBRE, emisor_nif=ALMACEN,
             receptor_nombre="CLIENTE PRUEBA", receptor_nif=cliente,
             num_factura="M-1", fecha="03/09/2026",
             lineas_iva=[{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0}],
             total=121.0, cuenta_gasto="622", subclave_gxx="G13",
             confianza="alta")
    d.update(extra)
    return d


def _lote(cliente=CLIENTE_A, **extra):
    crudos = [(b"", "taco.pdf", 1, _datos(cliente, **extra))]
    return procesar.preparar_lote(crudos, "CLIENTE PRUEBA", cliente)[0][1]


def _ventas(*numeros):
    return [Factura(num_factura=n, fecha="03/09/2026", nombre=f"COMPRADOR {i}",
                    nif="B12345674", concepto="700", subclave="I01",
                    base_iva=100.0, pct_iva=21.0, cuota_iva=21.0,
                    total_impreso=121.0)
            for i, n in enumerate(numeros)]


# ------------------------------------------- d5eccde: huecos sin MemoryError
# Las pruebas de hoy usan un número de 15 cifras, que desde a594b4a ni entra
# en la serie: el conteo previo de _faltan quedaba sin red. Con 9 cifras sí
# entra, y listar antes de contar recorre mil millones de números.
@pytest.mark.parametrize("anteriores", [(), ("0",)], ids=["lote", "con-anterior"])
def test_un_contador_de_9_cifras_en_la_serie_no_agota_la_memoria(anteriores):
    facturas = _ventas("1", "2", "4", "999999999")
    inicio = time.monotonic()
    avisos = huecos_de_numeracion(facturas, ["venta"] * 4, "CLIENTE PRUEBA",
                                  ventas_anteriores=anteriores)
    assert time.monotonic() - inicio < 2
    assert isinstance(avisos, list)


# ------------------------------- d5eccde: la ventana de error dice qué pasa
# La prueba de hoy llama a _texto_del_error, no a la ventana: si
# _aviso_de_error vuelve a poner {valor}, la ventana sale en blanco y pasa.
def test_la_ventana_de_error_de_memoria_no_sale_en_blanco(monkeypatch):
    from facturas_excel import app
    vistos = []
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda _p, _t, texto, *a, **k: vistos.append(texto)))
    monkeypatch.setattr(app.sys, "__excepthook__", lambda *a: None)
    app._aviso_de_error(MemoryError, MemoryError(), None)
    assert len(vistos) == 1
    assert "sin memoria" in vistos[0]


# --------------------------- 550814f: cuenta de un cliente sin NIF
# Las pruebas de hoy no tienen la cuenta de antes («*») ya guardada: con ella,
# sin la rama «else» del arreglo, lo que pone el usuario en un cliente sin NIF
# no entra nunca (gana la de antes de la 1.25 para siempre).
def test_un_cliente_sin_nif_corrige_aunque_ya_haya_cuenta_de_antes():
    clave = procesar.clave_proveedor(ALMACEN_NOMBRE)
    # Memoria de la 1.24: cuenta sin cliente.
    proveedores.guardar_campos(clave, nif=ALMACEN, nombre=ALMACEN_NOMBRE,
                               cuenta="600", gxx="G01", cuenta_manual=True)
    # En la 1.25, el cliente A le pone la suya (la de antes queda como «*»).
    procesar.recordar_cuenta_proveedor(ALMACEN, ALMACEN_NOMBRE, "629", "G22",
                                       CLIENTE_A)
    # Un cliente sin NIF la corrige.
    procesar.recordar_cuenta_proveedor(ALMACEN, ALMACEN_NOMBRE, "628", "G18", "")
    pr = _lote("")
    assert (pr.cuenta, pr.gxx) == ("628", "G18")
    assert _lote(CLIENTE_A).cuenta == "629"


# ------------------------------- 550814f: deshacer «Marcar revisada»
# La prueba de hoy mira el estado de la fila, no la memoria: sin reponer la
# ficha, deshacer deja la cuenta guardada para B y el siguiente lote de B ya
# no avisa.
def test_deshacer_marcar_revisada_deja_la_memoria_como_estaba():
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.validacion import REVISAR
    clientes.marcar_cliente(CLIENTE_B, "CLIENTE B PRUEBA")
    procesar.recordar_cuenta_proveedor(ALMACEN, ALMACEN_NOMBRE, "600", "G01",
                                       CLIENTE_A)
    antes = proveedores.leer_todo()
    crudos = [(b"", "taco.pdf", 1,
               _datos(CLIENTE_B, receptor_nombre="CLIENTE B PRUEBA"))]
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._rutas_actuales = ["taco.pdf"]
    v._on_terminado(procesar.preparar_lote(crudos, "CLIENTE B PRUEBA", CLIENTE_B),
                    "CLIENTE B PRUEBA", CLIENTE_B, crudos)
    assert v.filas[0]["estado"] == REVISAR
    v.tabla.selectRow(0)
    deshacer = v._marcar_revisada()
    assert proveedores.leer_todo() != antes          # se guardó para B
    deshacer()
    assert proveedores.leer_todo() == antes
    assert "en otro cliente" in (_lote(CLIENTE_B).aviso or "")


def test_reponer_sin_ficha_de_antes_la_borra():
    proveedores.guardar_campos("NUEVA", nif=ALMACEN, nombre=ALMACEN_NOMBRE,
                               cuenta="600", gxx="G01", cuenta_manual=True)
    proveedores.reponer("NUEVA", None)
    assert "NUEVA" not in proveedores.leer_todo()


# -------------------------------------- a594b4a: campos acotados al leer
def test_la_moneda_desbocada_se_acota():
    pr = procesar.construir(_datos(moneda="EUR " * 30), CLIENTE_A, "CLIENTE PRUEBA")
    assert len(pr.facturas[0].moneda) <= 10


def test_el_nombre_largo_se_corta_por_palabra_entera():
    # El corte cae en mitad de una palabra: se queda en la anterior entera.
    nombre = ("SUMINISTROS DE PRUEBA PARA HOSTELERIA Y RESTAURACION DEL NORTE "
              "Y DEL SUR DE LA PENINSULA CON SUS ISLAS Y TERRITORIOS DE ULTRAMAR "
              "SOCIEDAD LIMITADA")
    pr = procesar.construir(_datos(emisor_nombre=nombre), CLIENTE_A, "CLIENTE PRUEBA")
    acotado = pr.facturas[0].nombre
    assert len(acotado) <= procesar.MAX_NOMBRE_LEIDO
    assert nombre.startswith(acotado) and nombre[len(acotado)] == " "


def test_con_un_contador_desbocado_no_se_avisa_con_menos_de_tres_buenas():
    # «1», «3» y un número de 12 cifras: sin el raro solo quedan dos, y con
    # dos no hay serie (MINIMO_SERIE). Antes salía «FALTA la factura 2».
    assert huecos_de_numeracion(_ventas("1", "3", "900000000000"),
                                ["venta"] * 3, "CLIENTE PRUEBA") == []


# ------------------------------- d392f24: clientes y suite, cada defensa
def test_recordar_un_nombre_roto_no_pisa_el_del_cliente():
    # Mira lo guardado, no solo nombres_conocidos(): con el arreglo que la
    # filtra, mirarla a ella ya no cazaría que se pisa el nombre bueno.
    clientes.recordar_nombre(CLIENTE_A, "CLIENTE PRUEBA JOSÉ")
    clientes.recordar_nombre(CLIENTE_A, "CLIENTE PRUEBA JOS\x01")
    assert clientes._leer_todo()[CLIENTE_A]["nombre"] == "CLIENTE PRUEBA JOSÉ"
    assert "CLIENTE PRUEBA JOSÉ" in clientes.nombres_conocidos()


def test_confirmar_con_un_nombre_roto_no_pisa_el_del_cliente():
    clientes.marcar_cliente(CLIENTE_A, "CLIENTE PRUEBA JOSÉ")
    clientes.marcar_cliente(CLIENTE_A, "CLIENTE PRUEBA JOS\x01")
    assert clientes._leer_todo()[CLIENTE_A]["nombre"] == "CLIENTE PRUEBA JOSÉ"
    assert clientes.nombre_confirmado(CLIENTE_A) == "CLIENTE PRUEBA JOSÉ"


def test_un_nombre_roto_ya_guardado_en_clientes_no_se_propone():
    # Memoria de clientes de la 1.24 (ya guardaba nombres rotos).
    todo = clientes._leer_todo()
    todo[CLIENTE_A] = {"confirmado": True, "nombre": "CLIENTE\x01 PRUEBA"}
    clientes._guardar_ficha(CLIENTE_A, todo[CLIENTE_A])
    assert not tiene_invisibles(clientes.nombre_confirmado(CLIENTE_A))


# ------------------------------- d392f24: memoria de proveedores
def test_un_nombre_roto_al_guardar_la_cuenta_no_entra_en_la_memoria():
    # Una fila restaurada de una sesión de la 1.24 aún lleva el nombre roto.
    procesar.recordar_cuenta_proveedor(NIF, ROTO, "628", "G16", CLIENTE_A)
    assert not any(tiene_invisibles(f.get("nombre"))
                   for f in proveedores.leer_todo().values())


def test_un_nombre_roto_no_pisa_el_que_ya_tenia_la_ficha():
    proveedores.guardar_campos("CLAVE", nif=NIF, nombre="PRUEBA MARIA SL")
    proveedores.guardar_campos("CLAVE", nif=NIF, nombre="PRUEBA JOS\x01 SL")
    assert proveedores.leer("CLAVE")["nombre"] == "PRUEBA MARIA SL"


def test_guardar_campos_recupera_la_letra_con_otra_ficha_del_nif():
    proveedores.guardar_campos("BUENA", nif=NIF, nombre=BUENO)
    proveedores.guardar_campos("OTRA", nif=NIF, nombre=ROTO)
    assert proveedores.leer("OTRA")["nombre"] == BUENO


def test_al_leer_se_recupera_la_letra_con_el_nombre_del_cliente_confirmado():
    # Un cliente de la asesoría que a la vez le factura a otro cliente: su
    # nombre bueno solo está en la memoria de clientes.
    clientes.marcar_cliente(NIF, BUENO)
    datos = _datos(emisor_nombre=ROTO, emisor_nif=NIF)
    pr = procesar.construir(datos, CLIENTE_A, "CLIENTE PRUEBA")
    assert pr.facturas[0].nombre == BUENO


# ------------------------------------------- d392f24: texto.py
@pytest.mark.parametrize("raro", [chr(0xFFFF), chr(0xFFFE)], ids=["FFFF", "FFFE"])
def test_un_excel_con_un_no_caracter_se_vuelve_a_abrir(tmp_path, raro):
    # openpyxl lo escribe sin quejarse, pero el .xlsx ya no se puede abrir.
    from pathlib import Path
    from facturas_excel.config_columnas import leer_config
    from facturas_excel.exportar import exportar_excel, verificar_excel
    cfg = leer_config(Path(__file__).resolve().parent.parent / "config" / "gastos.xml")
    f = Factura(num_factura="F-1", fecha="03/09/2026", nombre=f"PRUEBA{raro} SL",
                nif=NIF, concepto="628", subclave="G16", base_iva=100.0,
                pct_iva=21.0, cuota_iva=21.0, total_impreso=121.0)
    ruta = str(tmp_path / "g.xlsx")
    exportar_excel([f], cfg, ruta)
    assert verificar_excel([f], cfg, ruta) == []


def test_el_aviso_ambar_ensena_donde_esta_el_caracter():
    from facturas_excel.validacion import validar
    f = Factura(num_factura="F-1", fecha="03/09/2026", nombre=ROTO, nif=NIF,
                concepto="628", subclave="G16", base_iva=100.0, pct_iva=21.0,
                cuota_iva=21.0, total_impreso=121.0)
    assert any("JOS· SOL" in str(m) for m in validar(f).mensajes)


def test_la_rectificada_desbocada_se_acota_tambien_en_la_factura():
    pr = procesar.construir(_datos(sustituye_a="X" * 80 + "-77"), CLIENTE_A,
                            "CLIENTE PRUEBA")
    assert len(pr.facturas[0].rectifica_a) <= procesar.MAX_NUMERO
    assert pr.facturas[0].rectifica_a.endswith("-77")


@pytest.mark.parametrize("lectura", [1, 2])
def test_la_ficha_usar_este_limpia_el_numero(lectura):
    """«Usar este» en la ficha: el nº de una lectura con un invisible no entra
    tal cual en la factura (lectura 1: tras cambiarlo a mano). Es el único
    dato de texto que pasa por ahí (nombre no se puede elegir en la ficha)."""
    from facturas_excel.app import VentanaPrincipal
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._cliente_nif, v._cliente_nombre = CLIENTE_A, "CLIENTE PRUEBA"
    v._bloques = [{"nombre": "b1", "cliente": "CLIENTE PRUEBA", "nif": CLIENTE_A}]
    f = Factura(num_factura="F-1", fecha="03/09/2026", nombre="PRUEBA MARIA SL",
                nif=NIF, concepto="628", subclave="G16", base_iva=100.0,
                pct_iva=21.0, cuota_iva=21.0, total_impreso=121.0,
                confianza_ia="alta", verificacion="doble")
    f.discrepancias = ({"campo": "num_factura", "etiqueta": "Nº",
                        "valor_1": "F\x01-77", "valor_2": "F\x02-77",
                        "campo_factura": "num_factura",
                        "texto": "Doble lectura: el nº no coincide"},)
    v._anadir_fila(b"", f, "gasto", f.concepto, f.subclave, "", "b1")
    v._revalidar_todo()
    v._resolver_discrepancia(0, 0, lectura)
    assert v.filas[0]["factura"].num_factura == "F-77"


def test_limpiar_no_deja_dos_espacios_donde_estaba_el_invisible():
    from facturas_excel.texto import limpiar
    assert limpiar("PRUEBA \x01 SOL SL") == ("PRUEBA SOL SL", True)
