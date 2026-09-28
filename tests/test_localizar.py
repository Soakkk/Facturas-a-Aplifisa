"""Recuadros en el documento: dónde está escrito cada dato (sin Gemini real)."""

import io

from PIL import Image
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from facturas_excel import ajustes, claves, localizar
from facturas_excel.app import C_NIF, C_TOTAL, VentanaPrincipal
from facturas_excel.modelo import Factura

_app = QApplication.instance() or QApplication([])


def _png(color="white"):
    buf = io.BytesIO()
    Image.new("RGB", (600, 800), color).save(buf, format="PNG")
    return buf.getvalue()


def _factura(**cambios):
    datos = dict(num_factura="F-1", fecha="10/03/2026", nombre="PROVEEDOR PRUEBA SL",
                 nif="B12345674", concepto="600", base_iva=100.0, pct_iva=21.0,
                 cuota_iva=21.0, total_impreso=121.0)
    datos.update(cambios)
    return Factura(**datos)


RESPUESTA = {"datos": [
    {"campo": "nif", "valor": "B12345674", "caja": [100, 600, 130, 800]},
    {"campo": "total", "valor": "121,00", "caja": [850, 700, 880, 900]},
    {"campo": "total", "valor": "112,00", "caja": [850, 100, 880, 250]},
    {"campo": "fecha", "valor": "10/03/2026", "caja": None},
    {"campo": "base", "valor": "100,00", "caja": [900, 10, 850, 20]},   # al revés
]}


# ----------------------------------------------------------- funciones
def test_se_pide_cada_dato_una_vez_y_tambien_los_valores_en_disputa():
    f = _factura()
    f.discrepancias = ({"campo": "total", "valor_1": 121.0, "valor_2": 112.0},)
    lista = localizar.peticiones([f, _factura(base_iva=50.0)], f.discrepancias)
    assert ("nif", "B12345674") in lista
    assert ("total", "121,00") in lista and ("total", "112,00") in lista
    assert ("base", "100,00") in lista and ("base", "50,00") in lista
    assert len(lista) == len(set(lista))


def test_se_descartan_las_cajas_vacias_o_imposibles():
    cajas = localizar.interpretar(RESPUESTA)
    assert [(c.campo, c.valor) for c in cajas] == [
        ("nif", "B12345674"), ("total_impreso", "121,00"), ("total_impreso", "112,00")]
    nif = cajas[0]
    assert (nif.y0, nif.x0, nif.y1, nif.x1) == (0.1, 0.6, 0.13, 0.8)


def test_cada_valor_se_empareja_con_su_caja():
    cajas = localizar.interpretar(RESPUESTA)
    [total] = localizar.cajas_de(cajas, "total_impreso", 121.0)
    assert total.x0 == 0.7
    [otra] = localizar.cajas_de(cajas, "total_impreso", "112")
    assert otra.x0 == 0.1
    assert localizar.cajas_de(cajas, "nif", "b-12345674")
    guardadas = localizar.de_guardado(localizar.a_guardar(cajas))
    assert guardadas == cajas


# ------------------------------------------------------------- ventana
def _ventana(monkeypatch, pedidas):
    def pedir(api_key, modelo, img, lista):
        pedidas.append(lista)
        return localizar.interpretar(RESPUESTA), [(modelo, 1200, 150)]
    monkeypatch.setattr(localizar, "pedir", pedir)
    monkeypatch.setattr(claves, "leer_api_key", lambda: "clave-de-prueba")
    return VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)


def _esperar(v):
    if v._hilo_localizar:
        v._hilo_localizar.wait(5000)
    QCoreApplication.processEvents()
    QCoreApplication.processEvents()


def test_las_dudosas_se_senalan_solas_y_las_correctas_no(monkeypatch):
    pedidas = []
    v = _ventana(monkeypatch, pedidas)
    dudosa = _factura(total_impreso=112.0)       # no cuadra: ámbar/rojo
    v._anadir_fila(_png("white"), dudosa, "gasto", "600", "", "")
    v._anadir_fila(_png("gray"), _factura(num_factura="F-2"), "gasto", "600", "", "")
    v._revalidar_todo()
    assert v.filas[0].estado != "ok" and v.filas[1].estado == "ok"
    v._localizar_dudosas()
    _esperar(v)
    assert len(pedidas) == 1                   # solo la hoja dudosa
    assert localizar.clave_imagen(v.filas[0].png) in v._localizaciones
    # Con la fila seleccionada, el total que no cuadra sale recuadrado.
    v.tabla.selectRow(0)
    v._mostrar_miniatura()
    recuadros = v.lbl_img.recuadros()
    assert any(r.texto == "Total" for r in recuadros)
    # Volver a pedirlo no gasta otra consulta.
    v._localizar_dudosas()
    _esperar(v)
    assert len(pedidas) == 1


def test_al_pulsar_una_celda_se_senala_ese_dato(monkeypatch):
    pedidas = []
    v = _ventana(monkeypatch, pedidas)
    v._anadir_fila(_png(), _factura(), "gasto", "600", "", "")
    v._revalidar_todo()
    v.tabla.selectRow(0)
    v._localizar_actual()                      # «¿De dónde sale?»
    _esperar(v)
    assert len(pedidas) == 1
    assert {r.texto for r in v.lbl_img.recuadros()} >= {"NIF", "Total"}
    v._senalar_celda(0, C_NIF)
    [nif] = v.lbl_img.recuadros()
    assert nif.texto == "NIF" and nif.destacado
    v._senalar_celda(0, C_TOTAL)
    [total] = v.lbl_img.recuadros()
    assert total.x0 == 0.7                     # el 121,00, no el 112,00


def test_una_disputa_ensena_las_dos_lecturas(monkeypatch):
    v = _ventana(monkeypatch, [])
    f = _factura()
    f.discrepancias = ({"campo": "total", "etiqueta": "Total",
                        "valor_1": 121.0, "valor_2": 112.0},)
    v._anadir_fila(_png(), f, "gasto", "600", "", "")
    v._revalidar_todo()
    v.tabla.selectRow(0)
    v._localizar_dudosas()
    _esperar(v)
    v._senalar_celda(0, C_TOTAL)
    textos = sorted((r.texto, r.discontinuo) for r in v.lbl_img.recuadros())
    assert textos == [("Total · lectura 1", False), ("Total · lectura 2", True)]


def test_se_puede_desactivar_y_se_guarda_en_la_sesion(monkeypatch):
    pedidas = []
    v = _ventana(monkeypatch, pedidas)
    ajustes.guardar("localizar_dudosas", False)
    v._anadir_fila(_png(), _factura(total_impreso=112.0), "gasto", "600", "", "")
    v._revalidar_todo()
    v._localizar_dudosas()
    _esperar(v)
    assert pedidas == []
    ajustes.guardar("localizar_dudosas", True)
    v._localizar_dudosas()
    _esperar(v)
    v._bloques = [{"nombre": "B", "procesadas": [], "crudos": [], "cliente": "",
                   "nif": ""}]
    v._guardar_sesion()
    otra = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    assert otra._localizaciones == v._localizaciones


def test_cerrar_con_la_busqueda_en_marcha_no_espera_ni_rompe(monkeypatch):
    import threading
    import time as _t
    liberar = threading.Event()

    def pedir_lento(api_key, modelo, img, lista):
        liberar.wait(10)
        return [], []
    monkeypatch.setattr(localizar, "pedir", pedir_lento)
    monkeypatch.setattr(claves, "leer_api_key", lambda: "clave-de-prueba")
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._anadir_fila(_png(), _factura(total_impreso=112.0), "gasto", "600", "", "")
    v._revalidar_todo()
    v._localizar_dudosas()
    assert v._hilo_localizar.isRunning()
    inicio = _t.monotonic()
    v.close()
    assert _t.monotonic() - inicio < 3
    assert v._hilo_localizar.cancelado
    liberar.set()
    v._hilo_localizar.wait(5000)
