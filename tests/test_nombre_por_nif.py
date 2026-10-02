"""Un NIF, un nombre: en Aplifisa un NIF es un solo proveedor.

Las facturas de una misma empresa llegaban unas veces con el nombre fiscal
(«PROVEEDOR TELECOMUNICACIONES, S.A.») y otras con el comercial
(«Proveedor»): con el mismo NIF salían dos nombres en la tabla y en el
Excel. Si los nombres se parecen, se deja uno solo; si no se parecen en
nada, uno de los dos está mal leído y se avisa.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from facturas_excel import proveedores
from facturas_excel.modelo import Factura
from facturas_excel.procesar import (
    construir, nombre_preferido, nombres_compatibles, unificar_nombres,
    unificar_nombres_por_nif,
)

NIF_A = "A12345674"
NIF_B = "B76543214"


@pytest.fixture(autouse=True)
def memoria_vacia(tmp_path, monkeypatch):
    monkeypatch.setattr(proveedores, "dir_datos", lambda: str(tmp_path))


def _f(nombre, nif=NIF_A, num="1"):
    return Factura(num_factura=num, fecha="09/07/2026", nombre=nombre, nif=nif,
                   base_iva=100.0, pct_iva=21.0, cuota_iva=21.0,
                   total_impreso=121.0)


def test_el_nombre_fiscal_gana_al_comercial():
    facturas = [_f("Proveedor", num="1"), _f("PROVEEDOR TELECOM, S.A.", num="2"),
                _f("Proveedor", num="3"), _f("Proveedor", num="4")]
    cambios = unificar_nombres_por_nif(facturas)
    assert {f.nombre for f in facturas} == {"PROVEEDOR TELECOM, S.A."}
    assert len(cambios) == 3


def test_entre_dos_con_forma_juridica_el_que_mas_se_repite():
    facturas = [_f("AGUAS DEL SUR, S.A."), _f("AGUAS DEL SUR S.A."),
                _f("AGUAS DEL SUR S.A.")]
    unificar_nombres_por_nif(facturas)
    assert {f.nombre for f in facturas} == {"AGUAS DEL SUR S.A."}


def test_el_nombre_guardado_manda():
    facturas = [_f("PROVEEDOR TELECOM, S.A."), _f("Proveedor")]
    unificar_nombres_por_nif(facturas, {NIF_A: "PROVEEDOR TELECOM SAU"})
    assert {f.nombre for f in facturas} == {"PROVEEDOR TELECOM SAU"}


def test_nombres_que_no_se_parecen_no_se_tocan():
    """Con el mismo NIF, «Proveedor» y «GASOLINERA NORTE, S.L.» no son la
    misma forma de escribir nada: o el NIF o el nombre está mal leído."""
    facturas = [_f("PROVEEDOR TELECOM, S.A."), _f("GASOLINERA NORTE, S.L.")]
    assert unificar_nombres_por_nif(facturas) == []
    assert [f.nombre for f in facturas] == ["PROVEEDOR TELECOM, S.A.",
                                            "GASOLINERA NORTE, S.L."]


def test_sin_nif_valido_no_se_agrupa():
    facturas = [_f("Proveedor", nif="A1234567"), _f("PROVEEDOR TELECOM, S.A.",
                                                    nif="A1234567")]
    assert unificar_nombres_por_nif(facturas) == []
    otros = [_f("Proveedor", nif=NIF_A), _f("PROVEEDOR TELECOM, S.A.", nif=NIF_B)]
    assert unificar_nombres_por_nif(otros) == []


def test_un_nombre_vacio_toma_el_de_su_nif():
    facturas = [_f("PROVEEDOR TELECOM, S.A."), _f("")]
    unificar_nombres_por_nif(facturas)
    assert facturas[1].nombre == "PROVEEDOR TELECOM, S.A."


def test_compatibles_y_preferido():
    assert nombres_compatibles("Proveedor", "PROVEEDOR TELECOM, S.A.")
    assert nombres_compatibles("Telefonica", "TELEFÓNICA DE ESPAÑA, S.A.U.")
    assert not nombres_compatibles("Proveedor", "GASOLINERA NORTE, S.L.")
    # «S. A.» con espacios también es forma jurídica.
    assert nombre_preferido(["Proveedor", "Proveedor", "Proveedor Telecom S. A."]) \
        == "Proveedor Telecom S. A."
    # Sin forma jurídica (una persona): el que más se repite.
    assert nombre_preferido(["JUAN PEREZ GARCIA", "J. PEREZ GARCIA",
                             "JUAN PEREZ GARCIA"]) == "JUAN PEREZ GARCIA"


def test_al_leer_un_lote_sale_un_solo_nombre_por_nif():
    def datos(nombre, num):
        return {"emisor_nif": NIF_A, "emisor_nombre": nombre,
                "receptor_nif": "12345678Z", "receptor_nombre": "CLIENTE",
                "num_factura": num, "fecha": "09/07/2026",
                "lineas_iva": [{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0}],
                "total": 121.0, "cuenta_gasto": "628", "subclave_gxx": "G17"}
    lote = [construir(datos("PROVEEDOR TELECOM, S.A.", "1"), "12345678Z", "CLIENTE"),
            construir(datos("Proveedor", "2"), "12345678Z", "CLIENTE")]
    assert unificar_nombres(lote) == 1
    assert {pr.facturas[0].nombre for pr in lote} == {"PROVEEDOR TELECOM, S.A."}


# ------------------------------------------------------------ la ventana

def _ventana(nombres):
    from PySide6.QtWidgets import QApplication
    from facturas_excel.app import VentanaPrincipal
    QApplication.instance() or QApplication([])
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    for i, (nombre, nif) in enumerate(nombres):
        v._anadir_fila(b"", _f(nombre, nif=nif, num=f"F-{i}"), "gasto", "628",
                       "G17", "")
    v._revalidar_todo()
    return v


def test_misma_nif_con_otro_nombre_se_avisa_en_las_dos():
    from facturas_excel.validacion import REVISAR
    v = _ventana([("PROVEEDOR TELECOM, S.A.", NIF_A),
                  ("GASOLINERA NORTE, S.L.", NIF_A),
                  ("OTRA EMPRESA, S.L.", NIF_B)])
    for r, otra in ((0, "GASOLINERA NORTE, S.L."), (1, "PROVEEDOR TELECOM, S.A.")):
        avisos = [m for m in v.filas[r]["mensajes"]
                  if "a nombre de" in str(m)]
        assert avisos and otra in str(avisos[0])
        assert set(avisos[0].campos) == {"nombre", "nif"}
        assert v.filas[r]["estado"] == REVISAR
    assert not any("a nombre de" in str(m) for m in v.filas[2]["mensajes"])
    v.close()


def test_al_corregir_el_nif_toma_el_nombre_de_ese_nif():
    from facturas_excel.tabla_facturas import C_NIF, C_NOMBRE
    v = _ventana([("PROVEEDOR TELECOM, S.A.", NIF_A),
                  ("Proveedor", "A1234567")])        # NIF cortado
    v.tabla.item(1, C_NIF).setText(NIF_A)
    assert v.filas[1].factura.nombre == "PROVEEDOR TELECOM, S.A."
    assert v.tabla.item(1, C_NOMBRE).text() == "PROVEEDOR TELECOM, S.A."
    assert not any("a nombre de" in str(m) for m in v.filas[1]["mensajes"])
    v.close()


def test_una_sesion_de_antes_se_abre_con_un_nombre_por_nif(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from facturas_excel import sesion
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.tabla_facturas import C_NOMBRE
    QApplication.instance() or QApplication([])
    filas = [{"png": b"", "factura": _f(nombre, num=str(i)), "tipo": "gasto",
              "cuenta": "628", "gxx": "G17", "aviso": "", "bloque": "Taco 1"}
             for i, nombre in enumerate(("Proveedor", "PROVEEDOR TELECOM, S.A.",
                                         "Proveedor"))]
    monkeypatch.setattr(sesion, "cargar", lambda: {
        "bloques": [{"nombre": "Taco 1", "procesadas": [], "crudos": [],
                     "nif": "12345678Z", "cliente": "CLIENTE"}],
        "filas": filas, "cliente_nif": "12345678Z", "cliente_nombre": "CLIENTE"})
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._restaurar_sesion()
    assert v.tabla.rowCount() == 3
    assert {v.tabla.item(r, C_NOMBRE).text() for r in range(3)} \
        == {"PROVEEDOR TELECOM, S.A."}
    v.close()
