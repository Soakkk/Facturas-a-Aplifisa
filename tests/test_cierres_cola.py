"""La cola de lectura con cosas a la vez: avisos, cerrar, vaciar, exportar.

Las pruebas de estrés encontraron que el programa se cerraba de golpe si
acababa un escaneo (o fallaba un bloque) con un aviso abierto, y al cerrar o
actualizar a mitad de lectura: se perdía lo ya pagado y se seguía pagando a
Gemini con la ventana cerrada. Y otras cosas que no cerraban el programa
pero perdían facturas: unir hojas con la tabla ordenada, exportar con la
cola a medias, un guardado a medias, «Vaciar todo» mientras se lee…

Las de cierres de golpe corren en un proceso aparte (guion_cierres_cola.py)
y exigen que acabe con código 0: un QThread vivo que Python suelta aborta
el proceso entero. Solo datos inventados (NIF de prueba).
"""

import json
import os
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from facturas_excel import errores, sesion, ventana_lectura
from facturas_excel.app import VentanaPrincipal
from facturas_excel.procesar import preparar_lote
from facturas_excel.rutas import dir_datos

_app = QApplication.instance() or QApplication([])

GUION = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guion_cierres_cola.py")
CLIENTE = ("CLIENTE PRUEBA", "12345678Z")


# ------------------------------------------------------- en otro proceso
def _escenario(tmp_path, nombre, latencia=0.3, tope=150):
    """Corre un escenario del guion; devuelve (código, resultado, carpeta)."""
    carpeta = tmp_path / nombre
    entorno = dict(os.environ, LATENCIA=str(latencia), QT_QPA_PLATFORM="offscreen")
    proceso = subprocess.run([sys.executable, GUION, nombre, str(carpeta)],
                             env=entorno, capture_output=True, text=True,
                             timeout=tope)
    try:
        with open(carpeta / "resultado.json", encoding="utf-8") as fh:
            resultado = json.load(fh)
    except (OSError, ValueError):
        resultado = {}
    detalle = (proceso.stderr or "")[-1500:]
    return proceso.returncode, resultado, carpeta, detalle


def _llamadas_tras_cerrar(carpeta):
    """Peticiones a Gemini que empezaron con la ventana ya cerrándose."""
    try:
        with open(carpeta / "llamadas.txt", encoding="utf-8") as fh:
            return [linea for linea in fh if linea.split()[1] == "1"]
    except OSError:
        return []


def _sesion_en_disco(carpeta):
    """Lo que quedó guardado del lote: (bloques, cola) o None."""
    import gzip
    import pickle
    ruta = carpeta / "appdata" / "FacturasAplifisa" / sesion.FICHERO
    if not ruta.exists():
        return None
    with gzip.open(ruta, "rb") as fh:
        datos = pickle.load(fh)["datos"]
    return datos["bloques"], datos.get("cola") or []


def test_un_pdf_que_llega_con_una_pregunta_abierta_no_tumba_el_programa(tmp_path):
    # La pregunta (aquí, de un conflicto de NIF) se abre al poner el primer
    # bloque en el lote; mientras, llega un escaneo. Antes arrancaba una
    # lectura dentro de la pregunta y otra al cerrarla: dos a la vez, y al
    # soltar la primera, viva, el programa se cerraba de golpe.
    codigo, resultado, _carpeta, detalle = _escenario(
        tmp_path, "pregunta_y_escaneo", latencia=2.0)
    assert codigo == 0, detalle
    assert resultado["max_vivos"] == 1
    assert len(resultado["facturas"]) == 35          # 30 del taco y 5 del escaneo


def test_un_bloque_que_falla_con_otro_llegando_no_tumba_el_programa(tmp_path):
    codigo, resultado, _carpeta, detalle = _escenario(
        tmp_path, "fallo_y_otro", latencia=2.0)
    assert codigo == 0, detalle
    assert resultado["max_vivos"] == 1
    assert len(resultado["facturas"]) == 30
    # El fallo se dice en la banda, sin una ventana que pare la cola.
    assert not any(d.startswith("critical") for d in resultado["dialogos"])


@pytest.mark.parametrize("latencia", [2.0, 8.0], ids=["llega_a_tiempo", "no_llega"])
def test_cerrar_a_mitad_de_lectura_guarda_la_cola_y_no_sigue_pagando(tmp_path, latencia):
    # Con 8 s la petición en vuelo no acaba mientras se espera al cerrar:
    # se guarda igual y se sale sin esperarla (antes, el programa abortaba).
    codigo, resultado, carpeta, detalle = _escenario(tmp_path, "cerrar", latencia)
    assert codigo == 0, detalle
    assert not _llamadas_tras_cerrar(carpeta)
    assert resultado["cerrar_s"] < 8
    guardado = _sesion_en_disco(carpeta)
    assert guardado is not None, "no se guardó nada al cerrar"
    _bloques, cola = guardado
    # El bloque a medias y el siguiente quedan para la próxima vez, con sus
    # partes temporales.
    assert len(cola) == 2
    assert all(os.path.exists(ruta) for e in cola for ruta in e["rutas"])


def test_actualizar_a_mitad_de_lectura_tampoco_tumba_el_programa(tmp_path):
    # El actualizador sale con QApplication.quit(), que también pasa por cerrar.
    codigo, _resultado, carpeta, detalle = _escenario(
        tmp_path, "salir_al_actualizar", latencia=2.0)
    assert codigo == 0, detalle
    assert not _llamadas_tras_cerrar(carpeta)
    assert len(_sesion_en_disco(carpeta)[1]) == 2


def test_al_salir_sin_esperar_la_lectura_se_apunta_lo_ya_gastado(tmp_path):
    # Una hoja se queda colgada en Gemini y se sale sin esperarla: lo gastado
    # se apuntaba al acabar el bloque, al que así no se llega, y las 24 hojas
    # ya leídas (y pagadas) del bloque no contaban en el gasto del mes.
    codigo, _resultado, carpeta, detalle = _escenario(
        tmp_path, "cerrar_con_una_hoja_lenta")
    assert codigo == 0, detalle
    with open(carpeta / "llamadas.txt", encoding="utf-8") as fh:
        pedidas = len(fh.readlines())
    with open(carpeta / "gasto.txt", encoding="utf-8") as fh:
        apuntadas = len(fh.readlines())
    assert pedidas == 50
    assert apuntadas == pedidas - 1               # todas menos la colgada
    assert len(_sesion_en_disco(carpeta)[1]) == 2  # y su bloque, en la cola


def test_cerrar_mientras_se_dibujan_las_hojas_no_pide_nada_a_gemini(tmp_path):
    codigo, resultado, carpeta, detalle = _escenario(tmp_path, "cerrar_dibujando")
    assert codigo == 0, detalle
    # Lo ya leído antes de cerrar se queda; tras cerrar no se pide nada.
    assert not _llamadas_tras_cerrar(carpeta)
    # Se deja de dibujar en la hoja siguiente: no se espera al bloque entero.
    assert resultado["cerrar_s"] < 3
    assert len(_sesion_en_disco(carpeta)[1]) == 2


def test_vaciar_todo_mientras_se_lee_no_deja_un_bloque_fantasma(tmp_path):
    codigo, resultado, carpeta, detalle = _escenario(tmp_path, "vaciar")
    assert codigo == 0, detalle
    assert resultado["filas"] == 0 and resultado["bloques"] == 0
    assert resultado["max_vivos"] == 1
    # Ni la barra sigue con lo que contaba la lectura cancelada («Cola 1/0…»).
    assert "Cola" not in resultado["estado"], resultado["estado"]
    # Ni las partes de lo que se estaba leyendo ni las de lo que esperaba.
    partes = carpeta / "appdata" / "FacturasAplifisa" / "cola_pdf"
    assert not [f for _r, _d, fs in os.walk(partes) for f in fs]


# ------------------------------------------------------- en esta ventana
class WorkerFalso(QObject):
    """Una lectura que no lee ni arranca hilo: la prueba dice cuándo acaba
    y qué entrega (por su señal, como la de verdad)."""
    progreso = Signal(int, int)
    terminado = Signal(object, str, str, object)
    gasto = Signal(str, float)
    fallo = Signal(str)
    creados = []

    def __init__(self, rutas, api_key):
        super().__init__()
        self.rutas = list(rutas)
        self.fallos = []
        self.corriendo = False
        self.cancelada = False
        WorkerFalso.creados.append(self)

    def start(self):
        self.corriendo = True

    def isRunning(self):
        return self.corriendo

    def wait(self, _milisegundos=0):
        return not self.corriendo

    def cancelar(self):
        self.cancelada = True

    def entregar(self, hojas):
        self.corriendo = False
        self.terminado.emit(preparar_lote(hojas, *CLIENTE), *CLIENTE, hojas)


def _hoja(origen, pagina, numero, nombre="PROVEEDOR PRUEBA SL", nif="B12345674"):
    """Lo que lee Gemini de una hoja: una factura inventada a CLIENTE."""
    base = 100.0 + pagina
    return (b"hoja %d" % pagina, str(origen), pagina, {
        "emisor_nombre": nombre, "emisor_nif": nif,
        "receptor_nombre": CLIENTE[0], "receptor_nif": CLIENTE[1],
        "num_factura": numero, "fecha": "15/03/2026",
        "estado_pagina_factura": "unica",
        "lineas_iva": [{"base": base, "tipo_iva": 21.0, "cuota_iva": round(base * .21, 2)}],
        "total": round(base * 1.21, 2)})


def _pdf(ruta, paginas):
    documento = fitz.open()
    for numero in range(1, paginas + 1):
        documento.new_page(width=300, height=420).insert_text(
            (30, 60), f"FACTURA DE PRUEBA {numero}", fontsize=9)
    documento.save(str(ruta))
    documento.close()
    return str(ruta)


def _jpg(ruta):
    ruta.write_bytes(b"no se llega a leer: la lectura es falsa")
    return str(ruta)


@pytest.fixture(autouse=True)
def cliente_conocido():
    """El cliente del lote ya es conocido: no se pregunta quién es."""
    from facturas_excel.clientes import marcar_cliente
    marcar_cliente(*reversed(CLIENTE))


@pytest.fixture
def ventana(monkeypatch):
    WorkerFalso.creados = []
    monkeypatch.setattr(ventana_lectura, "Worker", WorkerFalso)
    monkeypatch.setattr(ventana_lectura, "leer_api_key", lambda: "clave-de-prueba")
    return VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)


def _numeros(v):
    return {fila.factura.num_factura for fila in v.filas}


def _bloque_de(w, desde=1, hasta=25):
    """Lo que lee la lectura `w` de su parte (páginas locales)."""
    return [_hoja(w.rutas[0], n, f"F-{n:02d}-{os.path.basename(w.rutas[0])[:20]}")
            for n in range(desde, hasta + 1)]


# n.º 7 ----------------------------------------------------------------
def test_exportar_con_bloques_por_leer_pregunta_antes(ventana, tmp_path, monkeypatch):
    from PySide6.QtGui import QShortcut
    from facturas_excel.ventana_aplifisa import DialogoOrden
    ventana.procesar_rutas([_pdf(tmp_path / "taco.pdf", 30)])
    primera = WorkerFalso.creados[-1]
    primera.entregar(_bloque_de(primera))
    assert ventana._elemento_cola_actual is not None      # el 2.º, leyéndose
    # Exportar se queda apagado mientras quedan bloques por leer…
    assert not ventana.btn_gastos.isEnabled()
    ventana._marcar_revisada(list(range(len(ventana.filas))))
    preguntas, ordenes = [], []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(
        lambda *a, **k: preguntas.append(a[1]) or QMessageBox.No))
    monkeypatch.setattr(DialogoOrden, "exec", lambda self: ordenes.append(1) or 0)
    # …y Ctrl+G, que no mira el botón, pregunta antes.
    atajo = next(a for a in ventana.findChildren(QShortcut)
                 if a.key().toString() == "Ctrl+G")
    atajo.activated.emit()
    assert preguntas == ["Faltan bloques por leer"]
    assert not ordenes                       # no se ha llegado a exportar


def test_el_taco_apartado_cambia_tambien_en_lo_que_queda_por_leer(ventana, tmp_path):
    ventana.procesar_rutas([_pdf(tmp_path / "taco.pdf", 60)])
    primera = WorkerFalso.creados[-1]
    primera.entregar(_bloque_de(primera))
    viejo = ventana._elemento_cola_actual["original"]
    assert ventana._cola[0]["original"] == viejo
    nuevo = str(tmp_path / "Tacos escaneados" / "taco.pdf")

    ventana._cambiar_origen(viejo, nuevo)     # como al apartar el taco al exportar

    assert ventana._elemento_cola_actual["original"] == nuevo
    assert ventana._cola[0]["original"] == nuevo
    segunda = WorkerFalso.creados[-1]
    segunda.entregar(_bloque_de(segunda))
    assert {f.factura.origen_imagen for f in ventana.filas[25:]} == {nuevo}


# n.º 6 ----------------------------------------------------------------
def _lote_ordenado(ventana):
    """Seis facturas de proveedores que, por nombre, van al revés."""
    from facturas_excel.tabla_facturas import C_NOMBRE
    nombres = ["ZETA", "YPSILON", "XI", "OMEGA", "LAMBDA", "KAPPA"]
    hojas = [_hoja("taco.pdf", n, f"F-{n}", f"{nombre} PRUEBA SL", None)
             for n, nombre in enumerate(nombres, 1)]
    ventana._on_terminado(preparar_lote(hojas, *CLIENTE), *CLIENTE, hojas)
    ventana._ordenar_tabla_por(C_NOMBRE)
    assert [f.factura.num_factura for f in ventana.filas][:2] == ["F-6", "F-5"]


def test_unir_hojas_con_la_tabla_ordenada_y_un_bloque_que_llega(ventana, monkeypatch):
    _lote_ordenado(ventana)
    otro = [_hoja("otro.pdf", n, f"F-{6 + n}") for n in (1, 2)]

    def pregunta(*_a, **_k):
        # Mientras se pregunta llega otro bloque y la tabla se rehace (en el
        # orden de los bloques, no en el de la tabla).
        ventana._on_terminado(preparar_lote(otro, *CLIENTE), *CLIENTE, otro)
        return QMessageBox.Yes
    monkeypatch.setattr(ventana, "_filas_seleccionadas", lambda: [0, 1])
    monkeypatch.setattr(QMessageBox, "question", staticmethod(pregunta))
    monkeypatch.setattr(sesion, "guardar", lambda datos: None)

    ventana._unir_hojas_seleccionadas()

    # Se unen las dos elegidas (F-6 y F-5, en una) y las demás siguen ahí.
    assert _numeros(ventana) == {"F-1", "F-2", "F-3", "F-4", "F-5", "F-7", "F-8"}


def test_con_la_pregunta_de_unir_abierta_el_bloque_que_llega_espera(
        ventana, tmp_path, monkeypatch):
    _lote_ordenado(ventana)
    ventana.procesar_rutas([_jpg(tmp_path / "otro.jpg")])
    lectura = WorkerFalso.creados[-1]
    llegado = []

    def pregunta(*_a, **_k):
        lectura.entregar([_hoja(lectura.rutas[0], 1, "F-9")])
        llegado.append(len(ventana._bloques))
        return QMessageBox.Yes
    monkeypatch.setattr(ventana, "_filas_seleccionadas", lambda: [0, 1])
    monkeypatch.setattr(QMessageBox, "question", staticmethod(pregunta))
    monkeypatch.setattr(sesion, "guardar", lambda datos: None)

    ventana._unir_hojas_seleccionadas()

    assert llegado == [1]               # no entró con la pregunta abierta…
    assert _numeros(ventana) == {"F-1", "F-2", "F-3", "F-4", "F-5"}
    _esperar(lambda: "F-9" in _numeros(ventana))    # …sino al cerrarla


def _esperar(condicion, tope=5.0):
    import time
    fin = time.monotonic() + tope
    while time.monotonic() < fin and not condicion():
        _app.processEvents()
        time.sleep(0.02)
    assert condicion()


# n.º 8 ----------------------------------------------------------------
def _sesion_guardada():
    import gzip
    import pickle
    sesion.esperar()
    if not os.path.exists(sesion._ruta()):
        return None
    with gzip.open(sesion._ruta(), "rb") as fh:
        datos = pickle.load(fh)["datos"]
    en_filas = {f["factura"].num_factura for f in datos["filas"]}
    en_bloques = {f.num_factura for b in datos["bloques"]
                  for _, pr in b["procesadas"] for f in pr.facturas}
    return en_bloques - en_filas


def test_el_guardado_automatico_no_salta_con_un_bloque_a_medio_poner(
        ventana, tmp_path, monkeypatch):
    original = VentanaPrincipal._resolver_conflictos_nif
    dentro = []

    def pregunta(self):
        # Como si saltara el guardado automático con una pregunta abierta.
        dentro.append(self._timer_sesion.isActive())
        self._guardar_sesion_automatica()
        dentro.append(_sesion_guardada())
        return original(self)
    monkeypatch.setattr(VentanaPrincipal, "_resolver_conflictos_nif", pregunta)
    ventana.procesar_rutas([_jpg(tmp_path / "a.jpg"), _jpg(tmp_path / "b.jpg")])
    WorkerFalso.creados[0].entregar([_hoja(tmp_path / "a.jpg", 1, "F-1")])
    WorkerFalso.creados[1].entregar([_hoja(tmp_path / "b.jpg", 1, "F-2")])

    # Mientras se ponía el 2.º bloque: el temporizador parado, y si había
    # algo guardado, era coherente (ninguna factura fuera de las filas).
    assert dentro[2] is False and not dentro[3]
    assert ventana._timer_sesion.isActive()           # se arma al acabar


def test_al_abrir_un_lote_guardado_a_medias_se_recuperan_sus_facturas():
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    for origen, numeros in (("uno.pdf", ("F-1", "F-2")), ("dos.pdf", ("F-3",))):
        hojas = [_hoja(origen, n, numero) for n, numero in enumerate(numeros, 1)]
        v._rutas_actuales = [origen]
        v._on_terminado(preparar_lote(hojas, *CLIENTE), *CLIENTE, hojas)
    datos = v._datos_sesion()
    # Como lo dejaba un guardado con el bloque «dos» puesto y la tabla sin rehacer.
    datos["filas"] = [f for f in datos["filas"] if f["factura"].num_factura != "F-3"]
    sesion.guardar(datos)

    abierta = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)

    assert _numeros(abierta) == {"F-1", "F-2", "F-3"}
    assert any("no estaban en la tabla" in t for t in abierta.banda.historial)


# n.º 9 ----------------------------------------------------------------
def _partes_en_disco():
    raiz = os.path.join(dir_datos(), "cola_pdf")
    return sorted(os.path.join(r, f) for r, _d, fs in os.walk(raiz) for f in fs)


def test_vaciar_y_volver_a_cargar_el_mismo_pdf_no_borra_sus_partes(
        ventana, tmp_path, monkeypatch):
    # El mismo PDF tiene siempre las mismas partes (misma carpeta y nombre).
    # Al descartar la lectura cancelada se borraba su parte, que ya era la
    # del bloque 2 del PDF vuelto a cargar: «no such file» y 25 facturas
    # sin leer.
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    taco = _pdf(tmp_path / "taco.pdf", 60)
    ventana.procesar_rutas([taco])
    primera = WorkerFalso.creados[-1]
    primera.entregar(_bloque_de(primera))
    cancelada = WorkerFalso.creados[-1]           # el 2.º bloque, leyéndose
    ventana._vaciar_todo()
    ventana.procesar_rutas([taco])                # enseguida, el mismo PDF
    partes = [e["rutas"][0] for e in ventana._cola]
    assert len(partes) == 3 and cancelada.rutas[0] in partes

    cancelada.entregar(_bloque_de(cancelada))     # se descarta

    assert all(os.path.exists(p) for p in partes)
    for _ in partes:
        lectura = WorkerFalso.creados[-1]
        assert os.path.exists(lectura.rutas[0])
        lectura.entregar(_bloque_de(lectura))
    assert len(ventana._bloques) == 3
    assert not _partes_en_disco()                 # y no quedan huérfanas


def test_vaciar_con_el_mismo_pdf_cargado_dos_veces_no_deja_partes(
        ventana, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    taco = _pdf(tmp_path / "taco.pdf", 60)
    ventana.procesar_rutas([taco])
    ventana.procesar_rutas([taco])                # dos veces, por despiste
    leyendo = WorkerFalso.creados[-1]

    ventana._vaciar_todo()
    leyendo.entregar(_bloque_de(leyendo))         # se descarta

    assert not ventana._bloques and not ventana._cola
    assert not _partes_en_disco()


def test_lo_vaciado_no_se_guarda_como_cola_al_cerrar_enseguida(
        ventana, tmp_path, monkeypatch):
    # «Vaciar todo» con el 2.º bloque leyéndose y cerrar enseguida: si la
    # lectura cancelada no llegaba en la espera del cierre, volvía a la cola
    # y se guardaba (y el guardado automático, entre tanto, también), y al
    # abrir se ofrecía «Seguir leyendo» lo que se había vaciado. Y a esa
    # lectura, que ya no cuenta, tampoco se la espera al cerrar.
    import time
    monkeypatch.setattr(ventana_lectura, "ESPERA_LECTURA_AL_CERRAR_S", 3, raising=False)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    ventana.procesar_rutas([_pdf(tmp_path / "taco.pdf", 60)])
    primera = WorkerFalso.creados[-1]
    primera.entregar(_bloque_de(primera))
    cancelada = WorkerFalso.creados[-1]          # el 2.º, que no llegará

    ventana._vaciar_todo()
    assert cancelada.cancelada and ventana._bloques_por_leer() == 0
    ventana._guardar_sesion_automatica()
    assert sesion.cargar() is None
    inicio = time.monotonic()
    ventana.closeEvent(QCloseEvent())

    assert time.monotonic() - inicio < 1.5
    assert sesion.cargar() is None
    assert not _partes_en_disco()


# n.º 10 ---------------------------------------------------------------
def _ventana_con_un_bloque():
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    hojas = [_hoja("uno.pdf", 1, "F-1")]
    v._rutas_actuales = ["uno.pdf"]
    v._on_terminado(preparar_lote(hojas, *CLIENTE), *CLIENTE, hojas)
    return v


def test_si_falla_guardar_la_distribucion_el_lote_se_guarda_igual(monkeypatch):
    v = _ventana_con_un_bloque()
    monkeypatch.setattr(v, "_guardar_divisores", lambda: 1 / 0)

    v.closeEvent(QCloseEvent())

    assert os.path.exists(sesion._ruta())
    with open(os.path.join(dir_datos(), errores.FICHERO), encoding="utf-8") as fh:
        assert "ZeroDivisionError" in fh.read()


def test_si_no_se_puede_guardar_el_lote_se_pregunta_antes_de_cerrar(monkeypatch):
    v = _ventana_con_un_bloque()

    def disco_lleno(datos):
        raise OSError("disco lleno")
    monkeypatch.setattr(sesion, "guardar", disco_lleno)
    respuestas, preguntas = [QMessageBox.No, QMessageBox.Yes], []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(
        lambda *a, **k: preguntas.append(a[2]) or respuestas.pop(0)))

    sigue = QCloseEvent()
    v.closeEvent(sigue)
    assert not sigue.isAccepted()             # «No»: la ventana no se cierra
    assert "disco lleno" in preguntas[0]
    cierra = QCloseEvent()
    v.closeEvent(cierra)
    assert cierra.isAccepted()


# n.º 11 ---------------------------------------------------------------
def test_la_cola_se_guarda_al_cerrar_y_al_abrir_se_ofrece_seguir(
        ventana, tmp_path, monkeypatch):
    import time
    # La lectura falsa no entrega nada al cerrar: no se la espera mucho.
    monkeypatch.setattr(ventana_lectura, "ESPERA_LECTURA_AL_CERRAR_S", 0.1, raising=False)
    ventana.procesar_rutas([_pdf(tmp_path / "taco.pdf", 60)])
    primera = WorkerFalso.creados[-1]
    primera.entregar(_bloque_de(primera))
    partes = [ventana._elemento_cola_actual["rutas"][0], ventana._cola[0]["rutas"][0]]

    ventana.closeEvent(QCloseEvent())

    # Las partes que faltan se quedan, y la cola va en la sesión.
    assert all(os.path.exists(p) for p in partes)
    guardada = sesion.cargar()["cola"]
    assert [e["rutas"][0] for e in guardada] == partes
    # Al abrir otro día no se borran (como las de una cola sin guardar)…
    hace_dias = time.time() - 30 * 3600
    for parte in partes:
        os.utime(parte, (hace_dias, hace_dias))
    abierta = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    assert all(os.path.exists(p) for p in partes)
    # …y se ofrece seguir leyendo, en la banda.
    assert abierta.banda.btn_deshacer.text() == "Seguir leyendo"
    assert "2 bloque(s), 35 hoja(s)" in abierta.banda.historial[-1]
    # Mientras, «Organizar carpetas» no mueve sus PDF (como con un lote abierto).
    from types import SimpleNamespace
    from facturas_excel.dialogo_escaneos import DialogoEscaneos
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(
        lambda *a, **k: avisos.append(a[1])))
    assert not DialogoEscaneos._puede_organizar(SimpleNamespace(parent=lambda: abierta))
    assert avisos == ["Organizar carpetas"]
    abierta.banda.btn_deshacer.click()
    assert WorkerFalso.creados[-1].rutas == [partes[0]]
    assert [e["rutas"][0] for e in abierta._cola] == [partes[1]]


def test_vaciar_todo_tira_tambien_la_cola_guardada(ventana, tmp_path, monkeypatch):
    monkeypatch.setattr(ventana_lectura, "ESPERA_LECTURA_AL_CERRAR_S", 0.1, raising=False)
    ventana.procesar_rutas([_pdf(tmp_path / "taco.pdf", 60)])
    primera = WorkerFalso.creados[-1]
    primera.entregar(_bloque_de(primera))
    partes = [ventana._elemento_cola_actual["rutas"][0], ventana._cola[0]["rutas"][0]]
    ventana.closeEvent(QCloseEvent())
    abierta = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    assert all(os.path.exists(p) for p in partes) and abierta._cola_guardada
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    abierta._vaciar_todo()

    assert not any(os.path.exists(p) for p in partes)
    assert sesion.cargar() is None


def _abrir_con_cola_guardada(ventana, tmp_path, monkeypatch):
    """Cierra con el 2.º bloque leyéndose y abre otra vez: 1 bloque en el
    lote y 2 por leer de la última vez."""
    monkeypatch.setattr(ventana_lectura, "ESPERA_LECTURA_AL_CERRAR_S", 0.1, raising=False)
    ventana.procesar_rutas([_pdf(tmp_path / "taco.pdf", 60)])
    primera = WorkerFalso.creados[-1]
    primera.entregar(_bloque_de(primera))
    ventana.closeEvent(QCloseEvent())
    return VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)


def test_exportar_con_lo_que_quedo_por_leer_la_ultima_vez_pregunta(
        ventana, tmp_path, monkeypatch):
    # Lo que quedó por leer es del mismo lote: exportar sin preguntar sacaba
    # el Excel sin esos bloques (como con la cola a medias). Y si el aviso de
    # «Seguir leyendo» ya lo había tapado otro, no había forma de seguir.
    from facturas_excel.ventana_aplifisa import DialogoOrden
    abierta = _abrir_con_cola_guardada(ventana, tmp_path, monkeypatch)
    assert len(abierta._cola_guardada) == 2
    abierta._marcar_revisada(list(range(len(abierta.filas))))   # otro aviso
    assert abierta.banda.btn_deshacer.text() != "Seguir leyendo" \
        or abierta.banda.btn_deshacer.isHidden()
    preguntas, ordenes = [], []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(
        lambda *a, **k: preguntas.append(a[1]) or QMessageBox.No))
    monkeypatch.setattr(DialogoOrden, "exec", lambda self: ordenes.append(1) or 0)

    abierta._exportar_todo()

    assert preguntas == ["Faltan bloques por leer"]
    assert not ordenes                        # no se ha llegado a exportar
    # Al decir que no, vuelve a ofrecerse seguir leyendo.
    assert not abierta.banda.btn_deshacer.isHidden()
    assert abierta.banda.btn_deshacer.text() == "Seguir leyendo"


def test_si_lo_que_quedo_por_leer_ya_no_esta_se_dice_al_abrir(
        ventana, tmp_path, monkeypatch):
    # Las hojas de la cola guardada (sus partes, o el PDF o la imagen suelta)
    # ya no están: las borró otra versión del programa al arrancar, o se
    # limpió la carpeta. Antes se olvidaban sin decir nada.
    import shutil
    abierta = _abrir_con_cola_guardada(ventana, tmp_path, monkeypatch)
    abierta.close()
    shutil.rmtree(os.path.join(dir_datos(), "cola_pdf"))

    otra = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)

    assert not otra._cola_guardada
    aviso = otra.banda.historial[-1]
    assert "2 bloque(s) de taco.pdf" in aviso and "ya no están" in aviso
    assert otra.banda.btn_deshacer.isHidden()        # no hay nada que seguir


def test_si_falta_una_parte_se_ofrece_el_resto_y_se_dice_la_que_falta(
        ventana, tmp_path, monkeypatch):
    abierta = _abrir_con_cola_guardada(ventana, tmp_path, monkeypatch)
    ultima = abierta._cola_guardada[-1]["rutas"][0]
    abierta.close()
    os.remove(ultima)

    otra = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)

    assert len(otra._cola_guardada) == 1
    aviso = otra.banda.historial[-1]
    assert "1 bloque(s), 25 hoja(s)" in aviso
    assert "Además, 1 bloque(s) de taco.pdf" in aviso and "ya no están" in aviso
    assert otra.banda.btn_deshacer.text() == "Seguir leyendo"
    assert not otra.banda.btn_deshacer.isHidden()


def test_el_aviso_de_facturas_recuperadas_no_lo_tapa_el_de_seguir_leyendo(
        ventana, tmp_path, monkeypatch):
    # Cerrar con un bloque a medio poner (una pregunta abierta) guarda sus
    # facturas fuera de las filas y, casi siempre, una cola: al abrir, el
    # aviso de «Seguir leyendo» tapaba enseguida al de las recuperadas.
    abierta = _abrir_con_cola_guardada(ventana, tmp_path, monkeypatch)
    datos = abierta._datos_sesion()
    datos["filas"] = datos["filas"][:20]      # como guardado a medio poner
    sesion.guardar(datos)

    otra = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)

    assert len(otra.filas) == 25
    aviso = otra.banda.historial[-1]
    assert "5 factura(s) leídas que no estaban en la tabla" in aviso
    assert "quedó sin leer parte de taco.pdf" in aviso
    assert otra.banda.btn_deshacer.text() == "Seguir leyendo"


def test_volver_a_cargar_el_pdf_que_quedo_a_medias_no_lo_lee_dos_veces(
        ventana, tmp_path, monkeypatch):
    # Se abre con 2 bloques de taco.pdf por leer y, en vez de «Seguir
    # leyendo», se vuelve a cargar taco.pdf: esta carga tiene las mismas
    # partes y las lee (y borra). Se seguía ofreciendo «Seguir leyendo»
    # esos 2 bloques: leídos dos veces, o con sus partes ya borradas.
    abierta = _abrir_con_cola_guardada(ventana, tmp_path, monkeypatch)
    assert abierta.banda.btn_deshacer.text() == "Seguir leyendo"

    abierta.procesar_rutas([str(tmp_path / "taco.pdf")])

    assert not abierta._cola_guardada
    assert abierta.banda.isHidden() or abierta.banda.btn_deshacer.isHidden()
    for _ in range(3):
        lectura = WorkerFalso.creados[-1]
        lectura.entregar(_bloque_de(lectura))
    assert len(abierta._bloques) == 4 and not abierta._cola
    assert not _partes_en_disco()
    assert sesion.cargar() is None or not abierta._datos_sesion()["cola"]


def test_quien_es_el_cliente_que_no_se_pregunto_al_cerrar_se_pregunta_al_volver(
        ventana, tmp_path, monkeypatch):
    # Un taco de un cliente nuevo: no se sabe cuál de las dos partes es el
    # cliente y se pregunta al poner el bloque. Si el bloque llegaba en la
    # espera del cierre se ponía sin preguntar «para decidirlo al volver»,
    # pero al volver no se preguntaba nunca: el lote se quedaba con el
    # cliente supuesto (en un taco de ventas, el que compra: todo al revés).
    from facturas_excel.dialogo_cliente import DialogoCliente
    preguntas = []
    monkeypatch.setattr(DialogoCliente, "exec", lambda self: preguntas.append(1) or 0)
    nuevo = ("CLIENTE NUEVO SA", "A12345674")
    a = _jpg(tmp_path / "a.jpg")
    ventana.procesar_rutas([a])
    lectura = WorkerFalso.creados[-1]
    hojas = []
    for n in (1, 2):
        hoja = _hoja(a, n, f"F-{n}")
        hoja[3]["receptor_nombre"], hoja[3]["receptor_nif"] = nuevo
        hojas.append(hoja)
    # Llega en la espera del cierre (al cancelar la lectura).
    lectura.cancelar = lambda: lectura.terminado.emit(
        preparar_lote(hojas, *nuevo), *nuevo, hojas)

    ventana.closeEvent(QCloseEvent())
    assert len(ventana._bloques) == 1 and not preguntas    # al cerrar, no

    abierta = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    _esperar(lambda: preguntas)                             # al volver, sí
    assert preguntas == [1]
    abierta.closeEvent(QCloseEvent())
    VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    _app.processEvents()
    assert preguntas == [1]                     # y una vez, no cada vez


def test_al_volver_quien_es_el_cliente_no_tapa_seguir_leyendo(
        ventana, tmp_path, monkeypatch):
    # Al abrir se ofrece seguir leyendo y después se pregunta quién es el
    # cliente: al elegirlo, «Lote rehecho…» (la banda enseña un solo aviso)
    # tapaba «Seguir leyendo», y lo que quedaba por leer solo se podía
    # seguir pasando por Exportar y diciendo que no.
    from PySide6.QtWidgets import QDialog
    from facturas_excel.dialogo_cliente import DialogoCliente
    monkeypatch.setattr(ventana_lectura, "ESPERA_LECTURA_AL_CERRAR_S", 0.1, raising=False)
    nuevo = ("CLIENTE NUEVO SA", "A12345674")
    ventana.procesar_rutas([_pdf(tmp_path / "taco.pdf", 60)])
    lectura = WorkerFalso.creados[-1]
    hojas = _bloque_de(lectura)
    for hoja in hojas:
        hoja[3]["receptor_nombre"], hoja[3]["receptor_nif"] = nuevo
    # El 1.er bloque llega en la espera del cierre (al cancelar la lectura).
    lectura.cancelar = lambda: lectura.terminado.emit(
        preparar_lote(hojas, *nuevo), *nuevo, hojas)
    ventana.closeEvent(QCloseEvent())
    assert ventana._cliente_por_decidir and len(ventana._cola) == 2
    preguntas = []
    monkeypatch.setattr(DialogoCliente, "exec",
                        lambda self: preguntas.append(1) or QDialog.Accepted)

    abierta = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    _esperar(lambda: preguntas)
    _app.processEvents()

    aviso = abierta.banda.lbl.text()
    assert "Lote rehecho con CLIENTE NUEVO SA" in aviso
    assert "quedó sin leer parte de taco.pdf: 2 bloque(s)" in aviso
    assert abierta.banda.btn_deshacer.text() == "Seguir leyendo"
    assert not abierta.banda.btn_deshacer.isHidden()


def test_el_recargo_no_se_pregunta_al_cerrar_sino_al_volver(
        ventana, tmp_path, monkeypatch):
    # El bloque llega en la espera del cierre con facturas con recargo de un
    # cliente (persona física) sin régimen guardado: se abría la pregunta del
    # recargo con la ventana cerrándose y, sin contestarla, «desglose» se
    # quedaba guardado como su régimen para siempre.
    from facturas_excel import app as modulo_app
    from facturas_excel.clientes import TOTAL, regimen_recargo
    monkeypatch.setattr(ventana_lectura, "ESPERA_LECTURA_AL_CERRAR_S", 0.5, raising=False)
    preguntas = []
    monkeypatch.setattr(modulo_app.DialogoRecargo, "exec",
                        lambda self: preguntas.append(1) or 1)
    monkeypatch.setattr(modulo_app.DialogoRecargo, "elegido", lambda self: TOTAL)
    ventana.procesar_rutas([_pdf(tmp_path / "taco.pdf", 30)])
    lectura = WorkerFalso.creados[-1]
    hojas = _bloque_de(lectura)
    for hoja in hojas:
        linea = hoja[3]["lineas_iva"][0]
        linea["pct_requiv"] = 5.2
        linea["cuota_requiv"] = round(linea["base"] * 0.052, 2)
        hoja[3]["total"] = round(linea["base"] + linea["cuota_iva"]
                                 + linea["cuota_requiv"], 2)
    # El bloque llega justo en la espera del cierre.
    lectura.cancelar = lambda: lectura.entregar(hojas)

    ventana.closeEvent(QCloseEvent())
    assert len(ventana._bloques) == 1
    assert not preguntas and regimen_recargo(CLIENTE[1]) == ""   # al cerrar, no

    abierta = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    _esperar(lambda: preguntas)                                   # al volver, sí
    assert regimen_recargo(CLIENTE[1]) == TOTAL and abierta._por_el_total()
    abierta.closeEvent(QCloseEvent())
    VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    _app.processEvents()
    assert preguntas == [1]                       # y una vez, no cada vez


# n.º 30 ---------------------------------------------------------------
def test_el_tipo_declarado_va_con_cada_escaneo(ventana, tmp_path):
    from types import SimpleNamespace
    a, b = _jpg(tmp_path / "a.jpg"), _jpg(tmp_path / "b.jpg")
    ventana.procesar_rutas([a, b])          # cargados: sin tipo declarado
    # Empieza un escaneo de INGRESOS mientras se lee «a» (como _escanear).
    ventana._tipo_escaneo, ventana._escaneo_reciente = "ingresos", True
    WorkerFalso.creados[-1].entregar([_hoja(a, 1, "F-1")])
    WorkerFalso.creados[-1].entregar([_hoja(b, 1, "F-2")])
    escaneo = _pdf(tmp_path / "Escaneo_ingresos.pdf", 1)
    ventana._hilo_escaneo = SimpleNamespace(opciones={"tipo": "ingresos"},
                                            isRunning=lambda: False)
    ventana._on_escaneo_hecho(escaneo)
    WorkerFalso.creados[-1].entregar([_hoja(escaneo, 1, "V-1")])

    assert [b["tipo_declarado"] for b in ventana._bloques] == ["", "", "ingresos"]


# n.º 35 ---------------------------------------------------------------
def test_tras_apartar_un_lote_que_no_se_abre_la_barra_no_dice_sus_lineas(monkeypatch):
    v = _ventana_con_un_bloque()
    v._guardar_sesion()
    original = VentanaPrincipal._pintar_alerta

    def falla(self):
        if self.filas:                          # al restaurar ese lote
            raise RuntimeError("lote de otra versión")
        return original(self)
    monkeypatch.setattr(VentanaPrincipal, "_pintar_alerta", falla)

    abierta = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)

    assert abierta.tabla.rowCount() == 0
    assert "líneas" not in abierta.lbl_estado.text()
    assert sesion.apartada()


# n.º 1 y 2: la red de las lecturas, con la cola -----------------------
def _fallar_una_vez(monkeypatch, nombre, texto):
    """El método `nombre` de la ventana falla la primera vez que se llama."""
    original = getattr(VentanaPrincipal, nombre)
    veces = []

    def falla(self, *a, **k):
        veces.append(1)
        if len(veces) == 1:
            raise RuntimeError(texto)
        return original(self, *a, **k)
    monkeypatch.setattr(VentanaPrincipal, nombre, falla)


def _vivas():
    return [w for w in WorkerFalso.creados if w.corriendo]


def test_un_fallo_al_poner_un_bloque_deja_la_cola_sana(ventana, tmp_path, monkeypatch):
    # El 2.º de tres bloques falla al ponerlo en el lote, antes de pasar al
    # siguiente (pintando el cliente). La red solo lo apunta y lo avisa; la
    # cola sigue como con cualquier bloque: se cuenta una vez, se lee el 3.º
    # (una sola lectura viva) y Exportar no vuelve mientras queden bloques
    # por leer (la red lo encendía: había filas del 1.º).
    a, b, c = (_jpg(tmp_path / f"{n}.jpg") for n in "abc")
    ventana.procesar_rutas([a, b, c])
    WorkerFalso.creados[0].entregar([_hoja(a, 1, "F-1")])
    _fallar_una_vez(monkeypatch, "_pintar_cliente", "fallo inventado al pintar el cliente")

    WorkerFalso.creados[1].entregar([_hoja(b, 1, "F-2")])

    assert _vivas() == [WorkerFalso.creados[2]]           # una sola lectura viva…
    assert ventana._elemento_cola_actual["rutas"] == [c]  # …la del bloque siguiente
    assert ventana._cola_completados == 2                 # contado una sola vez
    assert not ventana.btn_gastos.isEnabled()
    assert any("errores.log" in t for t in ventana.banda.historial)
    with open(os.path.join(dir_datos(), errores.FICHERO), encoding="utf-8") as fh:
        assert "fallo inventado al pintar el cliente" in fh.read()
    # Y el último entra como siempre, sin perder nada.
    WorkerFalso.creados[2].entregar([_hoja(c, 1, "F-3")])
    assert len(WorkerFalso.creados) == 3 and not _vivas()
    assert _numeros(ventana) == {"F-1", "F-2", "F-3"}
    assert ventana._cola_completados == 3 and ventana._elemento_cola_actual is None
    assert ventana.btn_gastos.isEnabled()


def test_un_fallo_al_poner_el_ultimo_bloque_acaba_la_cola(ventana, tmp_path, monkeypatch):
    # Falla ya pasado al bloque siguiente y no queda ninguno: la cola se da
    # por acabada igual (antes se quedaba con la barra puesta, sin decir que
    # había acabado ni señalar lo dudoso).
    a = _jpg(tmp_path / "a.jpg")
    ventana.procesar_rutas([a])
    _fallar_una_vez(monkeypatch, "_revalidar_todo", "fallo inventado al revalidar")

    WorkerFalso.creados[0].entregar([_hoja(a, 1, "F-1")])

    assert len(WorkerFalso.creados) == 1 and not _vivas()
    assert ventana._elemento_cola_actual is None and ventana._cola_completados == 1
    assert ventana.progreso.isHidden()
    assert ventana.btn_gastos.isEnabled()          # ya no queda nada por leer
    assert ventana._timer_sesion.isActive() and ventana._timer_muestras.isActive()
    with open(os.path.join(dir_datos(), errores.FICHERO), encoding="utf-8") as fh:
        assert "fallo inventado al revalidar" in fh.read()


# Un corte de luz con la cola en marcha ---------------------------------
def _en_disco():
    """Lo que hay en la sesión del disco: (bloques, partes de la cola)."""
    import gzip
    import pickle
    sesion.esperar()
    if not os.path.exists(sesion._ruta()):
        return 0, []
    with gzip.open(sesion._ruta(), "rb") as fh:
        datos = pickle.load(fh)["datos"]
    return len(datos["bloques"]), [r for e in datos.get("cola") or []
                                   for r in e["rutas"]]


def test_lo_cargado_y_lo_leido_llegan_al_disco_sin_esperar(
        ventana, tmp_path, monkeypatch):
    # Un corte justo después de cargar un PDF, o de poner uno de sus bloques,
    # perdía la cola (al cargar no se armaba el guardado) o el bloque ya
    # pagado (se guardaba 3 s después, y cada bloque lo volvía a retrasar:
    # con fotos sueltas de 2 s no se guardaba nunca). Y su parte se borraba
    # antes, también con una pregunta abierta, con el disco aún contándola
    # por leer: al volver, «ya no está, vuelva a cargarla».
    ventana._timer_sesion.setInterval(60_000)      # sin el de cada poco
    ventana.procesar_rutas([_pdf(tmp_path / "taco.pdf", 75)])
    assert _en_disco() == (0, [e["rutas"][0] for e in
                               [ventana._elemento_cola_actual, *ventana._cola]])
    con_la_pregunta = []
    original = VentanaPrincipal._resolver_conflictos_nif

    def pregunta(self):
        # Como si se fuera la luz con una pregunta del bloque abierta: lo que
        # el disco dice que queda por leer tiene que estar para leerlo.
        _bloques, partes = _en_disco()
        con_la_pregunta.append(bool(partes) and all(map(os.path.isfile, partes)))
        return original(self)
    monkeypatch.setattr(VentanaPrincipal, "_resolver_conflictos_nif", pregunta)

    for puestos in (1, 2):
        lectura = WorkerFalso.creados[-1]
        lectura.entregar(_bloque_de(lectura))
        bloques, partes = _en_disco()
        assert bloques == puestos and len(partes) == 3 - puestos
        assert all(map(os.path.isfile, partes))
    assert con_la_pregunta == [True, True]
    assert len(_partes_en_disco()) == 1               # las puestas, ya borradas


def _fallar(lectura, mensaje):
    lectura.corriendo = False
    lectura.fallo.emit(mensaje)


def test_los_bloques_que_fallan_se_dicen_todos_y_se_pueden_volver_a_leer(
        ventana, tmp_path, monkeypatch):
    # Con el crédito agotado a mitad de un taco fallan enteros sus dos
    # últimos bloques. Cada fallo tapaba el aviso del anterior (solo se veía
    # el de la parte 4), sus partes se borraban (no se podían volver a leer)
    # y Exportar no preguntaba nada: el Excel salía sin las hojas 51 a 100.
    from facturas_excel.ventana_aplifisa import DialogoOrden
    ventana.procesar_rutas([_pdf(tmp_path / "taco.pdf", 100)])
    for _ in range(2):
        lectura = WorkerFalso.creados[-1]
        lectura.entregar(_bloque_de(lectura))
    partes = []
    for _ in range(2):
        lectura = WorkerFalso.creados[-1]
        partes.append(lectura.rutas[0])
        _fallar(lectura, "la API key se quedó sin crédito")

    assert len(ventana.filas) == 50 and not ventana._lectura_en_curso()
    aviso = ventana.banda.lbl.text()
    assert "taco_parte_04_de_04" in aviso
    assert "No se han podido leer 2 bloque(s) de taco.pdf (50 hoja(s))" in aviso
    assert all(map(os.path.isfile, partes))
    ventana._guardar_sesion_automatica()
    assert _en_disco() == (2, partes)            # y van con la sesión
    preguntas = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(
        lambda *a, **k: preguntas.append(a[2]) or QMessageBox.No))
    monkeypatch.setattr(DialogoOrden, "exec", lambda self: 0)
    ventana._exportar_todo()
    assert len(preguntas) == 1 and "Faltan 2 bloque(s)" in preguntas[0]

    # Resuelto (hay crédito otra vez), se vuelven a leer desde el aviso.
    assert ventana.banda.btn_deshacer.text() == "Volver a leer"
    ventana.banda.btn_deshacer.click()
    for parte in partes:
        lectura = WorkerFalso.creados[-1]
        assert lectura.rutas == [parte]
        lectura.entregar(_bloque_de(lectura))
    assert len(ventana.filas) == 100 and not ventana._cola_guardada
    assert not _partes_en_disco()
