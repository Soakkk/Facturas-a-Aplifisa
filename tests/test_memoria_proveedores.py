"""Memoria de NIF de proveedores: escribirlo una vez y no volver a escribirlo.

Caso real: el CIF de Antonio y Canizares va impreso en letra diminuta y no hay
lote en el que se lea bien. Los NIF de los tests son de empresas (publicos); el
cliente es inventado.
"""

import pytest

from facturas_excel import proveedores
from facturas_excel.procesar import (
    clave_proveedor, completar_desde_memoria, construir, recordar_nif,
)

CLIENTE = "12345678Z"
CANIZARES = "B30048276"
OTRO = "B73549388"


@pytest.fixture(autouse=True)
def memoria_limpia(tmp_path, monkeypatch):
    """Cada test con su propia memoria: no tocar la del usuario."""
    monkeypatch.setattr(proveedores, "dir_datos", lambda: str(tmp_path))


def factura(nombre, nif):
    return construir(
        dict(emisor_nombre=nombre, emisor_nif=nif, receptor_nif=CLIENTE,
             num_factura="F-1", fecha="07/05/2026", cuenta_gasto="600",
             lineas_iva=[{"base": 34.90, "tipo_iva": 10.0, "cuota_iva": 3.49}],
             total=38.39),
        CLIENTE, "CLIENTE DE PRUEBA", "lote.pdf", 1)


def test_lo_escrito_a_mano_se_recuerda_y_se_reutiliza():
    assert recordar_nif("ANTONIO Y CAÑIZARES SL", CANIZARES, manual=True)
    pr = factura("ANTONIO Y CAÑIZARES SL", None)
    assert completar_desde_memoria([pr]) == 1
    assert pr.facturas[0].nif == CANIZARES
    assert "no se leyó ninguno" in pr.aviso


def test_da_igual_como_venga_escrito_el_nombre():
    recordar_nif("ANTONIO Y CAÑIZARES SL", CANIZARES, manual=True)
    pr = factura("Antonio y Cañizares, S.L.", None)
    assert completar_desde_memoria([pr]) == 1
    assert pr.facturas[0].nif == CANIZARES


def test_tambien_corrige_un_nif_mal_leido():
    recordar_nif("ANTONIO Y CAÑIZARES SL", CANIZARES, manual=True)
    pr = factura("ANTONIO Y CAÑIZARES SL", "B3OO48276")   # O en vez de 0
    assert completar_desde_memoria([pr]) == 1
    assert pr.facturas[0].nif == CANIZARES
    assert "B3OO48276" in pr.aviso


def test_no_pisa_un_nif_valido_pero_avisa_si_no_es_el_guardado():
    recordar_nif("ANTONIO Y CAÑIZARES SL", CANIZARES, manual=True)
    pr = factura("ANTONIO Y CAÑIZARES SL", OTRO)
    assert completar_desde_memoria([pr]) == 0
    assert pr.facturas[0].nif == OTRO        # manda lo que trae la factura
    assert "Comprueba cuál es el bueno" in pr.aviso


def test_nunca_recuerda_un_nif_que_no_valida():
    assert not recordar_nif("TALLERES PEPE", "B3OO48276")
    assert not recordar_nif("TALLERES PEPE", "")
    assert proveedores.leer(clave_proveedor("TALLERES PEPE")) is None


def test_sin_nombre_no_hay_nada_que_recordar():
    assert not recordar_nif("", CANIZARES)
    assert not recordar_nif(None, CANIZARES)


def test_lo_de_la_persona_manda_sobre_lo_que_lea_la_ia():
    recordar_nif("ANTONIO Y CAÑIZARES SL", CANIZARES, manual=True)
    # una lectura automatica posterior NO debe pisarlo
    recordar_nif("ANTONIO Y CAÑIZARES SL", OTRO, manual=False)
    assert proveedores.leer(clave_proveedor("ANTONIO Y CAÑIZARES SL"))["nif"] == CANIZARES


def test_una_lectura_automatica_si_pisa_a_otra_automatica():
    recordar_nif("TALLERES PEPE", OTRO, manual=False)
    recordar_nif("TALLERES PEPE", CANIZARES, manual=False)
    assert proveedores.leer(clave_proveedor("TALLERES PEPE"))["nif"] == CANIZARES


def test_un_proveedor_desconocido_no_hereda_nada():
    recordar_nif("ANTONIO Y CAÑIZARES SL", CANIZARES, manual=True)
    pr = factura("PANADERIA LOS HERMANOS", None)
    assert completar_desde_memoria([pr]) == 0
    assert pr.facturas[0].nif is None
