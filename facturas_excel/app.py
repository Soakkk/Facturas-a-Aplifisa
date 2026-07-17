"""Ventana principal de Facturas a Aplifisa.

Flujo: Cargar facturas (PDF/imagenes) -> Gemini extrae y clasifica en segundo
plano -> autodetecta el cliente -> tabla de revision con miniatura y semaforo
(editable, se puede cambiar gasto/venta) -> Exportar gastos.xlsx / ventas.xlsx.
"""

from __future__ import annotations

import argparse
import os
import sys

from datetime import date

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QProgressDialog, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from facturas_excel import __version__, pendientes, updater
from facturas_excel.claves import guardar_api_key, leer_api_key
from facturas_excel.dialogo_pendientes import DialogoPendientes
from facturas_excel.clientes import (
    en_recargo_equivalencia, guardar_recargo_equivalencia,
)
from facturas_excel.config_columnas import leer_config
from facturas_excel.estilo import aplicar_tema
from facturas_excel.exportar import exportar_excel
from facturas_excel.extraccion import Extractor, SinCredito
from facturas_excel.modelo import Factura
from facturas_excel.pdf import cargar_imagenes
from facturas_excel.procesar import (
    a_total_factura, aprender_nifs, clave_proveedor, completar_desde_memoria,
    construir, detectar_cliente, marcar_sustituidas, normaliza_nif,
    propagar_nifs, recordar_nif,
)
from facturas_excel.resumen import describir, resumir
from facturas_excel.rutas import ruta_config
from facturas_excel.validacion import (
    ERROR, OK, REVISAR, detectar_periodo, encontrar_duplicados, fmt_periodo,
    periodo_de, validar, validar_nif,
)

ESCRITORIO = os.path.join(os.path.expanduser("~"), "Desktop")

COLOR_ESTADO = {OK: QColor("#2e7d32"), REVISAR: QColor("#f9a825"), ERROR: QColor("#c62828")}
ICONO_ESTADO = {OK: "OK", REVISAR: "!", ERROR: "X"}

HILOS = 6  # facturas procesadas en paralelo (con key de pago se puede subir)
EXT_FACTURA = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

COLS = ["Estado", "Tipo", "Cuenta", "GXX", "Fecha", "Nº Factura", "Nombre",
        "NIF", "Base", "% IVA", "Cuota", "Total"]
C_ESTADO, C_TIPO, C_CUENTA, C_GXX, C_FECHA, C_NUM, C_NOMBRE, C_NIF, \
C_BASE, C_PCT, C_CUOTA, C_TOTAL = range(len(COLS))


class _SinRueda:
    """Ignora la rueda del raton para que no cambie el valor sin querer.

    Bajando por el listado con la rueda, al pasar por encima de un desplegable
    este se tragaba el giro y cambiaba gasto<->venta en silencio (y el año del
    trimestre igual). El valor solo debe cambiarse haciendo clic; la rueda tiene
    que seguir moviendo la tabla, asi que el evento se deja pasar al padre.
    """

    def wheelEvent(self, evento):
        evento.ignore()


class ComboSinRueda(_SinRueda, QComboBox):
    pass


class SpinSinRueda(_SinRueda, QSpinBox):
    pass


def ruta_recurso(nombre):
    base = getattr(
        sys, "_MEIPASS",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "assets", nombre)


def parse_numero(texto):
    if texto is None:
        return None
    t = str(texto).strip()
    if not t:
        return None
    t = t.replace("€", "").replace(" ", "")
    if "," in t:
        # Formato español: 1.234,56
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1 or (
        t.count(".") == 1 and len(t.rsplit(".", 1)[1]) == 3
    ):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def rutas_factura_de_mime(mime):
    """Rutas locales compatibles contenidas en un arrastre."""
    if not mime.hasUrls():
        return []
    rutas = []
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        ruta = url.toLocalFile()
        if os.path.splitext(ruta)[1].lower() in EXT_FACTURA:
            rutas.append(ruta)
    return rutas


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.2f}".replace(".", ",")
    return str(v)


class Worker(QThread):
    progreso = Signal(int, int)
    terminado = Signal(object, str, str)   # lista[(png, FacturaProcesada)], nombre, nif
    fallo = Signal(str)

    def __init__(self, rutas, api_key):
        super().__init__()
        self.rutas = rutas
        self.api_key = api_key

    def run(self):
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            imagenes = cargar_imagenes(self.rutas, dpi=150)
            if not imagenes:
                raise ValueError("No se encontraron páginas o imágenes compatibles.")
            extractor = Extractor(self.api_key)
            total = len(imagenes)
            registros = [None] * total

            def tarea(idx):
                origen, pagina, img = imagenes[idx]
                try:
                    datos = extractor.extraer(img, origen, pagina).crudo
                except SinCredito:
                    raise  # detiene todo el lote con aviso
                except Exception as e:  # una factura ilegible no tumba el lote
                    datos = {"emisor_nombre": "(NO SE PUDO LEER)", "lineas_iva": [{}],
                             "_error": str(e)[:120]}
                return idx, (img, origen, pagina, datos)

            hechas = 0
            with ThreadPoolExecutor(max_workers=HILOS) as ex:
                futuros = [ex.submit(tarea, i) for i in range(total)]
                for fut in as_completed(futuros):
                    idx, reg = fut.result()
                    registros[idx] = reg
                    hechas += 1
                    self.progreso.emit(hechas, total)

            nombre, nif = detectar_cliente([d for *_, d in registros])
            procesadas = [(img, construir(datos, nif, nombre, origen, pag))
                          for img, origen, pag, datos in registros]
            # Rellenar los NIF ilegibles con los de otras facturas del mismo
            # proveedor (necesita el lote entero, por eso va aqui al final).
            solo_pr = [pr for _, pr in procesadas]
            propagar_nifs(solo_pr)              # 1º la prueba del propio lote
            completar_desde_memoria(solo_pr)    # 2º lo sabido de otras veces
            aprender_nifs(solo_pr)              # 3º memorizar lo leido bien
            # Post-facturaciones que rehacen un albaran anterior del lote.
            marcar_sustituidas(solo_pr)
            self.terminado.emit(procesadas, nombre, nif)
        except Exception as e:  # noqa
            self.fallo.emit(str(e))


class HiloActualizacion(QThread):
    resultado = Signal(object)   # Actualizacion o None
    error = Signal(str)

    def run(self):
        try:
            self.resultado.emit(updater.comprobar())
        except Exception as e:  # sin red, API caida, etc.
            self.error.emit(str(e))


class HiloDescargaActualizacion(QThread):
    progreso = Signal(int)
    terminado = Signal(str)
    error = Signal(str)

    def __init__(self, actualizacion):
        super().__init__()
        self.actualizacion = actualizacion

    def run(self):
        try:
            ruta = updater.descargar(
                self.actualizacion, progreso=self.progreso.emit)
            self.terminado.emit(ruta)
        except Exception as e:
            self.error.emit(str(e))


class VentanaPrincipal(QMainWindow):
    def __init__(self, comprobar_updates: bool = True):
        super().__init__()
        self.setWindowTitle(f"Facturas a Aplifisa — v{__version__}")
        self.setWindowIcon(QIcon(ruta_recurso("app.ico")))
        self.resize(1420, 820)
        self.setMinimumSize(1080, 680)
        self.setAcceptDrops(True)
        self.filas = []  # por fila: dict(png, factura, aviso)
        self._duplicados = set()
        self._rutas_actuales = []
        self._hilo_update = None
        self._hilo_descarga_update = None
        self._comprobar_updates = comprobar_updates
        self._crear_menu()

        self._crear_interfaz()
        if self._comprobar_updates:
            QTimer.singleShot(
                1500, lambda: self._comprobar_actualizaciones(silencioso=True))
            # Despues de la actualizacion: si hay version nueva, primero eso.
            QTimer.singleShot(2600, lambda: self._mostrar_pendientes(al_arrancar=True))

    def _crear_interfaz(self):
        central = QWidget()
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        cabecera = QFrame()
        cabecera.setObjectName("cabecera")
        cabecera.setFixedHeight(92)
        lc = QHBoxLayout(cabecera)
        lc.setContentsMargins(24, 14, 24, 14)
        logo = QLabel()
        logo.setPixmap(QPixmap(ruta_recurso("app.png")).scaled(
            52, 52, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        logo.setFixedSize(56, 56)
        lc.addWidget(logo)
        marca = QVBoxLayout()
        titulo = QLabel("Facturas a Aplifisa")
        titulo.setObjectName("marca")
        subtitulo = QLabel("Preparar, revisar y exportar facturas para captura masiva")
        subtitulo.setObjectName("marcaSubtitulo")
        marca.addWidget(titulo)
        marca.addWidget(subtitulo)
        lc.addLayout(marca)
        lc.addStretch()
        for texto, activo in (("1  Cargar", True), ("2  Revisar", False),
                              ("3  Exportar", False)):
            paso = QLabel(texto)
            paso.setObjectName("pasoActivo" if activo else "pasoInactivo")
            lc.addWidget(paso)
        raiz.addWidget(cabecera)

        cuerpo = QVBoxLayout()
        cuerpo.setContentsMargins(18, 16, 18, 12)
        cuerpo.setSpacing(12)

        acciones = QFrame()
        acciones.setObjectName("tarjeta")
        la = QHBoxLayout(acciones)
        la.setContentsMargins(16, 12, 16, 12)
        self.btn_cargar = QPushButton("Abrir PDF o imágenes")
        self.btn_cargar.setObjectName("primario")
        self.btn_cargar.setMinimumHeight(40)
        self.btn_cargar.clicked.connect(self._cargar)
        self.btn_key = QPushButton("Configurar Gemini")
        self.btn_key.clicked.connect(self._configurar_key)
        la.addWidget(self.btn_cargar)
        la.addWidget(self.btn_key)
        la.addSpacing(12)
        bloque_cliente = QVBoxLayout()
        etiqueta = QLabel("LOTE ACTUAL")
        etiqueta.setObjectName("textoSuave")
        self.lbl_cliente = QLabel("Cliente pendiente de detectar")
        self.lbl_cliente.setObjectName("cliente")
        bloque_cliente.addWidget(etiqueta)
        bloque_cliente.addWidget(self.lbl_cliente)
        self.chk_recargo = QCheckBox("En recargo de equivalencia (gastos por el total)")
        self.chk_recargo.setToolTip(
            "El cliente no deduce IVA: cada gasto se registra por el total de la\n"
            "factura (base + IVA + recargo), sin desglose. Se recuerda por NIF.")
        self.chk_recargo.setEnabled(False)
        self.chk_recargo.toggled.connect(self._on_recargo)
        bloque_cliente.addWidget(self.chk_recargo)
        la.addLayout(bloque_cliente, 1)

        bloque_periodo = QVBoxLayout()
        etiqueta_per = QLabel("TRIMESTRE QUE SE TRABAJA")
        etiqueta_per.setObjectName("textoSuave")
        fila_per = QHBoxLayout()
        fila_per.setSpacing(4)
        self.combo_trim = ComboSinRueda()
        self.combo_trim.addItems(["1T", "2T", "3T", "4T"])
        self.combo_trim.setFixedWidth(60)
        self.spin_anio = SpinSinRueda()
        self.spin_anio.setRange(2000, 2100)
        self.spin_anio.setValue(date.today().year)
        self.spin_anio.setFixedWidth(72)
        for w in (self.combo_trim, self.spin_anio):
            fila_per.addWidget(w)
        self.combo_trim.currentIndexChanged.connect(self._revalidar_todo)
        self.spin_anio.valueChanged.connect(self._revalidar_todo)
        bloque_periodo.addWidget(etiqueta_per)
        bloque_periodo.addLayout(fila_per)
        la.addLayout(bloque_periodo)
        self.btn_gastos = QPushButton("Exportar gastos")
        self.btn_gastos.setObjectName("exito")
        self.btn_gastos.setEnabled(False)
        self.btn_gastos.clicked.connect(lambda: self._exportar("gasto"))
        self.btn_ventas = QPushButton("Exportar ventas")
        self.btn_ventas.setEnabled(False)
        self.btn_ventas.clicked.connect(lambda: self._exportar("venta"))
        la.addWidget(self.btn_gastos)
        la.addWidget(self.btn_ventas)
        cuerpo.addWidget(acciones)

        self.progreso = QProgressBar()
        self.progreso.setVisible(False)
        cuerpo.addWidget(self.progreso)

        # Alerta de duplicados: tiene que verse sin tener que pasar el raton
        # por encima de una celda (un duplicado importado se paga dos veces).
        self.alerta = QFrame()
        self.alerta.setObjectName("alerta")
        self.alerta.setVisible(False)
        lal = QVBoxLayout(self.alerta)
        lal.setContentsMargins(14, 10, 14, 10)
        lal.setSpacing(2)
        self.lbl_alerta_titulo = QLabel()
        self.lbl_alerta_titulo.setObjectName("alertaTitulo")
        self.lbl_alerta_texto = QLabel()
        self.lbl_alerta_texto.setObjectName("alertaTexto")
        self.lbl_alerta_texto.setWordWrap(True)
        lal.addWidget(self.lbl_alerta_titulo)
        lal.addWidget(self.lbl_alerta_texto)
        cuerpo.addWidget(self.alerta)

        split = QSplitter(Qt.Horizontal)
        tabla_card = QFrame()
        tabla_card.setObjectName("tarjeta")
        lt = QVBoxLayout(tabla_card)
        lt.setContentsMargins(12, 12, 12, 12)
        titulo_tabla = QLabel("Datos extraídos")
        titulo_tabla.setObjectName("tituloSeccion")
        ayuda_tabla = QLabel("Revise las celdas en ámbar o rojo antes de exportar")
        ayuda_tabla.setObjectName("textoSuave")
        lt.addWidget(titulo_tabla)
        lt.addWidget(ayuda_tabla)
        self.tabla = QTableWidget(0, len(COLS))
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setHorizontalHeaderLabels(COLS)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.itemChanged.connect(self._on_celda)
        self.tabla.itemSelectionChanged.connect(self._mostrar_miniatura)
        lt.addWidget(self.tabla, 1)
        split.addWidget(tabla_card)

        visor_card = QFrame()
        visor_card.setObjectName("tarjeta")
        lv = QVBoxLayout(visor_card)
        lv.setContentsMargins(12, 12, 12, 12)
        titulo_visor = QLabel("Documento original")
        titulo_visor.setObjectName("tituloSeccion")
        self.lbl_origen = QLabel("Arrastre aquí un PDF o imágenes para comenzar")
        self.lbl_origen.setObjectName("textoSuave")
        self.lbl_origen.setWordWrap(True)
        self.lbl_img = QLabel("Suelte aquí las facturas\no use «Abrir PDF o imágenes»")
        self.lbl_img.setObjectName("visor")
        self.lbl_img.setAlignment(Qt.AlignCenter)
        self.lbl_img.setMinimumWidth(330)
        self.lbl_img.setMinimumHeight(430)
        lv.addWidget(titulo_visor)
        lv.addWidget(self.lbl_origen)
        lv.addWidget(self.lbl_img, 1)
        split.addWidget(visor_card)
        split.setSizes([980, 380])
        cuerpo.addWidget(split, 1)

        resumen_card = QFrame()
        resumen_card.setObjectName("tarjeta")
        lr = QVBoxLayout(resumen_card)
        lr.setContentsMargins(12, 10, 12, 10)
        lr.setSpacing(2)
        self.lbl_resumen_titulo = QLabel("Resumen del trimestre")
        self.lbl_resumen_titulo.setObjectName("tituloSeccion")
        self.lbl_resumen_gastos = QLabel("Gastos: —")
        self.lbl_resumen_ventas = QLabel("Ventas: —")
        self.lbl_resumen_fuera = QLabel("")
        self.lbl_resumen_fuera.setObjectName("textoSuave")
        for w in (self.lbl_resumen_titulo, self.lbl_resumen_gastos,
                  self.lbl_resumen_ventas, self.lbl_resumen_fuera):
            lr.addWidget(w)
        cuerpo.addWidget(resumen_card)

        self.lbl_estado = QLabel("Cargue un lote de facturas para empezar.")
        self.lbl_estado.setObjectName("textoSuave")
        cuerpo.addWidget(self.lbl_estado)
        cont = QWidget()
        cont.setLayout(cuerpo)
        raiz.addWidget(cont, 1)
        self.setCentralWidget(central)

    def esperar_hilos(self):
        """Espera a que terminen los hilos vivos (evita abortar al salir)."""
        for hilo in (
            getattr(self, "_hilo_update", None),
            getattr(self, "_hilo_descarga_update", None),
            getattr(self, "worker", None),
        ):
            if hilo and hilo.isRunning():
                hilo.wait(5000)

    # ---------- menu / actualizaciones ----------
    def _crear_menu(self):
        menu = self.menuBar().addMenu("Ayuda")
        menu.addAction("Buscar actualizaciones",
                       lambda: self._comprobar_actualizaciones(silencioso=False))
        menu.addAction("Para mejorar el programa…",
                       lambda: self._mostrar_pendientes(al_arrancar=False))
        menu.addAction("Acerca de", self._acerca_de)

    def _mostrar_pendientes(self, al_arrancar: bool):
        """Lo que hace falta saber para seguir afinando el programa, y un hueco
        para contestar. Al arrancar solo salta una vez por version."""
        if al_arrancar and (pendientes.ya_visto(__version__)
                            or not pendientes.leer_pendientes()):
            return
        DialogoPendientes(__version__, self, al_arrancar=al_arrancar).exec()

    def _acerca_de(self):
        QMessageBox.about(
            self, "Acerca de",
            f"<b>Facturas a Aplifisa</b> v{__version__}<br><br>"
            "Lee facturas escaneadas con IA (Gemini), detecta al cliente, "
            "clasifica gastos y ventas y genera el Excel que importa Aplifisa.<br><br>"
            "Actualizaciones: github.com/Soakkk/Facturas-a-Aplifisa/releases")

    def _comprobar_actualizaciones(self, silencioso: bool):
        if self._hilo_update and self._hilo_update.isRunning():
            return
        self._update_silencioso = silencioso
        self._hilo_update = HiloActualizacion()
        self._hilo_update.resultado.connect(self._on_update)
        self._hilo_update.error.connect(self._on_update_error)
        self._hilo_update.start()

    def _on_update(self, act):
        if act is None:
            if not getattr(self, "_update_silencioso", True):
                QMessageBox.information(self, "Actualizaciones",
                                        f"Ya tienes la última versión (v{__version__}).")
            return
        r = QMessageBox.question(
            self, "Actualización disponible",
            f"Hay una versión nueva: <b>v{act.version}</b> (tienes v{__version__}).<br><br>"
            "¿Descargar e instalar ahora? El programa se cerrará para actualizarse.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if r == QMessageBox.Yes:
            self._descargar_actualizacion(act)

    def _descargar_actualizacion(self, act):
        dialogo = QProgressDialog(
            "Descargando actualización…", None, 0, 100, self)
        dialogo.setWindowTitle("Actualizando")
        dialogo.setMinimumDuration(0)
        dialogo.setAutoClose(False)
        dialogo.setAutoReset(False)
        dialogo.setValue(0)
        self._dialogo_update = dialogo

        hilo = HiloDescargaActualizacion(act)
        self._hilo_descarga_update = hilo
        hilo.progreso.connect(dialogo.setValue)

        def terminado(ruta):
            dialogo.close()
            try:
                updater.lanzar_instalador(ruta)
            except Exception as e:
                QMessageBox.critical(
                    self, "Actualización", f"No se pudo abrir el instalador:\n{e}")
                return
            QApplication.quit()

        def error(mensaje):
            dialogo.close()
            QMessageBox.critical(
                self, "Actualización",
                f"No se pudo descargar la actualización:\n{mensaje}")

        hilo.terminado.connect(terminado)
        hilo.error.connect(error)
        hilo.start()
        dialogo.show()

    def _on_update_error(self, msg):
        if not getattr(self, "_update_silencioso", True):
            QMessageBox.warning(self, "Actualizaciones",
                                f"No se pudo comprobar:\n{msg}")

    def closeEvent(self, ev):
        # No destruir QThreads vivos (abortaria el proceso)
        self.esperar_hilos()
        super().closeEvent(ev)

    def dragEnterEvent(self, event):
        if rutas_factura_de_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        rutas = rutas_factura_de_mime(event.mimeData())
        if rutas:
            event.acceptProposedAction()
            self.procesar_rutas(rutas)

    # ---------- API key ----------
    def _configurar_key(self):
        actual = leer_api_key() or ""
        pista = ("•••" + actual[-4:]) if actual else "(no configurada)"
        texto, ok = QInputDialog.getText(
            self, "API key de Gemini",
            f"Pega tu API key de Google AI Studio.\nActual: {pista}")
        if ok and texto.strip():
            guardar_api_key(texto.strip())
            QMessageBox.information(self, "Guardada",
                                    "API key guardada de forma segura.")

    # ---------- carga ----------
    def _cargar(self):
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Elige facturas (PDF o imágenes)", ESCRITORIO,
            "Facturas (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp)")
        if rutas:
            self.procesar_rutas(rutas)

    def procesar_rutas(self, rutas):
        """Procesa rutas recibidas por diálogo, arrastre o Escáner Fotos."""
        rutas = [os.path.abspath(r) for r in rutas
                 if os.path.isfile(r) and os.path.splitext(r)[1].lower() in EXT_FACTURA]
        if not rutas:
            QMessageBox.warning(self, "Archivos no compatibles",
                                "No se encontraron PDFs o imágenes válidas.")
            return
        api_key = leer_api_key()
        if not api_key:
            QMessageBox.warning(self, "Falta la API key",
                                "Configura primero tu API key de Gemini.")
            return
        if getattr(self, "worker", None) and self.worker.isRunning():
            QMessageBox.information(self, "Procesando",
                                    "Espera a que termine el lote actual.")
            return
        self._rutas_actuales = rutas
        self.lbl_origen.setText(
            f"{len(rutas)} archivo{'s' if len(rutas) != 1 else ''}: "
            + ", ".join(os.path.basename(r) for r in rutas[:3])
            + ("…" if len(rutas) > 3 else ""))
        self.btn_cargar.setEnabled(False)
        self.btn_gastos.setEnabled(False)
        self.btn_ventas.setEnabled(False)
        self.progreso.setVisible(True)
        self.progreso.setValue(0)
        self.lbl_estado.setText("Leyendo facturas con Gemini…")
        self.worker = Worker(rutas, api_key)
        self.worker.progreso.connect(self._on_progreso)
        self.worker.terminado.connect(self._on_terminado)
        self.worker.fallo.connect(self._on_fallo)
        self.worker.start()

    def _on_progreso(self, actual, total):
        self.progreso.setMaximum(total)
        self.progreso.setValue(actual)
        self.lbl_estado.setText(f"Leyendo facturas con Gemini… {actual}/{total}")

    def _on_fallo(self, msg):
        self.progreso.setVisible(False)
        self.btn_cargar.setEnabled(True)
        self.lbl_estado.setText("No se pudo procesar el lote.")
        QMessageBox.critical(self, "Error al procesar", msg)

    def _on_terminado(self, procesadas, nombre, nif):
        self.progreso.setVisible(False)
        self.btn_cargar.setEnabled(True)
        self.lbl_cliente.setText(
            f"{nombre or 'Cliente no identificado'}"
            + (f"  ·  {nif}" if nif else ""))
        # El lote crudo se guarda tal cual: al marcar/desmarcar el recargo la
        # tabla se rehace desde aqui, sin volver a llamar a Gemini.
        self._procesadas = procesadas
        self._cliente_nif, self._cliente_nombre = nif, nombre
        self.chk_recargo.blockSignals(True)
        self.chk_recargo.setEnabled(bool(nif))
        self.chk_recargo.setChecked(en_recargo_equivalencia(nif))
        self.chk_recargo.blockSignals(False)
        self._rellenar_tabla()
        self._autoseleccionar_periodo()
        self._revalidar_todo()
        hay_datos = self.tabla.rowCount() > 0
        self.btn_gastos.setEnabled(hay_datos)
        self.btn_ventas.setEnabled(hay_datos)
        if hay_datos:
            self.tabla.selectRow(0)

    def _rellenar_tabla(self):
        recargo = self.chk_recargo.isChecked()
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(0)
        self.filas = []
        for png, pr in getattr(self, "_procesadas", []):
            vista = a_total_factura(pr) if recargo else pr
            for f in vista.facturas:
                self._anadir_fila(png, f, vista.tipo, vista.cuenta, vista.gxx,
                                  vista.aviso)
        self.tabla.blockSignals(False)

    def _on_recargo(self, activo):
        """Marcar el recargo rehace la tabla: cambia como se registra cada gasto."""
        guardar_recargo_equivalencia(getattr(self, "_cliente_nif", ""), activo,
                                     getattr(self, "_cliente_nombre", ""))
        self._rellenar_tabla()
        self._revalidar_todo()

    def _anadir_fila(self, png, f: Factura, tipo, cuenta, gxx, aviso):
        senales_bloqueadas = self.tabla.signalsBlocked()
        self.tabla.blockSignals(True)
        r = self.tabla.rowCount()
        self.tabla.insertRow(r)
        self.filas.append({"png": png, "factura": f, "aviso": aviso})

        est = QTableWidgetItem("")
        est.setFlags(Qt.ItemIsEnabled)
        est.setTextAlignment(Qt.AlignCenter)
        self.tabla.setItem(r, C_ESTADO, est)

        combo = ComboSinRueda()
        combo.addItems(["gasto", "venta"])
        combo.setCurrentText(tipo)
        combo.currentTextChanged.connect(lambda _t, row=r: self._revalidar_fila(row))
        self.tabla.setCellWidget(r, C_TIPO, combo)

        valores = {
            C_CUENTA: cuenta, C_GXX: gxx or "", C_FECHA: f.fecha, C_NUM: f.num_factura,
            C_NOMBRE: f.nombre, C_NIF: f.nif, C_BASE: fmt(f.base_iva),
            C_PCT: fmt(f.pct_iva), C_CUOTA: fmt(f.cuota_iva), C_TOTAL: fmt(f.total_impreso),
        }
        for col, val in valores.items():
            item = QTableWidgetItem("" if val is None else str(val))
            if col == C_GXX:
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setToolTip("Subclave orientativa; Aplifisa la recuerda por proveedor.")
            self.tabla.setItem(r, col, item)
        self.tabla.setRowHeight(r, 34)
        self.tabla.blockSignals(senales_bloqueadas)

    # ---------- edicion / validacion ----------
    def _on_celda(self, item):
        aviso = self._nif_escrito_a_mano(item.row()) \
            if item.column() == C_NIF else ""
        self._revalidar_todo()
        if aviso:
            self.lbl_estado.setText(aviso)  # despues: _resumen pisa la barra

    def _nif_escrito_a_mano(self, r) -> str:
        """Un NIF escrito por una persona vale mas que cualquier lectura: se
        guarda para siempre y se pone ya en el resto de facturas de ese mismo
        proveedor que esten sin el, aqui y en los proximos lotes."""
        if r >= len(self.filas):
            return ""
        f = self._leer_fila(r)
        nif = normaliza_nif(f.nif)
        if not f.nombre or not validar_nif(nif):
            return ""                  # a medio escribir o ilegible: no guardar
        if not recordar_nif(f.nombre, nif, manual=True):
            return ""
        clave = clave_proveedor(f.nombre)
        aplicadas = []
        self.tabla.blockSignals(True)
        for otra in range(self.tabla.rowCount()):
            if otra == r:
                continue
            g = self._leer_fila(otra)
            if clave_proveedor(g.nombre) != clave or validar_nif(normaliza_nif(g.nif)):
                continue
            g.nif = nif
            self.tabla.item(otra, C_NIF).setText(nif)
            self.filas[otra]["aviso"] = (
                f"{self.filas[otra]['aviso']} NIF puesto a mano ({nif}) desde "
                f"otra factura de {f.nombre}.").strip()
            aplicadas.append(otra + 1)
        self.tabla.blockSignals(False)
        aviso = f"NIF {nif} guardado para {f.nombre}: ya no habrá que escribirlo más."
        if aplicadas:
            aviso += ("  Puesto también en la línea "
                      + ", ".join(str(n) for n in aplicadas) + ".")
        return aviso

    def _leer_fila(self, r):
        """Actualiza la Factura de la fila con lo que hay en las celdas."""
        d = self.filas[r]
        f = d["factura"]
        f.concepto = self.tabla.item(r, C_CUENTA).text() or None
        f.fecha = self.tabla.item(r, C_FECHA).text() or None
        f.num_factura = self.tabla.item(r, C_NUM).text() or None
        f.nombre = self.tabla.item(r, C_NOMBRE).text() or None
        f.nif = self.tabla.item(r, C_NIF).text() or None
        f.base_iva = parse_numero(self.tabla.item(r, C_BASE).text())
        f.pct_iva = parse_numero(self.tabla.item(r, C_PCT).text())
        f.cuota_iva = parse_numero(self.tabla.item(r, C_CUOTA).text())
        f.total_impreso = parse_numero(self.tabla.item(r, C_TOTAL).text())
        return f

    def _tipo_fila(self, r):
        w = self.tabla.cellWidget(r, C_TIPO)
        return w.currentText() if w else "gasto"

    def _periodo(self):
        """Trimestre que se esta trabajando, segun los selectores."""
        return (self.spin_anio.value(), self.combo_trim.currentIndex() + 1)

    def _autoseleccionar_periodo(self):
        """Propone el trimestre mayoritario del lote (el que se esta trabajando);
        asi las descolgadas saltan solas. Se puede cambiar a mano."""
        periodo = detectar_periodo([d["factura"] for d in self.filas])
        if not periodo:
            return
        anio, trim = periodo
        for w in (self.combo_trim, self.spin_anio):
            w.blockSignals(True)
        self.spin_anio.setValue(anio)
        self.combo_trim.setCurrentIndex(trim - 1)
        for w in (self.combo_trim, self.spin_anio):
            w.blockSignals(False)

    def _revalidar_fila(self, r):
        if r >= len(self.filas):
            return
        f = self._leer_fila(r)
        res = validar(f, self._periodo())
        estado = res.estado
        msgs = list(res.mensajes)
        if self.filas[r]["aviso"]:
            msgs.append(self.filas[r]["aviso"])
            if estado == OK:
                estado = REVISAR
        if r in self._duplicados:
            # Rojo, no ambar: importar dos veces la misma factura la paga dos
            # veces. Que obligue a decidir, no que se quede en "ya lo miraré".
            msgs.append(f"FACTURA DUPLICADA: es la misma que la línea "
                        f"{self._duplicados[r] + 1} del lote (mismo nº, NIF, "
                        f"base y tipo de IVA). Bórrala o quedará registrada dos veces.")
            estado = ERROR
        celda = self.tabla.item(r, C_ESTADO)
        self.tabla.blockSignals(True)
        celda.setText(ICONO_ESTADO[estado])
        celda.setBackground(COLOR_ESTADO[estado])
        celda.setForeground(QColor("white"))
        celda.setToolTip("\n".join(msgs) if msgs else "Todo correcto")
        self.tabla.blockSignals(False)
        self._resumen()

    def _revalidar_todo(self):
        self._duplicados = encontrar_duplicados(
            [self._leer_fila(r) for r in range(self.tabla.rowCount())])
        for r in range(self.tabla.rowCount()):
            self._revalidar_fila(r)
        self._pintar_alerta()

    def _pintar_alerta(self):
        """Banner rojo arriba con las duplicadas y las sustituidas: las dos
        acaban registrando dos veces el mismo gasto si se cuelan."""
        avisos = []
        for r, original in sorted(self._duplicados.items()):
            f = self.filas[r]["factura"]
            avisos.append(f"Línea {r + 1}: factura {f.num_factura or '?'} de "
                          f"{f.nombre or '?'} — repetida de la línea {original + 1}.")
        sustituidas = [r for r in range(len(self.filas))
                       if "SUSTITUIDA" in (self.filas[r]["aviso"] or "")]
        for r in sustituidas:
            f = self.filas[r]["factura"]
            avisos.append(f"Línea {r + 1}: factura {f.num_factura or '?'} de "
                          f"{f.nombre or '?'} — sustituida por otra del lote.")
        if not avisos:
            self.alerta.setVisible(False)
            return
        n = len(avisos)
        self.lbl_alerta_titulo.setText(
            f"⚠  ATENCIÓN: {n} factura{'s' if n > 1 else ''} "
            f"{'repetidas' if n > 1 else 'repetida'} en el lote")
        self.lbl_alerta_texto.setText(
            "\n".join(avisos[:6])
            + (f"\n… y {n - 6} más." if n > 6 else "")
            + "\n\nSi se importan, el gasto se registra dos veces. Bórralas de "
              "la tabla antes de exportar.")
        self.alerta.setVisible(True)

    def _resumen(self):
        periodo = self._periodo()
        estados = []
        for r in range(self.tabla.rowCount()):
            f = self.filas[r]["factura"]
            e = validar(f, periodo).estado
            if self.filas[r]["aviso"] and e == OK:
                e = REVISAR
            if r in self._duplicados:
                e = ERROR
            estados.append(e)
        n_g = sum(1 for r in range(self.tabla.rowCount()) if self._tipo_fila(r) == "gasto")
        self.lbl_estado.setText(
            f"{len(estados)} líneas  ·  Gastos: {n_g}  ·  Ventas: {len(estados) - n_g}  ·  "
            f"🟢 {estados.count(OK)}  🟡 {estados.count(REVISAR)}  🔴 {estados.count(ERROR)}")
        self._pintar_resumen(periodo)

    def _pintar_resumen(self, periodo):
        """Suma solo lo del trimestre que se trabaja: es lo que se declara.
        Lo de fuera se cuenta aparte para que se vea que esta ahi."""
        dentro = {"gasto": [], "venta": []}
        fuera = 0
        for r in range(self.tabla.rowCount()):
            f = self.filas[r]["factura"]
            if periodo_de(f.fecha) == periodo:
                dentro[self._tipo_fila(r)].append(f)
            else:
                fuera += 1
        # En recargo el gasto no tiene desglose de IVA: solo el total factura.
        recargo = self.chk_recargo.isChecked()
        self.lbl_resumen_titulo.setText(
            f"Resumen del {fmt_periodo(periodo)}"
            + ("  ·  cliente en recargo de equivalencia" if recargo else ""))
        self.lbl_resumen_gastos.setText(
            f"Gastos:  {describir(resumir(dentro['gasto']), solo_total=recargo)}")
        self.lbl_resumen_ventas.setText(f"Ventas:  {describir(resumir(dentro['venta']))}")
        if fuera:
            self.lbl_resumen_fuera.setText(
                f"⚠ {fuera} línea(s) fuera del {fmt_periodo(periodo)} o sin fecha "
                f"válida: NO suman en este resumen (mírelas en la tabla, en ámbar).")
        else:
            self.lbl_resumen_fuera.setText("")

    # ---------- miniatura ----------
    def _mostrar_miniatura(self):
        r = self.tabla.currentRow()
        if r < 0 or r >= len(self.filas):
            return
        png = self.filas[r]["png"]
        factura = self.filas[r]["factura"]
        origen = os.path.basename(factura.origen_imagen or "")
        self.lbl_origen.setText(origen or "Documento cargado")
        pix = QPixmap()
        pix.loadFromData(png)
        if not pix.isNull():
            self.lbl_img.setPixmap(pix.scaled(
                self.lbl_img.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.tabla.currentRow() >= 0:
            self._mostrar_miniatura()

    # ---------- exportar ----------
    def _exportar(self, tipo):
        facturas = [self.filas[r]["factura"] for r in range(self.tabla.rowCount())
                    if self._tipo_fila(r) == tipo]
        if not facturas:
            QMessageBox.warning(self, "Sin datos", f"No hay {tipo}s que exportar.")
            return
        periodo = self._periodo()
        dups = [r for r in self._duplicados if r < len(self.filas)
                and self._tipo_fila(r) == tipo]
        if dups:
            lineas = "\n".join(
                f"  · Línea {r + 1}: {self.filas[r]['factura'].num_factura or '?'} — "
                f"{self.filas[r]['factura'].nombre or '?'}" for r in sorted(dups)[:8])
            r = QMessageBox.question(
                self, "⚠ Hay facturas duplicadas",
                f"{len(dups)} línea(s) están REPETIDAS en el lote:\n\n{lineas}\n\n"
                "Si las exportas, el registro se hará DOS VECES.\n"
                "¿Exportar de todas formas?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                return
        errores = sum(1 for f in facturas if validar(f, periodo).estado == ERROR)
        if errores:
            r = QMessageBox.question(
                self, "Hay errores",
                f"{errores} línea(s) con errores (rojo). ¿Exportar de todas formas?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                return
        fuera = [f for f in facturas if periodo_de(f.fecha) != periodo]
        if fuera:
            detalle = "\n".join(
                f"  · {f.fecha or '(sin fecha)'} — {f.nombre or '?'}" for f in fuera[:8])
            if len(fuera) > 8:
                detalle += f"\n  · … y {len(fuera) - 8} más"
            r = QMessageBox.question(
                self, f"Hay facturas fuera del {fmt_periodo(periodo)}",
                f"{len(fuera)} línea(s) NO son del {fmt_periodo(periodo)} "
                f"(o no tienen fecha válida):\n\n{detalle}\n\n"
                "Se exportarán igualmente. ¿Continuar?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                return
        xml = "gastos.xml" if tipo == "gasto" else "ingresos.xml"
        cfg = leer_config(ruta_config(xml))
        nombre = "gastos.xlsx" if tipo == "gasto" else "ventas.xlsx"
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar Excel", os.path.join(ESCRITORIO, nombre), "Excel (*.xlsx)")
        if not ruta:
            return
        exportar_excel(facturas, cfg, ruta)
        QMessageBox.information(self, "Exportado", f"Generado:\n{ruta}")


def _argumentos(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--import", dest="importar", nargs="+")
    args, _ = parser.parse_known_args(argv[1:])
    return args


def main():
    args = _argumentos(sys.argv)
    app = QApplication([sys.argv[0]])
    app.setWindowIcon(QIcon(ruta_recurso("app.ico")))
    aplicar_tema(app)
    v = VentanaPrincipal()
    app.aboutToQuit.connect(v.esperar_hilos)
    v.show()
    if args.importar:
        QTimer.singleShot(200, lambda: v.procesar_rutas(args.importar))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
