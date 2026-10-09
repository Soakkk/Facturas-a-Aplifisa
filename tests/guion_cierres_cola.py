"""Escenarios de la cola con la ventana de verdad, en un proceso aparte.

Lo usa tests/test_cierres_cola.py: cada escenario corre en su propio proceso
porque lo que se prueba es que el programa NO se cierre de golpe («QThread:
Destroyed while thread is still running» aborta el proceso entero). La
prueba exige que el proceso acabe con código 0 y mira lo que deja escrito.

    python guion_cierres_cola.py ESCENARIO CARPETA

- La lectura es de verdad (hilos.Worker dibuja las hojas) y Gemini es falso:
  cada hoja es una factura inventada (NIF de prueba). Como el de verdad, una
  petición en vuelo no se corta y, cancelada la lectura, las hojas que no
  han empezado fallan sin pedirse.
- Los diálogos no se abren: se apuntan, y algunos «se quedan abiertos» un rato
  (un bucle de eventos, como una ventana modal) para que lleguen otras cosas.
- En CARPETA quedan `resultado.json` (si el proceso llega al final),
  `llamadas.txt` (cada petición a Gemini: si se pidió con la ventana ya
  cerrándose) y el perfil del programa (APPDATA, HOME) con su sesión.

Funciona también con versiones anteriores del programa (lo que la prueba
usa para comprobar que, sin los arreglos, estos escenarios fallan).
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time

ESCENARIO, CARPETA = sys.argv[1], os.path.abspath(sys.argv[2])
RAIZ = os.environ.get("RAIZ_PROGRAMA") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
LATENCIA = float(os.environ.get("LATENCIA", "0.3"))

os.makedirs(CARPETA, exist_ok=True)
for variable, sub in (("APPDATA", "appdata"), ("LOCALAPPDATA", "local"),
                      ("HOME", "casa"), ("USERPROFILE", "casa")):
    os.environ[variable] = os.path.join(CARPETA, sub)
    os.makedirs(os.environ[variable], exist_ok=True)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("GEMINI_API_KEY", "clave-de-prueba")
sys.path.insert(0, RAIZ)

import fitz  # noqa: E402
from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication(["cierres"])

from facturas_excel import extraccion, hilos, notas_version, ventana_lectura  # noqa: E402
from facturas_excel import __version__  # noqa: E402
from facturas_excel.app import VentanaPrincipal  # noqa: E402
from facturas_excel.extraccion import DatosFactura  # noqa: E402

notas_version.marcar_vistas(__version__)
ventana_lectura.leer_api_key = lambda: "clave-de-prueba"
ESTADO = {"cerrando": False, "vivos": 0, "max_vivos": 0, "lecturas": 0,
          "dialogos": []}
CERROJO = threading.Lock()
T0 = time.monotonic()


def girar(segundos, al_medio=None, en=0.3):
    """Un diálogo que se queda abierto `segundos` (su propio bucle de
    eventos, como una ventana modal); `al_medio` pasa a los `en` segundos."""
    lazo = QEventLoop()
    if al_medio is not None:
        QTimer.singleShot(int(en * 1000), al_medio)
    QTimer.singleShot(int(segundos * 1000), lazo.quit)
    lazo.exec()


# ------------------------------------------------------------ diálogos
def _apunta(nombre, respuesta):
    def dialogo(*a, **k):
        ESTADO["dialogos"].append(f"{nombre}: {a[1] if len(a) > 1 else ''}")
        return respuesta
    return staticmethod(dialogo)


QMessageBox.critical = _apunta("critical", QMessageBox.Ok)
QMessageBox.warning = _apunta("warning", QMessageBox.Ok)
QMessageBox.information = _apunta("information", QMessageBox.Ok)
QMessageBox.question = _apunta("question", QMessageBox.No)
QDialog.exec = lambda self, *a: ESTADO["dialogos"].append(type(self).__name__) or 0


# ------------------------------------------------------------ Gemini falso
def _numero(origen, pagina):
    """Factura única por hoja: el nombre del PDF y su página de verdad."""
    base = os.path.splitext(os.path.basename(origen))[0]
    parte = re.search(r"_parte_(\d+)_de_", base)
    if parte:
        pagina += (int(parte.group(1)) - 1) * 25
        base = base[:parte.start()]
    return f"{base.upper()}-{pagina:03d}"


class ExtractorFalso:
    def __init__(self, api_key=None, *a, **k):
        self.cancelado = threading.Event()

    def extraer(self, img, origen="", pagina=0):
        if self.cancelado.is_set():
            # Como extraccion.Extractor: lo que no ha empezado no se pide.
            raise RuntimeError("No leída: se cerró el programa mientras se leía.")
        with open(os.path.join(CARPETA, "llamadas.txt"), "a", encoding="utf-8") as fh:
            fh.write(f"{time.monotonic() - T0:.2f} {int(ESTADO['cerrando'])} "
                     f"{_numero(origen, pagina)}\n")
        time.sleep(LATENCIA)                # la petición en vuelo no se corta
        base = 100.0 + pagina
        datos = {
            "emisor_nombre": "PROVEEDOR PRUEBA SL", "emisor_nif": "B12345674",
            "receptor_nombre": "CLIENTE PRUEBA", "receptor_nif": "12345678Z",
            "num_factura": _numero(origen, pagina), "fecha": "15/03/2026",
            "estado_pagina_factura": "unica",
            "lineas_iva": [{"base": base, "tipo_iva": 21.0,
                            "cuota_iva": round(base * 0.21, 2)}],
            "total": round(base * 1.21, 2),
        }
        return DatosFactura(crudo=datos, origen=origen, pagina=pagina,
                            modelo="gemini-falso", consumos=[("gemini-falso", 1, 1)])


hilos.Extractor = ExtractorFalso
extraccion.Extractor = ExtractorFalso
hilos.costes.registrar = lambda *a, **k: 0.0

_run = hilos.Worker.run


def _run_contado(self):
    """Cuántas lecturas hay a la vez (nunca debería haber dos)."""
    with CERROJO:
        ESTADO["vivos"] += 1
        ESTADO["lecturas"] += 1
        ESTADO["max_vivos"] = max(ESTADO["max_vivos"], ESTADO["vivos"])
    try:
        return _run(self)
    finally:
        with CERROJO:
            ESTADO["vivos"] -= 1


hilos.Worker.run = _run_contado


# ------------------------------------------------------------ PDF de prueba
def taco(nombre, hojas):
    ruta = os.path.join(CARPETA, "casa", nombre + ".pdf")
    if not os.path.exists(ruta):
        documento = fitz.open()
        for n in range(1, hojas + 1):
            hoja = documento.new_page(width=300, height=420)
            hoja.insert_text((30, 60), f"FACTURA {nombre} {n}", fontsize=9)
        documento.save(ruta)
        documento.close()
    return ruta


def esperar(condicion, tope):
    fin = time.monotonic() + tope
    while time.monotonic() < fin and not condicion():
        app.processEvents(QEventLoop.AllEvents, 50)
        time.sleep(0.02)
    return condicion()


def cola_quieta(v):
    w = getattr(v, "worker", None)
    corriendo = bool(w is not None and w.isRunning())
    return (not v._cola and v._elemento_cola_actual is None and not corriendo
            and ESTADO["vivos"] == 0)


def foto(v):
    numeros = sorted({f.num_factura for b in v._bloques
                      for _, pr in b.get("procesadas", []) for f in pr.facturas})
    return {"filas": len(v.filas), "bloques": len(v._bloques),
            "facturas": numeros, "max_vivos": ESTADO["max_vivos"],
            "lecturas": ESTADO["lecturas"], "dialogos": ESTADO["dialogos"],
            "cola": len(v._cola), "tipos_declarados": [b.get("tipo_declarado")
                                                       for b in v._bloques]}


def guardar(datos):
    with open(os.path.join(CARPETA, "resultado.json"), "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=1, default=str)


# ------------------------------------------------------------ escenarios
def pregunta_y_escaneo(v):
    """Llega otro PDF (un escaneo) mientras está abierta una pregunta dentro
    de la puesta en el lote de un bloque, y quedan bloques en la cola."""
    escaneo = taco("escaneo", 5)
    original = VentanaPrincipal._resolver_conflictos_nif
    veces = []

    def pregunta(self):
        veces.append(1)
        if len(veces) == 1:
            girar(1.0, lambda: self.procesar_rutas([escaneo]))
        return original(self)
    VentanaPrincipal._resolver_conflictos_nif = pregunta
    v.procesar_rutas([taco("taco", 30)])
    esperar(lambda: veces and cola_quieta(v), 60)


def fallo_y_otro(v):
    """Un bloque falla y, con su aviso abierto, llega otro PDF."""
    roto = os.path.join(CARPETA, "casa", "roto.jpg")
    with open(roto, "wb") as fh:
        fh.write(b"esto no es una imagen")
    otro = taco("taco", 30)
    original = VentanaPrincipal._on_fallo

    def al_fallar(self, mensaje):
        QTimer.singleShot(300, lambda: self.procesar_rutas([otro]))
        return original(self, mensaje)
    VentanaPrincipal._on_fallo = al_fallar
    QMessageBox.critical = staticmethod(lambda *a, **k: girar(1.0) or QMessageBox.Ok)
    v.procesar_rutas([roto])
    esperar(lambda: len(v._bloques) >= 2 and cola_quieta(v), 60)


def _cerrar_a_mitad(v, salir, cuando):
    """Cierra (o sale, como el actualizador) a mitad de lectura y deja que el
    programa acabe como en app.main(): aboutToQuit → esperar_hilos."""
    app.aboutToQuit.connect(v.esperar_hilos)

    def cerrar():
        ESTADO["cerrando"] = True
        t0 = time.monotonic()
        salir()
        ESTADO["cerrar_s"] = round(time.monotonic() - t0, 2)
        guardar({**foto(v), "cerrar_s": ESTADO["cerrar_s"]})

    def mirar():
        if cuando():
            QTimer.singleShot(200, cerrar)
        else:
            QTimer.singleShot(20, mirar)
    QTimer.singleShot(20, mirar)
    v.procesar_rutas([taco("taco", 30)])
    app.exec()


def _llamadas():
    try:
        with open(os.path.join(CARPETA, "llamadas.txt"), encoding="utf-8") as fh:
            return len(fh.readlines())
    except OSError:
        return 0


def cerrar(v):
    _cerrar_a_mitad(v, v.close, lambda: _llamadas() >= 5)


def salir_al_actualizar(v):
    _cerrar_a_mitad(v, QApplication.quit, lambda: _llamadas() >= 5)


def cerrar_dibujando(v):
    """Cierra mientras se dibujan las hojas (antes de pedir nada)."""
    dibujar = fitz.Page.get_pixmap

    def despacio(self, *a, **k):
        time.sleep(0.15)
        return dibujar(self, *a, **k)
    fitz.Page.get_pixmap = despacio
    _cerrar_a_mitad(v, v.close, lambda: ESTADO["lecturas"] >= 1)


def vaciar(v):
    """«Vaciar todo» con el segundo bloque leyéndose."""
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    v.procesar_rutas([taco("taco", 60)])
    esperar(lambda: v._bloques and ESTADO["vivos"] == 1, 60)
    time.sleep(0.2)
    v._vaciar_todo()
    esperar(lambda: cola_quieta(v), 60)
    esperar(lambda: False, 1.0)


ESCENARIOS = {f.__name__: f for f in (pregunta_y_escaneo, fallo_y_otro, cerrar,
                                       salir_al_actualizar, cerrar_dibujando, vaciar)}

if __name__ == "__main__":
    hilos.hilos_lectura = lambda: 10
    ventana = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    ventana.show()
    ESCENARIOS[ESCENARIO](ventana)
    if not ESCENARIO.startswith(("cerrar", "salir")):
        guardar(foto(ventana))
    # Se sale como el programa: si queda una lectura viva, Python la suelta
    # y Qt aborta el proceso (código distinto de 0).
    sys.exit(0)
