"""Reproducciones de la revisión adversarial de la 1.25 (no se ejecutan solas).

Copiadas del scratchpad para portarlas a tests/test_memoria_lectura.py. Ver
PLAN-MEJORAS.md, «Para seguir». Algunas simulan el diálogo de cliente antiguo
y ya no aplican tal cual (homónimo: ahora lo resuelve ventana_lectura)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from facturas_excel import clientes, procesar, proveedores
from facturas_excel.doble_lectura import comparar
from facturas_excel.procesar import construir
from facturas_excel.validacion import REVISAR, OK, validar

CLIENTE_A = "12345678Z"
CLIENTE_B = "B76543214"
MAKRO = "A12345674"


def _datos(cliente=CLIENTE_A, **extra):
    d = dict(emisor_nombre="MAKRO DE PRUEBA SA", emisor_nif=MAKRO,
             receptor_nombre="CLIENTE", receptor_nif=cliente,
             num_factura="M-1", fecha="03/09/2026",
             lineas_iva=[{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0}],
             total=121.0, cuenta_gasto="622", subclave_gxx="G13",
             confianza="alta")
    d.update(extra)
    return d


def _lote(cliente=CLIENTE_A, **extra):
    crudos = [(b"", "taco.pdf", 1, _datos(cliente, **extra))]
    return procesar.preparar_lote(crudos, "CLIENTE", cliente)[0][1]


# ---------------------------------------------------- cuentas_cliente raras
@pytest.mark.parametrize("raro", [
    {CLIENTE_A: ["600"]},            # lista de un elemento
    {CLIENTE_A: {"cuenta": "600"}},  # dict
    ["600", "G01"],                  # la colección entera como lista
])
def test_cuentas_cliente_raras_no_rompen_el_lote(raro):
    proveedores.guardar_campos("MAKRO PRUEBA", nif=MAKRO,
                               nombre="MAKRO DE PRUEBA SA", cuenta="600",
                               gxx="G01", cuenta_manual=True,
                               cuentas_cliente=raro)
    _lote(CLIENTE_A)          # no debe lanzar


def test_cuentas_cliente_lista_rompe_el_guardado():
    proveedores.guardar_campos("MAKRO PRUEBA", nif=MAKRO,
                               nombre="MAKRO DE PRUEBA SA", cuenta="600",
                               gxx="G01", cuenta_manual=True,
                               cuentas_cliente=["600", "G01"])
    procesar.recordar_cuenta_proveedor(MAKRO, "MAKRO DE PRUEBA SA", "629",
                                       "G22", CLIENTE_A)


# ---------------------------------------------- legado y cliente sin NIF
def test_la_cuenta_antigua_se_pierde_al_guardar_la_primera_por_cliente():
    # Antes de la 1.25: Makro -> 600 (sin cliente).
    procesar.recordar_cuenta_proveedor(MAKRO, "MAKRO DE PRUEBA SA", "600", "G01")
    assert _lote(CLIENTE_B).cuenta == "600"           # como antes, en silencio
    # En A se corrige a 629.
    procesar.recordar_cuenta_proveedor(MAKRO, "MAKRO DE PRUEBA SA", "629",
                                       "G22", CLIENTE_A)
    en_b = _lote(CLIENTE_B)
    # B, que usaba la 600 en silencio, ahora recibe la 629 en ámbar.
    assert (en_b.cuenta, "otro cliente" in en_b.aviso) == ("600", False)


def test_cliente_sin_nif_queda_en_ambar_para_siempre():
    procesar.recordar_cuenta_proveedor(MAKRO, "MAKRO DE PRUEBA SA", "600",
                                       "G01", CLIENTE_A)
    # Un cliente sin NIF (registro por nombre): la app le pasa "".
    procesar.recordar_cuenta_proveedor(MAKRO, "MAKRO DE PRUEBA SA", "629",
                                       "G22", "")
    crudos = [(b"", "taco.pdf", 1, _datos("", receptor_nombre="CLIENTE"))]
    pr = procesar.preparar_lote(crudos, "CLIENTE", "")[0][1]
    assert pr.cuenta == "629"
    assert "otro cliente" not in pr.aviso


def test_el_aviso_de_otro_cliente_no_se_quita_al_poner_la_cuenta():
    procesar.recordar_cuenta_proveedor(MAKRO, "MAKRO DE PRUEBA SA", "600",
                                       "G01", CLIENTE_A)
    pr = _lote(CLIENTE_B)
    assert "otro cliente" in pr.aviso
    assert "otro cliente" not in procesar.quitar_aviso_cuenta(pr.aviso)


# --------------------------------------------------------- la 200
def test_la_memoria_pisa_la_200_pero_el_texto_dice_200():
    procesar.recordar_cuenta_proveedor(MAKRO, "MAKRO DE PRUEBA SA", "622",
                                       "G13", CLIENTE_A)
    pr = _lote(CLIENTE_A, es_bien_inversion=True)
    f = pr.facturas[0]
    textos = " ".join(str(m) for m in validar(f).mensajes)
    assert (f.concepto, "va a la 200" in textos) != ("622", True), \
        f"cuenta {f.concepto} y el texto dice: {textos}"


def test_venta_bien_de_inversion_dice_200():
    pr = construir(_datos(emisor_nombre="CLIENTE", emisor_nif=CLIENTE_A,
                          receptor_nombre="COMPRADOR SL",
                          receptor_nif=CLIENTE_B, es_bien_inversion=True,
                          cuenta_ingreso="700", subclave_ingreso="I01"),
                   CLIENTE_A, "CLIENTE")
    assert pr.tipo == "venta"
    f = pr.facturas[0]
    textos = " ".join(str(m) for m in validar(f).mensajes)
    assert not ("va a la 200" in textos and f.concepto != "200"), \
        f"venta en {f.concepto} con texto: {textos}"


# ------------------------------------------- doble lectura: falsos ámbar
def _discrepancias(uno, dos, tipo="gasto"):
    crudo = dict(uno, _verificacion="doble", _modelo_1="a", _modelo_2="b",
                 _lectura_2=dos, _discrepancias=comparar(uno, dos))
    return procesar.discrepancias_de(crudo, tipo)


@pytest.mark.parametrize("uno,dos", [
    (dict(fecha_operacion=None), dict(fecha_operacion="03/09/2026")),
    (dict(base_irpf=None, pct_irpf=None), dict(base_irpf=0, pct_irpf=0)),
    (dict(subclave_gxx="G13"), dict(subclave_gxx=None)),        # 622: única
    (dict(cuenta_gasto="628", subclave_gxx="G16"),
     dict(cuenta_gasto="628 (G16)", subclave_gxx=None)),
])
def test_lecturas_equivalentes_no_dan_discrepancia(uno, dos):
    a, b = _datos(**uno), _datos(**dos)
    # Lo que se construye con cada lectura es lo mismo…
    fa = construir(a, CLIENTE_A, "CLIENTE").facturas[0]
    fb = construir(b, CLIENTE_A, "CLIENTE").facturas[0]
    campos = ("fecha_operacion", "base_irpf", "pct_irpf", "concepto", "subclave")
    iguales = all((getattr(fa, c) or None) == (getattr(fb, c) or None)
                  or (c == "fecha_operacion")  # mismo devengo
                  for c in campos)
    disc = _discrepancias(a, b)
    assert not (iguales and disc), f"discrepancias falsas: {[d['campo'] for d in disc]}"


def test_bien_de_inversion_y_cuenta_que_no_se_usa():
    """Las dos lecturas dicen bien de inversión: la cuenta de gasto da igual
    (va a la 200) pero se señala como discrepancia."""
    a = _datos(es_bien_inversion=True, cuenta_gasto="629", subclave_gxx="G22")
    b = _datos(es_bien_inversion=True, cuenta_gasto="622", subclave_gxx="G13")
    disc = _discrepancias(a, b)
    assert not disc, [d["campo"] for d in disc]


# --------------------------------------------------------- homónimo
def _dni(numero):
    return f"{numero}{'TRWAGMYFPDXBNJZSQVHLCKE'[numero % 23]}"


def test_homonimo_dudoso_pegajoso_y_memoria_contaminada():
    clientes.marcar_cliente(CLIENTE_A, "JUAN PEREZ GARCIA")
    otro = _dni(87654321)
    lote = [_datos(receptor_nombre="JUAN PEREZ GARCIA", num_factura=str(i))
            for i in range(5)]
    # Una sola factura con otro NIF válido junto al nombre del cliente.
    lote.append(_datos(receptor_nombre="JUAN PEREZ GARCIA", receptor_nif=otro,
                       num_factura="X"))
    analisis = procesar.analizar_cliente(lote)
    assert analisis.dudoso
    # Lo que hace _cambiar_cliente al aceptar el diálogo con el cliente bueno:
    elegido = analisis.mejor
    assert elegido.nif == CLIENTE_A
    clientes.marcar_cliente(elegido.nif, elegido.nombre)
    for c in analisis.candidatos:
        if c.nif != elegido.nif and c.nombre and c.nif:
            procesar.recordar_nif(c.nombre, c.nif, manual=True)
    # El siguiente bloque del mismo lote vuelve a preguntar.
    sigue = procesar.analizar_cliente(lote + [_datos(num_factura="Y")]).dudoso
    ficha = proveedores.leer(procesar.clave_proveedor("JUAN PEREZ GARCIA"))
    assert not sigue and not (ficha and ficha["nif"] == otro), \
        f"dudoso otra vez={sigue}; el cliente quedó como proveedor: {ficha}"


# ------------------------------------------------------ margen redondeo
def test_margen_con_abono():
    from facturas_excel.modelo import Factura
    f = Factura(num_factura="A1", fecha="03/09/2026", nombre="X", nif=MAKRO,
                concepto="622", subclave="G13", base_iva=-1000.0, pct_iva=21.0,
                cuota_iva=-210.04, total_impreso=-1210.04, confianza_ia="alta")
    res = validar(f)
    assert res.estado == REVISAR, res.mensajes


# ------------------------------------------- posiblemente ya exportada
def _ventana_con(facturas):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from facturas_excel.app import VentanaPrincipal
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._cliente_nif, v._cliente_nombre = CLIENTE_A, "CLIENTE PRUEBA"
    v._bloques = [{"nombre": "b1", "cliente": "CLIENTE PRUEBA", "nif": CLIENTE_A}]
    for f in facturas:
        v._anadir_fila(b"", f, "gasto", "621", None, "", "b1")
    v._revalidar_todo()
    return v


def _fra(numero, fecha, nif, nombre, total=605.0):
    from facturas_excel.modelo import Factura
    return Factura(num_factura=numero, fecha=fecha, nombre=nombre, nif=nif,
                   concepto="621", subclave=None, base_iva=500.0, pct_iva=21.0,
                   cuota_iva=105.0, total_impreso=total, confianza_ia="alta",
                   verificacion="doble")


@pytest.mark.parametrize("anterior,actual", [
    # El alquiler del año pasado: mismo arrendador, nº 1 cada enero.
    (("1", "31/01/2025", "B12345674", "INMUEBLES PRUEBA SL"),
     ("1", "31/01/2026", "B12345674", "INMUEBLES PRUEBA SL")),
    # Otro proveedor, con NIF válido y distinto, mismo nº corto y total.
    (("3", "15/02/2026", "B12345674", "INMUEBLES PRUEBA SL"),
     ("3", "20/05/2026", "A12345674", "OTRA EMPRESA SA")),
])
def test_posiblemente_ya_exportada_falso(anterior, actual):
    from facturas_excel import historial
    historial.registrar(CLIENTE_A, {"gasto": [_fra(*anterior)]},
                        {"gasto": "x.xlsx"}, "CLIENTE PRUEBA")
    v = _ventana_con([_fra(*actual)])
    textos = " ".join(str(m) for m in v.filas[0]["mensajes"])
    assert "POSIBLEMENTE YA EXPORTADA" not in textos, textos


# ------------------------------------------------- fechas y verificación
@pytest.mark.parametrize("fecha", ["2026-03-05", "5/3/26", "05.03.2026",
                                   "no es fecha", "05/03/2026 "])
def test_fechas_viejas_se_exportan_y_verifican(tmp_path, fecha):
    from pathlib import Path
    from facturas_excel.config_columnas import leer_config
    from facturas_excel.exportar import exportar_excel, verificar_excel
    from facturas_excel.modelo import Factura
    raiz = Path("/home/user/facturas-a-aplifisa")
    for xml in ("gastos.xml", "ingresos.xml"):
        cfg = leer_config(raiz / "config" / xml)
        f = Factura(num_factura="F1", fecha=fecha, fecha_operacion=fecha,
                    nombre="PROVEEDOR SL", nif="B12345674", concepto="628",
                    subclave="G16", base_iva=100.0, pct_iva=21.0,
                    cuota_iva=21.0, total_impreso=121.0)
        ruta = str(tmp_path / xml.replace(".xml", ".xlsx"))
        exportar_excel([f], cfg, ruta)
        assert verificar_excel([f], cfg, ruta) == []


def test_otro_cliente_ambar_aunque_gemini_diga_lo_mismo():
    procesar.recordar_cuenta_proveedor(MAKRO, "MAKRO DE PRUEBA SA", "622",
                                       "G13", CLIENTE_A)
    pr = _lote(CLIENTE_B)            # Gemini también dice 622 (G13)
    assert pr.cuenta == "622"
    assert "otro cliente" not in (pr.aviso or ""), pr.aviso


def test_sin_memoria_el_mismo_lote_es_verde():
    pr = _lote(CLIENTE_B)
    assert not pr.aviso, pr.aviso
