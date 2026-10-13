"""El NIF español con el «ES» del NIF-IVA delante se queda sin él (1.26.2).

Hay facturas que imprimen el NIF del proveedor (o del cliente) como NIF-IVA:
ESB12345674. Con «ES», Aplifisa no reconoce al proveedor de siempre, le abre
otra cuenta y puede dejarla como intracomunitaria (el Ámbito lo lleva la
cuenta del proveedor, no el Excel). El usuario pidió que el programa lo quite
solo: ESB12345674 y B12345674 son siempre el mismo, en la lectura, la tabla,
la memoria de proveedores, los clientes, el registro y el Excel, también con
lo guardado por versiones anteriores. Los NIF-IVA de otros países de la UE y
un «ES» seguido de algo que no es un NIF español no se tocan: siguen en ámbar.

Solo NIF de prueba (12345678Z, B12345674, A12345674, X1234567L, E12345674) y
NIF-IVA de otros países inventados.
"""

import json
import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from openpyxl import load_workbook
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from facturas_excel import (
    almacen, clientes, cuadre_anual, doble_lectura, historial,
    identidad_archivo, localizar, proveedores, recoger, registro,
    registro_facturas, sesion, suite, validacion,
)
from facturas_excel.app import C_NIF, VentanaPrincipal
from facturas_excel.config_columnas import leer_config
from facturas_excel.exportar import _valor_celda, exportar_excel
from facturas_excel.modelo import Factura
from facturas_excel.procesar import (
    analizar_cliente, aplicar_recordado, clave_proveedor,
    completar_desde_memoria, construir, normaliza_nif, recordar_cuenta_proveedor,
    recordar_nif,
)
from facturas_excel.rutas import dir_datos, ruta_config
from facturas_excel.tabla_facturas import valor_de_celda
from facturas_excel.validacion import (
    OK, REVISAR, quitar_prefijo_es, validar,
)

_app = QApplication.instance() or QApplication([])

CLIENTE = "12345678Z"
PROVEEDOR = "B12345674"
NOMBRE = "SUMINISTROS PRUEBA SL"


@pytest.fixture(autouse=True)
def hoy_fijo(monkeypatch):
    monkeypatch.setattr(validacion, "_hoy", lambda: date(2026, 10, 13))


def _gasto(emisor_nif="ESB12345674", receptor_nif=CLIENTE, **cambios):
    """Lo que devuelve Gemini de una compra del cliente al proveedor."""
    datos = {"emisor_nombre": NOMBRE, "emisor_nif": emisor_nif,
             "receptor_nombre": "CLIENTE PRUEBA", "receptor_nif": receptor_nif,
             "num_factura": "F-1", "fecha": "10/03/2026",
             "lineas_iva": [{"base": 100, "tipo_iva": 21, "cuota_iva": 21}],
             "total": 121, "concepto_texto": "material de oficina",
             "cuenta_gasto": "629", "subclave_gxx": "G22", "confianza": "alta"}
    datos.update(cambios)
    return datos


def _factura(nif=PROVEEDOR, numero="F-1", **cambios):
    datos = dict(num_factura=numero, fecha="10/03/2026", nombre=NOMBRE, nif=nif,
                 concepto="629", subclave="G22", base_iva=100.0, pct_iva=21.0,
                 cuota_iva=21.0, total_impreso=121.0, confianza_ia="alta",
                 verificacion="doble")
    datos.update(cambios)
    return Factura(**datos)


def _avisos_es(mensajes):
    return [m for m in mensajes if "prefijo ES" in str(m)]


# ------------------------------------------------------------ la función
@pytest.mark.parametrize("leido, queda", [
    ("ESB12345674", "B12345674"),
    ("ESA12345674", "A12345674"),      # empieza por letra: ES + A12345674
    ("ESE12345674", "E12345674"),      # comunidad de bienes
    ("ES12345678Z", "12345678Z"),      # DNI
    ("ESX1234567L", "X1234567L"),      # NIE
    ("es-b.123 456 74", "B12345674"),  # como venga escrito: sale limpio
    ("ES 12345678Z", "12345678Z"),
])
def test_se_quita_el_es_de_un_nif_espanol_valido(leido, queda):
    assert quitar_prefijo_es(leido) == queda
    assert normaliza_nif(leido) == queda


@pytest.mark.parametrize("leido", [
    "ES\tB12345674", "ES\nB12345674", "ES\u00a0B12345674"])
def test_lo_quitado_sale_limpio_aunque_venga_con_un_tabulador_o_un_salto(leido):
    """Un «ES» separado por un tabulador, un salto de línea o un espacio
    duro (pegado de un PDF). Sin limpiar, quedaba «\tB12345674»: pasa el
    control (que no mira los blancos de los extremos), sale en verde y así
    se guardaba en la memoria de proveedores, donde B12345674 ya no lo
    encontraba."""
    assert quitar_prefijo_es(leido) == PROVEEDOR
    assert normaliza_nif(leido) == PROVEEDOR
    assert valor_de_celda(C_NIF, leido) == ("nif", PROVEEDOR)
    assert recordar_nif(NOMBRE, leido)
    assert proveedores.buscar_por_nif(PROVEEDOR)["nif"] == PROVEEDOR


@pytest.mark.parametrize("nif", [
    "DE123456789", "IE1234567T", "FR12345678901", "LU12345678",  # otros de la UE
    "ESB12345670",      # «ES» + algo que no pasa el control: dudoso, tal cual
    "ES", "ESTACION", "B12345674", "12345678Z", "", None,
])
def test_lo_demas_no_se_toca(nif):
    assert quitar_prefijo_es(nif) == nif


# ------------------------------------------------- lectura, validación, Excel
def test_la_lectura_con_es_sale_sin_el_en_verde_y_asi_al_excel(tmp_path):
    pr = construir(_gasto(), CLIENTE, "CLIENTE PRUEBA")
    assert pr.tipo == "gasto"
    [f] = pr.facturas
    assert f.nif == PROVEEDOR
    res = validar(f)
    assert res.estado == OK, res.mensajes
    assert not _avisos_es(res.mensajes)

    config = leer_config(ruta_config("gastos.xml"))
    ruta = str(tmp_path / "gastos.xlsx")
    exportar_excel([f], config, ruta)
    libro = load_workbook(ruta)
    try:
        letra = config.columnas["nif"]
        assert libro.active[f"{letra}{config.primera_fila}"].value == PROVEEDOR
    finally:
        libro.close()


def test_el_nie_con_es_tambien():
    pr = construir(_gasto(emisor_nif="ESX1234567L"), CLIENTE, "CLIENTE PRUEBA")
    assert pr.facturas[0].nif == "X1234567L"
    assert validar(pr.facturas[0]).estado == OK


@pytest.mark.parametrize("nif, aviso", [
    ("DE123456789", "posible operación intracomunitaria"),
    ("IE1234567T", "posible operación intracomunitaria"),
    ("ESB12345670", "dudoso"),
])
def test_los_de_otros_paises_y_un_es_invalido_siguen_igual_y_en_ambar(nif, aviso):
    pr = construir(_gasto(emisor_nif=nif), CLIENTE, "CLIENTE PRUEBA")
    [f] = pr.facturas
    assert f.nif == nif
    res = validar(f)
    assert res.estado == REVISAR
    assert any(aviso in m for m in res.mensajes)
    assert _valor_celda("nif", f.nif, "texto") == nif


def test_si_llega_uno_con_es_sigue_avisando_y_al_excel_va_sin_el():
    """Por si algún camino lo deja pasar: la fila avisa en ámbar (como
    hasta ahora) y el Excel lo lleva ya sin «ES»."""
    res = validar(_factura(nif="ESB12345674"))
    assert res.estado == REVISAR and _avisos_es(res.mensajes)
    assert _valor_celda("nif", "ESB12345674", "texto") == PROVEEDOR
    assert _valor_celda("nif", "ES-12.345.678-Z", "texto") == CLIENTE


# -------------------------------------------------------------- doble lectura
def test_con_y_sin_es_las_dos_lecturas_dicen_lo_mismo():
    uno = _gasto(emisor_nif="ESB12345674", receptor_nif="ES12345678Z")
    dos = _gasto(emisor_nif=PROVEEDOR, receptor_nif=CLIENTE)
    assert not [d for d in doble_lectura.comparar(uno, dos)
                if d["campo"].endswith("_nif")]
    otro = _gasto(emisor_nif="ESA12345674")
    assert [d["campo"] for d in doble_lectura.comparar(uno, otro)] == ["emisor_nif"]
    # Un NIF bueno con «ES» no pide pagar otra lectura; uno de otro país sí.
    assert not doble_lectura.es_dudosa(uno)
    assert doble_lectura.es_dudosa(_gasto(emisor_nif="DE123456789"))


# -------------------------------------------------------------------- tabla
def _ventana(*facturas, cliente=CLIENTE):
    clientes.guardar_regimen_irpf(cliente, clientes.OTRO)
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._cliente_nif, v._cliente_nombre = cliente, "CLIENTE PRUEBA"
    v._bloques = [{"nombre": "b1", "procesadas": [], "crudos": [],
                   "cliente": "CLIENTE PRUEBA", "nif": cliente}]
    for f in facturas:
        v._anadir_fila(b"", f, "gasto", "629", "G22", "", "b1")
    v._revalidar_todo()
    return v


def test_escrito_en_la_tabla_con_es_se_queda_sin_el():
    v = _ventana(_factura(nif=None))
    v.tabla.item(0, C_NIF).setText("ESB12345674")
    f = v.filas[0].factura
    assert f.nif == PROVEEDOR
    assert v.tabla.item(0, C_NIF).text() == PROVEEDOR    # lo que irá al Excel
    assert not _avisos_es(v.filas[0]["mensajes"])
    # Escrito por una persona: se recuerda para ese proveedor, sin «ES».
    assert proveedores.leer(clave_proveedor(NOMBRE))["nif"] == PROVEEDOR
    # Uno de otro país, tal cual.
    v.tabla.item(0, C_NIF).setText("DE123456789")
    assert f.nif == "DE123456789"
    assert v.tabla.item(0, C_NIF).text() == "DE123456789"


def test_elegir_en_la_ficha_la_lectura_con_es_la_pone_sin_el():
    disc = {"campo": "emisor_nif", "etiqueta": "NIF del emisor",
            "valor_1": PROVEEDOR, "valor_2": "ESA12345674",
            "campo_factura": "nif", "texto": "Doble lectura: NIF no coincide"}
    f = _factura(discrepancias=(disc,))
    v = _ventana(f)
    v._resolver_discrepancia(0, 0, 2)
    assert f.nif == "A12345674"
    assert v.tabla.item(0, C_NIF).text() == "A12345674"


# ------------------------------------------------- memoria de proveedores
def test_el_proveedor_recordado_sin_es_se_encuentra_leyendo_con_es():
    recordar_cuenta_proveedor(PROVEEDOR, NOMBRE, "622", "G13", CLIENTE)
    pr = construir(_gasto(), CLIENTE, "CLIENTE PRUEBA")
    assert aplicar_recordado([pr], CLIENTE) == 1
    assert (pr.cuenta, pr.gxx) == ("622", "G13")
    assert proveedores.buscar_por_nif("ESB12345674")["nif"] == PROVEEDOR


def _ficha_vieja(**cambios):
    """Una ficha de proveedor como la dejaba una versión anterior: con el
    NIF y el cliente de su cuenta con «ES» delante."""
    ficha = {"nif": "ESB12345674", "nombre": NOMBRE, "manual": True,
             "cuenta": "622", "gxx": "G13", "cuenta_manual": True,
             "cuentas_cliente": {"ES12345678Z": ["622", "G13"]}}
    ficha.update(cambios)
    almacen.Coleccion("proveedores", dir_datos()).guardar(
        clave_proveedor(NOMBRE), ficha)


def test_la_ficha_vieja_con_es_se_encuentra_y_da_su_nif_sin_el():
    _ficha_vieja()
    assert proveedores.buscar_por_nif(PROVEEDOR)["nif"] == PROVEEDOR
    # Su cuenta para este cliente (guardada con el cliente con «ES»).
    pr = construir(_gasto(emisor_nif=PROVEEDOR), CLIENTE, "CLIENTE PRUEBA")
    assert aplicar_recordado([pr], CLIENTE) == 1
    assert (pr.cuenta, pr.gxx) == ("622", "G13")
    assert "otro cliente" not in pr.aviso
    # El mismo NIF leído sin «ES» no es un «OJO, tiene guardado otro».
    assert completar_desde_memoria([pr], CLIENTE) == 0
    assert not getattr(pr, "conflicto_nif", None) and "OJO" not in pr.aviso
    # Sin NIF en la hoja: el de memoria, ya sin «ES».
    sin_nif = construir(_gasto(emisor_nif=""), CLIENTE, "CLIENTE PRUEBA")
    assert completar_desde_memoria([sin_nif], CLIENTE) == 1
    assert sin_nif.facturas[0].nif == PROVEEDOR


def test_dos_fichas_del_proveedor_con_y_sin_es_no_pierden_su_cuenta():
    """Hasta la 1.26.1, ESB12345674 y B12345674 eran dos proveedores: leídos
    con otro nombre, cada uno tenía su ficha y la cuenta que una persona le
    puso para su cliente. Ahora son el mismo y se usa una de las dos fichas:
    la cuenta de este cliente que estaba en la otra no puede perderse (salía
    la de otro cliente, en ámbar)."""
    col = almacen.Coleccion("proveedores", dir_datos())
    col.guardar("AAA SUMINISTROS", {
        "nif": "ESB12345674", "nombre": "AAA SUMINISTROS", "manual": True,
        "cuenta": "600", "gxx": "G01", "cuenta_manual": True,
        "cuentas_cliente": {"ESX1234567L": ["600", "G01"]}})
    col.guardar(clave_proveedor(NOMBRE), {
        "nif": PROVEEDOR, "nombre": NOMBRE, "manual": True, "cuenta": "622",
        "gxx": "G13", "cuenta_manual": True,
        "cuentas_cliente": {CLIENTE: ["622", "G13"]}})
    for leido in (PROVEEDOR, "ESB12345674"):
        pr = construir(_gasto(emisor_nif=leido), CLIENTE, "CLIENTE PRUEBA")
        assert aplicar_recordado([pr], CLIENTE) == 1
        assert (pr.cuenta, pr.gxx) == ("622", "G13"), pr.aviso
        assert "otro cliente" not in pr.aviso
    # Y el otro cliente sigue con la suya.
    pr = construir(_gasto(receptor_nif="X1234567L"), "X1234567L", "OTRO CLIENTE")
    assert aplicar_recordado([pr], "X1234567L") == 1
    assert (pr.cuenta, pr.gxx) == ("600", "G01"), pr.aviso


def test_al_guardar_la_ficha_vieja_queda_sin_es_y_sin_duplicar():
    _ficha_vieja()
    recordar_cuenta_proveedor(PROVEEDOR, NOMBRE, "629", "G22", CLIENTE)
    crudas = almacen.Coleccion("proveedores", dir_datos()).leer_todo()
    assert list(crudas) == [clave_proveedor(NOMBRE)]
    ficha = crudas[clave_proveedor(NOMBRE)]
    assert ficha["nif"] == PROVEEDOR
    assert ficha["cuentas_cliente"] == {CLIENTE: ["629", "G22"]}


# ------------------------------------------------------------------ clientes
def test_el_cliente_del_lote_con_es_es_el_mismo():
    datos = [_gasto(emisor_nif="A12345674", receptor_nif="ESB12345674",
                    emisor_nombre="OTRO PROVEEDOR SA",
                    receptor_nombre="CLIENTE PRUEBA SL"),
             _gasto(emisor_nif="E12345674", receptor_nif=PROVEEDOR,
                    emisor_nombre="COMUNIDAD PRUEBA CB",
                    receptor_nombre="CLIENTE PRUEBA SL"),
             _gasto(emisor_nif="ES12345678Z", receptor_nif="ESB12345674",
                    emisor_nombre="AUTONOMO PRUEBA",
                    receptor_nombre="CLIENTE PRUEBA SL")]
    analisis = analizar_cliente(datos)
    assert analisis.mejor.nif == PROVEEDOR and analisis.mejor.veces == 3
    assert not any(c.nif.startswith("ES") for c in analisis.candidatos)


def test_las_fichas_viejas_de_clientes_con_es_se_encuentran_sin_perder_nada():
    almacen.Coleccion("clientes", dir_datos()).guardar(
        "ESB12345674", {"nombre": "CLIENTE PRUEBA SL", "confirmado": True,
                        "regimen_recargo": clientes.DESGLOSE})
    assert clientes.es_cliente_confirmado(PROVEEDOR)
    assert clientes.nombre_confirmado(PROVEEDOR) == "CLIENTE PRUEBA SL"
    assert clientes.regimen_recargo(PROVEEDOR) == clientes.DESGLOSE
    assert clientes.regimen_recargo("ESB12345674") == clientes.DESGLOSE
    # Al guardar algo nuevo del cliente queda una sola ficha, con todo.
    clientes.guardar_regimen_recargo("ESB12345674", clientes.TOTAL)
    crudas = almacen.Coleccion("clientes", dir_datos()).leer_todo()
    assert "ESB12345674" not in crudas
    assert crudas[PROVEEDOR] == {
        "nombre": "CLIENTE PRUEBA SL", "confirmado": True,
        "regimen_recargo": clientes.TOTAL, "recargo_equivalencia": True}


def test_con_las_dos_fichas_manda_la_de_sin_es():
    col = almacen.Coleccion("clientes", dir_datos())
    col.guardar("ES12345678Z", {"nombre": "VIEJO", "confirmado": True,
                                "regimen_recargo": clientes.TOTAL})
    col.guardar(CLIENTE, {"nombre": "NUEVO", "regimen_irpf": clientes.DIRECTA})
    assert clientes._leer_todo() == {CLIENTE: {
        "nombre": "NUEVO", "confirmado": True, "regimen_recargo": clientes.TOTAL,
        "regimen_irpf": clientes.DIRECTA}}
    assert clientes.regimen_irpf(CLIENTE) == clientes.DIRECTA
    # Un «ES» que no deja un NIF español no se junta con nada.
    col.guardar("ESB12345670", {"nombre": "DUDOSO"})
    assert clientes._leer_todo()["ESB12345670"] == {"nombre": "DUDOSO"}


def test_un_es_dudoso_no_cambia_la_letra_que_dice_si_es_sociedad():
    """ESB12345670 (un dígito mal leído) se queda tal cual, pero para la ley
    sigue siendo una B, una sociedad: ni recargo (art. 148 LIVA) ni
    estimación directa. Hasta la 1.26.1 se miraba la letra de detrás del
    «ES»; si se mira la «E» del «ES», pasaba por comunidad de bienes."""
    assert quitar_prefijo_es("ESB12345670") == "ESB12345670"
    assert not clientes.puede_estar_en_recargo("ESB12345670")
    assert not clientes.puede_tributar_irpf("ESB12345670")
    assert clientes.regimen_irpf("ESB12345670") == clientes.OTRO
    clientes.guardar_regimen_irpf("ESB12345670", clientes.DIRECTA)
    assert clientes.regimen_irpf("ESB12345670") == clientes.OTRO
    # Un DNI mal leído con «ES» delante sigue siendo una persona física.
    assert clientes.puede_estar_en_recargo("ES12345678A")


def test_el_directorio_de_la_suite_con_es_es_el_mismo_cliente():
    ruta = suite.ruta_directorio()
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump({"schema_version": 1, "clientes": {"ESB12345674": {
            "nif": "ESB12345674", "nombre": "CLIENTE PRUEBA SL"}}}, fh)
    assert suite.es_cliente(PROVEEDOR)
    assert suite.nombre_de(PROVEEDOR) == "CLIENTE PRUEBA SL"
    assert clientes.es_cliente_confirmado(PROVEEDOR)
    # Confirmarlo aquí no le hace otra ficha en el directorio común.
    suite.registrar_cliente(PROVEEDOR, "CLIENTE PRUEBA SL")
    with open(ruta, encoding="utf-8") as fh:
        assert list(json.load(fh)["clientes"]) == ["ESB12345674"]


@pytest.mark.parametrize("orden", [("B12345674", "ESB12345674"),
                                   ("ESB12345674", "B12345674")])
def test_en_el_directorio_de_la_suite_con_las_dos_formas_manda_la_de_sin_es(orden):
    """El directorio común puede tener al cliente de las dos formas (otro
    programa, o este antes de la 1.26.2, lo apuntó con «ES»). Como en las
    fichas de clientes, manda la de sin «ES», sea cual sea el orden del
    fichero, y no se le apuntan cosas a la otra."""
    entradas = {"B12345674": {"nif": "B12345674", "nombre": "CLIENTE PRUEBA SL"},
                "ESB12345674": {"nif": "ESB12345674", "nombre": "NOMBRE VIEJO SL"}}
    ruta = suite.ruta_directorio()
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump({"schema_version": 1,
                   "clientes": {k: entradas[k] for k in orden}}, fh)
    assert suite.nombre_de(PROVEEDOR) == "CLIENTE PRUEBA SL"
    assert suite.nombre_de("ESB12345674") == "CLIENTE PRUEBA SL"
    assert not suite.registrar_cliente(PROVEEDOR, "CLIENTE PRUEBA SL")
    with open(ruta, encoding="utf-8") as fh:
        assert json.load(fh)["clientes"] == entradas


# ------------------------------------------------- registro de exportadas
def _registro_viejo(*facturas, cliente=CLIENTE, quedan_las_nuevas=False):
    """Lo exportado como lo apuntaba una versión anterior: con el NIF del
    cliente y el del proveedor con «ES» delante (y, si se pide, también la
    ficha de cada una sin «ES»: la misma factura apuntada de las dos
    formas). Como antes de instalar la 1.26.2: sin pasar a sin «ES»."""
    historial.registrar(cliente, {"gasto": list(facturas)},
                        {"gasto": "C:/x/GASTOS 2026.xlsx"})
    with almacen.conexion(dir_datos()) as con:
        for fila in [dict(f) for f in con.execute("SELECT * FROM facturas")]:
            vieja = dict(
                fila, cliente="ES" + cliente, cliente_nif="ES" + cliente,
                nif="ES" + fila["nif"],
                id=fila["id"].replace(f"{cliente}#", f"ES{cliente}#").replace(
                    f"|{fila['nif']}|", f"|ES{fila['nif']}|"))
            if not quedan_las_nuevas:
                con.execute("DELETE FROM facturas WHERE id = ?", (fila["id"],))
            con.execute(registro_facturas._INSERTAR,
                        tuple(vieja[c] for c in registro_facturas._COLUMNAS))
        con.execute("DELETE FROM migraciones WHERE coleccion = 'nif_sin_es'")
    registro_facturas._sin_es_migradas.clear()


def _fichas_del_registro():
    with almacen.conexion(dir_datos()) as con:
        return [dict(f) for f in con.execute("SELECT * FROM facturas ORDER BY id")]


def test_lo_exportado_con_es_sale_como_ya_exportado():
    _registro_viejo(_factura(numero="F-1"), _factura(numero="F-2", base_iva=50.0,
                                                     cuota_iva=10.5,
                                                     total_impreso=60.5))
    ya = historial.buscar(CLIENTE, _factura(numero="F-1"), "gasto")
    assert ya and ya["archivo"] == "GASTOS 2026.xlsx" and ya["nif"] == PROVEEDOR
    assert set(historial.exportadas_de(CLIENTE)) == {
        "gasto|B12345674|F1|2026-03-10", "gasto|B12345674|F2|2026-03-10"}
    # El cuadre del año y la lista de clientes lo ven del cliente sin «ES».
    assert len(cuadre_anual.facturas_del_registro(
        CLIENTE, "", date(2026, 1, 1), date(2026, 12, 31))) == 2
    assert [nif for nif, _ in registro_facturas.clientes()] == [CLIENTE]
    with almacen.conexion(dir_datos()) as con:
        assert con.execute("SELECT origen FROM migraciones WHERE coleccion = ?",
                           ("nif_sin_es",)).fetchone()[0] == "2 fichas"
    # Y en la tabla, la misma factura leída otra vez avisa.
    v = _ventana(_factura(numero="F-1"))
    assert v.filas[0].ya_exportada
    assert any("YA EXPORTADA" in m for m in v.filas[0]["mensajes"])


def test_la_misma_factura_apuntada_con_y_sin_es_queda_en_una_ficha():
    """Exportada con «ES» y apuntada también sin él (solo leída): al
    juntarlas no se pierde que ya se exportó, ni su Excel."""
    _registro_viejo(_factura(numero="F-1"), quedan_las_nuevas=True)
    with almacen.conexion(dir_datos()) as con:
        con.execute("UPDATE facturas SET estado = 'leida', revisada_en = NULL, "
                    "exportada_en = NULL, excel = NULL WHERE cliente = ?",
                    (CLIENTE,))
    assert len(_fichas_del_registro()) == 2
    ya = historial.buscar(CLIENTE, _factura(numero="F-1"), "gasto")
    assert ya and ya["estado"] == registro_facturas.EXPORTADA
    assert ya["archivo"] == "GASTOS 2026.xlsx"
    [ficha] = _fichas_del_registro()
    assert (ficha["cliente"], ficha["nif"]) == (CLIENTE, PROVEEDOR)
    assert ficha["leida_en"] and ficha["exportada_en"]


def test_buscar_el_nif_con_es_encuentra_la_factura_apuntada_sin_el():
    """En el registro de facturas y en el buscador del lote se busca el NIF
    como viene en el papel. Con «ES» delante no encontraba nada: la factura
    ya está apuntada sin él (también las de antes, al convertir el
    registro)."""
    from facturas_excel.consulta import coincide_busqueda
    historial.registrar(CLIENTE, {"gasto": [_factura()]},
                        {"gasto": "C:/x/GASTOS 2026.xlsx"})
    for texto in (PROVEEDOR, "ESB12345674", "es-b12345674", "SUMINISTROS ESB12345674"):
        assert [f["nif"] for f in registro_facturas.consultar(texto)] == [PROVEEDOR], texto
        assert coincide_busqueda(_factura(), texto), texto
    # Lo que no es un NIF español con «ES» se busca tal cual.
    assert registro_facturas.consultar("ESB12345670") == []
    assert not coincide_busqueda(_factura(), "ESB12345670")
    assert not coincide_busqueda(_factura(), "ESTACION")


def test_restaurar_una_copia_de_antes_de_la_1262_tambien_la_pasa_a_sin_es():
    """Las copias de seguridad diarias de antes de instalar la 1.26.2 tienen
    el registro con «ES». Restaurada una con el programa abierto, se quedaba
    así hasta volver a abrirlo (la conversión constaba como hecha): la misma
    factura leída otra vez no salía «YA EXPORTADA», y se podía mandar dos
    veces a Aplifisa."""
    from facturas_excel import copias
    _registro_viejo(_factura(numero="F-1"))
    copia = copias.hacer("a mano")             # como la diaria de la 1.26.1
    assert historial.buscar(CLIENTE, _factura(numero="F-1"), "gasto")
    copias.restaurar(copia)
    ya = historial.buscar(CLIENTE, _factura(numero="F-1"), "gasto")
    assert ya and ya["nif"] == PROVEEDOR
    assert [nif for nif, _ in registro_facturas.clientes()] == [CLIENTE]


# --------------------------------------------------- listado de Aplifisa
def test_el_listado_con_un_nif_con_es_cuadra_con_el_del_programa():
    apunte = registro.Apunte(numero="1", fecha="10/03/2026", nif="ESB12345674",
                             nombre=NOMBRE, base=100.0, cuota=21.0, neto=121.0)
    informe = registro.contrastar([_factura()], registro.Registro(apuntes=[apunte]))
    assert informe.resultados[0] == "cuadra", informe.detalles
    # Con otro apunte igual de otro proveedor, se empareja con el suyo.
    otro = registro.Apunte(numero="2", fecha="10/03/2026", nif="A12345674",
                           nombre="OTRO PROVEEDOR SA", base=100.0, cuota=21.0,
                           neto=121.0)
    informe = registro.contrastar(
        [_factura()], registro.Registro(apuntes=[otro, apunte]))
    assert informe.resultados[0] == "cuadra", informe.detalles
    assert informe.apuntes_de_mas == [otro]
    assert registro.NIF_SUELTO.match("ESB12345674")
    assert not registro.NIF_SUELTO.match("ESTACION")


def test_el_nif_del_cliente_en_la_cabecera_del_listado_con_es():
    class Pagina:
        def get_text(self):
            return "LISTADO DE FACTURAS RECIBIDAS\nD.N.I./C.I.F.: ES12345678Z\n"

    class Documento:
        page_count = 1

        def __getitem__(self, i):
            return Pagina()

    assert registro._nif_del_cliente(Documento()) == CLIENTE


# ----------------------------------------------------- recuadros del visor
def test_el_recuadro_del_nif_se_encuentra_con_y_sin_es():
    caja = localizar.Caja("nif", "ESB12345674", 0.1, 0.6, 0.13, 0.8)
    assert localizar.cajas_de([caja], "nif", PROVEEDOR) == [caja]
    otra = localizar.Caja("nif", "ESA12345674", 0.1, 0.6, 0.13, 0.8)
    assert localizar.cajas_de([otra], "nif", PROVEEDOR) == []
    # A Gemini se le dice que puede estar impreso con «ES» delante.
    assert "«ES» delante" in localizar._prompt([("nif", PROVEEDOR)])


# ------------------------------------------------------------------ archivo
def test_la_carpeta_del_cliente_guardado_con_es_es_la_misma(tmp_path):
    base = tmp_path / "escaneos"
    base.mkdir()
    carpeta = "CLIENTE PRUEBA SL — ESB12345674"
    identidad_archivo.guardar(base / identidad_archivo.INDICE, {
        "ESB12345674": {"nombre": "CLIENTE PRUEBA SL", "carpeta": carpeta}})
    assert identidad_archivo.carpeta_cliente(base, "CLIENTE PRUEBA SL",
                                             PROVEEDOR) == carpeta
    assert recoger._carpeta_cliente(str(base), "CLIENTE PRUEBA SL",
                                    "ESB12345674") == carpeta
    with open(base / identidad_archivo.INDICE, encoding="utf-8") as fh:
        assert len(json.load(fh)) == 1                 # no hay otra ficha
    assert recoger.clientes_conocidos(str(base)) == {PROVEEDOR: "CLIENTE PRUEBA SL"}


def test_recoger_reconoce_al_cliente_leido_con_es(tmp_path, monkeypatch):
    import fitz
    from facturas_excel import extraccion

    clientes.marcar_cliente(PROVEEDOR, "CLIENTE PRUEBA SL")
    pdf = tmp_path / "escaneada.pdf"
    with fitz.open() as doc:
        doc.new_page()
        doc.save(pdf)

    class Lector:
        def __init__(self, *_a, **_k):
            pass

        def extraer(self, *_a, **_k):
            class Leido:
                consumos = []
                crudo = _gasto(emisor_nif="ESA12345674", receptor_nif="ESB12345674")
            return Leido()

    monkeypatch.setattr(extraccion, "Extractor", Lector)
    c = recoger.Candidato(ruta=str(pdf), sin_texto=True)
    recoger.leer_con_gemini([c], str(tmp_path / "escaneos"), "clave-falsa")
    assert (c.nif, c.tipo, c.ejercicio) == (PROVEEDOR, recoger.GASTOS, 2026)
    assert not c.dudas


# ------------------------------------------------------------------- sesión
def test_la_sesion_vieja_con_es_se_abre_ya_sin_el(tmp_path, monkeypatch):
    ruta = tmp_path / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))
    vieja = _ventana(_factura(nif="ESB12345674"), cliente="ES12345678Z")
    vieja._bloques[0]["nif"] = "ES12345678Z"
    assert _avisos_es(vieja.filas[0]["mensajes"])       # así estaba
    vieja.closeEvent(QCloseEvent())

    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    f = v.filas[0].factura
    assert f.nif == PROVEEDOR
    assert v.tabla.item(0, C_NIF).text() == PROVEEDOR
    assert v._cliente_nif == CLIENTE and v._bloques[0]["nif"] == CLIENTE
    assert not _avisos_es(v.filas[0]["mensajes"])
    por_tipo, _excluidas, _errores, _pendientes = v._clasificar_exportacion()
    assert [g.nif for g in por_tipo["gasto"]] == [PROVEEDOR]
