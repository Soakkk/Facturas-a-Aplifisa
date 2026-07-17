"""Completar NIF ilegibles copiandolos de otra factura del mismo proveedor."""

from facturas_excel.exportar import MAX_NOMBRE, _valor_celda
from facturas_excel.modelo import Factura
from facturas_excel.procesar import FacturaProcesada, propagar_nifs

COCA = "B86561412"   # NIFs reales: pasan el digito de control
OTRO = "A28017895"


def pr(nombre, nif, lineas=1):
    fs = [Factura(nombre=nombre, nif=nif, base_iva=100.0, pct_iva=21.0,
                  cuota_iva=21.0) for _ in range(lineas)]
    return FacturaProcesada("gasto", fs, "601", None, "x.pdf", 0)


def test_copia_el_nif_del_mismo_proveedor_cuando_falta_o_esta_mal():
    lote = [pr("COCA-COLA EUROPACIFIC PARTNERS IBERIA, S.L.U.", COCA),
            pr("COCA-COLA EUROPACIFIC PARTNERS IBERIA SLU", None),
            pr("COCA-COLA EUROPACIFIC PARTNERS IBERIA, S.L.U.", "B8656141Z")]
    assert propagar_nifs(lote) == 2
    assert [p.facturas[0].nif for p in lote] == [COCA] * 3
    assert "NIF copiado" in lote[1].aviso  # queda en ambar para revisar


def test_con_dos_nif_validos_para_el_mismo_nombre_no_copia_ninguno():
    lote = [pr("JOSE GARCIA MARTINEZ", COCA),
            pr("JOSE GARCIA MARTINEZ", OTRO),
            pr("JOSE GARCIA MARTINEZ", None)]
    assert propagar_nifs(lote) == 0
    assert lote[2].facturas[0].nif is None
    assert "escríbelo a mano" in lote[2].aviso


def test_no_contagia_el_nif_a_otro_proveedor():
    lote = [pr("COCA-COLA EUROPACIFIC PARTNERS IBERIA", COCA),
            pr("PANADERIA LOS HERMANOS", None)]
    assert propagar_nifs(lote) == 0
    assert lote[1].facturas[0].nif is None


def test_no_pisa_un_nif_que_ya_es_valido():
    lote = [pr("SUMINISTROS MURCIA", COCA), pr("SUMINISTROS MURCIA", OTRO)]
    assert propagar_nifs(lote) == 0
    assert [p.facturas[0].nif for p in lote] == [COCA, OTRO]


def test_sin_ningun_nif_fiable_no_inventa_nada():
    lote = [pr("TALLERES PEPE", None), pr("TALLERES PEPE", "XXXX")]
    assert propagar_nifs(lote) == 0
    assert [p.facturas[0].nif for p in lote] == [None, "XXXX"]


def test_rellena_todas_las_lineas_de_iva_de_la_factura():
    lote = [pr("BEBIDAS DEL SURESTE", COCA),
            pr("BEBIDAS DEL SURESTE", None, lineas=3)]
    propagar_nifs(lote)
    assert [f.nif for f in lote[1].facturas] == [COCA] * 3


def test_el_nombre_se_recorta_al_maximo_de_aplifisa():
    largo = "COCA-COLA EUROPACIFIC PARTNERS IBERIA, S.L.U."
    assert _valor_celda("nombre", largo, "texto") == \
        "COCA-COLA EUROPACIFIC PARTNERS IBERIA"
    for nombre in (largo, "DISTRIBUCIONES ALIMENTARIAS DEL MEDITERRANEO SOCIEDAD LIMITADA",
                   "ASOCIACION DE COMERCIANTES Y HOSTELEROS DE LA REGION DE MURCIA"):
        assert len(_valor_celda("nombre", nombre, "texto")) <= MAX_NOMBRE


def test_el_nombre_corto_no_se_toca():
    assert _valor_celda("nombre", "MAKRO SA", "texto") == "MAKRO SA"
