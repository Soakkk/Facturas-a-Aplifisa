"""Facturas ya exportadas en otro lote: se señalan y se preguntan al exportar."""
from facturas_excel import ventana_aplifisa
import os

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

import facturas_excel.app as modulo_app
from facturas_excel import historial, proveedores
from facturas_excel.app import C_ESTADO, ICONO_ESTADO, VentanaPrincipal
from facturas_excel.modelo import Factura
from facturas_excel.validacion import REVISAR

_app = QApplication.instance() or QApplication([])


def _factura(numero, nombre="PROVEEDOR PRUEBA SL", nif="B12345674"):
    return Factura(num_factura=numero, fecha="03/09/2026", nombre=nombre,
                   nif=nif, concepto="622", subclave="G13", base_iva=100.0,
                   pct_iva=21.0, cuota_iva=21.0, total_impreso=121.0,
                   confianza_ia="alta", verificacion="doble")


def _ventana(numeros):
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._cliente_nif, v._cliente_nombre = "12345678Z", "CLIENTE PRUEBA"
    v._bloques = [{"nombre": "b1", "cliente": "CLIENTE PRUEBA",
                   "nif": "12345678Z"}]
    for n in numeros:
        v._anadir_fila(b"", _factura(n), "gasto", "622", "G13", "", "b1")
    v._revalidar_todo()
    return v


def _preparar_exportacion(monkeypatch, tmp_path, escritos):
    class Orden:
        def __init__(self, parent):
            pass

        def exec(self):
            return QDialog.Accepted

        def recordar(self):
            pass

        def orden(self):
            return ventana_aplifisa.ORDEN_PDF

    monkeypatch.setattr(ventana_aplifisa, "DialogoOrden", Orden)
    monkeypatch.setattr(modulo_app.archivo, "ruta_excel_consolidado",
                        lambda cliente, ejercicio, tipo: str(tmp_path / f"{tipo}.xlsx"))
    monkeypatch.setattr(modulo_app.archivo, "eliminar_excel_temporales",
                        lambda cliente, tipo: [])
    monkeypatch.setattr(ventana_aplifisa, "leer_config", lambda ruta: object())
    monkeypatch.setattr(ventana_aplifisa, "exportar_excel",
                        lambda facturas, config, ruta, **_k: escritos.append(
                            [f.num_factura for f in facturas]))
    monkeypatch.setattr(ventana_aplifisa, "verificar_excel", lambda *a: [])
    monkeypatch.setattr(ventana_aplifisa, "totales_del_excel",
                        lambda *a: {"base_iva": 0, "cuota_iva": 0})
    monkeypatch.setattr(modulo_app.QMessageBox, "information", lambda *a: None)


def test_clave_exige_numero_y_fecha():
    assert historial.clave(_factura("F-1"), "gasto") == \
        "gasto|B12345674|F1|2026-09-03"
    assert historial.clave(_factura(""), "gasto") is None


def test_exportar_registra_y_aprende_y_la_siguiente_vez_avisa(
        monkeypatch, tmp_path):
    escritos = []
    _preparar_exportacion(monkeypatch, tmp_path, escritos)
    v = _ventana(["F-1", "F-2"])
    assert not proveedores.leer_todo()           # leer no memoriza nada
    v._exportar_todo()
    assert escritos == [["F-1", "F-2"]]
    assert historial.buscar("12345678Z", _factura("F-1"), "gasto")
    assert proveedores.leer_todo()               # exportar sí

    # Otro lote (otro día) con una factura repetida y otra nueva.
    otra = _ventana(["F-2", "F-3"])
    assert otra.tabla.item(0, C_ESTADO).text() == ICONO_ESTADO[REVISAR]
    assert "YA EXPORTADA" in otra.tabla.item(0, C_ESTADO).toolTip()
    assert otra.tabla.item(1, C_ESTADO).text() == ICONO_ESTADO["ok"]

    # Por defecto se exporta sin la repetida.
    monkeypatch.setattr(QMessageBox, "exec", lambda self: self.defaultButton().click())
    escritos.clear()
    otra._exportar_todo()
    assert escritos == [["F-3"]]


def test_se_puede_incluir_otra_vez_a_proposito(monkeypatch, tmp_path):
    escritos = []
    _preparar_exportacion(monkeypatch, tmp_path, escritos)
    v = _ventana(["F-1"])
    v._exportar_todo()
    escritos.clear()

    def incluir(caja):
        next(b for b in caja.buttons() if b.text() == "Incluirlas todas otra vez").click()
    monkeypatch.setattr(QMessageBox, "exec", incluir)
    _ventana(["F-1"])._exportar_todo()
    assert escritos == [["F-1"]]


def test_olvidar_quita_del_historial():
    historial.registrar("12345678Z", {"gasto": [_factura("F-9")]},
                        {"gasto": "GASTOS.xlsx"})
    assert historial.buscar("12345678Z", _factura("F-9"), "gasto")
    assert historial.olvidar("12345678Z", {"gasto": [_factura("F-9")]}) == 1
    assert not historial.buscar("12345678Z", _factura("F-9"), "gasto")


# --- Exportar las que faltaban en Aplifisa -------------------------------
# Una factura cuenta como exportada en cuanto se crea su Excel. Si la
# importación en Aplifisa se cancela o se queda a medias, faltan en Aplifisa
# pero el programa las da por exportadas: antes, «Exportar sin ellas» no
# dejaba nada y el programa se quedaba ahí, sin pasar a elegir el orden.

def _listado(v, estados):
    """Como si se hubiera comprobado el listado de Aplifisa."""
    def contrastar(*_a):
        v._informe_registro = object()
        for fila, estado in enumerate(estados):
            v.filas[fila]["registro_estado"] = estado
    return contrastar


def _contar_orden(monkeypatch):
    veces = []
    original = ventana_aplifisa.DialogoOrden

    class Contado(original):
        def exec(self):
            veces.append(1)
            return super().exec()
    monkeypatch.setattr(ventana_aplifisa, "DialogoOrden", Contado)
    return veces


def test_todo_exportado_ofrece_comprobar_y_exporta_solo_las_que_faltan(
        monkeypatch, tmp_path):
    escritos, botones = [], []
    _preparar_exportacion(monkeypatch, tmp_path, escritos)
    _ventana(["F-1", "F-2", "F-3"])._exportar_todo()
    escritos.clear()

    v = _ventana(["F-1", "F-2", "F-3"])        # todas ya exportadas
    v._contrastar_registro = _listado(v, ["cuadra", "sin_registrar", "sin_registrar"])
    orden = _contar_orden(monkeypatch)

    def pulsar_el_de_siempre(caja):
        botones.append([b.text() for b in caja.buttons()])
        caja.defaultButton().click()
    monkeypatch.setattr(QMessageBox, "exec", pulsar_el_de_siempre)
    v._exportar_todo()
    # Sin nada nuevo no se ofrece «solo las nuevas»: no quedaría nada.
    assert not any(t.startswith("Exportar solo las nuevas") for t in botones[0])
    assert "Comprobar con el listado de Aplifisa…" in botones[0]
    assert "Exportar las que faltan (2)" in botones[1]
    # Pasa a elegir el orden y el Excel lleva solo las que faltaban.
    assert orden == [1]
    assert escritos == [["F-2", "F-3"]]


def test_con_el_listado_ya_comprobado_salen_las_nuevas_y_las_que_faltan(
        monkeypatch, tmp_path):
    escritos = []
    _preparar_exportacion(monkeypatch, tmp_path, escritos)
    _ventana(["F-1", "F-2"])._exportar_todo()
    escritos.clear()

    v = _ventana(["F-1", "F-2", "F-3"])        # F-3 es nueva
    _listado(v, ["cuadra", "sin_registrar", "sin_registrar"])()
    monkeypatch.setattr(QMessageBox, "exec", lambda self: self.defaultButton().click())
    v._exportar_todo()
    assert escritos == [["F-2", "F-3"]]


def test_si_todo_esta_en_aplifisa_no_se_exporta_sin_querer(monkeypatch, tmp_path):
    escritos = []
    _preparar_exportacion(monkeypatch, tmp_path, escritos)
    _ventana(["F-1"])._exportar_todo()
    escritos.clear()
    v = _ventana(["F-1"])
    _listado(v, ["cuadra"])()
    monkeypatch.setattr(QMessageBox, "exec", lambda self: self.defaultButton().click())
    v._exportar_todo()
    assert escritos == []                       # por defecto, Cancelar

    def todas(caja):
        next(b for b in caja.buttons()
             if b.text() == "Exportarlas todas otra vez").click()
    monkeypatch.setattr(QMessageBox, "exec", todas)
    v._exportar_todo()
    assert escritos == [["F-1"]]


def test_sin_elegir_el_listado_no_se_exporta_nada(monkeypatch, tmp_path):
    escritos = []
    _preparar_exportacion(monkeypatch, tmp_path, escritos)
    _ventana(["F-1"])._exportar_todo()
    escritos.clear()
    v = _ventana(["F-1"])
    v._contrastar_registro = lambda *a: None    # cerró el diálogo de archivo
    monkeypatch.setattr(QMessageBox, "exec", lambda self: self.defaultButton().click())
    v._exportar_todo()
    assert escritos == []
