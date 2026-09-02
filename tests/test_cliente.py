"""Quien es el cliente de la asesoria y quien el proveedor.

Caso real que lo destapo: un taco de 4 facturas de la MISMA gasolinera al MISMO
cliente. Las dos partes salian 4 veces cada una, el desempate era al azar y
salio el proveedor como cliente: todas las facturas del reves.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from facturas_excel import clientes, procesar, proveedores
from facturas_excel.app import C_NIF, C_NOMBRE, C_TIPO, VentanaPrincipal

_app = QApplication.instance() or QApplication([])

# El cliente de la asesoria y su gasolinera (NIF de prueba, no reales).
CLIENTE = ("12345678Z", "RODRIGUEZ EJEMPLO JOSE")
GASOLINERA = ("B12345674", "AREA DE SERVICIO DE EJEMPLO SL")


@pytest.fixture(autouse=True)
def datos_aparte(tmp_path, monkeypatch):
    """Sin tocar los clientes ni proveedores de verdad del usuario."""
    monkeypatch.setattr(clientes, "dir_datos", lambda: str(tmp_path))
    monkeypatch.setattr(proveedores, "dir_datos", lambda: str(tmp_path))


def factura_gasolinera(numero):
    """Una compra de gasoil: la gasolinera emite, el cliente recibe."""
    return {
        "emisor_nif": GASOLINERA[0], "emisor_nombre": GASOLINERA[1],
        "receptor_nif": CLIENTE[0], "receptor_nombre": CLIENTE[1],
        "num_factura": numero, "fecha": "31/01/2025",
        "lineas_iva": [{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0}],
        "total": 121.0, "cuenta_gasto": "628", "subclave_gxx": "G18",
    }


def test_con_las_dos_partes_empatadas_se_marca_como_dudoso():
    lote = [factura_gasolinera(f"FA-{n}") for n in range(4)]
    analisis = procesar.analizar_cliente(lote)

    assert analisis.dudoso                       # nadie gana: hay que preguntar
    assert {c.nif for c in analisis.candidatos} == {CLIENTE[0], GASOLINERA[0]}
    assert analisis.candidatos[0].veces == 4


def test_un_cliente_confirmado_gana_aunque_empaten():
    clientes.marcar_cliente(*CLIENTE)
    analisis = procesar.analizar_cliente(
        [factura_gasolinera(f"FA-{n}") for n in range(4)])

    assert not analisis.dudoso
    assert analisis.mejor.nif == CLIENTE[0]
    assert analisis.mejor.cliente_confirmado


def test_un_proveedor_conocido_no_puede_ser_el_cliente():
    procesar.recordar_nif(GASOLINERA[1], GASOLINERA[0], manual=True)
    analisis = procesar.analizar_cliente(
        [factura_gasolinera(f"FA-{n}") for n in range(4)])

    assert not analisis.dudoso
    assert analisis.mejor.nif == CLIENTE[0]


def test_el_papel_de_cada_uno_se_cuenta_para_poder_enseñarlo():
    analisis = procesar.analizar_cliente(
        [factura_gasolinera(f"FA-{n}") for n in range(4)])
    por_nif = {c.nif: c for c in analisis.candidatos}
    assert por_nif[GASOLINERA[0]].papel == "siempre emite"
    assert por_nif[CLIENTE[0]].papel == "siempre recibe"


def test_si_uno_sale_mas_veces_sigue_ganando_sin_preguntar():
    # Lo de siempre: un lote variado donde el cliente sale en todas.
    lote = [factura_gasolinera("FA-1")]
    otra = factura_gasolinera("FA-2")
    otra["emisor_nif"], otra["emisor_nombre"] = "B12345674", "OTRO PROVEEDOR SL"
    otra["emisor_nif"] = "A12345674"
    lote.append(otra)
    analisis = procesar.analizar_cliente(lote)
    assert not analisis.dudoso
    assert analisis.mejor.nif == CLIENTE[0]


# ------------------------------------------------- rehacer el lote sin Gemini
def _crudos(n=4):
    return [(b"", "taco.pdf", i + 1, factura_gasolinera(f"FA-{i}"))
            for i in range(n)]


def test_cambiar_el_cliente_rehace_el_lote_sin_volver_a_pagar(monkeypatch):
    v = VentanaPrincipal(comprobar_updates=False)
    monkeypatch.setattr("facturas_excel.app.DialogoCliente.exec",
                        lambda self: 0)          # que no salte el dialogo solo
    crudos = _crudos()
    # Se carga con el cliente MAL detectado (la gasolinera).
    v._rutas_actuales = ["taco.pdf"]
    v._on_terminado(procesar.preparar_lote(crudos, GASOLINERA[1], GASOLINERA[0]),
                    GASOLINERA[1], GASOLINERA[0], crudos)
    assert v.tabla.item(0, C_NIF).text() == CLIENTE[0]      # contraparte al reves

    v._rehacer_con_cliente(CLIENTE[1], CLIENTE[0])

    assert v._cliente_nif == CLIENTE[0]
    assert v.tabla.rowCount() == 4
    # Ahora la contraparte es la gasolinera y son gastos
    assert v.tabla.item(0, C_NIF).text() == GASOLINERA[0]
    assert GASOLINERA[1].split()[0] in v.tabla.item(0, C_NOMBRE).text().upper()
    assert v.tabla.cellWidget(0, C_TIPO).currentData() == "gasto"


def test_al_elegir_cliente_se_recuerda_el_y_el_proveedor(monkeypatch):
    from facturas_excel.dialogo_cliente import DialogoCliente
    v = VentanaPrincipal(comprobar_updates=False)
    crudos = _crudos()
    v._rutas_actuales = ["taco.pdf"]
    monkeypatch.setattr(DialogoCliente, "exec", lambda self: 0)
    v._on_terminado(procesar.preparar_lote(crudos, GASOLINERA[1], GASOLINERA[0]),
                    GASOLINERA[1], GASOLINERA[0], crudos)

    # El usuario elige el bueno
    def elegir(self):
        for i, c in enumerate(self._candidatos):
            if c.nif == CLIENTE[0]:
                self.grupo.button(i).setChecked(True)
        return 1
    monkeypatch.setattr(DialogoCliente, "exec", elegir)
    v._cambiar_cliente()

    assert clientes.es_cliente_confirmado(CLIENTE[0])
    assert v._cliente_nif == CLIENTE[0]
    # y la proxima vez ya no hay duda
    assert not procesar.analizar_cliente(
        [factura_gasolinera("FA-9")] * 3).dudoso


def test_con_empate_se_propone_al_que_recibe():
    # Un taco de facturas iguales casi siempre es de compras: el cliente es
    # quien las recibe. Es solo la propuesta; el usuario decide y se recuerda.
    analisis = procesar.analizar_cliente(
        [factura_gasolinera(f"FA-{n}") for n in range(4)])
    assert analisis.mejor.nif == CLIENTE[0]
    assert analisis.dudoso          # se sigue preguntando


# ------------------------------------------- gasto o ingreso, con red de segur.
def test_avisa_si_una_factura_sale_del_reves_de_lo_declarado():
    from facturas_excel.app import C_ESTADO, ICONO_ESTADO
    from facturas_excel.validacion import REVISAR
    v = VentanaPrincipal(comprobar_updates=False)
    crudos = _crudos(2)
    v._rutas_actuales = ["taco.pdf"]
    v._tipo_escaneo = "ingresos"          # el usuario dijo: taco de ventas
    v._escaneo_reciente = True
    # ...pero son compras a la gasolinera
    v._on_terminado(procesar.preparar_lote(crudos, CLIENTE[1], CLIENTE[0]),
                    CLIENTE[1], CLIENTE[0], crudos)

    assert v.tabla.item(0, C_ESTADO).text() == ICONO_ESTADO[REVISAR]
    assert "INGRESOS" in v.tabla.item(0, C_ESTADO).toolTip()


def test_si_coincide_con_lo_declarado_no_molesta():
    from facturas_excel.app import C_ESTADO
    v = VentanaPrincipal(comprobar_updates=False)
    crudos = _crudos(2)
    v._rutas_actuales = ["taco.pdf"]
    v._tipo_escaneo = "gastos"
    v._escaneo_reciente = True
    v._on_terminado(procesar.preparar_lote(crudos, CLIENTE[1], CLIENTE[0]),
                    CLIENTE[1], CLIENTE[0], crudos)

    assert "taco" not in v.tabla.item(0, C_ESTADO).toolTip()


def test_la_unica_del_bloque_que_va_al_reves_se_marca():
    from facturas_excel.app import C_ESTADO, C_TIPO
    v = VentanaPrincipal(comprobar_updates=False)
    crudos = _crudos(6)
    v._rutas_actuales = ["taco.pdf"]
    v._on_terminado(procesar.preparar_lote(crudos, CLIENTE[1], CLIENTE[0]),
                    CLIENTE[1], CLIENTE[0], crudos)
    # Se cambia una a mano a ingreso: es la unica de las 6
    combo = v.tabla.cellWidget(0, C_TIPO)
    combo.setCurrentIndex(combo.findData("venta"))
    v._revalidar_todo()

    assert "única factura de su bloque" in v.tabla.item(0, C_ESTADO).toolTip()
