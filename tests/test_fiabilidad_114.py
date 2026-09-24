"""Controles añadidos en 1.14: no inventar datos y detectar lecturas imposibles."""
from datetime import date

import pytest

from facturas_excel import validacion
from facturas_excel.modelo import Factura
from facturas_excel.procesar import construir, quitar_aviso_cuenta
from facturas_excel.validacion import (
    ERROR, OK, REVISAR, Incidencia, clasificar_nif, validar, validar_nif,
)


@pytest.fixture(autouse=True)
def hoy_fijo(monkeypatch):
    monkeypatch.setattr(validacion, "_hoy", lambda: date(2026, 9, 24))


def _factura(**cambios):
    datos = dict(num_factura="7", fecha="10/02/2026", nombre="PROVEEDOR PRUEBA",
                 nif="B12345674", concepto="629", subclave="G22", base_iva=100.0,
                 pct_iva=21.0, cuota_iva=21.0, total_impreso=121.0)
    datos.update(cambios)
    return Factura(**datos)


def _gasto(**cambios):
    datos = {"emisor_nombre": "LOPEZ GARCIA JUAN", "emisor_nif": "12345678Z",
             "receptor_nombre": "CLIENTE PRUEBA SL", "receptor_nif": "B12345674",
             "num_factura": "7", "fecha": "10/02/2026",
             "lineas_iva": [{"base": 100, "tipo_iva": 21, "cuota_iva": 21}],
             "total": 121, "concepto_texto": "servicios varios",
             "confianza": "alta"}
    datos.update(cambios)
    return datos


def test_factura_correcta_sigue_en_verde():
    assert validar(_factura()).estado == OK


def test_tipo_de_iva_inexistente_es_error_aunque_la_cuota_cuadre():
    res = validar(_factura(pct_iva=22.0, cuota_iva=22.0, total_impreso=122.0))
    assert res.estado == ERROR
    assert any("22%" in m and "pct_iva" in m.campos for m in res.mensajes)


@pytest.mark.parametrize("tipo", [0, 2, 4, 5, 7.5, 10, 21])
def test_tipos_de_iva_espanoles_admitidos(tipo):
    cuota = round(100 * tipo / 100, 2)
    assert validar(_factura(pct_iva=tipo, cuota_iva=cuota,
                            total_impreso=100 + cuota)).estado == OK


def test_fecha_futura_es_error_y_se_senala_la_fecha():
    res = validar(_factura(fecha="31/12/2031"))
    assert res.estado == ERROR
    assert any(m.campos == ("fecha",) for m in res.mensajes)


def test_fecha_antigua_no_se_marca():
    assert validar(_factura(fecha="15/03/2019")).estado == OK


def test_operacion_muy_posterior_a_la_factura_se_revisa():
    res = validar(_factura(fecha_operacion="10/06/2026"))
    assert res.estado == REVISAR


def test_incidencias_son_texto_con_campos():
    res = validar(_factura(nif="B12345670"))
    aviso = res.mensajes[0]
    assert isinstance(aviso, str) and isinstance(aviso, Incidencia)
    assert aviso.campos == ("nif",) and aviso.gravedad == REVISAR
    import pickle
    copia = pickle.loads(pickle.dumps(aviso))
    assert copia == aviso and copia.campos == ("nif",)


@pytest.mark.parametrize("nif, valido", [
    ("B12345674", True),       # S.L.: control numérico
    ("B1234567D", False),      # una S.L. nunca termina en letra
    ("Q1234567D", True),       # organismo público: control con letra
    ("Q12345674", False),      # ... y nunca con número
    ("12345678Z", True),
    ("X1234567L", True),
    ("K1234567L", True),       # NIF K/L/M: letra con 7 dígitos
    ("K1234567A", False),
])
def test_control_de_nif(nif, valido):
    assert validar_nif(nif) is valido


def test_clasificar_nif_distingue_intracomunitario_y_extranjero():
    assert clasificar_nif("ESB12345674") == "es_prefijo"
    assert clasificar_nif("FR12345678901") == "ue"
    assert clasificar_nif("B12345670") == "invalido"
    res = validar(_factura(nif="ESB12345674"))
    assert "sin «ES»" in res.mensajes[0]


def test_gasto_sin_cuenta_no_se_pone_en_600_en_silencio():
    pr = construir(_gasto(), "B12345674", "CLIENTE PRUEBA SL")
    assert (pr.cuenta, pr.gxx) == ("629", "G22")
    assert "descarte" in pr.aviso


def test_gasto_con_cuenta_por_palabras_clave_avisa():
    pr = construir(_gasto(emisor_nombre="TALLER EJEMPLO"),
                   "B12345674", "CLIENTE PRUEBA SL")
    assert pr.cuenta == "622" and "palabras clave" in pr.aviso


def test_gasto_con_cuenta_de_gemini_no_avisa():
    pr = construir(_gasto(cuenta_gasto="622", subclave_gxx="G13"),
                   "B12345674", "CLIENTE PRUEBA SL")
    assert (pr.cuenta, pr.gxx, pr.aviso) == ("622", "G13", "")


def test_servicio_705_con_subclave_mala_no_se_convierte_en_700():
    venta = _gasto(emisor_nombre="CLIENTE PRUEBA SL", emisor_nif="B12345674",
                   receptor_nombre="COMPRADOR", receptor_nif="12345678Z",
                   cuenta_ingreso="705", subclave_ingreso="I05",
                   concepto_texto="mano de obra")
    pr = construir(venta, "B12345674", "CLIENTE PRUEBA SL")
    assert pr.tipo == "venta"
    assert (pr.cuenta, pr.gxx) == ("705", "I01")
    assert "I05" in pr.aviso


def test_venta_sin_cuenta_valida_avisa():
    venta = _gasto(emisor_nombre="CLIENTE PRUEBA SL", emisor_nif="B12345674",
                   receptor_nombre="COMPRADOR", receptor_nif="12345678Z",
                   cuenta_ingreso="999", concepto_texto="género")
    pr = construir(venta, "B12345674", "CLIENTE PRUEBA SL")
    assert pr.cuenta == "700" and "999" in pr.aviso


def test_quitar_aviso_cuenta_conserva_los_demas():
    aviso = ("Rol dudoso. Cuenta 629 puesta por descarte: no se ha podido "
             "determinar el concepto. Elija la cuenta correcta. Otro aviso.")
    assert quitar_aviso_cuenta(aviso) == "Rol dudoso. Otro aviso."
