"""Revisión adversarial de la 1.25: una o más pruebas por cada hallazgo.

Los nueve hallazgos están en PLAN-MEJORAS.md («Para seguir») y sus
reproducciones en docs/revisiones/rev125_reproducciones.py. Aquí se mira lo que
ve el usuario (la cuenta que sale, el aviso, lo que hace la ventana), no cómo
lo hace el código por dentro. Datos de prueba: ni nombres ni NIF reales.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from facturas_excel import clientes, historial, procesar, proveedores
from facturas_excel.app import (
    C_CUENTA, C_FECHA, C_GXX, C_PCT_IRPF, C_BASE_IRPF, VentanaPrincipal,
)
from facturas_excel.conceptos import asignar_concepto
from facturas_excel.dialogo_cliente import DialogoCliente
from facturas_excel.doble_lectura import comparar
from facturas_excel.lote import CORREGIDA
from facturas_excel.modelo import Factura
from facturas_excel.procesar import construir, normaliza_nif
from facturas_excel.validacion import ERROR, REVISAR, validar

_app = QApplication.instance() or QApplication([])

# NIF de prueba (válidos, de nadie).
CLIENTE_A = "12345678Z"
CLIENTE_B = "B76543214"
ALMACEN = "A12345674"
ALMACEN_NOMBRE = "ALMACENES DE PRUEBA SA"
PROVEEDOR = "B12345674"
PROVEEDOR_NOMBRE = "SERVICIOS DE PRUEBA SL"
HOMONIMO = "X1234567L"


@pytest.fixture(autouse=True)
def datos_aparte(tmp_path, monkeypatch):
    """La memoria de proveedores y clientes, en una carpeta de la prueba."""
    monkeypatch.setattr(proveedores, "dir_datos", lambda: str(tmp_path))
    monkeypatch.setattr(clientes, "dir_datos", lambda: str(tmp_path))


def _datos(cliente=CLIENTE_A, **extra):
    """Lo que leería Gemini de una compra de CLIENTE al almacén."""
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


def _textos(f):
    return " ".join(str(m) for m in validar(f).mensajes)


def _mensajes(v, fila=0):
    return " ".join(str(m) for m in v.filas[fila]["mensajes"])


# =====================================================================
# 1. Un «cuentas_cliente» raro no rompe el lote ni el guardado
# =====================================================================
RAROS = [
    pytest.param({CLIENTE_A: ["600"]}, id="lista-de-un-elemento"),
    pytest.param({CLIENTE_A: {"cuenta": "600"}}, id="dict-por-cliente"),
    pytest.param(["600", "G01"], id="lista-entera"),
    pytest.param(["600"], id="lista-entera-de-uno"),
    pytest.param({CLIENTE_A: []}, id="lista-vacia"),
    pytest.param({CLIENTE_A: "600"}, id="texto-suelto"),
    pytest.param("600", id="texto-entero"),
]


def _ficha_rara(raro):
    proveedores.guardar_campos(procesar.clave_proveedor(ALMACEN_NOMBRE),
                               nif=ALMACEN, nombre=ALMACEN_NOMBRE,
                               cuenta="600", gxx="G01", cuenta_manual=True,
                               cuentas_cliente=raro)


@pytest.mark.parametrize("raro", RAROS)
def test_cuentas_cliente_raras_no_rompen_el_lote(raro):
    _ficha_rara(raro)
    for cliente in (CLIENTE_A, CLIENTE_B):
        pr = _lote(cliente)                      # no debe lanzar
        assert pr.facturas[0].concepto in ("600", "622")
        assert pr.cuenta == pr.facturas[0].concepto


@pytest.mark.parametrize("raro", RAROS)
def test_cuentas_cliente_raras_no_rompen_el_guardado(raro):
    _ficha_rara(raro)
    assert procesar.recordar_cuenta_proveedor(ALMACEN, ALMACEN_NOMBRE, "629",
                                              "G22", CLIENTE_A)
    # Y lo guardado vale: en A entra la nueva, sin ámbar de «otro cliente».
    pr = _lote(CLIENTE_A)
    assert (pr.cuenta, pr.gxx) == ("629", "G22")
    assert "otro cliente" not in (pr.aviso or "")
    # Guardar otra vez sobre lo ya arreglado tampoco rompe.
    assert procesar.recordar_cuenta_proveedor(ALMACEN, ALMACEN_NOMBRE, "628",
                                              "G18", CLIENTE_B)
    assert _lote(CLIENTE_B).cuenta == "628"


# =====================================================================
# 2. La cuenta de antes de la 1.25 y el cliente sin NIF
# =====================================================================
def test_la_cuenta_de_antes_sigue_en_silencio_en_los_demas_clientes():
    # Antes de la 1.25: el almacén va a la 600, sin decir de qué cliente.
    procesar.recordar_cuenta_proveedor(ALMACEN, ALMACEN_NOMBRE, "600", "G01")
    pr = _lote(CLIENTE_B)
    assert pr.cuenta == "600" and "otro cliente" not in (pr.aviso or "")
    # En A se le pone la 629: es la de A…
    procesar.recordar_cuenta_proveedor(ALMACEN, ALMACEN_NOMBRE, "629", "G22",
                                       CLIENTE_A)
    en_a = _lote(CLIENTE_A)
    assert (en_a.cuenta, en_a.gxx) == ("629", "G22")
    # …y los demás siguen con la 600 de siempre, sin ámbar.
    for otro in (CLIENTE_B, HOMONIMO):
        pr = _lote(otro)
        assert (pr.cuenta, pr.gxx) == ("600", "G01"), otro
        assert "otro cliente" not in (pr.aviso or ""), pr.aviso


def test_un_cliente_sin_nif_no_queda_en_ambar_de_otro_cliente():
    procesar.recordar_cuenta_proveedor(ALMACEN, ALMACEN_NOMBRE, "600", "G01",
                                       CLIENTE_A)
    # Un cliente sin NIF (registro por nombre): la app pasa "".
    procesar.recordar_cuenta_proveedor(ALMACEN, ALMACEN_NOMBRE, "629", "G22",
                                       "")
    for _vez in range(2):                         # ni la primera ni después
        pr = _lote("")
        assert (pr.cuenta, pr.gxx) == ("629", "G22")
        assert "otro cliente" not in (pr.aviso or ""), pr.aviso
    # El cliente A conserva la suya.
    assert _lote(CLIENTE_A).cuenta == "600"


def test_un_cliente_sin_nif_puede_corregir_la_cuenta():
    # La primera vez (o la guardada antes de la 1.25, que es igual: sin
    # cliente) entra la 600…
    procesar.recordar_cuenta_proveedor(ALMACEN, ALMACEN_NOMBRE, "600", "G01",
                                       "")
    assert _lote("").cuenta == "600"
    # …y el usuario, en un cliente sin NIF, la corrige a la 629.
    procesar.recordar_cuenta_proveedor(ALMACEN, ALMACEN_NOMBRE, "629", "G22",
                                       "")
    pr = _lote("")
    assert (pr.cuenta, pr.gxx) == ("629", "G22")


# =====================================================================
# 3. «…en otro cliente»
# =====================================================================
def test_quitar_aviso_cuenta_quita_el_de_otro_cliente():
    procesar.recordar_cuenta_proveedor(ALMACEN, ALMACEN_NOMBRE, "600", "G01",
                                       CLIENTE_A)
    pr = _lote(CLIENTE_B)
    assert "en otro cliente" in pr.aviso
    limpio = procesar.quitar_aviso_cuenta(pr.aviso)
    assert "otro cliente" not in limpio
    # Lo demás que dijera el aviso se queda.
    otro = "Hay importes escritos a mano: compruébela."
    assert procesar.quitar_aviso_cuenta(f"{otro} {pr.aviso}") == \
        " ".join(f"{otro} {limpio}".split())


def test_quitar_aviso_cuenta_con_nombre_con_puntos():
    """El nombre del proveedor va dentro del aviso: «S.A.» no lo corta."""
    proveedores.guardar_campos(procesar.clave_proveedor("ALMACENES, S.A."),
                               nif=ALMACEN, nombre="ALMACENES, S.A.")
    procesar.recordar_cuenta_proveedor(ALMACEN, "ALMACENES, S.A.", "600",
                                       "G01", CLIENTE_A)
    pr = _lote(CLIENTE_B, emisor_nombre="ALMACENES, S.A.")
    assert "en otro cliente" in pr.aviso
    assert "otro cliente" not in procesar.quitar_aviso_cuenta(pr.aviso)


def test_sin_aviso_si_gemini_propone_la_misma_cuenta():
    procesar.recordar_cuenta_proveedor(ALMACEN, ALMACEN_NOMBRE, "622", "G13",
                                       CLIENTE_A)
    pr = _lote(CLIENTE_B)                         # Gemini también dice 622
    assert (pr.cuenta, pr.gxx) == ("622", "G13")
    assert "otro cliente" not in (pr.aviso or ""), pr.aviso
    # Si Gemini dice otra, sí se avisa (la prueba no es vacía).
    distinta = _lote(CLIENTE_B, cuenta_gasto="629", subclave_gxx="G22")
    assert distinta.cuenta == "622"
    assert "en otro cliente" in distinta.aviso


def test_sin_memoria_el_mismo_lote_no_tiene_aviso():
    pr = _lote(CLIENTE_B)
    assert not pr.aviso, pr.aviso


def _ventana_leida(crudos, nombre, nif):
    """Una ventana que acaba de leer `crudos`, como al terminar la cola."""
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._rutas_actuales = ["taco.pdf"]
    v._on_terminado(procesar.preparar_lote(crudos, nombre, nif), nombre, nif,
                    crudos)
    return v


def test_marcar_revisada_guarda_la_cuenta_de_otro_cliente():
    clientes.marcar_cliente(CLIENTE_B, "CLIENTE B PRUEBA")
    procesar.recordar_cuenta_proveedor(ALMACEN, ALMACEN_NOMBRE, "600", "G01",
                                       CLIENTE_A)
    crudos = [(b"", "taco.pdf", 1,
               _datos(CLIENTE_B, receptor_nombre="CLIENTE B PRUEBA"))]
    v = _ventana_leida(crudos, "CLIENTE B PRUEBA", CLIENTE_B)
    assert v.filas[0]["estado"] == REVISAR
    assert "en otro cliente" in _mensajes(v)

    v.tabla.selectRow(0)
    assert v._marcar_revisada() is not None
    assert "otro cliente" not in _mensajes(v)
    # La siguiente lectura de B ya entra en la 600 sin ámbar.
    pr = _lote(CLIENTE_B)
    assert (pr.cuenta, pr.gxx) == ("600", "G01")
    assert "otro cliente" not in (pr.aviso or ""), pr.aviso


def test_deshacer_marcar_revisada_la_deja_pendiente_otra_vez():
    clientes.marcar_cliente(CLIENTE_B, "CLIENTE B PRUEBA")
    procesar.recordar_cuenta_proveedor(ALMACEN, ALMACEN_NOMBRE, "600", "G01",
                                       CLIENTE_A)
    crudos = [(b"", "taco.pdf", 1,
               _datos(CLIENTE_B, receptor_nombre="CLIENTE B PRUEBA"))]
    v = _ventana_leida(crudos, "CLIENTE B PRUEBA", CLIENTE_B)
    assert v.filas[0]["estado"] == REVISAR
    v.tabla.selectRow(0)
    deshacer = v._marcar_revisada()
    deshacer()                     # «Revisión deshecha: vuelven a estar pendientes.»
    assert v.filas[0]["estado"] == REVISAR
    assert not v.filas[0]["factura"].revision_confirmada


# =====================================================================
# 4. Bien de inversión
# =====================================================================
def test_la_memoria_no_pisa_la_200():
    procesar.recordar_cuenta_proveedor(ALMACEN, ALMACEN_NOMBRE, "622", "G13",
                                       CLIENTE_A)
    pr = _lote(CLIENTE_A, es_bien_inversion=True)
    f = pr.facturas[0]
    assert (pr.cuenta, f.concepto, f.subclave) == ("200", "200", "200")
    assert "va a la 200" in _textos(f)
    # Y una compra normal del mismo proveedor sí lleva la recordada.
    assert _lote(CLIENTE_A, num_factura="M-2").cuenta == "622"


def test_la_memoria_no_pisa_la_200_aunque_lleve_suplido():
    procesar.recordar_cuenta_proveedor(ALMACEN, ALMACEN_NOMBRE, "622", "G13",
                                       CLIENTE_A)
    pr = _lote(CLIENTE_A, es_bien_inversion=True, suplidos=50.0, total=171.0)
    assert [(f.concepto, f.subclave) for f in pr.facturas] == \
        [("200", "200")] * 2


def test_va_a_la_200_solo_con_la_cuenta_200():
    f = Factura(num_factura="I-1", fecha="03/09/2026", nombre=ALMACEN_NOMBRE,
                nif=ALMACEN, concepto="200", subclave="200", base_iva=1000.0,
                pct_iva=21.0, cuota_iva=210.0, total_impreso=1210.0,
                confianza_ia="alta", tratamiento_manual="Bien de inversión")
    assert "va a la 200" in _textos(f)
    # La persona dice que es un gasto corriente: el aviso ya no dice «200».
    f.concepto, f.subclave = "622", "G13"
    textos = _textos(f)
    assert "Posible bien de inversión" in textos
    assert "la 200" not in textos


def test_una_venta_con_bien_de_inversion_no_dice_200():
    pr = construir(_datos(emisor_nombre="CLIENTE PRUEBA", emisor_nif=CLIENTE_A,
                          receptor_nombre="COMPRADOR PRUEBA SL",
                          receptor_nif=CLIENTE_B, es_bien_inversion=True,
                          cuenta_ingreso="700", subclave_ingreso="I01"),
                   CLIENTE_A, "CLIENTE PRUEBA")
    assert pr.tipo == "venta"
    f = pr.facturas[0]
    assert f.concepto != "200"
    textos = _textos(f)
    assert "Posible bien de inversión" in textos
    assert "la 200" not in textos


# =====================================================================
# 5. Varios: homónimo, «posiblemente ya exportada», redondeo en un abono
# =====================================================================
NOMBRE_CLIENTE = "JUAN PRUEBA EJEMPLO"


def _compra_del_cliente(numero, receptor_nif=CLIENTE_A):
    return _datos(receptor_nif, receptor_nombre=NOMBRE_CLIENTE,
                  num_factura=numero)


@pytest.mark.parametrize("nombre_leido", [
    NOMBRE_CLIENTE,
    # El apellido leído con guion es el mismo nombre para los clientes: el
    # homónimo tampoco puede quedar apuntado como proveedor.
    pytest.param("JUAN PRUEBA-EJEMPLO", id="apellido-con-guion"),
])
def test_homonimo_se_pregunta_una_vez_por_lote_y_no_es_proveedor(monkeypatch,
                                                                 nombre_leido):
    clientes.marcar_cliente(CLIENTE_A, NOMBRE_CLIENTE)
    preguntas = []

    def elegir_el_cliente(dialogo):
        preguntas.append([c.nif for c in dialogo._candidatos])
        for i, c in enumerate(dialogo._candidatos):
            if c.nif == CLIENTE_A:
                dialogo.grupo.button(i).setChecked(True)
        return QDialog.Accepted
    monkeypatch.setattr(DialogoCliente, "exec", elegir_el_cliente)

    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    for bloque in (1, 2):
        # Cada bloque trae compras del cliente y una de otra persona que se
        # llama igual, con su propio NIF (válido).
        crudos = [(b"", f"taco{bloque}.pdf", i + 1,
                   _compra_del_cliente(f"B{bloque}-{i:03d}")) for i in range(3)]
        homonimo = _compra_del_cliente(f"H{bloque}-001", HOMONIMO)
        homonimo["receptor_nombre"] = nombre_leido
        crudos.append((b"", f"taco{bloque}.pdf", 4, homonimo))
        v._rutas_actuales = [f"taco{bloque}.pdf"]
        v._on_terminado(procesar.preparar_lote(crudos, NOMBRE_CLIENTE,
                                               CLIENTE_A),
                        NOMBRE_CLIENTE, CLIENTE_A, crudos)

    assert len(preguntas) == 1, preguntas
    assert HOMONIMO in preguntas[0]
    assert v._cliente_nif == CLIENTE_A
    assert v.tabla.rowCount() == 8
    # El homónimo no queda apuntado como proveedor con el nombre del cliente…
    for nombre in {NOMBRE_CLIENTE, nombre_leido}:
        ficha = proveedores.leer(procesar.clave_proveedor(nombre))
        assert not ficha or normaliza_nif(ficha.get("nif")) != HOMONIMO, ficha
    assert not proveedores.buscar_por_nif(HOMONIMO)
    # …y el cliente sigue siendo el cliente en el siguiente lote.
    assert not procesar.analizar_cliente(
        [_compra_del_cliente("C-001")]).dudoso


def _fra(numero, fecha, nif, nombre, total=605.0):
    return Factura(num_factura=numero, fecha=fecha, nombre=nombre, nif=nif,
                   concepto="621", subclave="G12", base_iva=500.0, pct_iva=21.0,
                   cuota_iva=105.0, total_impreso=total, confianza_ia="alta",
                   verificacion="doble")


def _ventana_con(*facturas):
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._cliente_nif, v._cliente_nombre = CLIENTE_A, "CLIENTE PRUEBA"
    v._bloques = [{"nombre": "b1", "cliente": "CLIENTE PRUEBA",
                   "nif": CLIENTE_A}]
    for f in facturas:
        v._anadir_fila(b"", f, "gasto", f.concepto, f.subclave, "", "b1")
    v._revalidar_todo()
    return v


ALQUILER = "INMUEBLES DE PRUEBA SL"


@pytest.mark.parametrize("anterior,actual,sale", [
    # El caso bueno: exportada sin NIF y releída con él, mismo nº y total.
    pytest.param(("A-1047", "15/02/2026", None, ALQUILER),
                 ("A-1047", "20/02/2026", PROVEEDOR, ALQUILER), True,
                 id="mismo-numero-y-total"),
    # Nº corto: «12» o «F-1» se repiten cada año (el alquiler, la cuota).
    pytest.param(("12", "15/02/2026", None, ALQUILER),
                 ("12", "20/02/2026", PROVEEDOR, ALQUILER), False,
                 id="numero-de-dos-cifras"),
    pytest.param(("F-1", "15/02/2026", None, ALQUILER),
                 ("F-1", "20/02/2026", PROVEEDOR, ALQUILER), False,
                 id="numero-F-1"),
    pytest.param(("123", "15/02/2026", None, ALQUILER),
                 ("123", "20/02/2026", PROVEEDOR, ALQUILER), True,
                 id="tres-cifras-ya-cuenta"),
    # Otro año: la misma factura del año pasado no es esta.
    pytest.param(("A-1047", "15/02/2025", PROVEEDOR, ALQUILER),
                 ("A-1047", "15/02/2026", PROVEEDOR, ALQUILER), False,
                 id="otro-anio"),
    # Dos NIF válidos y distintos: otra empresa con el mismo nº y total.
    pytest.param(("A-1047", "15/02/2026", PROVEEDOR, ALQUILER),
                 ("A-1047", "20/05/2026", ALMACEN, ALMACEN_NOMBRE), False,
                 id="dos-nif-validos"),
    # Un NIF mal leído (no válido) frente al bueno: puede ser la misma.
    pytest.param(("A-1047", "15/02/2026", PROVEEDOR, ALQUILER),
                 ("A-1047", "20/02/2026", "B12345675", ALQUILER), True,
                 id="un-nif-mal-leido"),
])
def test_posiblemente_ya_exportada(anterior, actual, sale):
    historial.registrar(CLIENTE_A, {"gasto": [_fra(*anterior)]},
                        {"gasto": "x.xlsx"}, "CLIENTE PRUEBA")
    v = _ventana_con(_fra(*actual))
    assert ("POSIBLEMENTE YA EXPORTADA" in _mensajes(v)) is sale, _mensajes(v)


@pytest.mark.parametrize("base,cuota", [(-1000.0, -210.04),
                                        (-12345.67, -2592.62)])
def test_el_redondeo_de_un_abono_es_ambar_no_rojo(base, cuota):
    total = round(base + cuota, 2)
    f = Factura(num_factura="AB-1", fecha="03/09/2026", nombre=PROVEEDOR_NOMBRE,
                nif=PROVEEDOR, concepto="622", subclave="G13", base_iva=base,
                pct_iva=21.0, cuota_iva=cuota, total_impreso=total,
                confianza_ia="alta")
    res = validar(f)
    assert res.estado == REVISAR, res.mensajes
    assert any("redondeo por líneas" in str(m) for m in res.mensajes)
    # Más allá del margen sigue siendo un error, también en negativo.
    f.cuota_iva = round(cuota - 10, 2)
    f.total_impreso = round(base + f.cuota_iva, 2)
    assert validar(f).estado == ERROR


# =====================================================================
# 6. Doble lectura sin falsos ámbar
# =====================================================================
def _discrepancias(uno, dos, tipo="gasto"):
    crudo = dict(uno, _verificacion="doble", _modelo_1="a", _modelo_2="b",
                 _lectura_2=dos, _discrepancias=comparar(uno, dos))
    return procesar.discrepancias_de(crudo, tipo)


@pytest.mark.parametrize("uno,dos", [
    pytest.param(dict(fecha_operacion=None),
                 dict(fecha_operacion="03/09/2026"), id="fecha-operacion"),
    pytest.param(dict(fecha_operacion="01/09/2026"),
                 dict(fecha_operacion="02/08/2026"), id="fecha-operacion-otra"),
    pytest.param(dict(sustituye_a=None), dict(sustituye_a="M-0001"),
                 id="sustituye-a"),
    pytest.param(dict(base_irpf=None, pct_irpf=None, cuota_irpf=None,
                      suplidos=None),
                 dict(base_irpf=0, pct_irpf=0, cuota_irpf=0, suplidos=0),
                 id="irpf-y-suplidos-none-frente-a-0"),
    pytest.param(dict(base_irpf="", pct_irpf="", cuota_irpf="", suplidos=""),
                 dict(base_irpf=0.0, pct_irpf=0.0, cuota_irpf=0.0,
                      suplidos=0.0),
                 id="irpf-y-suplidos-vacio-frente-a-0"),
    pytest.param(dict(cuenta_gasto="628", subclave_gxx="G16"),
                 dict(cuenta_gasto="628 (G16) SUMINISTROS GAS",
                      subclave_gxx=None), id="628-con-su-texto"),
    pytest.param(dict(cuenta_gasto="622", subclave_gxx="G13"),
                 dict(cuenta_gasto="622", subclave_gxx=None),
                 id="subclave-unica-dada-por-puesta"),
])
def test_lecturas_equivalentes_no_dan_discrepancia(uno, dos):
    disc = _discrepancias(_datos(**uno), _datos(**dos))
    assert disc == (), [d["campo"] for d in disc]
    # Y la factura sale «Verificada» (sin ámbar de la doble lectura).
    crudo = _datos(**uno, _verificacion="doble",
                   _discrepancias=comparar(_datos(**uno), _datos(**dos)))
    [f] = construir(crudo, CLIENTE_A, "CLIENTE PRUEBA").facturas
    assert "Doble lectura" not in _textos(f)


def test_con_las_dos_en_bien_de_inversion_no_se_compara_la_cuenta():
    a = _datos(es_bien_inversion=True, cuenta_gasto="629", subclave_gxx="G22")
    b = _datos(es_bien_inversion=True, cuenta_gasto="622", subclave_gxx="G13")
    assert _discrepancias(a, b) == ()
    # Si solo una lo dice, sí: la cuenta y el bien de inversión.
    c = _datos(es_bien_inversion=False, cuenta_gasto="622", subclave_gxx="G13")
    campos = {d["campo"] for d in _discrepancias(a, c)}
    assert campos == {"es_bien_inversion", "cuenta_gasto"}


def test_bien_de_inversion_no_apunta_a_ninguna_columna():
    a = _datos(es_bien_inversion=False)
    b = _datos(es_bien_inversion=True)
    [d] = _discrepancias(a, b)
    assert d["campo"] == "es_bien_inversion"
    assert d["campo_factura"] == ""
    # En la tabla: la factura queda en ámbar, pero no se pinta la cuenta como
    # si la discrepancia fuera de la cuenta, y elegir una lectura no la toca.
    v = _ventana_con(_fra("B-100", "03/09/2026", PROVEEDOR, PROVEEDOR_NOMBRE)
                     .__class__(**{**_fra("B-100", "03/09/2026", PROVEEDOR,
                                          PROVEEDOR_NOMBRE).__dict__,
                                   "discrepancias": (d,)}))
    assert v.filas[0]["estado"] == REVISAR
    assert "Bien de inversión no coincide" in _mensajes(v)
    assert "Bien de inversión" not in v.tabla.item(0, C_CUENTA).toolTip()
    v._resolver_discrepancia(0, 0, 2)
    assert _cuentas(v) == [("621", "G12")]
    v._resolver_discrepancia(0, 0, 1)
    assert _cuentas(v) == [("621", "G12")]
    assert "Bien de inversión no coincide" not in _mensajes(v)


def test_una_diferencia_real_de_cuenta_si_sale():
    a = _datos(cuenta_gasto="622", subclave_gxx="G13")
    b = _datos(cuenta_gasto="629", subclave_gxx="G22")
    [d] = _discrepancias(a, b)
    assert (d["campo"], d["valor_1"], d["valor_2"], d["campo_factura"]) == \
        ("cuenta_gasto", "622 (G13)", "629 (G22)", "concepto")
    # Misma cuenta y otra subclave también es una diferencia de cuenta.
    c = _datos(cuenta_gasto="629", subclave_gxx="G44")
    [d] = _discrepancias(b, c)
    assert (d["valor_1"], d["valor_2"]) == ("629 (G22)", "629 (G44)")
    # En una venta la cuenta de gasto no cuenta.
    assert _discrepancias(a, b, "venta") == ()


# =====================================================================
# 7. Ficha: elegir la cuenta o la retención de una de las dos lecturas
# =====================================================================
def _factura(**cambios):
    datos = dict(num_factura="F-100", fecha="03/09/2026",
                 nombre=PROVEEDOR_NOMBRE, nif=PROVEEDOR, concepto="622",
                 subclave="G13", base_iva=100.0, pct_iva=21.0, cuota_iva=21.0,
                 total_impreso=176.0, confianza_ia="alta",
                 verificacion="doble")
    datos.update(cambios)
    return Factura(**datos)


def _documento(*lineas, disc):
    """Una factura de varias líneas (mismo documento) con una discrepancia,
    del cliente A."""
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._cliente_nif, v._cliente_nombre = CLIENTE_A, "CLIENTE PRUEBA"
    for cambios in lineas:
        f = _factura(documento_id="doc", lineas_factura=len(lineas),
                     discrepancias=(disc,), **cambios)
        v._anadir_fila(b"", f, "gasto", f.concepto, f.subclave, "")
    v._revalidar_todo()
    return v


DOS_LINEAS = (dict(), dict(base_iva=50.0, pct_iva=10.0, cuota_iva=5.0))

DISC_CUENTA = {"campo": "cuenta_gasto", "etiqueta": "Cuenta de gasto",
               "valor_1": "622 (G13)", "valor_2": "629 (G22)",
               "campo_factura": "concepto",
               "texto": "Doble lectura: Cuenta de gasto no coincide"}


def _cuentas(v):
    return [(x["factura"].concepto, x["factura"].subclave) for x in v.filas]


def _celdas_cuenta(v):
    return [(v.tabla.item(r, C_CUENTA).text(), v.tabla.item(r, C_GXX).text())
            for r in range(v.tabla.rowCount())]


def _lote_del_proveedor(cliente=CLIENTE_A):
    return _lote(cliente, emisor_nombre=PROVEEDOR_NOMBRE, emisor_nif=PROVEEDOR,
                 num_factura="F-200")


def test_usar_la_cuenta_de_la_lectura_2_la_pone_en_toda_la_factura():
    v = _documento(*DOS_LINEAS, disc=dict(DISC_CUENTA))
    v._resolver_discrepancia(0, 0, 2)
    assert _cuentas(v) == [("629", "G22"), ("629", "G22")]
    assert [c[0] for c in _celdas_cuenta(v)] == ["629", "629"]
    assert all(c[1].startswith("G22") for c in _celdas_cuenta(v))
    assert [x.presentacion for x in v.filas] == [CORREGIDA, CORREGIDA]
    assert "Doble lectura" not in _mensajes(v, 0) + _mensajes(v, 1)
    # Se recuerda para este proveedor y este cliente…
    pr = _lote_del_proveedor()
    assert (pr.cuenta, pr.gxx) == ("629", "G22")
    assert "otro cliente" not in (pr.aviso or "")
    # …y en otro cliente se propone en ámbar.
    assert "en otro cliente" in (_lote_del_proveedor(CLIENTE_B).aviso or "")


def test_es_correcto_con_la_cuenta_tras_cambiarla_a_mano_la_vuelve_a_poner():
    v = _documento(*DOS_LINEAS, disc=dict(DISC_CUENTA))
    v.tabla.item(0, C_CUENTA).setText("629")
    v.tabla.item(0, C_GXX).setText("G22")
    assert _cuentas(v)[0] == ("629", "G22")
    v._resolver_discrepancia(0, 0, 1)
    assert _cuentas(v) == [("622", "G13"), ("622", "G13")]
    assert [c[0] for c in _celdas_cuenta(v)] == ["622", "622"]
    # Lo que queda recordado es lo elegido, no lo tecleado antes.
    pr = _lote_del_proveedor()
    assert (pr.cuenta, pr.gxx) == ("622", "G13")


def test_la_cuenta_elegida_llega_a_las_lineas_de_una_fila_por_el_total():
    """Una fila «por el total» se rehace desde sus líneas: si la cuenta solo
    se pusiera en la fila, volvería la de antes al rehacerla."""
    lineas = [_factura(documento_id="doc", lineas_factura=2,
                       discrepancias=(dict(DISC_CUENTA),), **x)
              for x in DOS_LINEAS]
    resumen = _factura(documento_id="doc", lineas_factura=1,
                       base_iva=150.0, cuota_iva=26.0,
                       discrepancias=(dict(DISC_CUENTA),))
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._cliente_nif, v._cliente_nombre = CLIENTE_A, "CLIENTE PRUEBA"
    v._anadir_fila(b"", resumen, "gasto", "622", "G13", "", fuentes=lineas)
    v._revalidar_todo()
    v._resolver_discrepancia(0, 0, 2)
    assert [(x.concepto, x.subclave) for x in (resumen, *lineas)] == \
        [("629", "G22")] * 3


RETENCION = (dict(base_irpf=100.0, pct_irpf=15.0, cuota_irpf=15.0,
                  total_impreso=136.0),
             dict(base_iva=30.0, pct_iva=None, cuota_iva=None, es_suplido=True,
                  total_impreso=136.0))


@pytest.mark.parametrize("campo,etiqueta,leido,bueno,columna", [
    ("base_irpf", "Base de la retención", 10.0, 100.0, C_BASE_IRPF),
    ("pct_irpf", "% de retención", 7.0, 15.0, C_PCT_IRPF),
])
def test_la_retencion_de_la_lectura_2_va_a_su_unica_linea(
        campo, etiqueta, leido, bueno, columna):
    disc = {"campo": campo, "etiqueta": etiqueta, "valor_1": leido,
            "valor_2": bueno, "campo_factura": campo,
            "texto": f"Doble lectura: {etiqueta} no coincide"}
    normal, suplido = RETENCION
    v = _documento(dict(normal, **{campo: leido}), suplido, disc=disc)
    assert v._destino_discrepancia(disc, [0, 1]) == [0]
    v._resolver_discrepancia(0, 0, 2)
    assert getattr(v.filas[0]["factura"], campo) == bueno
    assert getattr(v.filas[1]["factura"], campo) is None   # el suplido no
    assert v.tabla.item(0, columna).text().startswith(
        f"{bueno:.2f}".replace(".", ","))
    assert v.filas[0]["estado"] != ERROR, _mensajes(v)
    assert "Doble lectura" not in _mensajes(v)


def test_la_base_de_la_retencion_en_un_abono_va_en_negativo():
    disc = {"campo": "base_irpf", "etiqueta": "Base de la retención",
            "valor_1": 10.0, "valor_2": 100.0, "campo_factura": "base_irpf",
            "texto": "Doble lectura: Base de la retención no coincide"}
    v = _documento(dict(base_iva=-100.0, cuota_iva=-21.0, base_irpf=-10.0,
                        pct_irpf=15.0, cuota_irpf=-15.0, total_impreso=-106.0),
                   disc=disc)
    v._resolver_discrepancia(0, 0, 2)
    assert v.filas[0]["factura"].base_irpf == -100.0


# =====================================================================
# 8. Palabras clave
# =====================================================================
@pytest.mark.parametrize("texto,no_va", [
    ("impuestos incluidos", "631"),
    ("ticket total impuestos incluidos", "631"),
    ("caja registradora", "623"),
    ("registro sanitario del proveedor", "623"),
])
def test_palabras_que_ya_no_cazan_una_cuenta(texto, no_va):
    assert asignar_concepto("gasto", texto) != no_va


@pytest.mark.parametrize("texto,cuenta", [
    ("registro mercantil", "623"),
    ("registro de la propiedad", "623"),
    ("registradores de espana", "623"),
    ("registradores de españa", "623"),
    ("impuesto de circulacion", "631"),
    ("tributos municipales", "631"),
])
def test_palabras_que_si_cazan_su_cuenta(texto, cuenta):
    assert asignar_concepto("gasto", texto) == cuenta


# =====================================================================
# 9. Ficha: la fecha elegida de cualquiera de las dos lecturas, dd/mm/aaaa
# =====================================================================
def _fechas(v):
    return ([x["factura"].fecha for x in v.filas],
            [v.tabla.item(r, C_FECHA).text() for r in range(len(v.filas))])


def test_la_fecha_de_la_lectura_2_queda_en_dd_mm_aaaa():
    disc = {"campo": "fecha", "etiqueta": "Fecha", "valor_1": "03/05/2026",
            "valor_2": "2026-03-05", "campo_factura": "fecha",
            "texto": "Doble lectura: Fecha no coincide"}
    v = _documento(*({**x, "fecha": "03/05/2026"} for x in DOS_LINEAS),
                   disc=disc)
    v._resolver_discrepancia(0, 0, 2)
    assert _fechas(v) == (["05/03/2026"] * 2, ["05/03/2026"] * 2)


def test_la_fecha_de_la_lectura_1_tras_cambiarla_queda_en_dd_mm_aaaa():
    disc = {"campo": "fecha", "etiqueta": "Fecha", "valor_1": "5/3/26",
            "valor_2": "06/03/2026", "campo_factura": "fecha",
            "texto": "Doble lectura: Fecha no coincide"}
    v = _documento(*({**x, "fecha": "05/03/2026"} for x in DOS_LINEAS),
                   disc=disc)
    v.tabla.item(0, C_FECHA).setText("07/03/2026")
    assert v.filas[0]["factura"].fecha == "07/03/2026"
    v._resolver_discrepancia(0, 0, 1)
    assert _fechas(v) == (["05/03/2026"] * 2, ["05/03/2026"] * 2)


# =====================================================================
# Refuerzos de la verificación
# =====================================================================
# 1. Con un cuentas_cliente raro, el otro cliente sigue recibiendo la cuenta
#    de la ficha (no basta con «no rompe»: saltarse la memoria también pasaba).
@pytest.mark.parametrize("raro", RAROS)
def test_cuentas_cliente_raras_no_pierden_la_cuenta_de_la_ficha(raro):
    _ficha_rara(raro)
    pr = _lote(CLIENTE_B)
    assert (pr.cuenta, pr.gxx) == ("600", "G01"), pr.aviso


# 5. Redondeo en abono: una diferencia por encima de 5 céntimos pero dentro
#    de la diezmilésima de la base (aquí 0,20 € con margen 1,23 €).
@pytest.mark.parametrize("signo", [1, -1], ids=["factura", "abono"])
def test_el_margen_de_redondeo_crece_con_la_base_tambien_en_abono(signo):
    base = signo * 12345.67
    esperada = round(base * 0.21, 2)
    f = Factura(num_factura="AB-2", fecha="03/09/2026", nombre=PROVEEDOR_NOMBRE,
                nif=PROVEEDOR, concepto="622", subclave="G13", base_iva=base,
                pct_iva=21.0, cuota_iva=round(esperada + signo * 0.20, 2),
                total_impreso=0.0, confianza_ia="alta")
    f.total_impreso = round(base + f.cuota_iva, 2)
    res = validar(f)
    assert res.estado == REVISAR, res.mensajes
    assert any("redondeo por líneas" in str(m) for m in res.mensajes)
    # Justo por encima del margen (1,23 €): rojo.
    f.cuota_iva = round(esperada + signo * 1.30, 2)
    f.total_impreso = round(base + f.cuota_iva, 2)
    assert validar(f).estado == ERROR


# 5. Homónimo: «una vez por LOTE»; al vaciar y empezar otro, se pregunta otra vez.
def test_homonimo_se_vuelve_a_preguntar_en_otro_lote(monkeypatch):
    clientes.marcar_cliente(CLIENTE_A, NOMBRE_CLIENTE)
    preguntas = []

    def elegir_el_cliente(dialogo):
        preguntas.append(1)
        for i, c in enumerate(dialogo._candidatos):
            if c.nif == CLIENTE_A:
                dialogo.grupo.button(i).setChecked(True)
        return QDialog.Accepted
    monkeypatch.setattr(DialogoCliente, "exec", elegir_el_cliente)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))

    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)

    def leer(nombre_pdf):
        crudos = [(b"", nombre_pdf, 1, _compra_del_cliente("B-001")),
                  (b"", nombre_pdf, 2, _compra_del_cliente("H-001", HOMONIMO))]
        v._rutas_actuales = [nombre_pdf]
        v._on_terminado(procesar.preparar_lote(crudos, NOMBRE_CLIENTE,
                                               CLIENTE_A),
                        NOMBRE_CLIENTE, CLIENTE_A, crudos)
    leer("taco1.pdf")
    leer("taco2.pdf")
    assert len(preguntas) == 1
    v._vaciar_todo()
    leer("taco3.pdf")
    assert len(preguntas) == 2


# 7. En la ficha, el botón «Usar este» de la cuenta de la lectura 2 está activo.
def test_la_cuenta_de_la_lectura_2_se_puede_elegir_en_la_ficha():
    v = _documento(*DOS_LINEAS, disc=dict(DISC_CUENTA))
    [d] = v._datos_ficha(0)["discrepancias"]
    assert d["campo"] == "cuenta_gasto" and d["aplicable"] is True


# 7. En un abono, el % de retención no cambia de signo (la base sí).
def test_el_pct_de_retencion_en_un_abono_sigue_en_positivo():
    disc = {"campo": "pct_irpf", "etiqueta": "% de retención",
            "valor_1": 7.0, "valor_2": 15.0, "campo_factura": "pct_irpf",
            "texto": "Doble lectura: % de retención no coincide"}
    v = _documento(dict(base_iva=-100.0, cuota_iva=-21.0, base_irpf=-100.0,
                        pct_irpf=7.0, cuota_irpf=-15.0, total_impreso=-106.0),
                   disc=disc)
    v._resolver_discrepancia(0, 0, 2)
    assert v.filas[0]["factura"].pct_irpf == 15.0


# 3. Si la cuenta de otro cliente coincide con una que la app puso POR
#    PALABRAS CLAVE (no Gemini), se dice de dónde viene y no se deja el
#    aviso de palabras clave.
def test_misma_cuenta_por_palabras_clave_dice_que_es_de_otro_cliente():
    previa = _lote(CLIENTE_B, cuenta_gasto=None, subclave_gxx=None,
                   concepto_texto="poliza de seguro del local")
    assert "palabras clave" in previa.aviso
    procesar.recordar_cuenta_proveedor(ALMACEN, "ALMACENES DE PRUEBA SA",
                                       previa.cuenta, previa.gxx, CLIENTE_A)
    pr = _lote(CLIENTE_B, cuenta_gasto=None, subclave_gxx=None,
               concepto_texto="poliza de seguro del local")
    assert (pr.cuenta, pr.gxx) == (previa.cuenta, previa.gxx)
    assert "en otro cliente" in pr.aviso
    assert "palabras clave" not in pr.aviso
