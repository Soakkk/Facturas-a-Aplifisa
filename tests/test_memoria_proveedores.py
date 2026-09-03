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


# ------------------------------- el mismo proveedor, escrito y leido igual ---
def test_el_nif_se_guarda_sin_guiones(tmp_path, monkeypatch):
    """El mismo proveedor venia "A-82018474" y "A82018474": con el guion se
    contaba como otro distinto y ni se veia el duplicado."""
    from facturas_excel.procesar import construir

    datos = {"emisor_nif": "A-82018474", "emisor_nombre": "TELEFONICA SA",
             "receptor_nif": "12345678Z", "receptor_nombre": "CLIENTE",
             "num_factura": "1", "fecha": "13/06/2025",
             "lineas_iva": [{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0}],
             "total": 121.0, "cuenta_gasto": "628", "subclave_gxx": "G17"}
    pr = construir(datos, "12345678Z", "CLIENTE")
    assert pr.facturas[0].nif == "A82018474"


def test_el_mismo_proveedor_se_escribe_siempre_igual(tmp_path, monkeypatch):
    """Aplifisa busca la cuenta por NIF y luego por NOMBRE EXACTO: dos formas
    de escribir el mismo proveedor pueden acabar en dos cuentas."""
    from facturas_excel import proveedores
    from facturas_excel.procesar import (
        construir, recordar_nif, unificar_nombres,
    )

    monkeypatch.setattr(proveedores, "dir_datos", lambda: str(tmp_path))
    recordar_nif("TELEFÓNICA DE ESPAÑA, S.A.U.", "A82018474", manual=True)

    datos = {"emisor_nif": "A82018474", "emisor_nombre": "Telefonica de España, S.A.U.",
             "receptor_nif": "12345678Z", "receptor_nombre": "CLIENTE",
             "num_factura": "2", "fecha": "13/07/2025",
             "lineas_iva": [{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0}],
             "total": 121.0, "cuenta_gasto": "628", "subclave_gxx": "G17"}
    pr = construir(datos, "12345678Z", "CLIENTE")
    assert unificar_nombres([pr]) == 1
    assert pr.facturas[0].nombre == "TELEFÓNICA DE ESPAÑA, S.A.U."


def test_lo_corregido_a_mano_se_queda_guardado(tmp_path, monkeypatch):
    """Nombre y cuenta que pone una persona valen para los proximos lotes."""
    from facturas_excel import proveedores
    from facturas_excel.procesar import (
        aplicar_recordado, construir, recordar_cuenta_proveedor,
        recordar_nombre_proveedor, unificar_nombres,
    )

    monkeypatch.setattr(proveedores, "dir_datos", lambda: str(tmp_path))
    recordar_nombre_proveedor("B73283798", "AREA DE SERVICIO DE MOLINA, S.L.")
    recordar_cuenta_proveedor("B73283798", "AREA DE SERVICIO DE MOLINA, S.L.",
                              "628", "G16")

    datos = {"emisor_nif": "B73283798", "emisor_nombre": "area servicio molina",
             "receptor_nif": "12345678Z", "receptor_nombre": "CLIENTE",
             "num_factura": "FA-1", "fecha": "31/01/2025",
             "lineas_iva": [{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0}],
             "total": 121.0, "cuenta_gasto": "600", "subclave_gxx": "G01"}
    pr = construir(datos, "12345678Z", "CLIENTE")
    unificar_nombres([pr])
    assert aplicar_recordado([pr]) == 1

    assert pr.facturas[0].nombre == "AREA DE SERVICIO DE MOLINA, S.L."
    assert (pr.cuenta, pr.gxx) == ("628", "G16")
    assert pr.facturas[0].concepto == "628"
    assert pr.facturas[0].subclave == "G16"


def test_una_cuenta_que_no_existe_en_aplifisa_no_se_guarda(tmp_path, monkeypatch):
    from facturas_excel import proveedores
    from facturas_excel.procesar import recordar_cuenta_proveedor

    monkeypatch.setattr(proveedores, "dir_datos", lambda: str(tmp_path))
    assert not recordar_cuenta_proveedor("B73283798", "PROVEEDOR", "999")
    assert not recordar_cuenta_proveedor("B73283798", "PROVEEDOR", "628", "G99")
