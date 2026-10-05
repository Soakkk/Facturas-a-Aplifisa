"""1.25: memoria por cliente y controles de lectura (datos de prueba)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from facturas_excel import procesar, proveedores
from facturas_excel.modelo import Factura
from facturas_excel.procesar import construir

CLIENTE_A = "12345678Z"
CLIENTE_B = "B76543214"
MAKRO = "A12345674"


@pytest.fixture(autouse=True)
def memoria_limpia(tmp_path, monkeypatch):
    monkeypatch.setattr(proveedores, "dir_datos", lambda: str(tmp_path))


def _datos(cliente=CLIENTE_A, **extra):
    d = dict(emisor_nombre="MAKRO DE PRUEBA SA", emisor_nif=MAKRO,
             receptor_nombre="CLIENTE", receptor_nif=cliente,
             num_factura="M-1", fecha="03/09/2026",
             lineas_iva=[{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0}],
             total=121.0, cuenta_gasto="622", subclave_gxx="G13")
    d.update(extra)
    return d


def _lote(cliente=CLIENTE_A, **extra):
    crudos = [(b"", "taco.pdf", 1, _datos(cliente, **extra))]
    return procesar.preparar_lote(crudos, "CLIENTE", cliente)[0][1]


# ------------------------------------------------- la cuenta, por cliente
def test_la_cuenta_puesta_en_un_cliente_no_se_impone_en_otro():
    """Makro puede ser 600 en un bar y 629 en una oficina."""
    assert procesar.recordar_cuenta_proveedor(MAKRO, "MAKRO DE PRUEBA SA",
                                              "600", "G01", CLIENTE_A)
    en_a = _lote(CLIENTE_A)
    assert (en_a.cuenta, en_a.gxx) == ("600", "G01")
    assert "otro cliente" not in (en_a.aviso or "")

    en_b = _lote(CLIENTE_B)
    assert (en_b.cuenta, en_b.gxx) == ("600", "G01")       # se propone…
    assert "en otro cliente" in en_b.aviso                  # …en ámbar

    # Cuando en B se pone la suya, cada uno conserva la propia.
    procesar.recordar_cuenta_proveedor(MAKRO, "MAKRO DE PRUEBA SA", "629",
                                       "G22", CLIENTE_B)
    assert (_lote(CLIENTE_B).cuenta, _lote(CLIENTE_A).cuenta) == ("629", "600")


def test_las_cuentas_guardadas_antes_se_siguen_poniendo_como_hasta_ahora():
    procesar.recordar_cuenta_proveedor(MAKRO, "MAKRO DE PRUEBA SA", "600", "G01")
    pr = _lote(CLIENTE_B)
    assert pr.cuenta == "600" and "otro cliente" not in (pr.aviso or "")


def test_la_cuenta_decidida_quita_la_discrepancia_de_cuenta_de_la_ia():
    procesar.recordar_cuenta_proveedor(MAKRO, "MAKRO DE PRUEBA SA", "600",
                                       "G01", CLIENTE_A)
    segunda = _datos(cuenta_gasto="629", subclave_gxx="G22")
    crudo = _datos(_verificacion="doble", _modelo_1="a", _modelo_2="b",
                   _discrepancias=[{"campo": "cuenta_gasto",
                                    "etiqueta": "Cuenta de gasto",
                                    "valor_1": "622", "valor_2": "629"}],
                   _lectura_2=segunda)
    pr = procesar.preparar_lote([(b"", "taco.pdf", 1, crudo)], "CLIENTE",
                                CLIENTE_A)[0][1]
    assert not pr.facturas[0].discrepancias


# ------------------------------------- NIF de memoria y cliente homónimo
def test_un_nif_de_memoria_de_otro_cliente_se_ve():
    procesar.recordar_nif("MAKRO DE PRUEBA SA", MAKRO, manual=True)
    pr = _lote(CLIENTE_B, emisor_nif=None)
    assert pr.facturas[0].nif == MAKRO
    assert "NIF puesto de memoria" in pr.aviso
    # Mal impreso (O por 0): es el mismo, sin aviso.
    otro = _lote(CLIENTE_B, emisor_nif="A1234567A")      # una cifra cambiada
    assert "NIF puesto de memoria" not in (otro.aviso or "")


def test_un_homonimo_del_cliente_con_su_nif_no_se_lleva_el_lote():
    from facturas_excel import clientes
    clientes.marcar_cliente(CLIENTE_A, "JUAN PEREZ GARCIA")
    datos = _datos(receptor_nombre="JUAN PEREZ GARCIA", receptor_nif="X1234567L")
    analisis = procesar.analizar_cliente([datos])
    assert "X1234567L" in {c.nif for c in analisis.candidatos}
    assert analisis.dudoso                       # se pregunta, no se decide


# --------------------------------------------------------------- lectura
def test_las_fechas_van_siempre_dd_mm_aaaa():
    from facturas_excel.exportar import _valor_celda
    [f] = construir(_datos(fecha="2026-03-05", fecha_operacion="05/03/26"),
                    CLIENTE_A, "CLIENTE").facturas
    assert (f.fecha, f.fecha_operacion) == ("05/03/2026", "05/03/2026")
    assert _valor_celda("fecha", "5/3/26", "texto") == "05/03/2026"
    assert _valor_celda("fecha", "no es fecha", "texto") == "no es fecha"


def test_el_bien_de_inversion_se_propone_en_la_200():
    [f] = construir(_datos(es_bien_inversion=True, cuenta_gasto="629"),
                    CLIENTE_A, "CLIENTE").facturas
    assert (f.concepto, f.subclave) == ("200", "200")
    from facturas_excel.validacion import validar
    textos = " ".join(str(m) for m in validar(f).mensajes)
    assert "va a la 200" in textos


def test_la_doble_lectura_compara_lo_contable():
    from facturas_excel.doble_lectura import comparar
    uno = _datos(cuenta_gasto="622", es_bien_inversion=False)
    dos = _datos(cuenta_gasto="200", es_bien_inversion=True)
    campos = {d["campo"] for d in comparar(uno, dos)}
    assert {"cuenta_gasto", "es_bien_inversion"} <= campos
    # «628» y «628 (G16) SUMINISTROS GAS» son lo mismo; None y False también.
    tres = _datos(cuenta_gasto="628", subclave_gxx="G16")
    cuatro = _datos(cuenta_gasto="628 (G16) SUMINISTROS GAS", subclave_gxx="G16 ")
    cuatro["es_bien_inversion"] = None
    tres["es_bien_inversion"] = False
    assert comparar(tres, cuatro) == []
    # En una venta, la cuenta de gasto no importa.
    from facturas_excel.procesar import discrepancias_de
    crudo = {"_discrepancias": [{"campo": "cuenta_gasto", "etiqueta": "x",
                                 "valor_1": "622", "valor_2": "629"}]}
    assert discrepancias_de(crudo, "venta") == ()
    assert len(discrepancias_de(crudo, "gasto")) == 1


def test_el_redondeo_por_lineas_de_una_factura_grande_no_es_rojo():
    from facturas_excel.validacion import ERROR, REVISAR, validar
    f = Factura(num_factura="G-1", fecha="03/09/2026", nombre="PROV SL",
                nif="B12345674", concepto="600", subclave="G01",
                base_iva=12345.67, pct_iva=21.0, cuota_iva=2592.62,
                total_impreso=14938.29)
    res = validar(f)
    assert res.estado == REVISAR
    assert any("redondeo por líneas" in m for m in res.mensajes)
    f.cuota_iva, f.total_impreso = 2600.0, 14945.67
    assert validar(f).estado == ERROR            # eso ya no es redondeo


def test_las_palabras_clave_con_raiz():
    from facturas_excel.conceptos import asignar_concepto
    assert asignar_concepto("gasto", "notaria lopez sl") == "623"
    assert asignar_concepto("gasto", "registro mercantil") == "623"
    assert asignar_concepto("gasto", "abogados asociados") == "623"
    assert asignar_concepto("gasto", "telefonica de espana") == "628"
    # «gas» sigue sin cazar «gasoleo».
    from facturas_excel.conceptos import _contiene
    assert not _contiene("gasoleo a", "gas")


def test_posiblemente_ya_exportada_con_otro_nif(monkeypatch, tmp_path):
    """Exportada sin NIF y releída con él: antes no se reconocía."""
    from PySide6.QtWidgets import QApplication

    from facturas_excel import historial
    from facturas_excel.app import VentanaPrincipal
    QApplication.instance() or QApplication([])
    # Un número de al menos 3 cifras: «1», «2» se repiten cada año.
    vieja = Factura(num_factura="M-1047", fecha="03/09/2026", nombre="MAKRO",
                    nif=None, base_iva=100.0, total_impreso=121.0)
    historial.registrar(CLIENTE_A, {"gasto": [vieja]}, {})

    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._cliente_nif, v._cliente_nombre = CLIENTE_A, "CLIENTE"
    v._bloques = [{"nombre": "b1", "cliente": "CLIENTE", "nif": CLIENTE_A}]
    nueva = Factura(num_factura="M-1047", fecha="04/09/2026", nombre="MAKRO",
                    nif=MAKRO, concepto="600", subclave="G01", base_iva=100.0,
                    pct_iva=21.0, cuota_iva=21.0, total_impreso=121.0)
    v._anadir_fila(b"", nueva, "gasto", "600", "G01", "", "b1")
    v._revalidar_todo()
    texto = " ".join(str(m) for m in v.filas[0]["mensajes"])
    assert "POSIBLEMENTE YA EXPORTADA" in texto
