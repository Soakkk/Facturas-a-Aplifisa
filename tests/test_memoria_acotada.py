"""Memoria acotada con PDF de 100-200 MB (200-450 hojas).

Lo que medía el banco de estrés con 450 hojas: la caché de MuPDF no se
vaciaba nunca (unos 250 MB fijos), la imagen de cada hoja vivía en memoria y
en cada guardado de la sesión (80 MB), la huella del original leía el PDF
entero de una vez (+200 MB) y «Vaciar todo» no soltaba nada. Estas pruebas
fijan cada arreglo; ninguno cambia lo que se ve ni lo que se decide.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from facturas_excel import imagen_visor, pdf

_app = QApplication.instance() or QApplication([])


def _pdf(ruta, paginas=3):
    documento = fitz.open()
    for numero in range(paginas):
        hoja = documento.new_page(width=300, height=420)
        hoja.insert_text((30, 60), f"FACTURA DE PRUEBA {numero + 1}", fontsize=9)
    documento.save(str(ruta))
    documento.close()
    return str(ruta)


class WorkerFalso(QObject):
    """Un Worker que no lee nada ni arranca hilo ninguno."""
    progreso = Signal(int, int)
    terminado = Signal(object, str, str, object)
    gasto = Signal(str, float)
    fallo = Signal(str)

    def __init__(self, rutas, api_key):
        super().__init__()
        self.rutas = rutas
        self.fallos = []

    def start(self):
        pass

    def isRunning(self):
        return False


def _apuntar_vaciados(monkeypatch):
    """Cada vaciado de la caché de MuPDF, y si se hizo con el cerrojo."""
    vaciados = []
    monkeypatch.setattr(fitz.TOOLS, "store_shrink", lambda porcentaje: vaciados.append(
        (porcentaje, pdf.CERROJO.locked())))
    return vaciados


# ------------------------------------------------- la caché de MuPDF (P1)
def test_cada_hoja_que_se_lee_vacia_la_cache_de_mupdf(tmp_path, monkeypatch):
    ruta = _pdf(tmp_path / "taco.pdf", 3)
    vaciados = _apuntar_vaciados(monkeypatch)
    imagenes = pdf.paginas_pdf_a_jpg(ruta)
    assert len(imagenes) == 3 and all(i.startswith(b"\xff\xd8") for i in imagenes)
    # Una vez por hoja, entera y siempre con el cerrojo: MuPDF no admite dos
    # llamadas a la vez y el visor puede estar dibujando en otro hilo.
    assert vaciados == [(100, True)] * 3


def test_una_hoja_suelta_y_la_del_visor_tampoco_se_quedan_en_la_cache(
        tmp_path, monkeypatch):
    ruta = _pdf(tmp_path / "taco.pdf", 2)
    vaciados = _apuntar_vaciados(monkeypatch)
    assert pdf.pagina_a_jpg(ruta, 2).startswith(b"\xff\xd8")
    hoja = imagen_visor.hoja(ruta, 1, 600, 840)
    assert hoja is not None and hoja.ancho == 600
    assert vaciados == [(100, True), (100, True)]


def test_vaciar_la_cache_desde_fuera_no_espera_a_la_lectura(monkeypatch):
    vaciados = _apuntar_vaciados(monkeypatch)
    with pdf.CERROJO:
        # La lectura está dibujando: no se para la ventana esperándola (ella
        # vacía la caché al acabar su hoja).
        assert pdf.vaciar_cache() is False
    assert vaciados == []
    assert pdf.vaciar_cache() is True
    assert vaciados == [(100, True)]
    assert not pdf.CERROJO.locked()


# ------------------------------------------- el original en las muestras (P2)
def test_la_huella_y_la_copia_del_original_no_lo_cargan_en_memoria(tmp_path):
    import hashlib
    import tracemalloc
    from facturas_excel import muestras_revision

    grande = tmp_path / "taco grande.pdf"
    contenido = os.urandom(1 << 20) * 24          # 24 MB, como un PDF escaneado
    grande.write_bytes(contenido)
    tracemalloc.start()
    try:
        identificador = muestras_revision.guardar_original(str(grande))
        _actual, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # La misma huella y la misma copia que antes, sin leerlo entero de golpe.
    assert identificador == hashlib.sha256(contenido).hexdigest()
    copia = muestras_revision.carpeta() / "originales" / (identificador + ".pdf")
    assert copia.read_bytes() == contenido
    assert pico < 8 * (1 << 20), f"pico de {pico / (1 << 20):.0f} MB"


def test_soltar_un_pdf_no_espera_a_copiar_su_original(tmp_path, monkeypatch):
    import threading
    import time
    from facturas_excel import muestras_revision, ventana_lectura
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.clientes import marcar_cliente
    from facturas_excel.procesar import construir

    puede_acabar = threading.Event()
    hilos = []

    def copia_lenta(ruta, raiz=None):
        hilos.append(threading.current_thread().name)
        puede_acabar.wait(3)
        return "huella-del-original"
    monkeypatch.setattr(muestras_revision, "guardar_original", copia_lenta)
    monkeypatch.setattr(ventana_lectura, "Worker", WorkerFalso)
    monkeypatch.setattr(ventana_lectura, "leer_api_key", lambda: "clave-de-prueba")
    marcar_cliente("12345678Z", "CLIENTE PRUEBA")
    ruta = tmp_path / "taco.jpg"
    ruta.write_bytes(b"no se llega a leer")
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)

    inicio = time.monotonic()
    v.procesar_rutas([str(ruta)])
    # La ventana sigue a lo suyo mientras se copia (un PDF de 200 MB tardaba
    # 1,6 s y subía la memoria 200 MB).
    assert time.monotonic() - inicio < 1.5
    assert v._elemento_cola_actual is not None
    puede_acabar.set()

    datos = dict(num_factura="F-1", fecha="01/09/2026", emisor_nombre="PROVEEDOR PRUEBA",
                 emisor_nif="B12345674", receptor_nombre="CLIENTE PRUEBA",
                 receptor_nif="12345678Z", total=121,
                 lineas_iva=[dict(base=100, tipo_iva=21, cuota_iva=21)])
    pr = construir(datos, "12345678Z", "CLIENTE PRUEBA", str(ruta), 1)
    v._on_terminado([(b"hoja", pr)], "CLIENTE PRUEBA", "12345678Z",
                    [(b"hoja", str(ruta), 1, datos)])
    # Al acabar el bloque la huella ya está y se apunta en la factura.
    assert hilos and hilos[0] != threading.current_thread().name
    assert v.filas[0]["factura"].original_id == "huella-del-original"


def test_si_la_copia_aparte_del_original_falla_se_avisa_y_se_sigue(
        tmp_path, monkeypatch):
    from facturas_excel import muestras_revision, ventana_lectura
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.clientes import marcar_cliente
    from facturas_excel.procesar import construir

    def disco_lleno(ruta, raiz=None):
        raise OSError("disco lleno")
    monkeypatch.setattr(muestras_revision, "guardar_original", disco_lleno)
    monkeypatch.setattr(ventana_lectura, "Worker", WorkerFalso)
    monkeypatch.setattr(ventana_lectura, "leer_api_key", lambda: "clave-de-prueba")
    avisos = []
    monkeypatch.setattr(VentanaPrincipal, "_avisar_error_muestras",
                        lambda self, error: avisos.append(str(error)))
    marcar_cliente("12345678Z", "CLIENTE PRUEBA")
    ruta = tmp_path / "taco.jpg"
    ruta.write_bytes(b"no se llega a leer")
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v.procesar_rutas([str(ruta)])
    datos = dict(num_factura="F-1", fecha="01/09/2026", emisor_nombre="PROVEEDOR PRUEBA",
                 emisor_nif="B12345674", total=121,
                 lineas_iva=[dict(base=100, tipo_iva=21, cuota_iva=21)])
    pr = construir(datos, "12345678Z", "CLIENTE PRUEBA", str(ruta), 1)
    v._on_terminado([(b"hoja", pr)], "CLIENTE PRUEBA", "12345678Z",
                    [(b"hoja", str(ruta), 1, datos)])
    assert "disco lleno" in avisos
    assert v.tabla.rowCount() == 1
