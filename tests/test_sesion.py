"""El lote solo se reinicia al pulsar Vaciar todo, no al cerrar la app."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QCloseEvent

from facturas_excel import sesion
from facturas_excel.app import C_BASE, C_TIPO, VentanaPrincipal
from facturas_excel.modelo import Factura
from facturas_excel.procesar import FacturaProcesada

_app = QApplication.instance() or QApplication([])


def _procesada(numero="F-1", base=100.0):
    f = Factura(
        num_factura=numero, fecha="16/07/2026", nombre="PROVEEDOR SL",
        nif="B30048276", concepto="600", base_iva=base, pct_iva=21.0,
        cuota_iva=round(base * .21, 2), total_impreso=round(base * 1.21, 2),
    )
    return FacturaProcesada(
        tipo="gasto", facturas=[f], cuenta="600", gxx=None,
        origen=f"{numero}.pdf", pagina=1)


def _anadir_bloque(v, numero="F-1", base=100.0):
    v._rutas_actuales = [f"C:\\tmp\\{numero}.pdf"]
    v._on_terminado(
        [(b"imagen", _procesada(numero, base))],
        "CLIENTE DE PRUEBA", "12345678Z")


def test_se_recuperan_correcciones_y_se_pueden_anadir_mas_bloques(
        tmp_path, monkeypatch):
    ruta = tmp_path / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))

    primera = VentanaPrincipal(
        comprobar_updates=False, restaurar_sesion=False)
    _anadir_bloque(primera)
    primera.tabla.item(0, C_BASE).setText("99,00")
    tipo = primera.tabla.cellWidget(0, C_TIPO)
    tipo.setCurrentIndex(tipo.findData("venta"))
    primera.closeEvent(QCloseEvent())
    assert ruta.exists()

    recuperada = VentanaPrincipal(
        comprobar_updates=False, restaurar_sesion=True)
    assert recuperada.tabla.rowCount() == 1
    assert recuperada.tabla.item(0, C_BASE).text() == "99,00"
    assert recuperada._tipo_fila(0) == "venta"
    assert len(recuperada._bloques) == 1

    _anadir_bloque(recuperada, "F-2", 50.0)
    assert recuperada.tabla.rowCount() == 2
    assert recuperada.tabla.item(0, C_BASE).text() == "99,00"
    assert recuperada._tipo_fila(0) == "venta"


def test_una_fila_eliminada_no_reaparece_al_anadir_otro_bloque(
        tmp_path, monkeypatch):
    ruta = tmp_path / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))
    primera = VentanaPrincipal(
        comprobar_updates=False, restaurar_sesion=False)
    _anadir_bloque(primera)
    primera.tabla.selectRow(0)
    primera._eliminar_seleccion()
    primera._guardar_sesion()

    recuperada = VentanaPrincipal(
        comprobar_updates=False, restaurar_sesion=True)
    assert recuperada.tabla.rowCount() == 0

    _anadir_bloque(recuperada, "F-2", 50.0)
    assert recuperada.tabla.rowCount() == 1
    assert recuperada.filas[0]["factura"].num_factura == "F-2"
    assert len(recuperada._bloques) == 2


def test_vaciar_todo_borra_tambien_la_sesion(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    ruta = tmp_path / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    _anadir_bloque(v)
    v._guardar_sesion()
    assert ruta.exists()

    v._vaciar_todo()

    assert not ruta.exists()
    assert not v._bloques and v.tabla.rowCount() == 0


def test_una_sesion_corrupta_no_impide_abrir(tmp_path, monkeypatch):
    ruta = tmp_path / "sesion.pkl.gz"
    ruta.write_bytes(b"no es una sesion")
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))

    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)

    assert not v._bloques and v.tabla.rowCount() == 0


# ------------------------------------------- 1.23: no perder el lote nunca
def test_una_sesion_que_no_se_puede_abrir_se_aparta_y_no_se_borra(
        tmp_path, monkeypatch):
    """Antes se vaciaba el lote y, al cerrar, se borraba el fichero: las
    lecturas pagadas y la revisión se perdían sin decir nada."""
    ruta = tmp_path / "sesion.pkl.gz"
    ruta.write_bytes(b"no es una sesion")
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))

    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    v.closeEvent(QCloseEvent())

    apartadas = list(tmp_path.glob("sesion_lote.no-recuperada-*.pkl.gz"))
    assert len(apartadas) == 1
    assert apartadas[0].read_bytes() == b"no es una sesion"
    assert "No se ha borrado" in v.banda.lbl.text()


def test_si_falla_al_montar_el_lote_tambien_se_aparta(tmp_path, monkeypatch):
    ruta = tmp_path / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))
    primera = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    _anadir_bloque(primera)
    primera._guardar_sesion()

    def falla(*_a, **_k):
        raise KeyError("campo de otra versión")
    monkeypatch.setattr(VentanaPrincipal, "_reparar_abonos_emitidos_guardados",
                        falla)
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    v._guardar_sesion()        # lote vacío: antes borraba la sesión

    assert v.tabla.rowCount() == 0
    [apartada] = tmp_path.glob("sesion_lote.no-recuperada-*.pkl.gz")
    monkeypatch.setattr(sesion, "_ruta", lambda: str(apartada))
    assert sesion.cargar()["bloques"]          # se puede recuperar entera


def test_el_lote_se_guarda_solo_mientras_se_trabaja(tmp_path, monkeypatch):
    ruta = tmp_path / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    _anadir_bloque(v)
    v.tabla.item(0, C_BASE).setText("99,00")
    assert v._timer_sesion.isActive()       # cada cambio programa un guardado

    v._guardar_sesion_automatica()
    sesion.esperar()
    datos = sesion.cargar()
    assert datos and datos["filas"][0]["factura"].base_iva == 99.0


def test_un_guardado_viejo_que_acaba_tarde_no_pisa_al_nuevo(
        tmp_path, monkeypatch):
    import threading
    ruta = tmp_path / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))
    soltar = threading.Event()
    escribir = sesion._escribir

    def lento(paquete, numero):
        if pickle_dice(paquete) == "viejo":
            soltar.wait(5)
        escribir(paquete, numero)
    monkeypatch.setattr(sesion, "_escribir", lento)

    sesion.guardar_en_segundo_plano({"bloques": ["viejo"]})
    sesion.guardar({"bloques": ["nuevo"]})
    soltar.set()
    sesion.esperar()
    assert sesion.cargar() == {"bloques": ["nuevo"]}

    # Y tras «Vaciar todo», un guardado pendiente no resucita el lote.
    soltar.clear()
    sesion.guardar_en_segundo_plano({"bloques": ["viejo"]})
    sesion.borrar()
    soltar.set()
    sesion.esperar()
    assert not ruta.exists()


def pickle_dice(paquete):
    import pickle
    return pickle.loads(paquete)["datos"]["bloques"][0]


def test_si_no_se_puede_guardar_se_avisa_una_vez(tmp_path, monkeypatch):
    ruta = tmp_path / "no-existe" / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    _anadir_bloque(v)
    v._guardar_sesion_automatica()
    sesion.esperar()
    assert sesion.ultimo_error()
    v._guardar_sesion_automatica()      # el aviso sale en el siguiente
    sesion.esperar()
    assert "No se puede guardar el lote" in v.banda.lbl.text()


def test_se_quedan_solo_las_cinco_ultimas_apartadas(tmp_path, monkeypatch):
    ruta = tmp_path / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))
    for _ in range(7):
        ruta.write_bytes(b"roto")
        assert sesion.cargar() is None
    assert len(list(tmp_path.glob("sesion_lote.no-recuperada-*"))) == 5
