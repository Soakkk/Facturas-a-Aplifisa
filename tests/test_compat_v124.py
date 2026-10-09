"""Lo guardado por la 1.24.0 sigue valiendo en la 1.25.

Las fichas de proveedor, el registro de exportadas y la sesión se escriben
aquí tal y como los dejaba la 1.24.0 (comprobado con el código de la
etiqueta v1.24.0) y se leen con el código nuevo. Datos inventados.
"""


from facturas_excel import historial, procesar, proveedores, registro_facturas, sesion, suite
from facturas_excel.modelo import Factura
from facturas_excel.validacion import huecos_de_numeracion

import pytest

CLIENTE = "B12345674"
NOMBRE_CLIENTE = "CLIENTE PRUEBA SL"
ROTO = "JOS\x01 GARC\x01A L\x03PEZ"          # «JOSÉ GARCÍA LÓPEZ» mal copiado


@pytest.fixture(autouse=True)
def _sin_cache_de_la_suite():
    suite._cache.update(mtime=None, ruta=None, datos=None)


def _gasto(nombre, nif, numero="F-1", cuenta="602", total=121.0):
    return dict(emisor_nif=nif, emisor_nombre=nombre,
                receptor_nif=CLIENTE, receptor_nombre=NOMBRE_CLIENTE,
                num_factura=numero, fecha="15/03/2026", total=total,
                lineas_iva=[{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0}],
                cuenta_gasto=cuenta)


def _lote(datos):
    return procesar.preparar_lote([(b"", "x.pdf", 1, datos)],
                                  NOMBRE_CLIENTE, CLIENTE)[0][1]


def _fichas_124(fichas):
    for clave, ficha in fichas.items():
        proveedores._col().guardar(clave, ficha)


# ------------------------------------------- 1. la cuenta que puso el usuario
@pytest.mark.parametrize("fichas", [
    # Cuenta puesta en una fila con el nombre roto (la única ficha).
    {"GARC\x01A JOS\x01 L\x03PEZ": {
        "nif": "12345678Z", "nombre": ROTO, "cuenta": "622", "gxx": "G13",
        "cuenta_manual": True}},
    # La ficha bien escrita existía y la cuenta pisó su nombre con el roto.
    {"GARCIA JOSE LOPEZ": {
        "nif": "12345678Z", "nombre": ROTO, "manual": False, "cuenta": "622",
        "gxx": "G13", "cuenta_manual": True}},
])
def test_la_cuenta_de_la_124_sigue_tras_exportar_con_el_nombre_limpio(fichas):
    _fichas_124(fichas)
    pr = _lote(_gasto(ROTO, "12345678Z", "F-1"))
    assert (pr.cuenta, pr.gxx) == ("622", "G13")
    procesar.aprender_nifs_exportados(pr.facturas)     # lo que hace exportar
    siguiente = _lote(_gasto(ROTO, "12345678Z", "F-2"))
    assert (siguiente.cuenta, siguiente.gxx) == ("622", "G13")


def test_la_cuenta_de_la_124_en_otra_ficha_del_mismo_nif():
    # Una ficha por cada forma de leer el nombre: el nombre puesto a mano en
    # una y la cuenta (puesta después) en la otra.
    _fichas_124({
        "AGUAS FONTANERIA PEREZ": {
            "nif": "B76543214", "nombre": "AGUAS Y FONTANERIA PEREZ",
            "manual": True, "cuenta": "622", "gxx": "G13", "cuenta_manual": True},
        "FONTANERIA PEREZ": {
            "nif": "B76543214", "nombre": "FONTANERIA PEREZ SL",
            "nombre_manual": True},
    })
    pr = _lote(_gasto("FONTANERIA PEREZ SL", "B76543214"))
    assert (pr.cuenta, pr.gxx) == ("622", "G13")


def test_cambiar_despues_esa_cuenta_vale_y_se_puede_deshacer():
    _fichas_124({
        "AGUAS FONTANERIA PEREZ": {
            "nif": "B76543214", "nombre": "AGUAS Y FONTANERIA PEREZ",
            "manual": True, "cuenta": "622", "gxx": "G13", "cuenta_manual": True},
        "FONTANERIA PEREZ": {
            "nif": "B76543214", "nombre": "FONTANERIA PEREZ SL",
            "nombre_manual": True},
    })
    clave, antes = procesar.ficha_de_cuenta("B76543214", "FONTANERIA PEREZ SL")
    assert procesar.recordar_cuenta_proveedor("B76543214", "FONTANERIA PEREZ SL",
                                              "628", "G16", CLIENTE)
    assert _lote(_gasto("FONTANERIA PEREZ SL", "B76543214")).cuenta == "628"
    proveedores.reponer(clave, antes)                    # «Deshacer»
    assert _lote(_gasto("FONTANERIA PEREZ SL", "B76543214")).cuenta == "622"
    # El nombre puesto a mano sigue mandando.
    assert procesar.nombres_guardados()["B76543214"] == "FONTANERIA PEREZ SL"


# ------------------------------- 2. número largo exportado con la 1.24.0
def test_un_numero_largo_exportado_con_la_124_sigue_siendo_ya_exportada():
    numero = "2026/FACT/ALMACEN-CENTRAL/0000123"          # 33: el SII admite 60
    vieja = Factura(num_factura=numero, fecha="15/03/2026",
                    nombre="SUMINISTROS GARCIA SL", nif="A12345674",
                    base_iva=100.0, pct_iva=21.0, cuota_iva=21.0,
                    total_impreso=121.0)                 # como la leía la 1.24.0
    historial.registrar(CLIENTE, {"gasto": [vieja]}, {"gasto": "a.xlsx"},
                        NOMBRE_CLIENTE)
    f = procesar.construir(_gasto("SUMINISTROS GARCIA SL", "A12345674", numero),
                           CLIENTE, NOMBRE_CLIENTE).facturas[0]
    assert f.num_factura == numero                      # a Aplifisa, entero
    assert historial.clave(f, "gasto") in historial.exportadas_de(CLIENTE)


# --------------------------- 3. sesión de la 1.24.0 con una línea revisada
def test_una_linea_revisada_en_la_124_con_el_nombre_roto_vuelve_a_pendiente():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from facturas_excel.app import VentanaPrincipal
    datos = _gasto("JOSE GARCIA LOPEZ", "12345678Z", "F-501")
    datos.pop("cuenta_gasto")                 # ámbar: cuenta puesta por descarte
    crudos = [(b"", "taco.pdf", 1, datos)]
    procesadas = procesar.preparar_lote(crudos, NOMBRE_CLIENTE, CLIENTE)
    pr = procesadas[0][1]
    f = pr.facturas[0]
    f.nombre = ROTO                           # la 1.24.0 no lo limpiaba
    f.revision_confirmada = True              # «Marcar revisada» por la cuenta
    sesion.guardar({"bloques": [{"nombre": "Taco 1", "procesadas": procesadas,
                                 "crudos": crudos, "nif": CLIENTE,
                                 "cliente": NOMBRE_CLIENTE}],
                    "filas": [{"png": b"", "factura": f, "aviso": pr.aviso,
                               "bloque": "Taco 1", "fuentes": None,
                               "tipo": "gasto", "cuenta": f.concepto or "",
                               "gxx": f.subclave or ""}],
                    "cliente_nif": CLIENTE, "cliente_nombre": NOMBRE_CLIENTE,
                    "hay_recargo": False, "regimen_recargo": None,
                    "periodo_modo": "auto", "localizaciones": {}, "su_suma": None})
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._restaurar_sesion()
    assert any("no se ve" in str(m) for m in v.filas[0]["mensajes"])
    por_tipo, _excl, _errs, pendientes = v._clasificar_exportacion()
    assert pendientes == [0] and not por_tipo["gasto"]
    # Visto el aviso, se puede volver a marcar revisada (como en un lote nuevo).
    assert v._marcar_revisada([0]) is not None
    por_tipo, _excl, _errs, pendientes = v._clasificar_exportacion()
    assert pendientes == [] and len(por_tipo["gasto"]) == 1
    v.close()


# ------------------- 4. NIF guardado con el nombre roto o con el nombre largo
@pytest.mark.parametrize("clave,ficha,leido", [
    ("GARC\x01A JOS\x01 L\x03PEZ",
     {"nif": "12345678Z", "nombre": ROTO, "manual": True}, ROTO),
    ("ANGELES CRISTOBAL ESTACION LIMITADA LOS SERVICIO SOCIEDAD",
     {"nif": "B76543214", "manual": True,
      "nombre": "ESTACION DE SERVICIO SAN CRISTOBAL DE LOS ANGELES SOCIEDAD LIMITADA"},
     "ESTACION DE SERVICIO SAN CRISTOBAL DE LOS ANGELES SOCIEDAD LIMITADA"),
])
def test_el_nif_guardado_en_la_124_se_sigue_poniendo_de_memoria(clave, ficha, leido):
    _fichas_124({clave: ficha})
    pr = _lote(_gasto(leido, "", "G-77"))
    assert pr.facturas[0].nif == ficha["nif"]


def test_dos_nif_distintos_para_el_mismo_nombre_limpio_no_se_pone_ninguno():
    _fichas_124({
        "GARC\x01A JOS\x01 L\x03PEZ": {"nif": "12345678Z", "nombre": ROTO,
                                       "manual": True},
        "GARC\x02A JOS L\x03PEZ": {"nif": "B76543214",
                                   "nombre": "JOS GARC\x02A L\x03PEZ",
                                   "manual": True},
    })
    assert _lote(_gasto(ROTO, "", "G-78")).facturas[0].nif in (None, "")


# ------------------------------------- 5. contador de 10 cifras en la serie
def test_una_serie_con_contador_de_10_cifras_sigue_avisando_del_hueco():
    ventas = [Factura(num_factura=n, nombre=f"COMPRADOR {i} SL", nif="",
                      fecha="10/04/2026")
              for i, n in enumerate(["2026000125", "2026000126", "2026000128"])]
    [aviso] = huecos_de_numeracion(ventas, ["venta"] * 3, NOMBRE_CLIENTE,
                                   ventas_anteriores=["2026000123"])
    assert "2026000124" in aviso and "2026000127" in aviso


# ----------------------- 6. cliente sin NIF con un carácter roto en su nombre
def test_cliente_sin_nif_con_nombre_roto_lo_exportado_se_encuentra():
    cliente = "PANADERIA JOS\x01 SL"
    f = procesar.construir(_gasto("SUMINISTROS GARCIA SL", "A12345674", "F-900"),
                           "", cliente).facturas[0]
    assert historial.registrar("", {"gasto": [f]}, {"gasto": "a.xlsx"}, cliente) == 1
    assert historial.buscar("", f, "gasto", cliente)
    assert len(historial.exportadas_de("", cliente)) == 1
    assert historial.registrar("", {"gasto": [f]}, {"gasto": "b.xlsx"}, cliente) == 0
    # Archivar el PDF no borra la marca de exportada.
    registro_facturas.archivar("", cliente, [("gasto", f, "F-900.pdf")])
    assert historial.buscar("", f, "gasto", cliente)
